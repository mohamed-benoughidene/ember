"""Migration 012 tests: metadata column, preservation, triggers, fresh, failure.

Every test builds a real v11 database by hand (scripts 001-011 applied, version
stamped 11) and then lets the runner apply 012, per the 011 test pattern.
"""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import open_database
from tests.fakes import FIXED_TIME, insert_item, insert_source

_MIGRATIONS_TO_11 = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
    "010_add_item_close_reason.sql",
    "011_add_links_reversed_at_and_enforcement_triggers.sql",
)

_ITEM_COLUMNS = (
    "id, type, statement, source_id, status, created_at, validated,"
    " rationale, source, close_reason, status_origin"
)

_CLOSED_ITEM_INSERT = (
    "INSERT INTO items (id, type, statement, source_id, status, created_at,"
    " validated, rationale, source, close_reason, status_origin)"
    " VALUES (9, 'Decision', 'closed item', 1, 'Closed', ?, NULL, NULL, NULL,"
    " NULL, 'derived')"
)


def _build_v11_db(db_path: str) -> None:
    """Build a real v11 database by hand and seed two items with real values."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (11)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_11:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn, "old note")
    insert_item(conn, source_id=source_id, item_id=1, statement="use SQLite")
    insert_item(
        conn,
        source_id=source_id,
        item_id=2,
        item_type="Question",
        statement="which db",
        created_at="2026-02-01T00:00:00+00:00",
        validated=False,
    )
    conn.commit()
    conn.close()


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def test_migration_012_adds_nullable_metadata_column(db_path) -> None:
    _build_v11_db(db_path)

    conn = open_database(db_path)
    info = {row["name"]: tuple(row) for row in conn.execute("PRAGMA table_info(items)")}
    conn.close()

    assert "metadata" in info
    _, name, column_type, notnull, default, pk = info["metadata"]
    assert name == "metadata"
    assert column_type == "TEXT"
    assert notnull == 0
    assert default is None
    assert pk == 0


def test_migration_012_preserves_all_rows_and_values(db_path) -> None:
    _build_v11_db(db_path)
    raw = sqlite3.connect(db_path)
    before = _rows(raw, f"SELECT {_ITEM_COLUMNS} FROM items ORDER BY id")
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    after = _rows(raw, f"SELECT {_ITEM_COLUMNS} FROM items ORDER BY id")
    assert after == before
    # The new column reads as NULL on every pre-existing row.
    star = _rows(raw, "SELECT * FROM items ORDER BY id")
    assert star == [row + (None,) for row in before]
    raw.close()


def test_migration_012_preserves_existing_schema(db_path) -> None:
    _build_v11_db(db_path)
    raw = sqlite3.connect(db_path)
    objects_before = {
        name: sql
        for name, sql in raw.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        ).fetchall()
    }
    tables = [
        name
        for (name,) in raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    columns_before = {
        table: _rows(raw, f"PRAGMA table_info({table})") for table in tables
    }
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    objects_after = {
        name: sql
        for name, sql in raw.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        ).fetchall()
    }
    columns_after = {
        table: _rows(raw, f"PRAGMA table_info({table})") for table in tables
    }
    raw.close()

    # No object was renamed, rebuilt or dropped. ADD COLUMN rewrites the stored
    # CREATE text of `items`, so its truth comes from the column diff below.
    for name, sql in objects_before.items():
        if name != "items":
            assert objects_after[name] == sql
    for table in tables:
        if table == "items":
            continue
        assert columns_after[table] == columns_before[table], table
    # items gains exactly one trailing nullable column.
    metadata_row = (11, "metadata", "TEXT", 0, None, 0)
    assert columns_after["items"] == columns_before["items"] + [metadata_row]


def test_migration_012_items_triggers_still_active(db_path) -> None:
    _build_v11_db(db_path)
    conn = open_database(db_path)

    # 011's Closed guard still rejects a Closed item with no close_reason.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_CLOSED_ITEM_INSERT, (FIXED_TIME,))

    # A metadata write never fires the status/close_reason update trigger.
    conn.execute("UPDATE items SET metadata = 'auth-network' WHERE id = 1")
    conn.commit()
    assert (
        conn.execute("SELECT metadata FROM items WHERE id = 1").fetchone()[0]
        == "auth-network"
    )
    conn.close()


def test_fresh_install_applies_all_migrations_through_012(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 12
    triggers = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    assert triggers == {
        "links_compat_insert",
        "links_compat_update",
        "items_closed_reason_insert",
        "items_closed_reason_update",
    }
    assert conn.execute("SELECT COUNT(*) FROM link_compat").fetchone()[0] == 16
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_failed_migration_leaves_intact_prior_database_012(
    db_path, monkeypatch
) -> None:
    _build_v11_db(db_path)
    raw = sqlite3.connect(db_path)
    items_before = _rows(raw, f"SELECT {_ITEM_COLUMNS} FROM items ORDER BY id")
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:11] + [(12, "CREATE TABLE half;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(sqlite3.Error):
        open_database(db_path)

    # The prior database file is intact at v11, and the pre-migration backup
    # was taken before the failing script ran.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    assert _rows(raw, f"SELECT {_ITEM_COLUMNS} FROM items ORDER BY id") == items_before
    raw.close()

    backup_path = Path(f"{db_path}.bak-v11")
    assert backup_path.is_file()
    backup = sqlite3.connect(backup_path)
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    assert (
        _rows(backup, f"SELECT {_ITEM_COLUMNS} FROM items ORDER BY id") == items_before
    )
    backup.close()

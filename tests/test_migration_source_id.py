"""Migration 014 tests: nullable source_id, preservation, fresh, backup.

Every test builds a real v13 database by hand (scripts 001-013 applied,
version stamped 13) and then lets the runner apply 014, per the 013 test
pattern. 014 is groundwork for the forget-source story (N14, D-07): the
ledger gains an optional `source_id` so a forgotten note can be named by
its source without any note text.
"""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.migrations import LATEST_VERSION
from ember.adapters.sqlite import open_database
from ember.capture.errors import DbOpenFailed as CaptureDbOpenFailed
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source

_MIGRATIONS_TO_13 = (
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
    "012_add_items_metadata.sql",
    "013_add_change_log_group_id.sql",
)

_LOG_COLUMNS = (
    "id, item_id, link_id, group_id, field_changed, old_value, new_value,"
    " timestamp, trigger_cause"
)


def _build_v13_db(db_path: str) -> None:
    """Build a real v13 database by hand and seed source, items, link, ledger."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (13)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_13:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn, "old note")
    insert_item(conn, source_id=source_id, item_id=1, statement="superseded")
    insert_item(conn, source_id=source_id, item_id=2, statement="newer")
    link_id = insert_link(conn, 2, 1, "supersedes")
    # One grouped ledger row (013's undo stamp) and one groupless row: the
    # migration must leave both alone and read their new column as NULL.
    conn.execute(
        "INSERT INTO change_log (id, item_id, link_id, group_id,"
        " field_changed, old_value, new_value, timestamp, trigger_cause)"
        " VALUES (7, 1, NULL, 1, 'status', 'Active', 'Challenged', ?,"
        " 'contradicts_confirmed')",
        (FIXED_TIME,),
    )
    conn.execute(
        "INSERT INTO change_log (id, item_id, link_id, group_id,"
        " field_changed, old_value, new_value, timestamp, trigger_cause)"
        " VALUES (8, 1, ?, NULL, 'status', 'Active', 'Closed:superseded',"
        " ?, 'supersedes_closed')",
        (link_id, FIXED_TIME),
    )
    conn.commit()
    conn.close()


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _pre_migration_snapshot(db_path: str) -> Path:
    """The one timestamped `.bak-<UTC stamp>-<hex>` pre-migration snapshot."""
    directory = Path(db_path).parent
    name = Path(db_path).name
    snapshots = sorted(
        p
        for p in directory.glob(f"{name}.bak-*")
        if not p.name.startswith(f"{name}.bak-v")  # the legacy family
    )
    assert len(snapshots) == 1, f"expected one snapshot, got {snapshots}"
    return snapshots[0]


def test_migration_014_adds_nullable_source_id_column(db_path) -> None:
    _build_v13_db(db_path)

    conn = open_database(db_path)
    info = {
        row["name"]: tuple(row)
        for row in conn.execute("PRAGMA table_info(change_log)")
    }
    conn.close()

    assert "source_id" in info
    _, name, column_type, notnull, default, pk = info["source_id"]
    assert name == "source_id"
    assert column_type == "INTEGER"
    assert notnull == 0
    assert default is None
    assert pk == 0


def test_migration_014_preserves_all_rows_and_values(db_path) -> None:
    _build_v13_db(db_path)
    raw = sqlite3.connect(db_path)
    log_before = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    star_before = _rows(raw, "SELECT * FROM change_log ORDER BY id")
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    after = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    assert after == log_before
    # The new column reads as NULL on every pre-existing row. `SELECT *`
    # order is the real table order (013's group_id sits last in the v13
    # file, 014's source_id is appended after it).
    star = _rows(raw, "SELECT * FROM change_log ORDER BY id")
    assert star == [row + (None,) for row in star_before]
    raw.close()


def test_migration_014_preserves_existing_schema(db_path) -> None:
    _build_v13_db(db_path)
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
    schema_version = raw.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]
    foreign_key_rows = _rows(raw, "PRAGMA foreign_key_check")
    raw.close()

    # No object was renamed, rebuilt or dropped. ADD COLUMN rewrites the
    # stored CREATE text of `change_log`, so its truth comes from the column
    # diff below: the schema diff is exactly one column.
    for name, sql in objects_before.items():
        if name != "change_log":
            assert objects_after[name] == sql
    for table in tables:
        if table == "change_log":
            assert columns_after[table] == columns_before[table] + [
                (9, "source_id", "INTEGER", 0, None, 0)
            ]
        else:
            assert columns_after[table] == columns_before[table], table
    assert schema_version == LATEST_VERSION
    # The FK check is clean after the structural change.
    assert foreign_key_rows == []


def test_migration_014_closed_item_guards_still_active(db_path) -> None:
    """011's Closed guard survives the structural change (same re-check 013 ran)."""
    _build_v13_db(db_path)
    conn = open_database(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO items (id, type, statement, source_id, status,"
            " created_at, validated, rationale, source, close_reason,"
            " status_origin)"
            " VALUES (9, 'Decision', 'closed item', 1, 'Closed', ?, NULL,"
            " NULL, NULL, NULL, 'derived')",
            (FIXED_TIME,),
        )
    conn.close()


def test_migration_014_writes_the_safety_copy(db_path) -> None:
    _build_v13_db(db_path)
    raw = sqlite3.connect(db_path)
    log_before = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    version_before = raw.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]
    raw.close()

    open_database(db_path).close()

    # The safety copy is the runner's own timestamped snapshot (B4-16): a
    # healthy copy at the pre-migration version.
    backup = sqlite3.connect(str(_pre_migration_snapshot(db_path)))
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    assert (
        _rows(backup, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
        == _rows(sqlite3.connect(db_path), f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    )
    backup.close()


def test_failed_migration_rolls_back_and_keeps_the_v13_file(
    db_path, monkeypatch
) -> None:
    _build_v13_db(db_path)
    raw = sqlite3.connect(db_path)
    log_before = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:13]
        + [(LATEST_VERSION, "ALTER TABLE change_log RENAME TO x;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(CaptureDbOpenFailed):
        open_database(db_path)

    # The prior database file is intact at v13, and the pre-migration backup
    # was taken before the failing script ran.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    assert (
        _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
    )
    raw.close()

    backup = sqlite3.connect(str(_pre_migration_snapshot(db_path)))
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    assert (
        _rows(backup, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
    )
    backup.close()


def test_fresh_install_applies_all_migrations_to_the_latest(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == LATEST_VERSION
    columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(change_log)")
    ]
    assert columns[-1] == "source_id"
    conn.close()

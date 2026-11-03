"""Migration 013 tests: group_id column, preservation, triggers, fresh, failure.

Every test builds a real v12 database by hand (scripts 001-012 applied, version
stamped 12) and then lets the runner apply 013, per the 011/012 test pattern.
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

_MIGRATIONS_TO_12 = (
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
)

_LOG_COLUMNS = (
    "id, item_id, link_id, field_changed, old_value, new_value, timestamp,"
    " trigger_cause"
)

_CLOSED_ITEM_INSERT = (
    "INSERT INTO items (id, type, statement, source_id, status, created_at,"
    " validated, rationale, source, close_reason, status_origin)"
    " VALUES (9, 'Decision', 'closed item', 1, 'Closed', ?, NULL, NULL, NULL,"
    " NULL, 'derived')"
)


def _build_v12_db(db_path: str) -> None:
    """Build a real v12 database by hand and seed source, items, link, ledger."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (12)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_12:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn, "old note")
    insert_item(conn, source_id=source_id, item_id=1, statement="superseded")
    insert_item(conn, source_id=source_id, item_id=2, statement="newer")
    link_id = insert_link(conn, 2, 1, "supersedes")
    conn.execute(
        "INSERT INTO change_log (id, item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, 1, NULL, 'status', 'Active', 'Challenged', ?,"
        " 'contradicts_confirmed')",
        (FIXED_TIME,),
    )
    conn.execute(
        "INSERT INTO change_log (id, item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (8, 1, ?, 'status', 'Active', 'Closed:superseded', ?,"
        " 'supersedes_closed')",
        (link_id, FIXED_TIME),
    )
    conn.commit()
    conn.close()


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _pre_migration_snapshot(db_path: str) -> Path:
    """The one timestamped `.bak-<UTC stamp>-<hex>` pre-migration snapshot.

    Since B4-16 the runner names the copy `<db>.bak-<stamp>-<6hex>`, never
    again the reusable `.bak-v<version>`, so a repeated run leaves its own
    snapshot instead of overwriting one file.
    """
    directory = Path(db_path).parent
    name = Path(db_path).name
    snapshots = sorted(
        p
        for p in directory.glob(f"{name}.bak-*")
        if not p.name.startswith(f"{name}.bak-v")  # the legacy family
    )
    assert len(snapshots) == 1, f"expected one snapshot, got {snapshots}"
    return snapshots[0]


def test_migration_013_adds_nullable_group_id_column(db_path) -> None:
    _build_v12_db(db_path)

    conn = open_database(db_path)
    info = {
        row["name"]: tuple(row)
        for row in conn.execute("PRAGMA table_info(change_log)")
    }
    conn.close()

    assert "group_id" in info
    _, name, column_type, notnull, default, pk = info["group_id"]
    assert name == "group_id"
    assert column_type == "INTEGER"
    assert notnull == 0
    assert default is None
    assert pk == 0


def test_migration_013_preserves_all_rows_and_values(db_path) -> None:
    _build_v12_db(db_path)
    raw = sqlite3.connect(db_path)
    log_before = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    star_before = _rows(raw, "SELECT * FROM change_log ORDER BY id")
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    after = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    assert after == log_before
    # The new columns read as NULL on every pre-existing row. `SELECT *`
    # order is the real table order; a v12 open runs 013 (group_id) AND
    # the migrations after 013 (source_id, then whatever ships next) before it
    # reaches the latest version.
    star = _rows(raw, "SELECT * FROM change_log ORDER BY id")
    assert star == [row + (None, None) for row in star_before]
    raw.close()


def test_migration_013_preserves_existing_schema(db_path) -> None:
    _build_v12_db(db_path)
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
                (8, "group_id", "INTEGER", 0, None, 0),
                # 014 appends its own nullable column after 013's.
                (9, "source_id", "INTEGER", 0, None, 0),
            ]
        else:
            assert columns_after[table] == columns_before[table], table
    assert schema_version == LATEST_VERSION
    # The FK check is clean after the structural change.
    assert foreign_key_rows == []


def test_migration_013_enforcement_triggers_still_active(db_path) -> None:
    _build_v12_db(db_path)
    conn = open_database(db_path)

    # 011's Closed guard still rejects a Closed item with no close_reason.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_CLOSED_ITEM_INSERT, (FIXED_TIME,))
    conn.close()


def test_migration_013_writes_the_safety_copy(db_path) -> None:
    _build_v12_db(db_path)
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
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 12
    assert (
        _rows(backup, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
        == _rows(sqlite3.connect(db_path), f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    )
    backup.close()


def test_failed_migration_rolls_back_and_keeps_the_v12_file(
    db_path, monkeypatch
) -> None:
    _build_v12_db(db_path)
    raw = sqlite3.connect(db_path)
    log_before = _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:12] + [(13, "ALTER TABLE change_log RENAME TO x;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(CaptureDbOpenFailed):
        open_database(db_path)

    # The prior database file is intact at v12, and the pre-migration backup
    # was taken before the failing script ran.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 12
    assert (
        _rows(raw, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
    )
    raw.close()

    backup = sqlite3.connect(str(_pre_migration_snapshot(db_path)))
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 12
    assert (
        _rows(backup, f"SELECT {_LOG_COLUMNS} FROM change_log ORDER BY id")
        == log_before
    )
    backup.close()


def test_fresh_install_applies_all_migrations_through_013(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    # Fresh installs go through 013 AND everything after it — the latest
    # version is derived from the shipped scripts (issue #45).
    assert version >= 13
    columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(change_log)")
    ]
    assert "group_id" in columns
    conn.close()

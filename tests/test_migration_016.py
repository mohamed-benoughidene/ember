"""Migration 016 tests: the history read's order index, rows, fresh, failure.

Every test builds a real v15 database by hand (scripts 001-015 applied, version
stamped 15 — the current latest before this batch) and then lets the runner
apply 016, per the 015 test pattern.

The new index `idx_change_log_ts_id` on `change_log (timestamp, id)` is
ADDITIVE (constitution D5): it touches no table, no column, no row — it only
gives the history read an ordering the SQL can walk to its page's end
(Batch 8, finding 4.7 #12). An every-day open re-applies nothing: the index
already exists.
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
from tests.fakes import FIXED_TIME, insert_item, insert_source

_MIGRATIONS_TO_15 = (
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
    "014_add_change_log_source_id.sql",
    "015_add_item_embeddings_format.sql",
)

_LEDGER_COLUMNS = (
    "id, item_id, link_id, field_changed, old_value, new_value,"
    " timestamp, trigger_cause, group_id, source_id"
)


def _build_v15_db(db_path: str) -> None:
    """Build a real v15 database by hand with items and ledger rows."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (15)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_15:
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
    # Two real ledger rows written the pre-016 way: no order index exists yet.
    conn.executemany(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, NULL, 'status', NULL, 'Active', ?, 'user_set_status')",
        [(1, "2026-01-01T00:00:00+00:00"), (2, "2026-02-01T00:00:00+00:00")],
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


def test_migration_016_creates_the_ts_id_index(db_path) -> None:
    _build_v15_db(db_path)

    conn = open_database(db_path)
    indexes = {
        row["name"]: row["sql"]
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    columns = _rows(conn, "PRAGMA index_info(idx_change_log_ts_id)")
    conn.close()

    assert "idx_change_log_ts_id" in indexes
    # The index carries exactly the history sort key, in order:
    # (seqno, column id within the table, column name).
    assert columns == [(0, 6, "timestamp"), (1, 0, "id")]


def test_migration_016_preserves_change_log_rows(db_path) -> None:
    _build_v15_db(db_path)
    raw = sqlite3.connect(db_path)
    rows_before = _rows(
        raw, f"SELECT {_LEDGER_COLUMNS} FROM change_log ORDER BY id"
    )
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    rows_after = _rows(
        raw, f"SELECT {_LEDGER_COLUMNS} FROM change_log ORDER BY id"
    )
    assert rows_after == rows_before
    assert len(rows_after) == 2
    assert [(row[1], row[7]) for row in rows_after] == [
        (1, "user_set_status"),
        (2, "user_set_status"),
    ]
    raw.close()


def test_migration_016_preserves_existing_schema(db_path) -> None:
    _build_v15_db(db_path)
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

    # Exactly one object was added — the index — and every table's columns
    # are untouched (an index rewrites nothing).
    added = set(objects_after) - set(objects_before)
    dropped = set(objects_before) - set(objects_after)
    assert added == {"idx_change_log_ts_id"}
    assert dropped == set()
    for name, sql in objects_before.items():
        assert objects_after[name] == sql, name
    assert columns_after == columns_before


def test_fresh_install_applies_all_migrations_through_016(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    # Fresh installs land at the derived latest — 16 with this batch, from
    # the migrations directory listing alone (issue #45).
    assert version == LATEST_VERSION
    assert version >= 16
    indexes = [
        name
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
            " AND name = 'idx_change_log_ts_id'"
        ).fetchall()
    ]
    assert indexes == ["idx_change_log_ts_id"]
    conn.close()


def test_failed_migration_leaves_intact_prior_database_016(
    db_path, monkeypatch
) -> None:
    _build_v15_db(db_path)
    raw = sqlite3.connect(db_path)
    ledger_before = _rows(
        raw, f"SELECT {_LEDGER_COLUMNS} FROM change_log ORDER BY id"
    )
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:15] + [(16, "CREATE TABLE half;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(CaptureDbOpenFailed):
        open_database(db_path)

    # The prior database file is intact at v15, and the pre-migration backup
    # was taken before the failing script ran — its own timestamped
    # snapshot (B4-16), a healthy copy at the pre-migration version.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 15
    assert (
        _rows(raw, f"SELECT {_LEDGER_COLUMNS} FROM change_log ORDER BY id")
        == ledger_before
    )
    raw.close()

    backup = sqlite3.connect(str(_pre_migration_snapshot(db_path)))
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 15
    assert (
        _rows(
            backup,
            f"SELECT {_LEDGER_COLUMNS} FROM change_log ORDER BY id",
        )
        == ledger_before
    )
    backup.close()

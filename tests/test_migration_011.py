"""Migration 011 tests: preservation, guards, backfill, fresh install, failure.

Every test builds a real v10 database by hand (scripts 001-010 applied, version
stamped 10) and then lets the runner apply 011, per the L2 hardening plan §13.
"""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import open_database
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source

_MIGRATIONS_TO_10 = (
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
)

_LINKS_SELECT = (
    "SELECT id, source_item_id, target_item_id, link_type, status, created_at"
    " FROM links ORDER BY id"
)


def _marker(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    link_id: int,
    timestamp: str,
) -> None:
    """Write one `link_reversed` change_log row with a controlled timestamp."""
    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        " trigger_cause)"
        " VALUES (?, ?, 'link_reversed', 'Confirmed', 'Reversed', ?, 'reversal')",
        (item_id, link_id, timestamp),
    )


def _build_v10_db(db_path: str, *, with_reversal_markers: bool = False) -> None:
    """Build a real v10 database by hand and seed compat-legal rows.

    Graph: item 2 supersedes item 1 (Decision/Decision), item 1 answers item 3
    (Decision/Question), item 4 contradicts item 1 (Finding/Decision).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_10:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn)
    insert_item(
        conn, source_id=source_id, item_id=1, statement="old decision"
    )
    insert_item(conn, source_id=source_id, item_id=2, statement="new decision")
    insert_item(
        conn, source_id=source_id, item_id=3, item_type="Question",
        statement="which db",
    )
    insert_item(
        conn, source_id=source_id, item_id=4, item_type="Finding",
        statement="latency high",
    )
    insert_link(conn, 2, 1, "supersedes")
    insert_link(conn, 1, 3, "answers")
    insert_link(conn, 4, 1, "contradicts")
    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        " trigger_cause)"
        " VALUES (1, NULL, 'created', NULL, 'old decision', ?, 'user_confirmed')",
        (FIXED_TIME,),
    )
    if with_reversal_markers:
        _marker(
            conn, item_id=1, link_id=1, timestamp="2026-01-02T00:00:00+00:00"
        )
        _marker(
            conn, item_id=1, link_id=1, timestamp="2026-01-03T00:00:00+00:00"
        )
        _marker(
            conn, item_id=3, link_id=2, timestamp="2026-01-04T00:00:00+00:00"
        )
    conn.commit()
    conn.close()


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def test_migration_011_preserves_all_rows_and_values(db_path) -> None:
    _build_v10_db(db_path)
    raw = sqlite3.connect(db_path)
    items_before = _rows(raw, "SELECT * FROM items ORDER BY id")
    links_before = _rows(raw, _LINKS_SELECT)
    log_before = _rows(raw, "SELECT * FROM change_log ORDER BY id")
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    assert _rows(raw, "SELECT * FROM items ORDER BY id") == items_before
    assert _rows(raw, _LINKS_SELECT) == links_before
    assert _rows(raw, "SELECT * FROM change_log ORDER BY id") == log_before
    raw.close()


def test_migration_011_preserves_existing_schema(db_path) -> None:
    _build_v10_db(db_path)

    def _sqlite_master(conn: sqlite3.Connection) -> dict[str, str]:
        return {
            row["name"]: row["sql"]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE"
                " 'sqlite_%'"
            )
        }

    def _table_infos(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: _rows(conn, f"PRAGMA table_info({name})") for name in tables
        }

    def _index_lists(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: _rows(conn, f"PRAGMA index_list({name})") for name in tables
        }

    def _fk_lists(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: _rows(conn, f"PRAGMA foreign_key_list({name})")
            for name in tables
        }

    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    master_before = _sqlite_master(raw)
    infos_before = _table_infos(raw)
    indexes_before = _index_lists(raw)
    fks_before = _fk_lists(raw)
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    master_after = _sqlite_master(raw)
    infos_after = _table_infos(raw)
    indexes_after = _index_lists(raw)
    fks_after = _fk_lists(raw)

    # Every pre-011 object keeps its exact sqlite_master SQL, except `links`:
    # ADD COLUMN rewrites the stored CREATE text, so its truth comes from the
    # PRAGMA diffs below.
    for name, sql in master_before.items():
        if name != "links":
            assert master_after[name] == sql

    # Every pre-011 table keeps its columns, indexes and foreign keys, except
    # `links`, which gains exactly one trailing nullable column.
    for name, info in infos_before.items():
        if name == "links":
            assert [row[-1] for row in info] == [
                row[-1] for row in infos_after[name][:-1]
            ]
            added = infos_after[name][-1]
            assert added[1] == "reversed_at"
            assert added[2] == "TEXT"
            assert added[3] == 0  # notnull
            assert added[4] is None  # no default
            assert added[5] == 0  # not pk
        else:
            assert infos_after[name] == info
        assert indexes_after[name] == indexes_before[name]
        assert fks_after[name] == fks_before[name]
    raw.close()


def test_migration_011_foreign_key_check_empty(db_path) -> None:
    _build_v10_db(db_path)

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    assert _rows(raw, "PRAGMA foreign_key_check") == []
    raw.close()


def test_migration_011_preserves_sqlite_sequence(db_path) -> None:
    _build_v10_db(db_path)
    raw = sqlite3.connect(db_path)
    sequence_before = _rows(raw, "SELECT name, seq FROM sqlite_sequence ORDER BY name")
    raw.close()

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    assert _rows(raw, "SELECT name, seq FROM sqlite_sequence ORDER BY name") == (
        sequence_before
    )
    raw.close()


def test_migration_011_backfills_reversed_at_from_ledger(db_path) -> None:
    _build_v10_db(db_path, with_reversal_markers=True)

    open_database(db_path).close()

    raw = sqlite3.connect(db_path)
    # Link 1 holds two markers: the highest-id one (2026-01-03) wins.
    # Link 2 holds one marker. Link 3 holds none. The `_marker` inserts came
    # after the `created` row, so ids 2, 3 and 4 are the markers in order.
    reversed_by_id = {
        row[0]: row[1]
        for row in raw.execute("SELECT id, reversed_at FROM links ORDER BY id")
    }
    raw.close()
    assert reversed_by_id == {
        1: "2026-01-03T00:00:00+00:00",
        2: "2026-01-04T00:00:00+00:00",
        3: None,
    }


def test_migration_011_guard_rejects_closed_row_without_close_reason(db_path) -> None:
    _build_v10_db(db_path)
    raw = sqlite3.connect(db_path)
    raw.execute("UPDATE items SET status = 'Closed' WHERE id = 3")
    raw.commit()
    raw.close()

    with pytest.raises(sqlite3.IntegrityError):
        open_database(db_path)

    raw = sqlite3.connect(db_path)
    # The runner rolled back: still v10, no reversed_at, the bad row untouched.
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert raw.execute(
        "SELECT status, close_reason FROM items WHERE id = 3"
    ).fetchone() == ("Closed", None)
    raw.row_factory = sqlite3.Row
    columns = [row["name"] for row in raw.execute("PRAGMA table_info(links)")]
    assert "reversed_at" not in columns
    raw.close()


def test_migration_011_links_guard_rejects_preexisting_illegal_pair(db_path) -> None:
    _build_v10_db(db_path)
    raw = sqlite3.connect(db_path)
    raw.execute("UPDATE items SET type = 'Question' WHERE id = 1")
    # Question supports Question is not in TYPE_COMPAT.
    raw.execute(
        "INSERT INTO links"
        " (source_item_id, target_item_id, link_type, status, created_at)"
        " VALUES (1, 3, 'supports', 'Confirmed', ?)",
        (FIXED_TIME,),
    )
    raw.commit()
    raw.close()

    with pytest.raises(sqlite3.IntegrityError):
        open_database(db_path)

    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    raw.close()


def test_backup_only_when_pending_and_keeps_newest_three(db_path) -> None:
    _build_v10_db(db_path)
    backup_dir = Path(db_path).parent
    for version in (1, 2, 3):
        Path(f"{db_path}.bak-v{version}").write_text("old", encoding="utf-8")

    open_database(db_path).close()

    # The 011 run backed up once (v10) and pruned to the newest 3 backups.
    names = sorted(p.name for p in backup_dir.glob("*.bak-v*"))
    assert len(names) == 3
    assert {"test.db.bak-v2", "test.db.bak-v3", "test.db.bak-v10"} == set(names)

    # A no-op open has no pending scripts, so it must not churn the window.
    open_database(db_path).close()
    names_after = sorted(p.name for p in backup_dir.glob("*.bak-v*"))
    assert names_after == names


def test_fresh_install_applies_all_migrations_through_011(db_path) -> None:
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 11
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


def test_failed_migration_leaves_intact_prior_database(db_path, monkeypatch) -> None:
    _build_v10_db(db_path)
    raw = sqlite3.connect(db_path)
    items_before = _rows(raw, "SELECT * FROM items ORDER BY id")
    links_before = _rows(raw, _LINKS_SELECT)
    raw.close()

    real_scripts = sqlite_adapter._migration_scripts()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: real_scripts[:10] + [(11, "CREATE TABLE half;\nTHIS IS NOT SQL;")],
    )

    with pytest.raises(sqlite3.Error):
        open_database(db_path)

    # The prior database file is intact at v10, and the pre-migration backup
    # was taken before the failing script ran.
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert _rows(raw, "SELECT * FROM items ORDER BY id") == items_before
    assert _rows(raw, _LINKS_SELECT) == links_before
    raw.close()

    backup_path = Path(f"{db_path}.bak-v10")
    assert backup_path.is_file()
    backup = sqlite3.connect(f"{db_path}.bak-v10")
    assert backup.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert _rows(backup, _LINKS_SELECT) == links_before
    backup.close()

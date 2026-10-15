"""Migration tests for the `items` and `change_log` tables."""

from __future__ import annotations

import sqlite3

import pytest

from ember.adapters.sqlite import open_database


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"]: row["type"] for row in rows}


def test_items_table_has_expected_columns(db_path) -> None:
    conn = open_database(db_path)

    columns = _columns(conn, "items")
    assert list(columns) == [
        "id",
        "type",
        "statement",
        "source_id",
        "status",
        "created_at",
        "validated",
    ]


def test_change_log_table_has_expected_columns(db_path) -> None:
    conn = open_database(db_path)

    columns = _columns(conn, "change_log")
    assert list(columns) == [
        "id",
        "item_id",
        "link_id",
        "field_changed",
        "old_value",
        "new_value",
        "timestamp",
        "trigger_cause",
    ]


def test_items_reject_unknown_type(db_path) -> None:
    conn = open_database(db_path)
    conn.execute(
        "INSERT INTO sources (title, full_text, timestamp, content_hash)"
        " VALUES ('t', 'body', '2026-01-01T00:00:00+00:00', 'h')"
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO items (type, statement, source_id, status, created_at)"
            " VALUES ('Risk', 'x', 1, 'Active', '2026-01-01T00:00:00+00:00')"
        )


def test_items_source_id_is_required(db_path) -> None:
    conn = open_database(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO items (type, statement, source_id, status, created_at)"
            " VALUES ('Decision', 'x', 999, 'Active', '2026-01-01T00:00:00+00:00')"
        )


def test_change_log_allows_null_item_id(db_path) -> None:
    conn = open_database(db_path)

    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        " trigger_cause)"
        " VALUES (NULL, NULL, 'proposed', NULL, 'x', '2026-01-01T00:00:00+00:00',"
        " 'rejected')"
    )

    count = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    assert count == 1


def test_migrations_run_once_and_reach_version_3(db_path) -> None:
    open_database(db_path).close()
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 3

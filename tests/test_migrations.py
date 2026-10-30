"""Migration tests for the `items` and `change_log` tables."""

from __future__ import annotations

import importlib.resources
import sqlite3

import pytest

from ember.adapters.sqlite import open_database
from tests.fakes import FIXED_TIME, insert_item, insert_source


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
        "rationale",
        "source",
        "close_reason",
        "status_origin",
        "metadata",
    ]


def test_ai_responses_table_has_expected_columns(db_path) -> None:
    conn = open_database(db_path)

    columns = _columns(conn, "ai_responses")
    assert list(columns) == ["id", "source_id", "item_id", "response_text", "timestamp"]


def test_links_table_has_expected_columns(db_path) -> None:
    conn = open_database(db_path)

    columns = _columns(conn, "links")
    assert list(columns) == [
        "id",
        "source_item_id",
        "target_item_id",
        "link_type",
        "status",
        "created_at",
        "reversed_at",
    ]


def test_item_embeddings_table_has_expected_columns(db_path) -> None:
    conn = open_database(db_path)

    columns = _columns(conn, "item_embeddings")
    assert list(columns) == ["item_id", "vector", "model_name", "embedded_at"]


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
        "group_id",
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


def test_links_reject_self_link(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO links"
            " (source_item_id, target_item_id, link_type, status, created_at)"
            " VALUES (1, 1, 'supports', 'Confirmed', ?)",
            (FIXED_TIME,),
        )


def test_links_enforce_unique_triple(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)
    insert_item(conn, source_id=source_id, item_id=2)
    # Decision depends_on Decision is compat-legal, so the UNIQUE triple (not
    # the compat trigger) is what rejects the duplicate here.
    conn.execute(
        "INSERT INTO links"
        " (source_item_id, target_item_id, link_type, status, created_at)"
        " VALUES (1, 2, 'depends_on', 'Confirmed', ?)",
        (FIXED_TIME,),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO links"
            " (source_item_id, target_item_id, link_type, status, created_at)"
            " VALUES (1, 2, 'depends_on', 'Confirmed', ?)",
            (FIXED_TIME,),
        )


def test_change_log_link_id_foreign_key_enforced(db_path) -> None:
    conn = open_database(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO change_log"
            " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
            " trigger_cause)"
            " VALUES (NULL, 999, 'link_confirmed', NULL, 'x', ?, 'user_confirmed')",
            (FIXED_TIME,),
        )


_VERSION_5_MIGRATIONS = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
)


def test_migrations_008_009_preserve_existing_rows(db_path) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _VERSION_5_MIGRATIONS:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO sources (id, title, full_text, timestamp, content_hash)"
        " VALUES (1, 't', 'body', ?, 'h')",
        (FIXED_TIME,),
    )
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (1, 'Decision', 'Use SQLite', 1, 'Active', ?)",
        (FIXED_TIME,),
    )
    conn.execute(
        "INSERT INTO change_log (id, item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (7, 1, NULL, 'created', NULL, 'Use SQLite', ?, 'user_confirmed')",
        (FIXED_TIME,),
    )
    conn.execute(
        "INSERT INTO ai_responses (id, source_id, response_text, timestamp)"
        " VALUES (3, 1, 'raw', ?)",
        (FIXED_TIME,),
    )
    conn.commit()
    conn.close()

    conn = open_database(db_path)

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    assert conn.execute(
        "SELECT COUNT(*) FROM change_log WHERE id = 7"
    ).fetchone()[0] == 1
    ai_row = conn.execute(
        "SELECT source_id, item_id FROM ai_responses WHERE id = 3"
    ).fetchone()
    assert ai_row["source_id"] == 1
    assert ai_row["item_id"] is None
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    sequences = {
        row["name"]: row["seq"]
        for row in conn.execute("SELECT name, seq FROM sqlite_sequence")
    }
    assert sequences["change_log"] == 7
    assert sequences["ai_responses"] == 3

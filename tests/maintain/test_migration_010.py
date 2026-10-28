"""Regression test: migration 010 on a non-empty database."""

from __future__ import annotations

import importlib.resources
import sqlite3

from ember.adapters.sqlite import open_database
from tests.fakes import FIXED_TIME, insert_source

_MIGRATIONS_TO_9 = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
)


def test_migration_010_preserves_existing_rows(db_path) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (9)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_9:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    source_id = insert_source(conn)
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (1, 'Decision', 'Use SQLite', ?, 'Active', ?)",
        (source_id, FIXED_TIME),
    )
    conn.commit()
    conn.close()

    conn = open_database(db_path)

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    row = conn.execute(
        "SELECT close_reason, status_origin FROM items WHERE id = 1"
    ).fetchone()
    assert row is not None
    assert row["close_reason"] is None
    assert row["status_origin"] == "derived"
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1

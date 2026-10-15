"""Integration tests for phase 1 against a real SQLite temp DB."""

from __future__ import annotations

import sqlite3

from ember.adapters.sqlite import SqliteSourceStore, open_database
from ember.capture.input_reader import InputMode, read_raw_text
from ember.capture.source_storage import store_source

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _store(conn: sqlite3.Connection) -> SqliteSourceStore:
    return SqliteSourceStore(conn, clock=lambda: FIXED_TIME)


def test_same_text_twice_one_row_same_id(db_path) -> None:
    conn = open_database(db_path)
    store = _store(conn)

    first = store_source(store, "hello")
    second = store_source(store, "hello")

    count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert count == 1
    assert first.source_id == second.source_id
    assert second.reused is True


def test_different_text_two_rows_different_ids(db_path) -> None:
    conn = open_database(db_path)
    store = _store(conn)

    first = store_source(store, "hello")
    second = store_source(store, "world")

    count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert count == 2
    assert first.source_id != second.source_id


def test_file_mode_writes_one_row_with_fields(db_path, tmp_path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("file content", encoding="utf-8")

    raw_text = read_raw_text(mode=InputMode.FILE, path=str(sample))
    conn = open_database(db_path)
    store = _store(conn)
    result = store_source(store, raw_text)

    row = conn.execute(
        "SELECT id, title, full_text, timestamp, content_hash FROM sources"
    ).fetchone()
    assert row["id"] == result.source_id
    assert row["title"] == "file content"
    assert row["full_text"] == "file content"
    assert row["timestamp"] == FIXED_TIME
    assert row["content_hash"] == result.content_hash


def test_migrations_are_idempotent(db_path) -> None:
    open_database(db_path).close()
    conn = open_database(db_path)

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 3
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

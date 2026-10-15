"""Integration tests for the SQLite item adapters (not the gatekeeper writes)."""

from __future__ import annotations

import sqlite3

from ember.adapters.sqlite import SqliteItemContext, open_database

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def seed_source(conn: sqlite3.Connection, full_text: str = "body") -> int:
    cursor = conn.execute(
        "INSERT INTO sources (title, full_text, timestamp, content_hash)"
        " VALUES ('t', ?, ?, ?)",
        (full_text, FIXED_TIME, f"hash-{full_text}"),
    )
    return int(cursor.lastrowid)


def add_item(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    source_id: int,
    statement: str,
    created_at: str,
    item_type: str = "Decision",
) -> None:
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (?, ?, ?, ?, 'Active', ?)",
        (item_id, item_type, statement, source_id, created_at),
    )


def test_recent_items_returns_newest_first(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    add_item(
        conn, item_id=1, source_id=source_id, statement="old", created_at=FIXED_TIME
    )
    add_item(
        conn,
        item_id=2,
        source_id=source_id,
        statement="new",
        created_at="2026-02-01T00:00:00+00:00",
    )
    conn.commit()

    items = SqliteItemContext(conn).recent_items(50)

    assert [item.id for item in items] == [2, 1]
    assert items[0].statement == "new"
    assert items[0].type.value == "Decision"


def test_recent_items_respects_limit(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    for index in range(1, 6):
        add_item(
            conn,
            item_id=index,
            source_id=source_id,
            statement=f"item {index}",
            created_at=f"2026-01-0{index}T00:00:00+00:00",
        )
    conn.commit()

    items = SqliteItemContext(conn).recent_items(3)

    assert [item.id for item in items] == [5, 4, 3]

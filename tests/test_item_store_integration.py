"""Integration tests for the SQLite item adapters (reads and gatekeeper writes)."""

from __future__ import annotations

import json
import sqlite3

from ember.adapters.sqlite import (
    SqliteItemContext,
    SqliteItemGatekeeper,
    open_database,
)
from ember.capture.item_gatekeeper import ExistingItem, StoredItem, ValidatedItem

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


def make_item(
    item_id: int = 1,
    *,
    item_type: str = "Decision",
    statement: str = "Use SQLite",
    source_id: int = 1,
) -> ValidatedItem:
    return ValidatedItem(
        id=item_id,
        type=item_type,
        statement=statement,
        source_quote="use SQLite",
        confidence=0.9,
        source_id=source_id,
        created_at=FIXED_TIME,
        status="Active",
        near_dup_warning=None,
    )


def test_statements_returns_id_and_statement_pairs(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    add_item(conn, item_id=1, source_id=source_id, statement="a", created_at=FIXED_TIME)
    add_item(conn, item_id=2, source_id=source_id, statement="b", created_at=FIXED_TIME)
    conn.commit()

    assert SqliteItemGatekeeper(conn).statements() == [
        ExistingItem(1, "a"),
        ExistingItem(2, "b"),
    ]


def test_next_item_id_is_unique_and_above_existing(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    add_item(
        conn, item_id=5, source_id=source_id, statement="x", created_at=FIXED_TIME
    )
    conn.commit()

    gatekeeper = SqliteItemGatekeeper(conn)

    assert gatekeeper.next_item_id() == 6
    assert gatekeeper.next_item_id() == 7


def test_insert_item_writes_the_row(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)

    SqliteItemGatekeeper(conn).insert_item(
        make_item(source_id=source_id), validated=None
    )

    row = conn.execute("SELECT * FROM items WHERE id = 1").fetchone()
    assert row["type"] == "Decision"
    assert row["statement"] == "Use SQLite"
    assert row["source_id"] == source_id
    assert row["status"] == "Active"
    assert row["created_at"] == FIXED_TIME
    assert row["validated"] is None


def test_insert_assumption_sets_the_validated_flag(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)

    SqliteItemGatekeeper(conn).insert_item(
        make_item(item_type="Assumption", source_id=source_id), validated=False
    )

    row = conn.execute("SELECT validated FROM items WHERE id = 1").fetchone()
    assert row["validated"] == 0


def test_log_created_writes_a_change_log_row(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    gatekeeper = SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME)
    item = make_item(source_id=source_id)
    gatekeeper.insert_item(item, validated=None)

    gatekeeper.log_created(item)

    row = conn.execute("SELECT * FROM change_log").fetchone()
    assert row["item_id"] == 1
    assert row["link_id"] is None
    assert row["field_changed"] == "created"
    assert row["old_value"] is None
    assert row["new_value"] == "Use SQLite"
    assert row["timestamp"] == FIXED_TIME
    assert row["trigger_cause"] == "user_confirmed"


def test_log_rejected_writes_a_null_item_id(db_path) -> None:
    conn = open_database(db_path)

    SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME).log_rejected(make_item(9))

    row = conn.execute("SELECT * FROM change_log").fetchone()
    assert row["item_id"] is None
    assert row["field_changed"] == "proposed"
    assert row["trigger_cause"] == "rejected"
    assert row["timestamp"] == FIXED_TIME
    assert json.loads(row["new_value"])["statement"] == "Use SQLite"
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def test_find_item_returns_the_row(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    add_item(
        conn,
        item_id=3,
        source_id=source_id,
        statement="Team ships weekly",
        created_at=FIXED_TIME,
        item_type="Assumption",
    )
    conn.commit()

    item = SqliteItemGatekeeper(conn).find_item(3)

    assert item == StoredItem(id=3, type="Assumption", validated=None)


def test_find_item_returns_none_when_missing(db_path) -> None:
    conn = open_database(db_path)

    assert SqliteItemGatekeeper(conn).find_item(99) is None


def test_save_validated_flag_flips_the_row_and_logs(db_path) -> None:
    conn = open_database(db_path)
    source_id = seed_source(conn)
    add_item(
        conn,
        item_id=3,
        source_id=source_id,
        statement="Team ships weekly",
        created_at=FIXED_TIME,
        item_type="Assumption",
    )
    conn.commit()
    gatekeeper = SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME)
    item = gatekeeper.find_item(3)

    gatekeeper.save_validated_flag(item, validated=True)

    assert conn.execute("SELECT validated FROM items WHERE id = 3").fetchone()[0] == 1
    log = conn.execute("SELECT * FROM change_log").fetchone()
    assert log["item_id"] == 3
    assert log["field_changed"] == "validated"
    assert log["old_value"] is None
    assert log["new_value"] == "true"
    assert log["timestamp"] == FIXED_TIME
    assert log["trigger_cause"] == "user_set_validated"

"""Schema enforcement tests: the DB now refuses what the gatekeepers refuse.

The triggers from migration 011 are the castle wall behind the gatekeepers:
a direct SQL INSERT/UPDATE bypassing every port still cannot write an illegal
pair or a reason-less close (L2 hardening plan §13, issues #17 and #23).
"""

from __future__ import annotations

import sqlite3

import pytest

from ember.adapters.sqlite import (
    SqliteItemGatekeeper,
    SqliteLinkStore,
    SqliteMaintainStore,
    open_database,
)
from ember.maintain.rows import StatusChange
from ember.relate.compat import TYPE_COMPAT
from ember.relate.rows import ChangeLogEntry, Link
from tests.fakes import FIXED_TIME, insert_source, make_item


def _validated_item(item_id: int, source_id: int):
    """Build one `ValidatedItem` via the shared fake factory."""
    return make_item(item_id=item_id, source_id=source_id)


def _insert_items(conn: sqlite3.Connection, source_id: int, count: int) -> None:
    gatekeeper = SqliteItemGatekeeper(conn)
    for item_id in range(1, count + 1):
        gatekeeper.insert_item(_validated_item(item_id, source_id), validated=None)
    conn.commit()


def test_links_trigger_rejects_illegal_pair_insert(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (1, 'Question', 'q1', ?, 'Active', ?)",
        (source_id, FIXED_TIME),
    )
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (2, 'Question', 'q2', ?, 'Active', ?)",
        (source_id, FIXED_TIME),
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="link_compat"):
        conn.execute(
            "INSERT INTO links"
            " (source_item_id, target_item_id, link_type, status, created_at)"
            " VALUES (1, 2, 'supports', 'Confirmed', ?)",
            (FIXED_TIME,),
        )
    assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
    conn.close()


def test_links_compat_matches_compat_table(db_path) -> None:
    conn = open_database(db_path)

    rows = conn.execute(
        "SELECT source_type, target_type, link_type FROM link_compat"
    ).fetchall()
    table_set = {(row[0], row[1], row[2]) for row in rows}
    compat_set = {
        (source, target, link_type)
        for (source, target), link_types in TYPE_COMPAT.items()
        for link_type in link_types
    }
    assert table_set == compat_set
    assert len(rows) == 16
    conn.close()


def test_links_trigger_allows_existing_writers(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    _insert_items(conn, source_id, 2)

    store = SqliteLinkStore(conn)
    link_id = store.insert_link_with_log(
        Link(
            id=None,
            source_item_id=1,
            target_item_id=2,
            link_type="depends_on",
            status="Confirmed",
            created_at=FIXED_TIME,
        ),
        ChangeLogEntry(
            id=None,
            item_id=1,
            link_id=None,
            field_changed="link_confirmed",
            new_value="depends_on:2",
            timestamp=FIXED_TIME,
            trigger_cause="user_confirmed",
        ),
    )

    row = conn.execute(
        "SELECT source_item_id, target_item_id, link_type, status FROM links"
        " WHERE id = ?",
        (link_id,),
    ).fetchone()
    assert tuple(row) == (1, 2, "depends_on", "Confirmed")
    conn.close()


def test_items_trigger_rejects_closed_without_reason(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (1, 'Decision', 'd1', ?, 'Active', ?)",
        (source_id, FIXED_TIME),
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="close_reason"):
        conn.execute("UPDATE items SET status = 'Closed' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="close_reason"):
        conn.execute(
            "INSERT INTO items (type, statement, source_id, status, created_at)"
            " VALUES ('Decision', 'd2', ?, 'Closed', ?)",
            (source_id, FIXED_TIME),
        )
    assert (
        conn.execute("SELECT status FROM items WHERE id = 1").fetchone()[0]
        == "Active"
    )
    conn.close()


def test_v10_rows_satisfy_closed_rule(db_path) -> None:
    conn = open_database(db_path)
    source_id = insert_source(conn)
    _insert_items(conn, source_id, 2)

    # The real maintain writer closes item 1 through the port surface.
    SqliteMaintainStore(conn, clock=lambda: FIXED_TIME).apply_status_changes(
        [
            StatusChange(
                item_id=1,
                old_status="Active",
                new_status="Closed",
                close_reason="invalidated",
                old_close_reason=None,
                trigger_cause="user_closed",
                link_id=None,
            )
        ]
    )

    count = conn.execute(
        "SELECT COUNT(*) FROM items WHERE status = 'Closed'"
        " AND close_reason IS NULL"
    ).fetchone()[0]
    assert count == 0
    conn.close()

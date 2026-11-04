"""Integration: `history` over a ledger written by the real engine writers."""

from __future__ import annotations

import json
from pathlib import Path

from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    SqliteQueryContext,
    open_database,
    open_maintain_database,
    open_query_database,
)
from ember.maintain.rows import StatusChange
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_set_status,
    run_undo,
    UndoRequest,
)
from ember.query.run_query import run_history
from ember.relate.rows import ChangeLogEntry, Link
from tests.fakes import FIXED_TIME, insert_item, insert_source
from tests.query.fakes import make_v10


def _seed_ledger(db_path: str) -> int:
    """Write one confirmed link and one machine close through the real writers.

    The real writers stamp their ledger rows with undo group ids
    (`change_log.group_id`, migration 013), so the seed needs a CURRENT
    file: `open_database` migrates the fresh file to 13 and returns a
    writing handle. Returns the link id. Item 2 supersedes item 1
    (Decision -> Decision is compat-legal), so the ledger holds Engine B's
    `link_confirmed` row and Engine C's `status` row.
    """
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="Old decision")
        insert_item(conn, source_id=source_id, item_id=2, statement="New decision")
        link_store = SqliteLinkStore(conn)
        link_id = link_store.insert_link_with_log(
            _link(2, 1), _link_row(2, "supersedes")
        )
        SqliteMaintainStore(conn).apply_status_changes(
            [
                StatusChange(
                    item_id=1,
                    old_status="Active",
                    new_status="Closed",
                    close_reason="superseded",
                    old_close_reason=None,
                    trigger_cause="supersedes_confirmed",
                    link_id=link_id,
                )
            ]
        )
        conn.commit()
    finally:
        conn.close()
    return link_id


def _link(source: int, target: int) -> Link:
    return Link(
        id=None,
        source_item_id=source,
        target_item_id=target,
        link_type="supersedes",
        status="Confirmed",
        created_at=FIXED_TIME,
    )


def _link_row(item_id: int, link_type: str) -> ChangeLogEntry:
    return ChangeLogEntry(
        id=None,
        item_id=item_id,
        link_id=None,
        field_changed="link_confirmed",
        old_value=None,
        new_value=link_type,
        timestamp=FIXED_TIME,
        trigger_cause="user_confirmed",
    )


def test_item_history_shows_the_link_and_status_events(db_path) -> None:
    link_id = _seed_ledger(db_path)
    conn = open_query_database(db_path)
    try:
        document = json.loads(run_history(SqliteQueryContext(conn), 1))
    finally:
        conn.close()

    assert document["mode"] == "history"
    assert document["item_id"] == 1
    assert [event["kind"] for event in document["events"]] == [
        # Newest first (Batch 6): both rows share FIXED_TIME, so the
        # status row (the higher ledger id) renders first.
        "status_changed",
        "link_confirmed",
    ]
    assert document["events"][0]["link_id"] == link_id
    assert document["events"][0]["close_reason"] == "superseded"


def test_global_history_returns_every_row(db_path) -> None:
    _seed_ledger(db_path)
    conn = open_query_database(db_path)
    try:
        item_scoped = json.loads(run_history(SqliteQueryContext(conn), 1))
        global_view = json.loads(run_history(SqliteQueryContext(conn), None))
    finally:
        conn.close()

    assert global_view["item_id"] is None
    assert global_view["count"] >= item_scoped["count"]


def test_history_for_an_item_with_no_events_is_not_an_error(db_path) -> None:
    _seed_ledger(db_path)
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn, "another body")
        insert_item(conn, source_id=source_id, item_id=3, statement="Quiet item")
        conn.commit()
    finally:
        conn.close()

    conn = open_query_database(db_path)
    try:
        document = json.loads(run_history(SqliteQueryContext(conn), 3))
    finally:
        conn.close()

    assert document["count"] == 0


def test_history_rows_carry_their_group_id(db_path) -> None:
    """The ledger read carries `change_log.group_id` (migration 013).

    One real human action, then one real undo: the status row is stamped
    with the action's group id and the `undo_of` marker row with the undo's
    own new group id (engine-undo-plan §5.1). Engine D's `list_change_log`
    must select that column (gated by `column_exists`, so a pre-013 file
    keeps `None`), otherwise every grouped row silently reads groupless
    (finding 4.7 #11).
    """
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, status="Active")
        conn.commit()
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        run_set_status(ports, MaintainRequest(item_id=1, to_status="Challenged"))
        conn.commit()
        run_undo(ports, UndoRequest())
        conn.commit()
    finally:
        conn.close()

    conn = open_query_database(db_path)
    try:
        rows = SqliteQueryContext(conn).list_change_log()
    finally:
        conn.close()

    # Newest first now (Batch 8, finding 4.7 #13): the undo's inverse rows
    # and its `undo_of` marker sort FIRST, every one stamped with the
    # undo's OWN new group id; the group-stamped human action's status row
    # sorts LAST with its own different group id.
    fields = [row.field_changed for row in rows]
    assert fields[0] == "undo_of"  # the undo's marker row, newest
    assert fields[-1] == "status"  # the group-stamped human action, oldest
    marker = next(row for row in rows if row.field_changed == "undo_of")
    assert marker.group_id is not None
    action = rows[-1]
    assert action.trigger_cause == "user_set_status"
    assert action.group_id is not None
    assert action.group_id != marker.group_id
    # And the inverse rows the undo wrote are stamped like their marker.
    inverses = [row for row in rows if row.group_id == marker.group_id]
    assert len(inverses) >= 2

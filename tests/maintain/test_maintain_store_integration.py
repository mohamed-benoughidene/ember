"""Integration: the real `SqliteMaintainStore` write paths.

These tests need foreign keys ON (the atomicity test depends on the
`change_log.link_id` FK from migration 008), so every case opens the DB through
`open_maintain_database`, never a bare `sqlite3.connect` (Constitution T10).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ember.adapters.sqlite import SqliteMaintainStore, open_maintain_database
from ember.maintain.errors import (
    ChangeLogWriteFailed as MaintainChangeLogWriteFailed,
    StatusWriteFailed as MaintainStatusWriteFailed,
)
from ember.maintain.rows import StatusChange
from tests.fakes import FIXED_TIME, insert_item, insert_source


def _open_v10(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _change(
    item_id: int,
    *,
    old_status: str = "Active",
    new_status: str = "Challenged",
    close_reason: str | None = None,
    old_close_reason: str | None = None,
    trigger_cause: str = "contradicts_confirmed",
    link_id: int | None = None,
) -> StatusChange:
    return StatusChange(
        item_id=item_id,
        old_status=old_status,
        new_status=new_status,
        close_reason=close_reason,
        old_close_reason=old_close_reason,
        trigger_cause=trigger_cause,
        link_id=link_id,
    )


def test_apply_status_changes_writes_status_and_log_rows(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    insert_item(conn, source_id=source_id, item_id=2, status="Challenged")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    applied = store.apply_status_changes(
        [
            _change(
                1,
                new_status="Closed",
                close_reason="superseded",
                trigger_cause="user_closed",
            ),
            _change(
                2,
                old_status="Challenged",
                new_status="Active",
                trigger_cause="user_set_status",
            ),
        ]
    )

    assert applied == 2
    rows = {
        row["id"]: row
        for row in conn.execute("SELECT id, status, close_reason FROM items")
    }
    assert rows[1]["status"] == "Closed"
    assert rows[1]["close_reason"] == "superseded"
    assert rows[2]["status"] == "Active"
    assert rows[2]["close_reason"] is None

    log = conn.execute("SELECT * FROM change_log ORDER BY id").fetchall()
    assert len(log) == 2
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 2

    first = log[0]
    assert first["item_id"] == 1
    assert first["link_id"] is None
    assert first["field_changed"] == "status"
    assert first["old_value"] == "Active"
    assert first["new_value"] == "Closed:superseded"
    assert first["trigger_cause"] == "user_closed"
    assert first["timestamp"] == FIXED_TIME

    second = log[1]
    assert second["item_id"] == 2
    assert second["field_changed"] == "status"
    assert second["old_value"] == "Challenged"
    assert second["new_value"] == "Active"
    assert second["trigger_cause"] == "user_set_status"
    assert second["timestamp"] == FIXED_TIME
    conn.close()


def test_old_value_predicate_keys_on_closed_status_not_reason(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Challenged")
    insert_item(
        conn,
        source_id=source_id,
        item_id=2,
        status="Closed",
        close_reason="superseded",
    )
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    store.apply_status_changes(
        [
            _change(
                1,
                old_status="Challenged",
                old_close_reason="superseded",
                new_status="Active",
            ),
            _change(
                2,
                old_status="Closed",
                old_close_reason="superseded",
                new_status="Active",
            ),
        ]
    )

    rows = conn.execute(
        "SELECT item_id, old_value, new_value FROM change_log ORDER BY id"
    ).fetchall()
    assert [(row["item_id"], row["old_value"]) for row in rows] == [
        (1, "Challenged"),
        (2, "Closed:superseded"),
    ]
    conn.close()


def test_apply_status_changes_rolls_back_on_change_log_fk_violation(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    with pytest.raises(MaintainChangeLogWriteFailed) as exc:
        store.apply_status_changes([_change(1, new_status="Challenged", link_id=99999)])

    assert exc.value.code == "MAINTAIN-012"
    assert conn.execute("SELECT status FROM items WHERE id = 1").fetchone()[0] == "Active"
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    conn.close()


def test_apply_status_changes_rolls_back_whole_batch_on_bad_status(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    insert_item(conn, source_id=source_id, item_id=2, status="Active")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    with pytest.raises(MaintainStatusWriteFailed) as exc:
        store.apply_status_changes(
            [
                _change(1, new_status="Challenged"),
                _change(2, new_status="Bogus"),
            ]
        )

    assert exc.value.code == "MAINTAIN-011"
    statuses = {
        row["id"]: row["status"]
        for row in conn.execute("SELECT id, status FROM items")
    }
    assert statuses == {1: "Active", 2: "Active"}
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    conn.close()


def test_apply_status_origin_writes_shield_and_log_row(db_path) -> None:
    conn = _open_v10(db_path)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        status="Challenged",
        status_origin="derived",
    )
    conn.commit()
    store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

    store.apply_status_origin(1, "manual")

    row = conn.execute(
        "SELECT status_origin FROM items WHERE id = 1"
    ).fetchone()
    assert row["status_origin"] == "manual"
    log = conn.execute("SELECT * FROM change_log").fetchall()
    assert len(log) == 1
    only = log[0]
    assert only["item_id"] == 1
    assert only["link_id"] is None
    assert only["field_changed"] == "status_origin"
    assert only["old_value"] == "derived"
    assert only["new_value"] == "manual"
    assert only["trigger_cause"] == "user_set_status"
    assert only["timestamp"] == FIXED_TIME
    conn.close()

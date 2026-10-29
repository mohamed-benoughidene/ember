"""Integration: `apply_item_edit` and the grown Phase-1 read, real temp DB.

Each test drives `open_maintain_database` (foreign keys ON, Constitution T10)
and asserts the real `items` and `change_log` rows. The failure-injection
vehicle is a test-local delegating connection proxy: a fake per T3 that raises
`sqlite3.Error` only when the SQL matches the write under test and delegates
everything else, including `rollback()`, to the real connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ember.adapters.sqlite import (
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.errors import ChangeLogWriteFailed, ItemEditWriteFailed
from ember.maintain.rows import EditChange
from ember.maintain.run_maintain import MaintainPorts, MaintainRequest, run_sweep
from tests.fakes import FIXED_TIME, insert_item, insert_source


class DelegatingConnection:
    """Real connection behind a gate: `execute` raises on the target SQL only."""

    def __init__(self, conn: sqlite3.Connection, poison: str) -> None:
        self._conn = conn
        self._poison = poison

    def execute(self, sql: str, *args: object, **kwargs: object):
        if self._poison in sql:
            raise sqlite3.OperationalError("injected failure")
        return self._conn.execute(sql, *args, **kwargs)

    def rollback(self) -> None:
        self._conn.rollback()

    def commit(self) -> None:
        self._conn.commit()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def _change(item_id: int, field: str, old: str | None, new: str) -> EditChange:
    return EditChange(
        item_id=item_id,
        field=field,
        old_value=old,
        new_value=new,
        trigger_cause="user_edit_item",
    )


def _open(db_path: str) -> sqlite3.Connection:
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _seed_decision(conn: sqlite3.Connection, item_id: int = 1) -> None:
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=item_id,
        item_type="Decision",
        statement="Choose SQLite",
    )
    conn.commit()


def _rationale(conn: sqlite3.Connection, item_id: int = 1) -> str | None:
    row = conn.execute(
        "SELECT rationale FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    return row["rationale"]


def _log_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT item_id, link_id, field_changed, old_value, new_value,"
        " trigger_cause, timestamp FROM change_log ORDER BY id"
    ).fetchall()


def test_apply_item_edit_update_and_ledger_row_one_transaction(db_path) -> None:
    conn = _open(db_path)
    try:
        _seed_decision(conn)
        store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

        applied = store.apply_item_edit(_change(1, "rationale", None, "why"))

        assert applied == 1
        assert _rationale(conn) == "why"
        rows = _log_rows(conn)
        assert len(rows) == 1
        assert rows[0]["item_id"] == 1
        assert rows[0]["link_id"] is None
        assert rows[0]["field_changed"] == "rationale"
        assert rows[0]["old_value"] is None
        assert rows[0]["new_value"] == "why"
        assert rows[0]["trigger_cause"] == "user_edit_item"
        assert rows[0]["timestamp"] == FIXED_TIME
    finally:
        conn.close()


def test_apply_item_edit_sqlite_error_injection_raises_016_and_rolls_back(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        _seed_decision(conn)
        gated = DelegatingConnection(
            conn, poison="UPDATE items SET rationale"
        )
        store = SqliteMaintainStore(gated, clock=lambda: FIXED_TIME)

        try:
            store.apply_item_edit(_change(1, "rationale", None, "why"))
            raised = False
        except ItemEditWriteFailed as exc:
            raised = True
            assert exc.code == "MAINTAIN-016"

        assert raised
        assert _rationale(conn) is None
        assert _log_rows(conn) == []
    finally:
        conn.close()


def test_apply_item_edit_insert_failure_raises_012_and_rolls_back(db_path) -> None:
    conn = _open(db_path)
    try:
        _seed_decision(conn)
        gated = DelegatingConnection(
            conn, poison="INSERT INTO change_log"
        )
        store = SqliteMaintainStore(gated, clock=lambda: FIXED_TIME)

        try:
            store.apply_item_edit(_change(1, "rationale", None, "why"))
            raised = False
        except ChangeLogWriteFailed as exc:
            raised = True
            assert exc.code == "MAINTAIN-012"

        assert raised
        assert _rationale(conn) is None
        assert _log_rows(conn) == []
    finally:
        conn.close()


def test_item_state_read_carries_rationale_and_source(db_path) -> None:
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            item_type="Decision",
            statement="A",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Finding",
            statement="B",
        )
        conn.execute(
            "UPDATE items SET rationale = 'why', source = 'pubmed:1'"
            " WHERE id = 2"
        )
        conn.commit()

        items = SqliteMaintainContext(conn).list_items()

        by_id = {item.id: item for item in items}
        assert by_id[1].rationale is None
        assert by_id[1].source is None
        assert by_id[2].rationale == "why"
        assert by_id[2].source == "pubmed:1"
    finally:
        conn.close()


def test_sweep_never_reads_rationale_or_source(db_path) -> None:
    conn = _open(db_path)
    try:
        _seed_decision(conn, item_id=1)
        conn.execute(
            "UPDATE items SET rationale = 'kept', source = 'kept-source'"
            " WHERE id = 1"
        )
        conn.commit()
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
        )

        result = run_sweep(ports, MaintainRequest())

        assert result.changed == []
        assert result.applied == 0
        assert _rationale(conn) == "kept"
        assert _log_rows(conn) == []
    finally:
        conn.close()


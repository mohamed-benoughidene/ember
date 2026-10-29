"""Integration: `apply_remove_link`, the ONE links UPDATE, real temp DB.

Each test drives `open_maintain_database` (foreign keys ON, Constitution T10)
and asserts the real `links` and `change_log` rows. The failure-injection
vehicle is a test-local delegating connection proxy: a fake per T3 that raises
`sqlite3.Error` only when the SQL matches the write under test and delegates
everything else, including `rollback()`, to the real connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.db_check import check_database
from ember.adapters.sqlite import (
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.errors import (
    ChangeLogWriteFailed,
    RemoveLinkWriteFailed,
)
from ember.maintain.rows import LinkChange, StatusChange
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_remove_link,
    run_sweep,
)
from ember.relate.rows import ChangeLogEntry
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source


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


def _change(link_id: int, source_item_id: int) -> LinkChange:
    return LinkChange(
        link_id=link_id,
        old_status="Confirmed",
        new_status="Rejected",
        trigger_cause="user_remove_link",
        item_id=source_item_id,
    )


def _open(db_path: str) -> sqlite3.Connection:
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _link_status(conn: sqlite3.Connection, link_id: int) -> str:
    row = conn.execute(
        "SELECT status FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    return row["status"]


def _log_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT item_id, link_id, field_changed, old_value, new_value,"
        " trigger_cause, timestamp FROM change_log ORDER BY id"
    ).fetchall()


def _ports(conn: sqlite3.Connection) -> MaintainPorts:
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
    )


def _seed_pair(
    conn: sqlite3.Connection,
    link_type: str,
    *,
    target: tuple[str, str, str | None] = ("Decision", "Active", None),
    source: tuple[str, str, str | None] = ("Decision", "Active", None),
) -> int:
    """Insert item 1 (the link's target), item 2 (the link's source), and one
    Confirmed link 2 -> 1 of `link_type`."""
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type=target[0],
        status=target[1],
        close_reason=target[2],
        statement="target",
    )
    insert_item(
        conn,
        source_id=source_id,
        item_id=2,
        item_type=source[0],
        status=source[1],
        close_reason=source[2],
        statement="source",
    )
    link_id = insert_link(conn, 2, 1, link_type)
    conn.commit()
    return link_id


# Per-type seeds, legal per TYPE_COMPAT (supersedes same-type pairs, answers
# (Decision|Finding) -> Question, contradicts (Finding, Assumption|Decision),
# depends_on (Decision|Assumption) -> (Assumption|Finding|Decision), supports
# (Finding) -> (Assumption|Decision)). The expected statuses after the removal
# and the next sweep are exactly the seeded ones: nothing re-fires, nothing
# unwinds. supports feeds no trigger even Confirmed, so its param pins a
# trivially-true case.
_REMOVED_LINK_CASES = {
    "supersedes": (
        ("Decision", "Active", None),
        ("Decision", "Closed", "superseded"),
    ),
    "answers": (
        ("Decision", "Active", None),
        ("Question", "Closed", "answered"),
    ),
    "contradicts": (
        ("Finding", "Active", None),
        ("Decision", "Challenged", None),
    ),
    "depends_on": (
        ("Decision", "Challenged", None),
        ("Decision", "Closed", "invalidated"),
    ),
    "supports": (
        ("Finding", "Active", None),
        ("Decision", "Active", None),
    ),
}


def test_apply_remove_link_flip_and_ledger_row_one_transaction(db_path) -> None:
    conn = _open(db_path)
    try:
        link_id = _seed_pair(conn, "depends_on")
        store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)

        applied = store.apply_remove_link(_change(link_id, 2))

        assert applied == 1
        assert _link_status(conn, link_id) == "Rejected"
        rows = _log_rows(conn)
        assert len(rows) == 1
        assert rows[0]["item_id"] == 2  # the link's source
        assert rows[0]["link_id"] == link_id
        assert rows[0]["field_changed"] == "link_removed"
        assert rows[0]["old_value"] == "Confirmed"
        assert rows[0]["new_value"] == "Rejected"
        assert rows[0]["trigger_cause"] == "user_remove_link"
        assert rows[0]["timestamp"] == FIXED_TIME
    finally:
        conn.close()


def test_apply_remove_link_sqlite_error_injection_raises_017_and_rolls_back(
    db_path,
) -> None:
    conn = _open(db_path)
    try:
        link_id = _seed_pair(conn, "depends_on")
        gated = DelegatingConnection(conn, poison="UPDATE links SET status")
        store = SqliteMaintainStore(gated, clock=lambda: FIXED_TIME)

        with pytest.raises(RemoveLinkWriteFailed) as exc:
            store.apply_remove_link(_change(link_id, 2))

        assert exc.value.code == "MAINTAIN-017"
        assert exc.value.context["link_id"] == link_id
        # Everything rolled back on the real connection behind the proxy.
        assert _link_status(conn, link_id) == "Confirmed"
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    finally:
        conn.close()


def test_apply_remove_link_insert_failure_raises_012_and_rolls_back(db_path) -> None:
    conn = _open(db_path)
    try:
        link_id = _seed_pair(conn, "depends_on")
        gated = DelegatingConnection(conn, poison="INSERT INTO change_log")
        store = SqliteMaintainStore(gated, clock=lambda: FIXED_TIME)

        with pytest.raises(ChangeLogWriteFailed) as exc:
            store.apply_remove_link(_change(link_id, 2))

        assert exc.value.code == "MAINTAIN-012"
        assert exc.value.context["link_id"] == link_id
        assert _link_status(conn, link_id) == "Confirmed"
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("link_type", sorted(_REMOVED_LINK_CASES))
def test_sweep_ignores_removed_link(db_path, link_type) -> None:
    """§12.5's per-type table, one param per removed link type: after each
    removal the next sweep writes zero rows and no derived state unwinds."""
    conn = _open(db_path)
    try:
        source_seed, target_seed = _REMOVED_LINK_CASES[link_type]
        link_id = _seed_pair(conn, link_type, source=source_seed, target=target_seed)
        store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)
        store.apply_remove_link(_change(link_id, 2))
        log_count = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]

        result = run_sweep(_ports(conn), MaintainRequest())

        assert result.applied == 0
        assert result.changed == []
        assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == (
            log_count
        )
        assert _link_status(conn, link_id) == "Rejected"
        for item_id, (item_type, status, close_reason) in (
            (1, target_seed),
            (2, source_seed),
        ):
            row = conn.execute(
                "SELECT type, status, close_reason FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
            assert (row["status"], row["close_reason"]) == (status, close_reason)
    finally:
        conn.close()


def test_removed_supersedes_does_not_reopen_the_closed_item(db_path) -> None:
    """Named regression 1 (engine-maintain-plan §8, verbatim)."""
    conn = _open(db_path)
    try:
        link_id = _seed_pair(
            conn,
            "supersedes",
            source=("Decision", "Active", None),
            target=("Decision", "Closed", "superseded"),
        )

        changes = run_remove_link(
            _ports(conn), MaintainRequest(link_id=link_id)
        )
        assert len(changes) == 1
        result = run_sweep(_ports(conn), MaintainRequest())

        assert result.applied == 0
        row = conn.execute(
            "SELECT status, close_reason FROM items WHERE id = 1"
        ).fetchone()
        assert (row["status"], row["close_reason"]) == ("Closed", "superseded")
        assert _link_status(conn, link_id) == "Rejected"
    finally:
        conn.close()


def test_reversed_then_removed_link_has_both_marker_rows_sweep_unaffected(
    db_path,
) -> None:
    """Named regression 2 (§12.5, orthogonal to reversal): the ledger ends
    with both a `link_reversed` and a `link_removed` row, the removal never
    touches `reversed_at`, and the next sweep writes zero rows."""
    conn = _open(db_path)
    try:
        link_id = _seed_pair(
            conn,
            "supersedes",
            source=("Decision", "Active", None),
            target=("Decision", "Closed", "superseded"),
        )
        store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)
        store.apply_reversal(
            StatusChange(
                item_id=1,
                old_status="Closed",
                new_status="Active",
                close_reason=None,
                old_close_reason="superseded",
                trigger_cause="reversal",
                link_id=link_id,
            ),
            ChangeLogEntry(
                item_id=1,
                link_id=link_id,
                field_changed="link_reversed",
                old_value="Confirmed",
                new_value="Reversed",
                timestamp="",
                trigger_cause="reversal",
            ),
        )
        assert (
            conn.execute(
                "SELECT reversed_at FROM links WHERE id = ?", (link_id,)
            ).fetchone()["reversed_at"]
            == FIXED_TIME
        )

        store.apply_remove_link(_change(link_id, 2))

        fields = [
            row["field_changed"]
            for row in _log_rows(conn)
            if row["link_id"] == link_id
        ]
        # The reversal's item restore (`status`) plus both markers on the
        # one link id, in write order.
        assert fields == ["status", "link_reversed", "link_removed"]
        # The removal writes status only: reversed_at stays exactly as the
        # reversal pair left it.
        assert (
            conn.execute(
                "SELECT reversed_at FROM links WHERE id = ?", (link_id,)
            ).fetchone()["reversed_at"]
            == FIXED_TIME
        )
        result = run_sweep(_ports(conn), MaintainRequest())
        assert result.applied == 0
        assert result.changed == []
    finally:
        conn.close()


def test_change_log_still_joins_links_after_removal(db_path) -> None:
    """The migration-008 reason proven: no DELETE ever ran, so the ledger's
    foreign key still joins, and no violation exists."""
    conn = _open(db_path)
    try:
        link_id = _seed_pair(
            conn, "supports", source=("Finding", "Active", None)
        )
        SqliteMaintainStore(conn, clock=lambda: FIXED_TIME).apply_remove_link(
            _change(link_id, 2)
        )

        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert violations == []
        joined = conn.execute(
            "SELECT links.id, links.status, change_log.field_changed"
            " FROM change_log JOIN links ON change_log.link_id = links.id"
            " WHERE change_log.field_changed = 'link_removed'"
        ).fetchall()
        assert len(joined) == 1
        assert joined[0]["id"] == link_id
        assert joined[0]["status"] == "Rejected"
    finally:
        conn.close()


def test_remove_link_db_check_replay_still_matches(db_path) -> None:
    """§4.1's db-check interaction (cluster 1 landed, so it applies): a
    removal writes no reversal marker, so the replay still rebuilds
    `reversed_at` from `link_reversed` rows only, with the link removed."""
    conn = _open(db_path)
    try:
        link_id = _seed_pair(
            conn,
            "supersedes",
            source=("Decision", "Active", None),
            target=("Decision", "Closed", "superseded"),
        )
        store = SqliteMaintainStore(conn, clock=lambda: FIXED_TIME)
        store.apply_reversal(
            StatusChange(
                item_id=1,
                old_status="Closed",
                new_status="Active",
                close_reason=None,
                old_close_reason="superseded",
                trigger_cause="reversal",
                link_id=link_id,
            ),
            ChangeLogEntry(
                item_id=1,
                link_id=link_id,
                field_changed="link_reversed",
                old_value="Confirmed",
                new_value="Reversed",
                timestamp="",
                trigger_cause="reversal",
            ),
        )

        store.apply_remove_link(_change(link_id, 2))

        report = check_database(db_path)
        assert report.result == "OK", report.lines
    finally:
        conn.close()

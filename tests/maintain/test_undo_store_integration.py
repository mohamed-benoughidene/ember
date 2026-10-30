"""Integration: `apply_inverse_group` + the reversal/shield readers (undo 03).

Every case drives a real temp database through `open_maintain_database`
(foreign keys ON, Constitution T10), performs one undoable human action
through the real entry points (group-stamped, undo step 01), then undoes and
redoes it with `derive_undo` / `derive_redo` + `apply_inverse_group` and
asserts the exact prior state. The failure-injection vehicle is the
test-local delegating connection proxy (the `test_remove_link_integration`
pattern): a fake per T3 that raises `sqlite3.Error` only when the SQL matches
the write under test and delegates everything else, including `rollback()`,
to the real connection.

The undo snapshot is assembled here from the grouped ledger read plus the
item read plus a raw all-links read (status and `reversed_at` included): the
refusal rule compares every row against the LIVE link state, so it must see
a `Rejected` link and a set `reversed_at`, which the Confirmed-only link
read cannot return. Undo step 04 owns wiring this assembly into the CLI
(recorded in the ticket build notes).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.db_check import OK, check_database
from ember.adapters.link_replay import replay_reversals
from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.capture.item_gatekeeper import StoredItem
from ember.maintain.derive import derive_status_changes
from ember.maintain.errors import (
    ChangeLogWriteFailed,
    GroupRecordInvalid,
    UndoWriteFailed,
)
from ember.maintain.rows import MaintainSnapshot, UndoSnapshot
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_close_item,
    run_edit_item,
    run_remove_link,
    run_reverse_supersedes,
    run_set_status,
    run_sweep,
    run_undo,
    UndoRequest,
)
from ember.maintain.undo import derive_redo, derive_undo
from ember.query.rows import ChangeRow
from ember.relate.errors import SupersedesCycle
from ember.relate.link_gatekeeper import (
    LinkDraft,
    RejectedLink,
    ValidatedLink,
    validate_add_link,
)
from ember.relate.rows import Link
from tests.fakes import insert_item, insert_link, insert_source


class StepClock:
    """One later ISO stamp per call, so `(timestamp, id)` ordering follows
    the order of the writes the test performs."""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"2026-01-01T00:{self.n // 60:02d}:{self.n % 60:02d}+00:00"


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


def _open(db_path: str) -> sqlite3.Connection:
    Path(db_path).touch()
    return open_maintain_database(db_path)


def _ports(conn: sqlite3.Connection, clock: StepClock) -> MaintainPorts:
    store = SqliteMaintainStore(conn, clock=clock)
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=store,
        group_ids=SqliteGroupIdPort(conn),
    )


def _state(conn: sqlite3.Connection) -> tuple:
    """The whole live state undo must restore, minus the labelled
    `reversed_at` copy (a redo re-stamps it with the new time by design)."""
    items = sorted(
        tuple(row)
        for row in conn.execute(
            "SELECT id, type, status, close_reason, status_origin,"
            " rationale, source, validated FROM items"
        )
    )
    links = sorted(
        tuple(row)
        for row in conn.execute(
            "SELECT id, source_item_id, target_item_id, link_type, status,"
            " created_at FROM links"
        )
    )
    return items, links


def _item_state(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    return conn.execute(
        "SELECT status, close_reason, status_origin, validated FROM items"
        " WHERE id = ?",
        (item_id,),
    ).fetchone()


def _reversed_at(conn: sqlite3.Connection, link_id: int) -> str | None:
    row = conn.execute(
        "SELECT reversed_at FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    return None if row is None else row["reversed_at"]


def _ledger_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0])


def _ledger_rows(conn: sqlite3.Connection) -> list[ChangeRow]:
    return [
        ChangeRow(
            id=row["id"],
            item_id=row["item_id"],
            link_id=row["link_id"],
            field_changed=row["field_changed"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            timestamp=row["timestamp"],
            trigger_cause=row["trigger_cause"],
        )
        for row in conn.execute(
            "SELECT id, item_id, link_id, field_changed, old_value, new_value,"
            " timestamp, trigger_cause FROM change_log ORDER BY id"
        )
    ]


def _all_links_with_reversal_state(conn: sqlite3.Connection) -> list[Link]:
    """Every links row, any status, with `reversed_at` (see module docstring)."""
    return [
        Link(
            id=row["id"],
            source_item_id=row["source_item_id"],
            target_item_id=row["target_item_id"],
            link_type=row["link_type"],
            status=row["status"],
            created_at=row["created_at"],
            reversed_at=row["reversed_at"],
        )
        for row in conn.execute(
            "SELECT id, source_item_id, target_item_id, link_type, status,"
            " created_at, reversed_at FROM links ORDER BY id"
        )
    ]


def _undo_snapshot(conn: sqlite3.Connection) -> UndoSnapshot:
    context = SqliteMaintainContext(conn)
    return UndoSnapshot(
        groups=context.list_grouped_ledger(),
        items=context.list_items(),
        links=_all_links_with_reversal_state(conn),
        ungrouped_rows_exist=bool(
            conn.execute(
                "SELECT 1 FROM change_log WHERE group_id IS NULL LIMIT 1"
            ).fetchone()
        ),
    )


def _apply_undo(
    conn: sqlite3.Connection, store: SqliteMaintainStore
):
    plan = derive_undo(_undo_snapshot(conn))
    applied = store.apply_inverse_group(plan)
    assert applied == len(plan.changes)
    return plan


def _apply_redo(
    conn: sqlite3.Connection, store: SqliteMaintainStore
):
    plan = derive_redo(_undo_snapshot(conn))
    applied = store.apply_inverse_group(plan)
    assert applied == len(plan.changes)
    return plan


def _undo_redo_roundtrip(
    conn,
    store,
    db_path,
    before: tuple,
    after_action: tuple,
) -> tuple:
    """Shared assertions: undo returns the exact prior state (ledger only
    grows), redo returns the exact post-action state, db-check reads OK."""
    count_action = _ledger_count(conn)
    undo_plan = _apply_undo(conn, store)
    assert _state(conn) == before
    count_undo = _ledger_count(conn)
    assert count_undo == count_action + len(undo_plan.changes) + 1  # + marker
    redo_plan = _apply_redo(conn, store)
    assert _state(conn) == after_action
    assert _ledger_count(conn) == (
        count_undo + len(redo_plan.changes) + 1  # + marker
    )
    assert check_database(db_path).result == OK
    return undo_plan, redo_plan


# ---------------------------------------------------------------------------
# The six undoable actions: undo -> exact prior state; redo -> exact state.
# ---------------------------------------------------------------------------


def test_undo_then_redo_close_item_restores_exact_state(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    before = _state(conn)

    run_close_item(ports, MaintainRequest(item_id=1, reason="expired"))
    assert _ledger_count(conn) == 1  # the close row, group-stamped
    undo_plan, redo_plan = _undo_redo_roundtrip(
        conn, ports.store, db_path, before, _state(conn)
    )
    assert undo_plan.source_action == "close-item"
    assert redo_plan.source_action == "close-item"
    conn.close()


def test_undo_then_redo_set_status_restores_exact_state(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    before = _state(conn)

    run_set_status(ports, MaintainRequest(item_id=1, to_status="Challenged"))
    undo_plan, _ = _undo_redo_roundtrip(
        conn, ports.store, db_path, before, _state(conn)
    )
    assert undo_plan.source_action == "set-status"
    conn.close()


def test_undo_clear_returns_status_to_challenged_and_origin_to_old_value(
    db_path,
) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    store = ports.store
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Challenged")
    conn.commit()
    before = _state(conn)

    # The clear: Challenged -> Active sets the manual shield.
    run_set_status(ports, MaintainRequest(item_id=1, to_status="Active"))
    assert _item_state(conn, 1)["status_origin"] == "manual"
    assert _ledger_count(conn) == 2  # the status row + the origin row

    # The undo: status back to Challenged, origin back to the recorded OLD
    # value (spec 12.3 rule 3; the old `restores manual` text was wrong).
    undo_plan = _apply_undo(conn, store)
    row = _item_state(conn, 1)
    assert row["status"] == "Challenged"
    assert row["status_origin"] == "derived"
    assert _state(conn) == before
    assert undo_plan.source_action == "set-status"
    assert _ledger_count(conn) == 2 + len(undo_plan.changes) + 1
    assert check_database(db_path).result == OK

    # The redo re-sets the clear: status Active, origin manual again.
    redo_plan = _apply_redo(conn, store)
    row = _item_state(conn, 1)
    assert row["status"] == "Active"
    assert row["status_origin"] == "manual"
    assert len(redo_plan.changes) == 2
    conn.close()


def test_undo_then_redo_edit_item_restores_exact_state(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, rationale="old why")
    conn.commit()
    before = _state(conn)

    run_edit_item(
        ports, MaintainRequest(item_id=1, field="rationale", value="new why")
    )
    undo_plan, redo_plan = _undo_redo_roundtrip(
        conn, ports.store, db_path, before, _state(conn)
    )
    assert undo_plan.source_action == "edit-item"
    assert redo_plan.source_action == "edit-item"
    conn.close()


def test_undo_then_redo_remove_link_restores_exact_state(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)
    insert_item(conn, source_id=source_id, item_id=2)
    link_id = insert_link(conn, 1, 2, "depends_on")
    conn.commit()
    before = _state(conn)

    run_remove_link(ports, MaintainRequest(link_id=link_id))
    assert (
        conn.execute(
            "SELECT status FROM links WHERE id = ?", (link_id,)
        ).fetchone()["status"]
        == "Rejected"
    )
    undo_plan, redo_plan = _undo_redo_roundtrip(
        conn, ports.store, db_path, before, _state(conn)
    )
    assert undo_plan.source_action == "remove-link"
    assert redo_plan.source_action == "remove-link"
    # The removal flip-back is the first `links.status` upward write: the
    # migration-011 trigger does not block it, and db-check still read OK
    # inside the roundtrip.
    conn.close()


def test_undo_then_redo_reverse_supersedes_restores_exact_state(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    store = ports.store
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)  # S
    insert_item(conn, source_id=source_id, item_id=2)  # T
    supersedes_id = insert_link(conn, 1, 2, "supersedes")
    conn.commit()

    # The sweep closes T `superseded` (ungrouped rows, invisible to undo).
    run_sweep(ports, MaintainRequest())
    before = _state(conn)
    assert _item_state(conn, 2)["close_reason"] == "superseded"

    # The reversal restores T and stamps `reversed_at` (an undoable group).
    run_reverse_supersedes(
        ports, MaintainRequest(item_id=2, link_id=supersedes_id)
    )
    after_action = _state(conn)
    assert after_action != before
    assert _item_state(conn, 2)["status"] == "Active"
    assert _reversed_at(conn, supersedes_id) is not None

    # The undo re-closes T EXACTLY as before and clears `reversed_at`.
    _apply_undo(conn, store)
    assert _state(conn) == before
    assert _item_state(conn, 2)["close_reason"] == "superseded"
    assert _reversed_at(conn, supersedes_id) is None

    # The redo restores T and re-stamps `reversed_at` with the NEW time
    # (L2 §5.4): equal to the redo's own `link_reversed` ledger timestamp,
    # which is what the db-check replay reads back (OK asserted below).
    _apply_redo(conn, store)
    assert _state(conn) == after_action
    redo_stamp = conn.execute(
        "SELECT timestamp FROM change_log WHERE field_changed ="
        " 'link_reversed' AND trigger_cause = 'user_redo'"
    ).fetchone()["timestamp"]
    assert _reversed_at(conn, supersedes_id) == redo_stamp
    assert check_database(db_path).result == OK
    conn.close()


def test_undo_of_validated_writes_items_validated_b2_exception(db_path) -> None:
    conn = _open(db_path)
    clock = StepClock()
    ids = SqliteGroupIdPort(conn)
    gatekeeper = SqliteItemGatekeeper(conn, clock=clock, group_ids=ids)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, item_type="Assumption")
    conn.commit()
    store = SqliteMaintainStore(conn, clock=clock)

    before = _state(conn)

    # The capture-side write (B2's owner), through the real gatekeeper.
    gatekeeper.save_validated_flag(
        StoredItem(id=1, type="Assumption", validated=None),
        validated=True,
        group_id=ids.next_group_id(),
    )
    assert _item_state(conn, 1)["validated"] == 1

    # The declared B2 exception: undo writes the Capture-owned column back.
    _apply_undo(conn, store)
    assert _item_state(conn, 1)["validated"] is None
    assert _state(conn) == before
    assert check_database(db_path).result == OK

    _apply_redo(conn, store)
    assert _item_state(conn, 1)["validated"] == 1
    assert check_database(db_path).result == OK
    conn.close()


# ---------------------------------------------------------------------------
# Reversal readers: one rule, both places.
# ---------------------------------------------------------------------------


def test_reverse_undo_sweep_sees_link_live_and_redo_skips_again(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    context = SqliteMaintainContext(conn)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)  # S
    insert_item(conn, source_id=source_id, item_id=2)  # T
    supersedes_id = insert_link(conn, 1, 2, "supersedes")
    conn.commit()

    run_sweep(ports, MaintainRequest())  # T closed `superseded`
    run_reverse_supersedes(
        ports, MaintainRequest(item_id=2, link_id=supersedes_id)
    )
    assert context.list_reversed_link_ids() == {supersedes_id}
    assert run_sweep(ports, MaintainRequest()).applied == 0  # skipped

    # Undo of the reversal: the highest-id marker is now `link_unreversed`,
    # so the link reads live again — through the sweep reader AND the pure
    # replay the db-check line uses.
    _apply_undo(conn, ports.store)
    assert context.list_reversed_link_ids() == set()
    assert replay_reversals(_ledger_rows(conn))[supersedes_id] is None
    # The derivation sees it live: with T Active the close re-derives.
    derived = derive_status_changes(
        MaintainSnapshot(
            items=[
                item.model_copy(
                    update={"status": "Active", "close_reason": None}
                )
                for item in context.list_items()
            ],
            links=context.list_confirmed_links(),
            reversed_link_ids=context.list_reversed_link_ids(),
            shield_log=context.list_shield_log(),
        )
    )
    assert [(change.item_id, change.close_reason) for change in derived] == [
        (2, "superseded")
    ]

    # Reverse again by redo: the new `link_reversed` marker hides it again.
    _apply_redo(conn, ports.store)
    assert context.list_reversed_link_ids() == {supersedes_id}
    assert replay_reversals(_ledger_rows(conn))[supersedes_id] is not None
    result = run_sweep(ports, MaintainRequest())
    assert result.applied == 0  # skipped again: T stays Active
    assert check_database(db_path).result == OK
    conn.close()


# ---------------------------------------------------------------------------
# The manual shield across an undo and a redo of the clear.
# ---------------------------------------------------------------------------


def test_redo_of_clear_keeps_item_shielded_against_older_evidence(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    context = SqliteMaintainContext(conn)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Decision",
        status="Challenged",
    )
    insert_item(conn, source_id=source_id, item_id=2, item_type="Finding")
    conn.commit()

    # The clear (t1, group-stamped), then its undo (t2).
    run_set_status(ports, MaintainRequest(item_id=1, to_status="Active"))
    _apply_undo(conn, ports.store)

    # Relate confirms a new contradicts link (t3): its own `link_confirmed`
    # row is the candidate's evidence, older than the coming redo clear.
    validated = validate_add_link(
        LinkDraft(source_item_id=2, target_item_id=1, link_type="contradicts"),
        SqliteLinkContext(conn),
        clock=lambda: "2026-01-01T00:00:03+00:00",  # after t2, before t4
    )
    assert isinstance(validated, ValidatedLink)
    SqliteLinkStore(conn).insert_link_with_log(
        validated.link_row, validated.change_log_row
    )

    # The redo (t4): the shield reader must accept the `user_redo` clear, so
    # the shield boundary moves to t4 — LATER than the t3 evidence.
    _apply_redo(conn, ports.store)
    clears = [
        row
        for row in context.list_shield_log()
        if row.field_changed == "status_origin"
    ]
    assert [(row.trigger_cause, row.new_value) for row in clears] == [
        ("user_set_status", "manual"),  # the clear, t1
        ("user_redo", "manual"),  # the redo re-sets the boundary, t4
    ]

    # The sweep keeps the item shielded: the t3 evidence cannot beat the t4
    # clear, so the contradicts candidate is skipped. With the old reader the
    # boundary stayed t1, the t3 evidence won, and the item would have moved.
    result = run_sweep(ports, MaintainRequest())
    assert result.applied == 0
    row = _item_state(conn, 1)
    assert row["status"] == "Active"
    assert row["status_origin"] == "manual"
    assert check_database(db_path).result == OK
    conn.close()


# ---------------------------------------------------------------------------
# The relate gatekeeper sees a link restored by undo live (rules 8/9).
# ---------------------------------------------------------------------------


def test_undo_restored_supersedes_link_is_live_for_rules_8_and_9(db_path) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1)  # A
    insert_item(conn, source_id=source_id, item_id=2)  # B
    link_id = insert_link(conn, 1, 2, "supersedes")
    conn.commit()

    run_remove_link(ports, MaintainRequest(link_id=link_id))
    # Rules 8/9 walk only live edges (`Confirmed`, `reversed_at IS NULL`):
    # with the link `Rejected` the inverse B -> A passes the nine rules.
    allowed = validate_add_link(
        LinkDraft(source_item_id=2, target_item_id=1, link_type="supersedes"),
        SqliteLinkContext(conn),
        clock=lambda: "2026-01-01T00:00:01+00:00",
    )
    assert isinstance(allowed, ValidatedLink)

    # The undo flips the SAME row back to `Confirmed`; the real gatekeeper's
    # rule 8 now walks it: the corrective inverse is a supersedes cycle,
    # blocked by the restored link itself (the detail names it).
    _apply_undo(conn, ports.store)
    blocked = validate_add_link(
        LinkDraft(source_item_id=2, target_item_id=1, link_type="supersedes"),
        SqliteLinkContext(conn),
        clock=lambda: "2026-01-01T00:00:02+00:00",
    )
    assert isinstance(blocked, RejectedLink)
    assert blocked.code == SupersedesCycle.code
    assert (
        blocked.detail is not None
        and f"blocked by link {link_id}" in blocked.detail
    )
    assert check_database(db_path).result == OK
    conn.close()


# ---------------------------------------------------------------------------
# Failure injection: delegating connection, zero rows changed, full rollback.
# ---------------------------------------------------------------------------


def test_injected_update_failure_raises_026_and_rolls_back(db_path) -> None:
    conn = _open(db_path)
    clock = StepClock()
    ports = _ports(conn, clock)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    run_close_item(ports, MaintainRequest(item_id=1, reason="expired"))
    state_after_action = _state(conn)
    count = _ledger_count(conn)
    plan = derive_undo(_undo_snapshot(conn))

    poisoned = SqliteMaintainStore(
        DelegatingConnection(conn, "UPDATE"), clock=clock
    )
    with pytest.raises(UndoWriteFailed) as excinfo:
        poisoned.apply_inverse_group(plan)
    assert excinfo.value.code == "MAINTAIN-026"
    # Zero rows changed: the ledger gained nothing, the item never moved.
    assert _ledger_count(conn) == count
    assert _state(conn) == state_after_action
    assert check_database(db_path).result == OK
    conn.close()


def test_injected_insert_failure_raises_012_and_rolls_back(db_path) -> None:
    conn = _open(db_path)
    clock = StepClock()
    ports = _ports(conn, clock)
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    run_close_item(ports, MaintainRequest(item_id=1, reason="expired"))
    state_after_action = _state(conn)
    count = _ledger_count(conn)
    plan = derive_undo(_undo_snapshot(conn))

    poisoned = SqliteMaintainStore(
        DelegatingConnection(conn, "INSERT INTO change_log"), clock=clock
    )
    with pytest.raises(ChangeLogWriteFailed) as excinfo:
        poisoned.apply_inverse_group(plan)
    assert excinfo.value.code == "MAINTAIN-012"
    # The UPDATEs (already run inside the transaction) roll back with the
    # failed INSERT: zero rows changed.
    assert _ledger_count(conn) == count
    assert _state(conn) == state_after_action
    assert check_database(db_path).result == OK
    conn.close()


# ---------------------------------------------------------------------------
# Corrupt ledger: a marker pointing at itself fails closed, zero rows written.
# ---------------------------------------------------------------------------


def test_corrupt_self_pointing_marker_raises_027_and_writes_nothing(
    db_path,
) -> None:
    conn = _open(db_path)
    ports = _ports(conn, StepClock())
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, status="Active")
    conn.commit()
    run_close_item(ports, MaintainRequest(item_id=1, reason="expired"))
    count = _ledger_count(conn)
    # A corrupt row a healthy write can never produce: marker group 2 names
    # its OWN group. `run_undo` must refuse with both ids, writing nothing.
    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        "  trigger_cause, group_id)"
        " VALUES (1, NULL, 'undo_of', NULL, '2', ?, 'user_undo', 2)",
        ("2026-01-01T00:00:59+00:00",),
    )
    conn.commit()
    with pytest.raises(GroupRecordInvalid) as excinfo:
        run_undo(ports, UndoRequest(dry_run=True))
    assert excinfo.value.code == "MAINTAIN-027"
    assert excinfo.value.context == {"group_id": 2, "target_group_id": 2}
    assert _ledger_count(conn) == count + 1  # only the corrupt row itself
    conn.close()

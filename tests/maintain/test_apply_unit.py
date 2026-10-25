"""Unit tests for the sweep pipeline, using the fake store (T2/T3).

These cover the pipeline's shape, not the adapter's atomicity — the atomicity
and constraint tests run against the real `SqliteMaintainStore` elsewhere.
"""

from __future__ import annotations

from ember.maintain.derive import derive_status_changes
from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    MaintainResult,
    _apply_and_report,
    index_items,
    run_sweep,
)
from ember.relate.rows import Link
from tests.maintain.fakes import FakeMaintainLookup, FakeMaintainStore

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _item(
    item_id: int,
    item_type: str = "Decision",
    status: str = "Active",
    close_reason: str | None = None,
    status_origin: str = "derived",
) -> ItemState:
    return ItemState(
        id=item_id,
        type=item_type,
        status=status,
        close_reason=close_reason,
        status_origin=status_origin,
    )


def _link(
    link_id: int,
    source_id: int,
    target_id: int,
    link_type: str,
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type=link_type,
        status="Confirmed",
        created_at=FIXED_TIME,
    )


def _ports(
    items: list[ItemState] | None = None,
    links: list[Link] | None = None,
    reversed_ids: set[int] | None = None,
) -> tuple[MaintainPorts, FakeMaintainStore]:
    store = FakeMaintainStore()
    ports = MaintainPorts(
        lookup=FakeMaintainLookup(
            items=items, links=links, reversed_link_ids=reversed_ids
        ),
        store=store,
    )
    return ports, store


def _snapshot(items: list[ItemState], links: list[Link]) -> MaintainSnapshot:
    return MaintainSnapshot(items=items, links=links, reversed_link_ids=set())


def test_run_sweep_calls_apply_exactly_once_with_derived_list() -> None:
    ports, store = _ports(
        items=[_item(1), _item(2)],
        links=[_link(10, 1, 2, "supersedes")],
    )
    expected = derive_status_changes(
        _snapshot([_item(1), _item(2)], [_link(10, 1, 2, "supersedes")])
    )

    result = run_sweep(ports, MaintainRequest())

    assert len(store.applied_changes) == 1
    assert store.applied_changes[0] == expected
    assert len(expected) == 1
    assert result.changed == expected
    assert result.total_items == 2


def test_run_sweep_empty_snapshot_reports_zero() -> None:
    ports, store = _ports()

    result = run_sweep(ports, MaintainRequest())

    assert result == MaintainResult(
        changed=[], applied=0, reopened=0, total_items=0
    )
    assert store.applied_changes == [[]]


def test_run_sweep_applied_equals_len_changed_and_never_reopens() -> None:
    ports, _store = _ports(
        items=[_item(1), _item(2), _item(3)],
        links=[_link(10, 1, 2, "supersedes"), _link(11, 3, 2, "contradicts")],
    )

    result = run_sweep(ports, MaintainRequest())

    assert result.applied == len(result.changed)
    assert result.reopened == 0
    assert [change.item_id for change in result.changed] == [2]
    assert result.changed[0].new_status == "Closed"


def test_apply_and_report_counts_reopen_for_challenged_to_active() -> None:
    ports, store = _ports()
    change = StatusChange(
        item_id=1,
        old_status="Challenged",
        new_status="Active",
        close_reason=None,
        trigger_cause="user_set_status",
        link_id=None,
    )

    result = _apply_and_report(ports, _snapshot([], []), [change])

    assert result == MaintainResult(
        changed=[change], applied=1, reopened=1, total_items=0
    )
    assert store.applied_changes == [[change]]


def test_apply_and_report_ignores_non_reopen_moves() -> None:
    ports, _store = _ports()
    active_to_active = StatusChange(
        item_id=1,
        old_status="Active",
        new_status="Active",
        close_reason=None,
        trigger_cause="user_set_status",
        link_id=None,
    )
    active_to_challenged = StatusChange(
        item_id=2,
        old_status="Active",
        new_status="Challenged",
        close_reason=None,
        trigger_cause="contradicts_confirmed",
        link_id=7,
    )
    closed_to_active = StatusChange(
        item_id=3,
        old_status="Closed",
        new_status="Active",
        close_reason=None,
        trigger_cause="reversal",
        link_id=8,
    )

    result = _apply_and_report(
        ports, _snapshot([], []), [active_to_active, active_to_challenged, closed_to_active]
    )

    assert result.applied == 3
    assert result.reopened == 1


def test_index_items_returns_dict_keyed_by_id() -> None:
    first = _item(1)
    second = _item(2, status="Challenged")

    indexed = index_items(
        MaintainSnapshot(items=[first, second], links=[], reversed_link_ids=set())
    )

    assert indexed == {1: first, 2: second}
    assert indexed[2].status == "Challenged"


def test_index_items_empty_snapshot_returns_empty_dict() -> None:
    assert index_items(_snapshot([], [])) == {}

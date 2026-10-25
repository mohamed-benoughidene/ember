"""Maintain Phase-1 load helper, the by-id item index, and the sweep pipeline.

Step 02 adds `MaintainPorts` / `MaintainRequest` / `MaintainResult` and the
`run_sweep` entry point here (it owns the store port). Step 03 adds the three
validators and their human entry points. This module owns the read step.
"""

from __future__ import annotations

from dataclasses import dataclass

from ember.maintain.apply_status import MaintainStorePort
from ember.maintain.derive import derive_status_changes
from ember.maintain.maintain_lookup import MaintainLookupPort
from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange


@dataclass(frozen=True)
class MaintainPorts:
    """The two ports the maintain pipeline reads and writes through."""

    lookup: MaintainLookupPort
    store: MaintainStorePort


@dataclass(frozen=True)
class MaintainRequest:
    """The data for one maintain run; each command reads only its own fields."""

    item_id: int | None = None
    reason: str | None = None
    to_status: str | None = None
    link_id: int | None = None


@dataclass(frozen=True)
class MaintainResult:
    """The outcome Phase 4 reports from (I4: named object, not a tuple).

    `total_items` is the size of the snapshot this run derived from, so the
    caller can render the report without re-reading the graph.
    """

    changed: list[StatusChange]
    applied: int
    reopened: int
    total_items: int


def _load(ports: MaintainLookupPort) -> MaintainSnapshot:
    """Read the whole world the Phase-2 derivation needs (Phase 1).

    Raises `MAINTAIN-010 ItemsReadFailed` when any of the three port reads
    fails. The engine core trusts what the port returns (I9).
    """
    return MaintainSnapshot(
        items=ports.list_items(),
        links=ports.list_confirmed_links(),
        reversed_link_ids=ports.list_reversed_link_ids(),
    )


def index_items(snapshot: MaintainSnapshot) -> dict[int, ItemState]:
    """Return the snapshot's items keyed by id (I4: a named dict, not a tuple).

    The validators and `merge_and_filter` use this to find one item by id, so
    no extra port method is needed.
    """
    return {item.id: item for item in snapshot.items}


def _apply_and_report(
    ports: MaintainPorts,
    snapshot: MaintainSnapshot,
    changes: list[StatusChange],
) -> MaintainResult:
    """Write the batch through the store port, then count the reopens.

    Raises `MAINTAIN-011 StatusWriteFailed` / `MAINTAIN-012 ChangeLogWriteFailed`
    from the store, which rolls the whole batch back (I7).

    `reopened` counts the changes that actually moved to `Active` from a
    non-`Active` status — a `Challenged -> Active` or `Closed -> Active` move.
    It is computed from the merged list passed to the store, so a change the
    merge dropped is never counted. `total_items` is the snapshot size, carried
    so the caller can report without a second load.
    """
    applied = ports.store.apply_status_changes(changes)
    reopened = sum(
        1
        for change in changes
        if change.new_status == "Active" and change.old_status != "Active"
    )
    return MaintainResult(
        changed=changes,
        applied=applied,
        reopened=reopened,
        total_items=len(snapshot.items),
    )


def run_sweep(ports: MaintainPorts, request: MaintainRequest) -> MaintainResult:
    """Run the whole sweep pipeline: load, derive, apply, report.

    Raises `MAINTAIN-010` on a read failure, `MAINTAIN-011` / `MAINTAIN-012`
    from the store write. The sweep takes no input fields, so `request` is
    carried only for the shared four-command contract.
    """
    snapshot = _load(ports.lookup)
    changes = derive_status_changes(snapshot)
    return _apply_and_report(ports, snapshot, changes)

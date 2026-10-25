"""Maintain Phase-1 load helper, the by-id item index, and the sweep pipeline.

Step 02 adds `MaintainPorts` / `MaintainRequest` / `MaintainResult` and the
`run_sweep` entry point here (it owns the store port). Step 03 adds the three
validators and their human entry points. This module owns the read step.
"""

from __future__ import annotations

from dataclasses import dataclass

from ember.maintain.apply_status import MaintainStorePort
from ember.maintain.derive import derive_status_changes
from ember.maintain.human_actions import (
    validate_close_item,
    validate_reverse_supersedes,
    validate_set_status,
)
from ember.maintain.maintain_lookup import MaintainLookupPort
from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange
from ember.relate.rows import ChangeLogEntry


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


def _build_result(
    changes: list[StatusChange],
    applied: int,
    snapshot: MaintainSnapshot,
) -> MaintainResult:
    """Build the report result from the changes, the applied count, the snapshot.

    `reopened` counts the changes that actually moved to `Active` from a
    non-`Active` status — a `Challenged -> Active` or `Closed -> Active` move.
    It is computed from the changes passed in, so a change the merge dropped is
    never counted. `total_items` is the snapshot size, carried so the caller can
    report without a second load.
    """
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


def _apply_and_report(
    ports: MaintainPorts,
    snapshot: MaintainSnapshot,
    changes: list[StatusChange],
) -> MaintainResult:
    """Write the batch through the store port, then build the result.

    Raises `MAINTAIN-011 StatusWriteFailed` / `MAINTAIN-012 ChangeLogWriteFailed`
    from the store, which rolls the whole batch back (I7).
    """
    applied = ports.store.apply_status_changes(changes)
    return _build_result(changes, applied, snapshot)


def run_sweep(ports: MaintainPorts, request: MaintainRequest) -> MaintainResult:
    """Run the whole sweep pipeline: load, derive, apply, report.

    Raises `MAINTAIN-010` on a read failure, `MAINTAIN-011` / `MAINTAIN-012`
    from the store write. The sweep takes no input fields, so `request` is
    carried only for the shared four-command contract.
    """
    snapshot = _load(ports.lookup)
    changes = derive_status_changes(snapshot)
    return _apply_and_report(ports, snapshot, changes)


def run_close_item(ports: MaintainPorts, request: MaintainRequest) -> MaintainResult:
    """Retire an item by hand: load, validate, apply the close and its fan-out.

    Reads `request.item_id` and `request.reason`. Raises `MAINTAIN-001` /
    `002` / `003` / `004` from the validator, `MAINTAIN-010` on a read failure,
    `MAINTAIN-011` / `012` from the store. The close does **not** set the shield
    (a human close is a derived close, step-03 §4.1).
    """
    snapshot = _load(ports.lookup)
    changes = validate_close_item(snapshot, request.item_id, request.reason)
    return _apply_and_report(ports, snapshot, changes)


def run_set_status(ports: MaintainPorts, request: MaintainRequest) -> MaintainResult:
    """Move an item between Active and Challenged by hand, then shield a clear.

    Reads `request.item_id` and `request.to_status`. Raises `MAINTAIN-001` /
    `006` from the validator, `MAINTAIN-010` on a read failure, `MAINTAIN-011` /
    `012` from the store. Only a `Challenged -> Active` clear writes the
    `status_origin='manual'` shield, and only when a change was actually applied
    (so a no-op does not shield). The shield is a second transaction (step-03
    §4.2).
    """
    snapshot = _load(ports.lookup)
    changes = validate_set_status(snapshot, request.item_id, request.to_status)
    result = _apply_and_report(ports, snapshot, changes)
    if (
        result.applied
        and request.to_status == "Active"
        and changes
        and changes[0].old_status == "Challenged"
    ):
        ports.store.apply_status_origin(request.item_id, "manual")
    return result


def run_reverse_supersedes(
    ports: MaintainPorts, request: MaintainRequest
) -> MaintainResult:
    """Undo a supersedes by hand: restore the item and append the marker.

    Reads `request.item_id` and `request.link_id`. Raises `MAINTAIN-001` /
    `005` from the validator, `MAINTAIN-010` on a read failure, `MAINTAIN-011` /
    `012` from the store. The reversal writes the item restore, the `status`
    row, and the `link_reversed` marker row in one transaction; it never touches
    the `links` row and never sets the shield (step-03 §4.3).
    """
    snapshot = _load(ports.lookup)
    changes = validate_reverse_supersedes(
        snapshot, request.item_id, request.link_id
    )
    change = changes[0]
    marker = ChangeLogEntry(
        item_id=change.item_id,
        link_id=change.link_id,
        field_changed="link_reversed",
        old_value="Confirmed",
        new_value="Reversed",
        timestamp="",
        trigger_cause="reversal",
    )
    applied = ports.store.apply_reversal(change, marker)
    return _build_result(changes, applied, snapshot)

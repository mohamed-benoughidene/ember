"""Maintain Phase-1 load helper, the by-id item index, and the sweep pipeline.

Step 02 adds `MaintainPorts` / `MaintainRequest` / `MaintainResult` and the
`run_sweep` entry point here (it owns the store port). Step 03 adds the three
validators and their human entry points. Step 04 adds `run_edit_item`, which
returns the edit changes directly (`MaintainResult` stays the sweep's shape).
Step 05 adds `run_remove_link`, the same single-element shape. This module
owns the read step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ember.maintain.apply_status import MaintainStorePort
from ember.maintain.close_proposer import (
    PROMPT,
    CloseProposerPort,
    ConfirmPort,
    ProposalOutcome,
    format_proposal_block,
    propose_close_with_retry,
    stale_close_candidates,
)
from ember.maintain.derive import derive_status_changes
from ember.maintain.errors import CloseAiStoreFailed, UserAbort
from ember.maintain.human_actions import (
    validate_close_item,
    validate_edit_item,
    validate_remove_link,
    validate_reverse_supersedes,
    validate_set_status,
)
from ember.maintain.maintain_lookup import MaintainLookupPort
from ember.maintain.report import format_report
from ember.maintain.rows import (
    EditChange,
    ItemState,
    LinkChange,
    MaintainSnapshot,
    StatusChange,
)
from ember.relate.ai_response_store import AiResponseStorePort
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
    field: str | None = None
    value: str | None = None


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

    Raises `MAINTAIN-010 ItemsReadFailed` when any of the four port reads
    fails (items, confirmed links, reversed link ids, shield log). The
    engine core trusts what the port returns (I9).
    """
    return MaintainSnapshot(
        items=ports.list_items(),
        links=ports.list_confirmed_links(),
        reversed_link_ids=ports.list_reversed_link_ids(),
        shield_log=ports.list_shield_log(),
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
    """Undo a supersedes by hand: restore the item and mark the link reversed.

    Reads `request.item_id` and `request.link_id`. Raises `MAINTAIN-001` /
    `005` from the validator, `MAINTAIN-010` on a read failure, `MAINTAIN-011` /
    `012` from the store. The reversal writes the item restore, the `status`
    row, the `reversed_at` column on the `links` row, and the `link_reversed`
    marker row in one transaction from one clock read (L2 §6 pairing rule). It
    never sets the shield (step-03 §4.3).
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


def run_edit_item(
    ports: MaintainPorts, request: MaintainRequest
) -> list[EditChange]:
    """Write one item's rationale or source by hand, then return the changes.

    Reads `request.item_id`, `request.field`, `request.value`. Returns the
    single-element change list, or an **empty** list on a same-value no-op
    (nothing applied, nothing reported, and `MaintainResult` stays the
    sweep's shape, not stretched to carry this). Raises `MAINTAIN-001` /
    `013` / `014` from the validator, `MAINTAIN-010` on a read failure,
    `MAINTAIN-016` / `012` from the store.
    """
    snapshot = _load(ports.lookup)
    changes = validate_edit_item(
        snapshot, request.item_id, request.field, request.value
    )
    if not changes:
        return []
    ports.store.apply_item_edit(changes[0])
    return changes


def run_remove_link(
    ports: MaintainPorts, request: MaintainRequest
) -> list[LinkChange]:
    """Remove one confirmed link by hand: load, validate, apply the ONE flip.

    Reads `request.link_id`. Returns the single-element change list. A no-op
    is impossible by design (MAINTAIN-015 eats it, an error not a silent
    success). Raises `MAINTAIN-015` from the validator, `MAINTAIN-010` on a
    read failure, `MAINTAIN-017` / `012` from the store. The store writes the
    one `links` status UPDATE and its `link_removed` ledger row in one
    transaction, and never touches `reversed_at` (step-05 §4.1).
    """
    snapshot = _load(ports.lookup)
    changes = validate_remove_link(snapshot, request.link_id)
    ports.store.apply_remove_link(changes[0])
    return changes


@dataclass(frozen=True)
class CloseProposalPorts(MaintainPorts):
    """The sweep ports plus the three Phase-5 ports: the AI boundary, the
    raw-answer store (D8) and the user I/O edge."""

    close_proposer: CloseProposerPort
    ai_response_store: AiResponseStorePort
    confirm: ConfirmPort


_CLOSE_CHOICES = {
    "y": "yes",
    "yes": "yes",
    "n": "no",
    "no": "no",
    "q": "quit",
    "quit": "quit",
}


def run_close_proposals(ports: CloseProposalPorts, now: datetime) -> ProposalOutcome:
    """Propose AI closes for the stale shortlist, confirm each, write accepts.

    Phase 5 of the maintain pipeline (engine-maintain-plan §14). Runs the
    free pre-filter on a FRESH post-apply snapshot (a card the sweep just
    machine-closed is `Closed`, not `Active`, so it cannot be proposed twice
    in one run). `run_sweep` is untouched: this is a separate entry point.

    Per candidate: one AI call (`propose_close_with_retry`, retry ONCE, the
    second failure propagates `MAINTAIN-018` / `MAINTAIN-019`), then the raw
    answer saved verbatim in `ai_responses` keyed by `item_id` BEFORE
    anything is judged (D8, storage failure maps to `MAINTAIN-021`). A decline
    displays `no close proposed` and prompts nothing. A proposal displays its
    block and asks `[y]es / [n]o / [q]uit` (unknown answers re-ask). `y`
    writes through the existing `run_close_item` validate path (zero new
    write code), raising `MAINTAIN-001/002/003/004` from the validator,
    `MAINTAIN-010` on a read, `MAINTAIN-011`/`012` from the store, and prints
    the close's report lines through the confirm port. `n` counts and writes
    nothing. `q` or the end of input (`MAINTAIN-022 UserAbort`) stops the
    loop: leftover candidates get no AI call, nothing more is written, and
    the outcome reports `aborted=True`.
    """
    snapshot = _load(ports.lookup)
    shortlist = stale_close_candidates(snapshot, now=now)
    total = len(shortlist.candidates)
    proposed = 0
    accepted = 0
    rejected = 0
    try:
        for index, candidate in enumerate(shortlist.candidates, start=1):
            response = propose_close_with_retry(
                ports.close_proposer, candidate=candidate
            )
            _save_close_raw_response(
                ports.ai_response_store, candidate.item_id, response.raw_response
            )
            for line in format_proposal_block(
                candidate, response.proposal, index=index, total=total
            ):
                ports.confirm.write(line)
            if response.proposal is None:
                continue
            proposed += 1
            choice = _CLOSE_CHOICES.get(ports.confirm.ask(PROMPT).strip().lower())
            while choice is None:
                choice = _CLOSE_CHOICES.get(
                    ports.confirm.ask(PROMPT).strip().lower()
                )
            if choice == "quit":
                return ProposalOutcome(
                    stale=total,
                    proposed=proposed,
                    accepted=accepted,
                    rejected=rejected,
                    aborted=True,
                )
            if choice == "no":
                rejected += 1
                continue
            result = run_close_item(
                MaintainPorts(lookup=ports.lookup, store=ports.store),
                MaintainRequest(
                    item_id=candidate.item_id, reason=response.proposal.reason
                ),
            )
            for line in format_report(result.changed, result.total_items):
                ports.confirm.write(line)
            accepted += 1
    except UserAbort:
        return ProposalOutcome(
            stale=total,
            proposed=proposed,
            accepted=accepted,
            rejected=rejected,
            aborted=True,
        )
    return ProposalOutcome(
        stale=total,
        proposed=proposed,
        accepted=accepted,
        rejected=rejected,
    )


def _save_close_raw_response(
    store: AiResponseStorePort, item_id: int, raw_response: str
) -> None:
    """D8: store the raw answer verbatim, keyed by `item_id`, before anything
    is judged. `ValueError` (the exactly-one-of owner check) is
    engine-constructed here - one owner, always - so it propagates raw: a
    code bug crashes loudly (I5). Any storage failure maps to `MAINTAIN-021
    CloseAiStoreFailed`."""
    try:
        store.save(item_id=item_id, raw_response=raw_response)
    except ValueError:
        raise
    except CloseAiStoreFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - boundary: any storage failure maps to 021
        raise CloseAiStoreFailed(
            "ai response save failed", item_id=item_id
        ) from exc

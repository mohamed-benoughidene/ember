"""Pure Phase-2 derivation: read a snapshot, compute the intended changes.

No I/O, no clock, no DB (T1). `merge_and_filter` is the shared Phase-2
boundary every command passes its candidates through.
"""

from __future__ import annotations

from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange

FLAGGING_REASONS: frozenset[str] = frozenset(
    {"invalidated", "superseded", "reversed"}
)

_LADDER: dict[str, int] = {"Active": 0, "Challenged": 1, "Closed": 2}

_PRECEDENCE: dict[str, int] = {"Closed": 2, "Challenged": 1, "Active": 0}


def derive_status_changes(snapshot: MaintainSnapshot) -> list[StatusChange]:
    """Return the status changes the sweep should apply, one per item (Rule B4).

    Rules (step-01 §4.2):
      1. Confirmed `supersedes` (not reversed) closes its target `superseded`.
      2. Confirmed `answers` whose target is a `Question` closes it `answered`.
         Tie-break: `superseded` wins over `answered` for the same target.
      3. Confirmed `contradicts` challenges its target.
      4. Confirmed `depends_on` whose target is flagging-closed challenges its
         source. Single step only.

    Deterministic. Never raises on an empty or unknown-id snapshot.
    """
    by_id = {item.id: item for item in snapshot.items}
    close_candidates = _close_candidates(snapshot, by_id)
    flagging_ids = _flagging_closed_ids(snapshot, by_id, close_candidates)
    challenge_candidates = _challenge_candidates(snapshot, by_id, flagging_ids)
    candidates = [*close_candidates, *challenge_candidates]
    return merge_and_filter(candidates, snapshot)


def merge_and_filter(
    candidates: list[StatusChange],
    snapshot: MaintainSnapshot,
    *,
    exempt: StatusChange | None = None,
) -> list[StatusChange]:
    """Reduce candidates to at most one change per item.

    - One change per item_id: precedence `Closed > Challenged > Active`, the
      exempt change outranking everything for its item.
    - Derived changes are escalation-only: kept only if they move strictly up
      `Active < Challenged < Closed`; a manual-shield item
      (`status_origin == 'manual'`) is skipped.
    - `exempt` is a human command's authoritative primary change (the seam for
      step 3): it bypasses the ladder check and the manual shield. It is
      recognized by value equality. Steps 1's sweep passes none.

    Returns a list sorted by item_id, at most one entry per item_id.
    """
    by_id = {item.id: item for item in snapshot.items}
    chosen: dict[int, StatusChange] = {}
    for change in candidates:
        item = by_id.get(change.item_id)
        if item is None:
            continue
        is_exempt = exempt is not None and change == exempt
        if not is_exempt:
            if item.status_origin == "manual":
                continue
            if _LADDER.get(change.new_status, -1) <= _LADDER.get(
                change.old_status, -1
            ):
                continue
        current = chosen.get(change.item_id)
        if current is None:
            chosen[change.item_id] = change
        elif current == exempt:
            continue
        elif is_exempt or _PRECEDENCE.get(change.new_status, -1) > _PRECEDENCE.get(
            current.new_status, -1
        ):
            chosen[change.item_id] = change
    return sorted(chosen.values(), key=lambda change: change.item_id)


def _close_candidates(
    snapshot: MaintainSnapshot, by_id: dict[int, ItemState]
) -> list[StatusChange]:
    closes: dict[int, StatusChange] = {}
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "supersedes":
            continue
        if link.id in snapshot.reversed_link_ids:
            continue
        target = by_id.get(link.target_item_id)
        if target is None:
            continue
        closes[target.id] = _close(
            target, "superseded", "supersedes_confirmed", link.id
        )
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "answers":
            continue
        target = by_id.get(link.target_item_id)
        if target is None or target.type != "Question":
            continue
        closes.setdefault(
            target.id, _close(target, "answered", "answers_confirmed", link.id)
        )
    return list(closes.values())


def _flagging_closed_ids(
    snapshot: MaintainSnapshot,
    by_id: dict[int, ItemState],
    close_candidates: list[StatusChange],
) -> set[int]:
    flagging = {
        item.id
        for item in snapshot.items
        if item.status == "Closed" and item.close_reason in FLAGGING_REASONS
    }
    effective_closes = merge_and_filter(close_candidates, snapshot)
    flagging.update(
        change.item_id
        for change in effective_closes
        if change.new_status == "Closed"
        and change.close_reason in FLAGGING_REASONS
    )
    return flagging


def _challenge_candidates(
    snapshot: MaintainSnapshot,
    by_id: dict[int, ItemState],
    flagging_ids: set[int],
) -> list[StatusChange]:
    candidates: list[StatusChange] = []
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "contradicts":
            continue
        target = by_id.get(link.target_item_id)
        if target is None:
            continue
        candidates.append(
            _challenge(target, "contradicts_confirmed", link.id)
        )
    for link in snapshot.links:
        if link.status != "Confirmed" or link.link_type != "depends_on":
            continue
        if link.target_item_id not in flagging_ids:
            continue
        source = by_id.get(link.source_item_id)
        if source is None:
            continue
        candidates.append(_challenge(source, "dependency_closed", link.id))
    return candidates


def _close(
    item: ItemState, reason: str, trigger_cause: str, link_id: int | None
) -> StatusChange:
    return StatusChange(
        item_id=item.id,
        old_status=item.status,
        new_status="Closed",
        close_reason=reason,
        old_close_reason=item.close_reason,
        trigger_cause=trigger_cause,
        link_id=link_id,
    )


def _challenge(
    item: ItemState, trigger_cause: str, link_id: int | None
) -> StatusChange:
    return StatusChange(
        item_id=item.id,
        old_status=item.status,
        new_status="Challenged",
        close_reason=None,
        old_close_reason=item.close_reason,
        trigger_cause=trigger_cause,
        link_id=link_id,
    )

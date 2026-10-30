"""Pure Phase-2 derivation: read a snapshot, compute the intended changes.

No I/O, no clock, no DB (T1). `merge_and_filter` is the shared Phase-2
boundary every command passes its candidates through. The manual shield is
timestamp-scoped (L2 §13): a `status_origin='manual'` item skips only the
candidates whose evidence does not beat the item's latest manual clear.
"""

from __future__ import annotations

from ember.maintain.rows import ItemState, MaintainSnapshot, StatusChange
from ember.relate.rows import ChangeLogEntry

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
      `Active < Challenged < Closed`.
    - The manual shield is timestamp-scoped (L2 §13.4): a manual-shield item
      (`status_origin == 'manual'`) is skipped unless the candidate's
      evidence (`_shield_passes`) beats the item's latest manual clear. A
      winning shielded change is stamped `rearm=True` on a model copy, so
      the adapter returns `status_origin` to `'derived'` in the same batch.
    - `exempt` is a human command's authoritative primary change (the seam for
      step 3): it bypasses the ladder check and the manual shield, and is
      never stamped `rearm`. It is recognized by value equality. Steps 1's
      sweep passes none.

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
            if item.status_origin == "manual" and not _shield_passes(
                change, snapshot
            ):
                continue
            if _LADDER.get(change.new_status, -1) <= _LADDER.get(
                change.old_status, -1
            ):
                continue
        current = chosen.get(change.item_id)
        if current is None:
            chosen[change.item_id] = _maybe_rearm(change, item, is_exempt)
        elif current == exempt:
            continue
        elif is_exempt or _PRECEDENCE.get(change.new_status, -1) > _PRECEDENCE.get(
            current.new_status, -1
        ):
            chosen[change.item_id] = _maybe_rearm(change, item, is_exempt)
    return sorted(chosen.values(), key=lambda change: change.item_id)


def _shield_sort_key(row: ChangeLogEntry) -> tuple[str, int]:
    """Return the row's `(timestamp, id)` ordering key (the history sort
    convention: timestamps are UTC `isoformat()`, so the string compare is
    chronological, and equal timestamps go to the higher id). A missing id
    counts as 0: store rows always carry ids, and the fallback only keeps
    the rule total on synthetic snapshots."""
    return (row.timestamp, row.id if row.id is not None else 0)


def _latest_clear(
    shield_log: list[ChangeLogEntry], item_id: int
) -> ChangeLogEntry | None:
    """Return the item's latest manual-clear row, latest = max
    `(timestamp, id)` (L2 §13.3). A clear is the row
    `apply_status_origin` writes (`field_changed='status_origin'`,
    `new_value='manual'`, cause `user_set_status`) — or the same-shaped row
    a redo of a clear writes (cause `user_redo`, undo step 03), so a redo
    re-sets the shield boundary to the redo time. Older clears are inert.
    An undo of a clear (`new_value='derived'`) is never one, and neither
    are the re-arm rows of this amendment (`new_value='derived'`, cause
    `sweep_rearm`): only `new_value='manual'` sets the boundary."""
    best: ChangeLogEntry | None = None
    best_key: tuple[str, int] | None = None
    for row in shield_log:
        if row.item_id != item_id:
            continue
        if (
            row.field_changed != "status_origin"
            or row.trigger_cause not in ("user_set_status", "user_redo")
            or row.new_value != "manual"
        ):
            continue
        key = _shield_sort_key(row)
        if best_key is None or key > best_key:
            best, best_key = row, key
    return best


def _evidence_row(
    shield_log: list[ChangeLogEntry], link_id: int
) -> ChangeLogEntry | None:
    """Return the link's `link_confirmed` ledger row (L2 §13.2): the pinned
    evidence event for every derived cause family, one deterministic source."""
    best: ChangeLogEntry | None = None
    best_key: tuple[str, int] | None = None
    for row in shield_log:
        if row.field_changed != "link_confirmed" or row.link_id != link_id:
            continue
        key = _shield_sort_key(row)
        if best_key is None or key > best_key:
            best, best_key = row, key
    return best


def _shield_passes(change: StatusChange, snapshot: MaintainSnapshot) -> bool:
    """Return whether `change`'s evidence beats the item's latest manual
    clear (L2 §13.4): strictly newer wins on `(timestamp, id)`, equal
    timestamps go to the higher `change_log.id`, a tie lost skips. Fail-
    closed: no clear row visible for the item, no `link_confirmed` row for
    the candidate's `link_id`, or no `link_id` at all means skip, exactly
    as the old blanket shield did."""
    if change.link_id is None:
        return False
    clear = _latest_clear(snapshot.shield_log, change.item_id)
    evidence = _evidence_row(snapshot.shield_log, change.link_id)
    if clear is None or evidence is None:
        return False
    return _shield_sort_key(evidence) > _shield_sort_key(clear)


def _maybe_rearm(
    change: StatusChange, item: ItemState, is_exempt: bool
) -> StatusChange:
    """Stamp `rearm=True` on the winning change of a shielded item (a model
    copy: the pure core decides, the adapter executes). Exempt (human)
    changes are never stamped."""
    if is_exempt or item.status_origin != "manual":
        return change
    return change.model_copy(update={"rearm": True})


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

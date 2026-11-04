"""The pure undo/redo core (undo step 02, L2 §5.3, spec 12.6).

`derive_undo(snapshot)` and `derive_redo(snapshot)` read `UndoSnapshot` and
return `UndoResult` — the plan the store applies in one later transaction
(step 03). They are pure: no I/O, no clock, no storage import (T1). They
return a result or RAISE; a refusal is never a returned value (I4):

- `MAINTAIN-023 NothingToUndo` — no original-action group is undoable. The
  detail says whether older ledger rows carry no undo group (story 123).
- `MAINTAIN-024 NothingToRedo` — no redo target, or a newer original action
  cleared the redo (spec 12.6 rule 2).
- `MAINTAIN-025 UndoRefused` — some row's live value no longer equals its
  recorded new value, so nothing is written. Carries `group_id` and the
  `item_id` or `link_id` at the mismatch.
- `MAINTAIN-027 GroupRecordInvalid` — a row shape this build does not know
  inside a grouped ledger row; fail closed.

Stack rules (L2 §5.3 rules 1-3, spec 12.6): the undo stack is the
original-action groups in id order. A group is undone when a LATER
`undo_of` marker names it and no later `redo_of` marker names that undo;
undo takes the newest still-undone original group, redo takes the newest
not-yet-redone undo group — valid only while no original action followed
it (a new original action clears redo).
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from ember.maintain.rows import (
    InverseChange,
    ItemState,
    LedgerGroup,
    UndoResult,
    UndoSnapshot,
    split_status_value,
)
from ember.maintain.errors import (
    GroupRecordInvalid,
    NothingToRedo,
    NothingToUndo,
    UndoRefused,
)
from ember.relate.rows import ChangeLogEntry, Link

UNDO_MARKER_FIELD = "undo_of"
REDO_MARKER_FIELD = "redo_of"
MARKER_FIELDS = frozenset({UNDO_MARKER_FIELD, REDO_MARKER_FIELD})

_ORIGINAL_CAUSES: frozenset[str] = frozenset(
    {
        "user_closed",
        "dependency_closed",
        "user_set_status",
        "user_set_validated",
        "user_edit_item",
        "user_remove_link",
        "reversal",
    }
)
"""The ledger causes the six undoable human actions stamp (L2 §5.1).
Fix G1-B: a close that re-arms a shielded dependent also writes one
`sweep_rearm` passenger row inside the same group (not an original
action of its own — see derive_undo)."""


# --------------------------------------------------------------------------
# Stack derivation (L2 §5.3 rules 1-3)
# --------------------------------------------------------------------------


def _marker_group_id(row: ChangeLogEntry, group: LedgerGroup) -> int:
    """Parse the pointer row's `new_value`, or fail closed (MAINTAIN-027)."""
    value = row.new_value or ""
    if not value.isdigit():
        raise GroupRecordInvalid(
            "undo pointer row does not name a group",
            group_id=group.group_id,
            field_changed=row.field_changed,
            new_value=value,
        )
    return int(value)


def _kind(group: LedgerGroup) -> Literal["original", "undo", "redo"]:
    """Classify one group: original action, undo of one, or redo of an undo.

    Two pointer rows of different kinds in one group is a corrupt ledger:
    fail closed.
    """
    kinds = {
        UNDO_MARKER_FIELD if row.field_changed == UNDO_MARKER_FIELD
        else REDO_MARKER_FIELD if row.field_changed == REDO_MARKER_FIELD
        else None
        for row in group.rows
    }
    kinds.discard(None)
    if len(kinds) > 1:
        raise GroupRecordInvalid(
            "group mixes undo and redo pointer rows", group_id=group.group_id
        )
    if UNDO_MARKER_FIELD in kinds:
        return "undo"
    if REDO_MARKER_FIELD in kinds:
        return "redo"
    return "original"


def _active_undos(groups: list[LedgerGroup]) -> dict[int, int]:
    """Map each original group id to the undo group now standing over it.

    "Standing" = the `undo_of` marker is LATER (higher id) than the group it
    names, and no later `redo_of` marker re-applied that undo (L2 §5.3
    rule 1). A later undo of the same group wins. A pointer naming a group
    not strictly earlier than its own cannot exist in a healthy ledger (a
    group is only ever written after the group it points at): fail closed
    (MAINTAIN-027, both ids) rather than let a corrupt ledger flip the
    stack. Each pointer must also name the right KIND of group (4.6 #5):
    `undo_of` a normal action group, `redo_of` the undo group it
    re-applies — a pointer at another pointer group is a ledger that
    cannot exist, and running off it would undo the wrong group.
    """
    by_id = {group.group_id: group for group in groups}
    redone: set[int] = set()
    active: dict[int, int] = {}
    for group in groups:
        if _kind(group) != "redo":
            continue
        undone_by = _marker_group_id(
            next(
                row
                for row in group.rows
                if row.field_changed == REDO_MARKER_FIELD
            ),
            group,
        )
        _require_earlier(group, undone_by)
        _require_kind(group, by_id, undone_by, wanted="undo")
        redone.add(undone_by)
    for group in groups:
        if _kind(group) != "undo":
            continue
        undo_id = _marker_group_id(
            next(
                row
                for row in group.rows
                if row.field_changed == UNDO_MARKER_FIELD
            ),
            group,
        )
        _require_earlier(group, undo_id)
        _require_kind(group, by_id, undo_id, wanted="original")
        if group.group_id in redone:
            continue
        active[undo_id] = group.group_id
    return active


def _require_kind(
    group: LedgerGroup,
    by_id: dict[int, LedgerGroup],
    target_id: int,
    *,
    wanted: str,
) -> None:
    """Fail closed (MAINTAIN-027) when a pointer names the wrong KIND of group.

    An `undo_of` pointer must name a normal action group, a `redo_of`
    pointer the undo group it re-applies (L2 §5.3 rule 1). A pointer at
    another pointer group is a ledger that cannot exist (finding 4.6 #5):
    fail closed with both ids rather than undo the wrong group.
    """
    target = by_id.get(target_id)
    if target is None:
        raise GroupRecordInvalid(
            "marker names a group the ledger does not hold",
            group_id=group.group_id,
            target_group_id=target_id,
        )
    if _kind(target) != wanted:
        raise GroupRecordInvalid(
            "pointer row names a group of the wrong kind",
            group_id=group.group_id,
            target_group_id=target_id,
            named_group_kind=_kind(target),
        )


def _require_earlier(group: LedgerGroup, target_id: int) -> None:
    """Fail closed (MAINTAIN-027) when a pointer names an earlier-or-equal id.

    The pointer row's own group must be written AFTER the group it names,
    so its id must be strictly higher (L2 §5.3 rule 1, rule-6 fail-closed).
    """
    if target_id >= group.group_id:
        raise GroupRecordInvalid(
            "marker names a group not earlier than its own",
            group_id=group.group_id,
            target_group_id=target_id,
        )


# --------------------------------------------------------------------------
# Row inversion (L2 §5.3 rule 5, spec 12.2)
# --------------------------------------------------------------------------


def _invert_row(
    row: ChangeLogEntry, group: LedgerGroup, cause: str
) -> InverseChange:
    """Return the one inverse write that undoes or re-applies `row`.

    The inverse swaps the row's recorded values and appends a ledger row
    with `cause` (`user_undo` or `user_redo`). Marker fields flip name, not
    just value: undoing a reversal appends `link_unreversed`, re-applying it
    appends `link_reversed` (L2 §5.4). An unknown shape fails closed.
    """
    if row.field_changed == "status":
        return InverseChange(
            item_id=row.item_id,
            field="status",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=_row(row, cause, _swapped(row, "status")),
        )
    if row.field_changed == "status_origin":
        return InverseChange(
            item_id=row.item_id,
            field="status_origin",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=_row(row, cause, _swapped(row, "status_origin")),
        )
    if row.field_changed == "validated":
        return InverseChange(
            item_id=row.item_id,
            field="validated",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=_row(row, cause, _swapped(row, "validated")),
        )
    if row.field_changed in ("rationale", "source"):
        return InverseChange(
            item_id=row.item_id,
            field=row.field_changed,
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=_row(row, cause, _swapped(row, row.field_changed)),
        )
    if row.field_changed == "link_removed":
        return InverseChange(
            link_id=row.link_id,
            field="status",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=_row(row, cause, _swapped(row, "link_removed")),
        )
    if row.field_changed == "link_reversed":
        return InverseChange(
            link_id=row.link_id,
            field="reversed_at",
            expected_value="Reversed",
            new_value=None,
            ledger_row=_row(
                row, cause, LedgerValues("link_unreversed", "Reversed", "Confirmed")
            ),
        )
    if row.field_changed == "link_unreversed":
        return InverseChange(
            link_id=row.link_id,
            field="reversed_at",
            expected_value="Confirmed",
            new_value="Reversed",
            ledger_row=_row(
                row, cause, LedgerValues("link_reversed", "Confirmed", "Reversed")
            ),
        )
    raise GroupRecordInvalid(
        "unknown row shape in grouped ledger",
        group_id=group.group_id,
        field_changed=row.field_changed,
        trigger_cause=row.trigger_cause,
    )


class LedgerValues(NamedTuple):
    """The three values one appended ledger row carries (fix C1, I3/I4).

    The one named object `_row` takes instead of three loose values:
    `field` is the ledger column, `old_value`/`new_value` the swapped
    or re-applied pair."""

    field: str
    old_value: str | None
    new_value: str | None


def _swapped(row: ChangeLogEntry, field: str) -> LedgerValues:
    """The row's own values, swapped — the common inverse shape."""
    return LedgerValues(field=field, old_value=row.new_value, new_value=row.old_value)


def _row(source: ChangeLogEntry, cause: str, values: LedgerValues) -> ChangeLogEntry:
    """Build the appended ledger row: `source`'s item ids, `values`' content."""
    return ChangeLogEntry(
        item_id=source.item_id,
        link_id=source.link_id,
        field_changed=values.field,
        old_value=values.old_value,
        new_value=values.new_value,
        # The store owns the clock (T1); the empty string is the same
        # placeholder the reversal marker passes today.
        timestamp="",
        trigger_cause=cause,
    )


# --------------------------------------------------------------------------
# Refusal rule (L2 §5.3 rule 4, spec 12.6 rule 4)
# --------------------------------------------------------------------------


def _live_value(snapshot: UndoSnapshot, change: InverseChange) -> str | None:
    """Return the CURRENT value of what `change` writes, in the ledger's form.

    Status values compare in the writer's encoded `<status>:<reason>` form;
    a `reversed_at` change compares against the link's marker state
    (`Reversed` when a reversal timestamp is set, else `Confirmed`).
    An unknown field fails closed (MAINTAIN-027, finding 4.6 #6): the
    refusal rule must never pass by comparing a wrong attribute in
    silence.
    """
    if change.link_id is not None:
        link = _link(snapshot, change.link_id)
        if link is None:
            return None
        if change.field == "status":
            return link.status
        if change.field == "reversed_at":
            return "Reversed" if link.reversed_at is not None else "Confirmed"
        raise GroupRecordInvalid(
            "unknown field in grouped ledger row",
            field_changed=change.field,
            link_id=change.link_id,
        )
    item = _item(snapshot, change.item_id)
    if item is None:
        return None
    if change.field == "status":
        if item.status == "Closed":
            return f"{item.status}:{item.close_reason}"
        return item.status
    if change.field == "status_origin":
        return item.status_origin
    if change.field == "validated":
        return item.validated
    if change.field == "rationale":
        return item.rationale
    if change.field == "source":
        return item.source
    raise GroupRecordInvalid(
        "unknown field in grouped ledger row",
        field_changed=change.field,
        item_id=change.item_id,
    )


def _item(snapshot: UndoSnapshot, item_id: int | None) -> ItemState | None:
    if item_id is None:
        return None
    return next(
        (item for item in snapshot.items if item.id == item_id), None
    )


def _link(snapshot: UndoSnapshot, link_id: int | None) -> Link | None:
    if link_id is None:
        return None
    return next(
        (link for link in snapshot.links if link.id == link_id), None
    )


def _check_refusals(
    snapshot: UndoSnapshot, group: LedgerGroup, changes: list[InverseChange]
) -> None:
    """Raise `MAINTAIN-025` on the first value that moved since the action.

    For every row of the group the current value must equal the row's
    recorded new value — else the world moved on (a sweep, an add, a link
    confirm in between) and undo would overwrite a newer fact. Nothing is
    written (spec 12.6 rule 4). A target row that no longer exists must
    refuse too: the state cannot be verified.
    """
    for change in changes:
        live = _live_value(snapshot, change)
        if live != change.expected_value:
            if change.link_id is not None:
                raise UndoRefused(
                    "not undoable: the link changed since this action",
                    group_id=group.group_id,
                    link_id=change.link_id,
                )
            raise UndoRefused(
                "not undoable: the item changed since this action",
                group_id=group.group_id,
                item_id=change.item_id,
            )


# --------------------------------------------------------------------------
# Menu labels (story 113: "Undo Close item 3")
# --------------------------------------------------------------------------


def _primary_row(group: LedgerGroup) -> ChangeLogEntry:
    """Return the group's primary row: the close itself, else the first write.

    A close group's primary row carries `user_closed` (the fan-out rows
    carry `dependency_closed`); a shielded set-status's primary is its
    `status` row rather than the later `status_origin` row.
    """
    rows = [row for row in group.rows if row.field_changed not in MARKER_FIELDS]
    if not rows:
        raise GroupRecordInvalid(
            "group holds no writable rows", group_id=group.group_id
        )
    for row in rows:
        if row.trigger_cause == "user_closed":
            return row
    for row in rows:
        if row.field_changed == "status":
            return row
    return rows[0]


def _target_label(group: LedgerGroup) -> str:
    """Return "item 3" or "link 7" for the group's primary target."""
    row = _primary_row(group)
    if row.field_changed == "link_removed" and row.link_id is not None:
        return f"link {row.link_id}"
    return f"item {row.item_id}"


def _source_action_of_original(
    group: LedgerGroup, rows: list[ChangeLogEntry]
) -> str:
    """Name the original action `group`'s rows describe (its id on every
    027 raise). Reads the rows' original causes (L2 §5.2); unknown shapes
    fail closed (MAINTAIN-027), naming the group (I19)."""
    fields = {row.field_changed for row in rows}
    if "user_closed" in {row.trigger_cause for row in rows}:
        return "close-item"
    if "dependency_closed" in {row.trigger_cause for row in rows}:
        return "close-item"
    if "link_reversed" in fields:
        return "reverse-supersedes"
    if "validated" in fields:
        applied = next(
            row.new_value for row in rows if row.field_changed == "validated"
        )
        return "set-validated" if applied == "true" else "clear-validated"
    if "link_removed" in fields:
        return "remove-link"
    if "rationale" in fields or "source" in fields:
        return "edit-item"
    if "status" in fields:
        return "set-status"
    raise GroupRecordInvalid(
        "unknown row shape in grouped ledger", group_id=group.group_id
    )


def _source_action_of_undo(
    group: LedgerGroup, rows: list[ChangeLogEntry]
) -> str:
    """Name the action a REDO's `rows` re-apply (its id on every 027 raise).

    An inverse row's cause is always `user_undo` (L2 §5.2) and cannot say
    what the original action was, so this reads the VALUE the redo
    re-applies instead. Unknown shapes fail closed (MAINTAIN-027)."""
    fields = {row.field_changed for row in rows}
    if "link_unreversed" in fields:
        return "reverse-supersedes"
    if "link_removed" in fields:
        return "remove-link"
    if "validated" in fields:
        applied = next(
            row.old_value for row in rows if row.field_changed == "validated"
        )
        return "set-validated" if applied == "true" else "clear-validated"
    if "rationale" in fields or "source" in fields:
        return "edit-item"
    if "status" in fields:
        applied = next(
            row.old_value for row in rows if row.field_changed == "status"
        )
        if split_status_value(applied or "").status == "Closed":
            return "close-item"
        return "set-status"
    raise GroupRecordInvalid(
        "unknown row shape in grouped ledger", group_id=group.group_id
    )


# --------------------------------------------------------------------------
# The two entry points (L2 §5.3)
# --------------------------------------------------------------------------


def derive_undo(snapshot: UndoSnapshot) -> UndoResult:
    """Derive the plan that undoes the newest still-undoable human action.

    Pure: returns `UndoResult` or raises `MAINTAIN-023` / `MAINTAIN-025` /
    `MAINTAIN-027`. The 023 detail tells the user whether older ledger rows
    carry no undo group (story 123): those rows exist but are invisible to
    this stack, by design.
    """
    groups = sorted(snapshot.groups, key=lambda group: group.group_id)
    active = _active_undos(groups)
    done = [
        group
        for group in groups
        if _kind(group) == "original" and group.group_id not in active
    ]
    if not done:
        if snapshot.ungrouped_rows_exist:
            raise NothingToUndo(
                "nothing to undo: older ledger rows carry no undo group "
                "(they were written before the grouping upgrade) and are "
                "not undoable",
                ungrouped_rows_exist=True,
            )
        raise NothingToUndo(
            "nothing to undo", ungrouped_rows_exist=False
        )
    target = done[-1]
    rows = [row for row in target.rows if row.field_changed not in MARKER_FIELDS]
    # Fix G1-B: a close that re-arms a shielded dependent writes ONE
    # extra passenger row with cause `sweep_rearm` (the changed
    # `status_origin`) inside the close's group. It is undoable WITH
    # its group: the inverse restores the manual shield (derived ->
    # manual), and a redo re-arms again. It never travels alone — a
    # group with no original-cause row is a corrupt ledger (027).
    known = _ORIGINAL_CAUSES | {"sweep_rearm"}
    for row in rows:
        if row.trigger_cause not in known:
            raise GroupRecordInvalid(
                "unknown row shape in grouped ledger",
                group_id=target.group_id,
                field_changed=row.field_changed,
                trigger_cause=row.trigger_cause,
            )
    if not any(row.trigger_cause in _ORIGINAL_CAUSES for row in rows):
        raise GroupRecordInvalid(
            "group carries no original action, only re-arm rows",
            group_id=target.group_id,
        )
    changes = [_invert_row(row, target, "user_undo") for row in rows]
    _check_refusals(snapshot, target, changes)
    primary = _primary_row(target)
    marker = ChangeLogEntry(
        item_id=primary.item_id,
        link_id=None,
        field_changed=UNDO_MARKER_FIELD,
        old_value=None,
        new_value=str(target.group_id),
        timestamp="",
        trigger_cause="user_undo",
    )
    return UndoResult(
        source_group_id=target.group_id,
        source_action=_source_action_of_original(target, rows),
        target_label=_target_label(target),
        direction="undo",
        changes=changes,
        marker=marker,
    )


def derive_redo(snapshot: UndoSnapshot) -> UndoResult:
    """Derive the plan that re-applies the most recent undone action.

    Pure: returns `UndoResult` or raises `MAINTAIN-024` / `MAINTAIN-025` /
    `MAINTAIN-027`. The redo target is the newest undo group not yet
    redone, and it stays valid only while no original action was written
    after it — a new original action clears redo (spec 12.6 rule 2).
    """
    groups = sorted(snapshot.groups, key=lambda group: group.group_id)
    active = _active_undos(groups)
    standing_undos = set(active.values())
    candidates = [
        group for group in groups
        if _kind(group) == "undo" and group.group_id in standing_undos
    ]
    original_ids = [
        group.group_id for group in groups if _kind(group) == "original"
    ]
    if not candidates:
        raise NothingToRedo("nothing to redo", has_newer_original=False)
    newest_undo = max(candidates, key=lambda group: group.group_id)
    if any(gid > newest_undo.group_id for gid in original_ids):
        raise NothingToRedo(
            "nothing to redo: a newer change cleared it",
            has_newer_original=True,
        )
    target = newest_undo
    rows = [row for row in target.rows if row.field_changed not in MARKER_FIELDS]
    for row in rows:
        if row.trigger_cause != "user_undo":
            raise GroupRecordInvalid(
                "unknown row shape in grouped ledger",
                group_id=target.group_id,
                field_changed=row.field_changed,
                trigger_cause=row.trigger_cause,
            )
    changes = [_invert_row(row, target, "user_redo") for row in rows]
    _check_refusals(snapshot, target, changes)
    primary = _primary_row(target)
    marker = ChangeLogEntry(
        item_id=primary.item_id,
        link_id=None,
        field_changed=REDO_MARKER_FIELD,
        old_value=None,
        new_value=str(target.group_id),
        timestamp="",
        trigger_cause="user_redo",
    )
    return UndoResult(
        source_group_id=target.group_id,
        source_action=_source_action_of_undo(target, rows),
        target_label=_target_label(target),
        direction="redo",
        changes=changes,
        marker=marker,
    )

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

from typing import Literal

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
"""The ledger causes the six undoable human actions stamp (L2 §5.1)."""


# --------------------------------------------------------------------------
# Stack derivation (L2 §5.3 rules 1-3)
# --------------------------------------------------------------------------


def _marker_target(group: LedgerGroup) -> int | None:
    """Return the group id the group's `undo_of`/`redo_of` row names.

    None when the group carries no pointer row, so it is an original action.
    """
    for row in group.rows:
        if row.field_changed == UNDO_MARKER_FIELD:
            return _marker_group_id(row, group)
        if row.field_changed == REDO_MARKER_FIELD:
            return _marker_group_id(row, group)
    return None


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
    rule 1). A later undo of the same group wins.
    """
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
        if group.group_id in redone:
            continue
        active[undo_id] = group.group_id
    return active


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
    field = row.field_changed
    if field == "status":
        ledger = _row(row, cause, "status", row.new_value, row.old_value)
        return InverseChange(
            item_id=row.item_id,
            field="status",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=ledger,
        )
    if field == "status_origin":
        ledger = _row(
            row, cause, "status_origin", row.new_value, row.old_value
        )
        return InverseChange(
            item_id=row.item_id,
            field="status_origin",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=ledger,
        )
    if field == "validated":
        ledger = _row(
            row, cause, "validated", row.new_value, row.old_value
        )
        return InverseChange(
            item_id=row.item_id,
            field="validated",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=ledger,
        )
    if field in ("rationale", "source"):
        ledger = _row(row, cause, field, row.new_value, row.old_value)
        return InverseChange(
            item_id=row.item_id,
            field=field,
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=ledger,
        )
    if field == "link_removed":
        ledger = _row(
            row, cause, "link_removed", row.new_value, row.old_value
        )
        return InverseChange(
            link_id=row.link_id,
            field="status",
            expected_value=row.new_value,
            new_value=row.old_value,
            ledger_row=ledger,
        )
    if field == "link_reversed":
        ledger = _row(
            row, cause, "link_unreversed", "Reversed", "Confirmed"
        )
        return InverseChange(
            link_id=row.link_id,
            field="reversed_at",
            expected_value="Reversed",
            new_value=None,
            ledger_row=ledger,
        )
    if field == "link_unreversed":
        ledger = _row(
            row, cause, "link_reversed", "Confirmed", "Reversed"
        )
        return InverseChange(
            link_id=row.link_id,
            field="reversed_at",
            expected_value="Confirmed",
            new_value="Reversed",
            ledger_row=ledger,
        )
    raise GroupRecordInvalid(
        "unknown row shape in grouped ledger",
        group_id=group.group_id,
        field_changed=field,
        trigger_cause=row.trigger_cause,
    )


def _row(
    source: ChangeLogEntry,
    cause: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> ChangeLogEntry:
    """Build the appended ledger row: same item ids and field, swapped values."""
    return ChangeLogEntry(
        item_id=source.item_id,
        link_id=source.link_id,
        field_changed=field,
        old_value=old_value,
        new_value=new_value,
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
    """
    if change.link_id is not None:
        link = _link(snapshot, change.link_id)
        if link is None:
            return None
        if change.field == "status":
            return link.status
        return "Reversed" if link.reversed_at is not None else "Confirmed"
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
    return item.source


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


def _source_action(rows: list[ChangeLogEntry], redo: bool) -> str:
    """Name the action a group's rows describe.

    `redo=False` (an original group) reads the original causes; `redo=True`
    (an undo group) reads the value the redo re-applies, because an inverse
    row's cause is always `user_undo` (L2 §5.2) and cannot say what the
    original action was. Unknown shapes fail closed (MAINTAIN-027).
    """
    fields = {row.field_changed for row in rows}
    if redo:
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
        raise GroupRecordInvalid("unknown row shape in grouped ledger")

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
    raise GroupRecordInvalid("unknown row shape in grouped ledger")


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
    for row in rows:
        if row.trigger_cause not in _ORIGINAL_CAUSES:
            raise GroupRecordInvalid(
                "unknown row shape in grouped ledger",
                group_id=target.group_id,
                field_changed=row.field_changed,
                trigger_cause=row.trigger_cause,
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
        source_action=_source_action(rows, redo=False),
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
        source_action=_source_action(rows, redo=True),
        target_label=_target_label(target),
        direction="redo",
        changes=changes,
        marker=marker,
    )

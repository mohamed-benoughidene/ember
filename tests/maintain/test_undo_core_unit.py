"""Unit tests for the pure undo core, fakes only, no DB (undo step 02 §2).

One test per undoable action row of spec 12.2, the stack rules, the
refusal rule with the right entity ids, the sweep re-arm case, the
unknown-row-shape fail-closed case, and the pre-013 invisibility. The
snapshots are built by hand: the core reads `UndoSnapshot`, never a port.
"""

from __future__ import annotations

import pytest

from ember.maintain.errors import (
    GroupRecordInvalid,
    NothingToRedo,
    NothingToUndo,
    UndoRefused,
)
from ember.maintain.rows import (
    ItemState,
    LedgerGroup,
    StatusValue,
    UndoSnapshot,
    split_status_value,
)
from ember.maintain.undo import derive_redo, derive_undo
from ember.relate.rows import ChangeLogEntry, Link

FIXED_TIME = "2026-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------


def _item(
    item_id: int,
    *,
    item_type: str = "Decision",
    status: str = "Active",
    close_reason: str | None = None,
    status_origin: str = "derived",
    validated: str | None = None,
    rationale: str | None = None,
    source: str | None = None,
) -> ItemState:
    return ItemState(
        id=item_id,
        type=item_type,
        status=status,
        close_reason=close_reason,
        status_origin=status_origin,
        validated=validated,
        rationale=rationale,
        source=source,
    )


def _link(
    link_id: int,
    source_id: int,
    target_id: int,
    link_type: str,
    *,
    status: str = "Confirmed",
    reversed_at: str | None = None,
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_id,
        target_item_id=target_id,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
        reversed_at=reversed_at,
    )


def _row(
    item_id: int,
    field: str,
    old: str | None,
    new: str | None,
    cause: str,
    *,
    link_id: int | None = None,
) -> ChangeLogEntry:
    return ChangeLogEntry(
        item_id=item_id,
        link_id=link_id,
        field_changed=field,
        old_value=old,
        new_value=new,
        timestamp=FIXED_TIME,
        trigger_cause=cause,
    )


def _undo_marker(target_group_id: int) -> ChangeLogEntry:
    return _row(0, "undo_of", None, str(target_group_id), "user_undo")


def _redo_marker(target_group_id: int) -> ChangeLogEntry:
    return _row(0, "redo_of", None, str(target_group_id), "user_redo")


def _group(group_id: int, *rows: ChangeLogEntry) -> LedgerGroup:
    return LedgerGroup(group_id=group_id, rows=list(rows))


def _snap(
    groups: list[LedgerGroup],
    items: list[ItemState] | None = None,
    links: list[Link] | None = None,
    *,
    ungrouped: bool = False,
) -> UndoSnapshot:
    return UndoSnapshot(
        groups=groups,
        items=items or [],
        links=links or [],
        ungrouped_rows_exist=ungrouped,
    )


# --------------------------------------------------------------------------
# one test per undoable action (spec 12.2)
# --------------------------------------------------------------------------


def test_undo_close_restores_item_and_dependents() -> None:
    """close-item invalidated: the close row and the dependency row swap."""
    group = _group(
        1,
        _row(3, "status", "Active", "Closed:invalidated", "user_closed"),
        _row(5, "status", "Active", "Challenged", "dependency_closed", link_id=2),
    )
    snapshot = _snap(
        [group],
        [_item(3, status="Closed", close_reason="invalidated"), _item(5, status="Challenged")],
        [_link(2, 5, 3, "depends_on")],
    )
    result = derive_undo(snapshot)
    assert result.direction == "undo"
    assert result.source_group_id == 1
    assert result.source_action == "close-item"
    assert result.target_label == "item 3"
    assert [change.item_id for change in result.changes] == [3, 5]
    primary = result.changes[0]
    assert (primary.field, primary.expected_value, primary.new_value) == (
        "status",
        "Closed:invalidated",
        "Active",
    )
    assert primary.ledger_row.trigger_cause == "user_undo"
    assert primary.ledger_row.new_value == "Active"
    dependent = result.changes[1]
    assert (dependent.expected_value, dependent.new_value) == (
        "Challenged",
        "Active",
    )
    assert result.marker.field_changed == "undo_of"
    assert result.marker.new_value == "1"
    assert result.marker.trigger_cause == "user_undo"


def test_undo_set_status_with_shield_restores_status_and_origin() -> None:
    """Challenged -> Active: the status row and the manual shield row both swap."""
    group = _group(
        4,
        _row(4, "status", "Challenged", "Active", "user_set_status"),
        _row(4, "status_origin", "derived", "manual", "user_set_status"),
    )
    snapshot = _snap([group], [_item(4, status_origin="manual")])
    result = derive_undo(snapshot)
    assert result.source_action == "set-status"
    assert result.target_label == "item 4"
    assert [(c.field, c.expected_value, c.new_value) for c in result.changes] == [
        ("status", "Active", "Challenged"),
        ("status_origin", "manual", "derived"),
    ]


def test_undo_set_status_active_to_challenged_restores_status_only() -> None:
    """Active -> Challenged writes no shield row, so undo restores status only."""
    group = _group(
        5, _row(4, "status", "Active", "Challenged", "user_set_status")
    )
    snapshot = _snap([group], [_item(4, status="Challenged")])
    result = derive_undo(snapshot)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert (change.field, change.expected_value, change.new_value) == (
        "status",
        "Challenged",
        "Active",
    )


def test_undo_set_validated_flips_mark_back() -> None:
    group = _group(
        6, _row(6, "validated", "false", "true", "user_set_validated")
    )
    snapshot = _snap(
        [group], [_item(6, item_type="Assumption", validated="true")]
    )
    result = derive_undo(snapshot)
    assert result.source_action == "set-validated"
    assert result.target_label == "item 6"
    change = result.changes[0]
    assert (change.field, change.expected_value, change.new_value) == (
        "validated",
        "true",
        "false",
    )


def test_undo_clear_validated_flips_mark_back() -> None:
    group = _group(
        7, _row(6, "validated", "true", "false", "user_set_validated")
    )
    snapshot = _snap(
        [group], [_item(6, item_type="Assumption", validated="false")]
    )
    result = derive_undo(snapshot)
    assert result.source_action == "clear-validated"
    change = result.changes[0]
    assert (change.expected_value, change.new_value) == ("false", "true")


def test_undo_edit_item_restores_rationale() -> None:
    group = _group(
        8, _row(7, "rationale", "old why", "new why", "user_edit_item")
    )
    snapshot = _snap([group], [_item(7, rationale="new why")])
    result = derive_undo(snapshot)
    assert result.source_action == "edit-item"
    change = result.changes[0]
    assert (change.field, change.expected_value, change.new_value) == (
        "rationale",
        "new why",
        "old why",
    )
    assert change.ledger_row.old_value == "new why"
    assert change.ledger_row.new_value == "old why"


def test_undo_edit_item_restores_source() -> None:
    group = _group(
        9, _row(7, "source", "old src", "new src", "user_edit_item")
    )
    snapshot = _snap(
        [group], [_item(7, item_type="Finding", source="new src")]
    )
    result = derive_undo(snapshot)
    assert result.source_action == "edit-item"
    change = result.changes[0]
    assert (change.field, change.expected_value, change.new_value) == (
        "source",
        "new src",
        "old src",
    )


def test_undo_remove_link_confirms_link_again() -> None:
    group = _group(
        10,
        _row(4, "link_removed", "Confirmed", "Rejected", "user_remove_link",
             link_id=9),
    )
    snapshot = _snap(
        [group], [_item(4)], [_link(9, 4, 3, "depends_on", status="Rejected")]
    )
    result = derive_undo(snapshot)
    assert result.source_action == "remove-link"
    assert result.target_label == "link 9"
    change = result.changes[0]
    assert change.link_id == 9
    assert (change.field, change.expected_value, change.new_value) == (
        "status",
        "Rejected",
        "Confirmed",
    )
    assert change.ledger_row.field_changed == "link_removed"
    assert change.ledger_row.trigger_cause == "user_undo"


def test_undo_reverse_supersedes_recloses_and_unreverses() -> None:
    """Undo of a reversal: item closes as superseded again, link un-reverses."""
    group = _group(
        11,
        _row(8, "status", "Closed:superseded", "Active", "reversal", link_id=2),
        _row(8, "link_reversed", "Confirmed", "Reversed", "reversal", link_id=2),
    )
    snapshot = _snap(
        [group],
        [_item(8)],
        [_link(2, 8, 1, "supersedes", reversed_at=FIXED_TIME)],
    )
    result = derive_undo(snapshot)
    assert result.source_action == "reverse-supersedes"
    assert result.target_label == "item 8"
    status_change = result.changes[0]
    assert (status_change.item_id, status_change.field) == (8, "status")
    assert (status_change.expected_value, status_change.new_value) == (
        "Active",
        "Closed:superseded",
    )
    link_change = result.changes[1]
    assert link_change.link_id == 2
    assert link_change.field == "reversed_at"
    assert link_change.expected_value == "Reversed"
    assert link_change.new_value is None
    assert link_change.ledger_row.field_changed == "link_unreversed"
    assert link_change.ledger_row.trigger_cause == "user_undo"


def test_redo_of_close_reapplies_closed_state() -> None:
    """Redo of an undo-of-close re-closes: the undo group's rows swap back."""
    original = _group(
        1, _row(3, "status", "Active", "Closed:expired", "user_closed")
    )
    undone = _group(
        2,
        _row(3, "status", "Closed:expired", "Active", "user_undo"),
        _undo_marker(1),
    )
    snapshot = _snap(
        [original, undone], [_item(3, status="Active")]
    )
    result = derive_redo(snapshot)
    assert result.direction == "redo"
    assert result.source_group_id == 2
    assert result.source_action == "close-item"
    assert result.target_label == "item 3"
    change = result.changes[0]
    assert (change.expected_value, change.new_value) == (
        "Active",
        "Closed:expired",
    )
    assert change.ledger_row.trigger_cause == "user_redo"
    assert result.marker.field_changed == "redo_of"
    assert result.marker.new_value == "2"


def test_redo_of_reverse_supersedes_re_reverses_link() -> None:
    """Redo of an undo-of-reversal appends `link_reversed` again (L2 §5.4)."""
    undone = _group(
        3,
        _row(8, "status", "Active", "Closed:superseded", "user_undo", link_id=2),
        _row(8, "link_unreversed", "Reversed", "Confirmed", "user_undo",
             link_id=2),
        _undo_marker(2),
    )
    original = _group(
        2,
        _row(8, "status", "Closed:superseded", "Active", "reversal", link_id=2),
        _row(8, "link_reversed", "Confirmed", "Reversed", "reversal", link_id=2),
    )
    snapshot = _snap(
        [original, undone],
        [_item(8, status="Closed", close_reason="superseded")],
        [_link(2, 8, 1, "supersedes", reversed_at=None)],
    )
    result = derive_redo(snapshot)
    assert result.source_action == "reverse-supersedes"
    status_change, link_change = result.changes
    assert (status_change.expected_value, status_change.new_value) == (
        "Closed:superseded",
        "Active",
    )
    assert link_change.field == "reversed_at"
    assert (link_change.expected_value, link_change.new_value) == (
        "Confirmed",
        "Reversed",
    )
    assert link_change.ledger_row.field_changed == "link_reversed"
    assert link_change.ledger_row.trigger_cause == "user_redo"


# --------------------------------------------------------------------------
# stack rules (spec 12.6 rules 1 and 2)
# --------------------------------------------------------------------------


def test_undo_twice_steps_back_in_order() -> None:
    """Undo, undo steps back through the newest first; undo-after-redo cycles."""
    first = _group(
        1, _row(4, "status", "Active", "Challenged", "user_set_status")
    )
    second = _group(
        2, _row(4, "status", "Challenged", "Active", "user_set_status")
    )
    latest = _snap([first, second], [_item(4, status="Active")])
    assert derive_undo(latest).source_group_id == 2
    undone_second = _group(
        3,
        _row(4, "status", "Challenged", "Active", "user_undo"),
        _undo_marker(2),
    )
    after_first_undo = _snap(
        [first, second, undone_second], [_item(4, status="Challenged")]
    )
    assert derive_undo(after_first_undo).source_group_id == 1
    # Redo the first undo, then undo again: group 2 is the target again.
    redone = _group(
        4,
        _row(4, "status", "Active", "Challenged", "user_redo"),
        _redo_marker(3),
    )
    after_redo = _snap(
        [first, second, undone_second, redone],
        [_item(4, status="Active")],
    )
    assert derive_undo(after_redo).source_group_id == 2


def test_redo_without_undo_raises_024() -> None:
    group = _group(
        1, _row(4, "status", "Active", "Challenged", "user_set_status")
    )
    with pytest.raises(NothingToRedo) as excinfo:
        derive_redo(_snap([group], [_item(4, status="Challenged")]))
    assert excinfo.value.code == "MAINTAIN-024"


def test_new_original_action_clears_redo_024() -> None:
    """No original action may be written after the redo target (spec 12.6)."""
    original = _group(
        1, _row(4, "status", "Active", "Challenged", "user_set_status")
    )
    undone = _group(
        2,
        _row(4, "status", "Challenged", "Active", "user_undo"),
        _undo_marker(1),
    )
    newer = _group(
        3, _row(5, "status", "Active", "Challenged", "user_set_status")
    )
    snapshot = _snap(
        [original, undone, newer],
        [_item(4, status="Active"), _item(5, status="Challenged")],
    )
    with pytest.raises(NothingToRedo) as excinfo:
        derive_redo(snapshot)
    assert excinfo.value.context["has_newer_original"] is True


# --------------------------------------------------------------------------
# refusal rule (spec 12.6 rule 4): 025 with group_id + item_id / link_id
# --------------------------------------------------------------------------


def test_refusal_status_mismatch_names_group_and_item_025() -> None:
    group = _group(
        1, _row(3, "status", "Active", "Closed:invalidated", "user_closed")
    )
    snapshot = _snap([group], [_item(3, status="Challenged")])
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    error = excinfo.value
    assert error.code == "MAINTAIN-025"
    assert error.context["group_id"] == 1
    assert error.context["item_id"] == 3


def test_refusal_validated_mismatch_names_item_025() -> None:
    group = _group(
        2, _row(6, "validated", "false", "true", "user_set_validated")
    )
    snapshot = _snap(
        [group], [_item(6, item_type="Assumption", validated="false")]
    )
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    assert excinfo.value.context == {"group_id": 2, "item_id": 6}


def test_refusal_edit_mismatch_names_item_025() -> None:
    group = _group(
        3, _row(7, "rationale", "old why", "new why", "user_edit_item")
    )
    snapshot = _snap([group], [_item(7, rationale="edited again")])
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    assert excinfo.value.context == {"group_id": 3, "item_id": 7}


def test_refusal_link_mismatch_names_link_025() -> None:
    group = _group(
        4,
        _row(4, "link_removed", "Confirmed", "Rejected", "user_remove_link",
             link_id=9),
    )
    snapshot = _snap(
        [group], [_item(4)], [_link(9, 4, 3, "depends_on", status="Confirmed")]
    )
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    assert excinfo.value.context == {"group_id": 4, "link_id": 9}


def test_refusal_reversal_mismatch_names_item_025() -> None:
    group = _group(
        5,
        _row(8, "status", "Closed:superseded", "Active", "reversal", link_id=2),
        _row(8, "link_reversed", "Confirmed", "Reversed", "reversal", link_id=2),
    )
    snapshot = _snap(
        [group],
        [_item(8, status="Challenged")],
        [_link(2, 8, 1, "supersedes", reversed_at=FIXED_TIME)],
    )
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    assert excinfo.value.context == {"group_id": 5, "item_id": 8}


def test_sweep_rearm_between_clear_and_undo_refuses_025() -> None:
    """Clear shielded the item, the sweep re-armed it, undo must refuse."""
    group = _group(
        6,
        _row(4, "status", "Challenged", "Active", "user_set_status"),
        _row(4, "status_origin", "derived", "manual", "user_set_status"),
    )
    snapshot = _snap(
        [group], [_item(4, status="Active", status_origin="derived")]
    )
    with pytest.raises(UndoRefused) as excinfo:
        derive_undo(snapshot)
    assert excinfo.value.context == {"group_id": 6, "item_id": 4}


def test_redo_refuses_when_state_changed_after_undo() -> None:
    original = _group(
        1, _row(3, "status", "Active", "Closed:expired", "user_closed")
    )
    undone = _group(
        2,
        _row(3, "status", "Closed:expired", "Active", "user_undo"),
        _undo_marker(1),
    )
    snapshot = _snap(
        [original, undone], [_item(3, status="Challenged")]
    )
    with pytest.raises(UndoRefused) as excinfo:
        derive_redo(snapshot)
    assert excinfo.value.context == {"group_id": 2, "item_id": 3}


# --------------------------------------------------------------------------
# fail-closed cases
# --------------------------------------------------------------------------


def test_unknown_row_shape_raises_027() -> None:
    group = _group(
        7, _row(2, "metadata", "x", "y", "user_edit_item")
    )
    with pytest.raises(GroupRecordInvalid) as excinfo:
        derive_undo(_snap([group], [_item(2)]))
    assert excinfo.value.code == "MAINTAIN-027"
    assert excinfo.value.context["group_id"] == 7


def test_pre013_rows_invisible_but_023_says_so() -> None:
    """Pre-013 rows carry no group id: invisible to the stack, named in 023."""
    with pytest.raises(NothingToUndo) as with_old_rows:
        derive_undo(_snap([], [_item(3, status="Challenged")], ungrouped=True))
    assert with_old_rows.value.code == "MAINTAIN-023"
    assert with_old_rows.value.context["ungrouped_rows_exist"] is True
    assert "no undo group" in with_old_rows.value.message
    with pytest.raises(NothingToUndo) as without_old_rows:
        derive_undo(_snap([], ungrouped=False))
    assert without_old_rows.value.context["ungrouped_rows_exist"] is False


# --------------------------------------------------------------------------
# the public status-value splitter (B1/B5)
# --------------------------------------------------------------------------


def test_split_status_value_round_trips_writer_encoding() -> None:
    closed = split_status_value("Closed:superseded")
    assert closed == StatusValue(status="Closed", close_reason="superseded")
    no_reason = split_status_value("Closed:None")
    assert no_reason == StatusValue(status="Closed", close_reason=None)
    bare = split_status_value("Closed")
    assert bare == StatusValue(status="Closed", close_reason=None)
    open_ = split_status_value("Active")
    assert open_ == StatusValue(status="Active", close_reason=None)

"""Phase-4 report formatter shared by the dry run and the real run."""

from __future__ import annotations

from ember.maintain.rows import (
    InverseChange,
    StatusChange,
    UndoResult,
    split_status_value,
)


def format_report(changes: list[StatusChange], total_items: int) -> list[str]:
    """Return the report lines: one per change, then the summary last.

    Line: `item <id>: <old_status> -> <new_status>` plus ` (<close_reason>)`
    when the change is a close. Ordered by item_id ascending.

    Summary: `closed: N, challenged: N, reopened: N, unchanged: N`.
    `reopened` counts changes moving to `Active` from a non-`Active` status;
    `unchanged` = total_items - the number of distinct items changed.
    """
    lines: list[str] = []
    for change in sorted(changes, key=lambda item: item.item_id):
        line = f"item {change.item_id}: {change.old_status} -> {change.new_status}"
        if change.new_status == "Closed" and change.close_reason is not None:
            line += f" ({change.close_reason})"
        lines.append(line)

    closed = sum(1 for change in changes if change.new_status == "Closed")
    challenged = sum(1 for change in changes if change.new_status == "Challenged")
    reopened = sum(
        1
        for change in changes
        if change.new_status == "Active" and change.old_status != "Active"
    )
    changed_items = len({change.item_id for change in changes})
    unchanged = total_items - changed_items
    lines.append(
        f"closed: {closed}, challenged: {challenged}, "
        f"reopened: {reopened}, unchanged: {unchanged}"
    )
    return lines


# --------------------------------------------------------------------------
# The `ember undo` / `ember redo` report line (undo step 04)
# --------------------------------------------------------------------------


def _undo_segment(change: InverseChange) -> str:
    """Render one inverse change with the `format_report` line shape.

    A status change renders as `item <id>: <old> -> <new>`, the close
    reason in brackets on the NEW side only (exactly `format_report`'s
    convention); a link change renders the link's own values
    (`link <id>: Rejected -> Confirmed`, the marker vocabulary for a
    reversal); every other item field follows the `edit-item` line shape.
    """
    if change.link_id is not None:
        return (
            f"link {change.link_id}: {change.ledger_row.old_value}"
            f" -> {change.ledger_row.new_value}"
        )
    if change.field == "status":
        old = split_status_value(change.expected_value or "").status
        new = split_status_value(change.new_value or "")
        line = f"item {change.item_id}: {old} -> {new.status}"
        if new.status == "Closed" and new.close_reason is not None:
            line += f" ({new.close_reason})"
        return line
    old = change.expected_value if change.expected_value is not None else "<null>"
    new = change.new_value if change.new_value is not None else "<null>"
    return f"item {change.item_id}: {change.field}: {old} -> {new}"


def format_undo_line(
    result: UndoResult, new_group_id: int | None, dry_run: bool
) -> str:
    """The one `ember undo` / `ember redo` report line (undo step 04).

    Shape (L2 §4 samples): first the group being undone or redone, its
    action and primary target — `undone group 7 as group 8 (close-item,
    item 3):` — then one segment per changed item or link, joined with
    `; `. `new_group_id` is None only for `--dry-run` (nothing was written,
    so no new group exists) and the line then ends in `(dry-run)`.
    """
    label = f"({result.source_action}, {result.target_label})"
    segments = "; ".join(_undo_segment(change) for change in result.changes)
    if dry_run:
        verb = "undo" if result.direction == "undo" else "redo"
        return (
            f"{verb} group {result.source_group_id} {label}:"
            f" {segments} (dry-run)"
        )
    verb = "undone" if result.direction == "undo" else "redone"
    return (
        f"{verb} group {result.source_group_id} as group {new_group_id}"
        f" {label}: {segments}"
    )

"""Phase-4 report formatter shared by the dry run and the real run."""

from __future__ import annotations

from ember.maintain.rows import StatusChange


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

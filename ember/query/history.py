"""The `change_log` classifier and the `history` derivation (pure Phase 2).

The ledger is read, never rewritten: `old_value` / `new_value` render verbatim
and the one derived field, `close_reason`, comes from the same splitter that
documents the writer's encoding, so the two cannot disagree.
"""

from __future__ import annotations

from ember.query.rows import ChangeRow, HistoryEvent, HistoryPage
from ember.relate.rows import Link

UNKNOWN_KIND = "unknown"

_KIND_BY_PAIR: dict[tuple[str, str], str] = {
    ("created", "user_confirmed"): "created",
    ("proposed", "rejected"): "proposed_rejected",
    ("validated", "user_set_validated"): "validated",
    ("link_confirmed", "user_confirmed"): "link_confirmed",
    ("link_rejected", "rejected"): "link_rejected",
    ("status", "supersedes_confirmed"): "status_changed",
    ("status", "answers_confirmed"): "status_changed",
    ("status", "dependency_closed"): "status_changed",
    ("status", "contradicts_confirmed"): "status_changed",
    ("status", "user_closed"): "status_changed",
    ("status", "user_set_status"): "status_changed",
    ("status", "reversal"): "status_changed",
    ("status_origin", "user_set_status"): "status_origin_changed",
    ("status_origin", "sweep_rearm"): "status_origin_changed",
    ("link_reversed", "reversal"): "link_reversed",
}


def classify_change_row(row: ChangeRow) -> str:
    """Return the row's `kind`, derived from the `(field, cause)` pair.

    Neither half works alone: `status` covers seven causes, and both
    `user_set_status` and `reversal` cover two different field types. A pair
    this build does not know is `unknown`, a future engine's row or a hand
    edit, and it still renders with its raw values.
    """
    return _KIND_BY_PAIR.get((row.field_changed, row.trigger_cause), UNKNOWN_KIND)


def _close_reason(new_value: str | None) -> str | None:
    """Return the reason from a `Closed` status value, else `None`.

    The writer encodes a status row as `<status>` or `<status>:<reason>`, and
    formats a null reason as the literal `None`, so `Closed:None` means no
    reason. Split on the **first** colon only.
    """
    if new_value is None:
        return None
    status, separator, reason = new_value.partition(":")
    if status != "Closed" or not separator or not reason or reason == "None":
        return None
    return reason


def _belongs_to(row: ChangeRow, item_id: int, links: dict[int, Link]) -> bool:
    """Return whether the row is about `item_id` by subject or by link."""
    if row.item_id == item_id:
        return True
    if row.link_id is None:
        return False
    link = links.get(row.link_id)
    if link is None:
        return False
    return item_id in (link.source_item_id, link.target_item_id)


def _to_event(row: ChangeRow, link: Link | None) -> HistoryEvent:
    """Build the rendered event for one row, filling the link's fields."""
    kind = classify_change_row(row)
    return HistoryEvent(
        timestamp=row.timestamp,
        kind=kind,
        cause=row.trigger_cause,
        field_changed=row.field_changed,
        item_id=row.item_id,
        link_id=row.link_id,
        link_source_item_id=link.source_item_id if link else None,
        link_target_item_id=link.target_item_id if link else None,
        link_type=link.link_type if link else None,
        old_value=row.old_value,
        new_value=row.new_value,
        close_reason=_close_reason(row.new_value)
        if kind == "status_changed"
        else None,
    )


def history(
    rows: list[ChangeRow],
    links: list[Link],
    item_id: int | None,
    page: HistoryPage = HistoryPage(),
) -> list[HistoryEvent]:
    """Return the ledger events for `item_id`, or the whole ledger.

    A row belongs to an item when its `item_id` is that item **or** its
    `link_id` names a link touching that item. A row matching both appears
    once. A row with no subject and no link belongs to no item and appears in
    the global view only. Order is `(timestamp, id)`, unchanged.

    The window composes strictly after that union and sort: `page.since`
    keeps rows with `timestamp >= since` as opaque ISO text (the exact
    comparison the sort already uses, the validator has normalised it to
    UTC), then `page.offset` skips, then `page.limit` caps. `None` on an
    axis means no cut, so the default page crops nothing and the no-page
    call behaves exactly as before. A stored timestamp that cannot parse
    renders everywhere today but is invisible to a `--since` view (a
    hand-edited row, recorded here, not hidden).
    """
    links_by_id = {int(link.id): link for link in links if link.id is not None}
    selected: list[tuple[ChangeRow, HistoryEvent]] = []
    for row in rows:
        if item_id is not None and not _belongs_to(row, item_id, links_by_id):
            continue
        selected.append((row, _to_event(row, links_by_id.get(row.link_id))))
    selected.sort(key=lambda pair: (pair[0].timestamp, pair[0].id))
    events = [event for _, event in selected]
    if page.since is not None:
        events = [event for event in events if event.timestamp >= page.since]
    if page.offset is not None:
        events = events[page.offset :]
    if page.limit is not None:
        events = events[: page.limit]
    return events

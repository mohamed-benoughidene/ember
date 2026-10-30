"""The `list_items` derivation: filter, then page (pure Phase 2).

No I/O, no DB, no printing. Every status is kept: `Closed` items are listed
on purpose, that is the point of the command (bridge plan L2 §5.3).
"""

from __future__ import annotations

from ember.query.rows import ListPage, QueryItem, TopicFilter


def list_items(
    items: list[QueryItem], filter: TopicFilter, page: ListPage
) -> tuple[int, list[QueryItem]]:
    """Return `(total, window)`: the filtered count before the page, then the page.

    `filter.status` / `filter.type` narrow the list (exact-case, the same
    value sets the gate validated). `page.offset` then skips and `page.limit`
    caps behind the id order the port gave, so `total` is always the full
    filtered count, never the cropped one, and `limit` 0 is an explicit empty
    window, never an error.
    """
    filtered = [
        item
        for item in items
        if (filter.status is None or item.status == filter.status)
        and (filter.type is None or item.type == filter.type)
    ]
    total = len(filtered)
    start = 0 if page.offset is None else page.offset
    window = filtered[start:]
    if page.limit is not None:
        window = window[: page.limit]
    return total, window

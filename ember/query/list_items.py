"""The `list_items` derivation: filter, then page (pure Phase 2).

No I/O, no DB, no printing. Every status is kept: `Closed` items are listed
on purpose, that is the point of the command (bridge plan L2 §5.3).
"""

from __future__ import annotations

from ember.query.rows import ListPage, QueryItem, TopicFilter


def list_items(
    items: list[QueryItem], filter_: TopicFilter, page: ListPage
) -> tuple[int, list[QueryItem]]:
    """Return `(total, window)`: the filtered count before the page, then the page.

    `filter_.status` / `filter_.type` narrow the list (exact-case, the same
    value sets the gate validated). `page.offset` then skips and `page.limit`
    caps behind the id order the port gave, so `total` is always the full
    filtered count, never the cropped one, and `limit` 0 is an explicit empty
    window, never an error.
    """
    filtered = [
        item
        for item in items
        if (filter_.status is None or item.status == filter_.status)
        and (filter_.type is None or item.type == filter_.type)
    ]
    total = len(filtered)
    start = 0 if page.offset is None else page.offset
    window = filtered[start:]
    if page.limit is not None:
        window = window[: page.limit]
    return total, window


def count_by_status(items: list[QueryItem]) -> dict[str, int]:
    """Return the four Home counts derived from one full item load.

    The counter reads the same port load `list_items` filters (`lookup.list_items()`,
    the `items` table), so each number agrees with the per-status `list-items`
    call's `total`: `active` / `challenged` / `closed` count that status, and
    `total` counts every loaded item, any status included (a status outside
    the three names adds to `total` only, exactly as it falls outside every
    per-status filter). No I/O, no DB: the load feeds the counters, the
    counters only count.
    """
    counts = {"active": 0, "challenged": 0, "closed": 0}
    for item in items:
        key = item.status.lower()
        if key in counts:
            counts[key] += 1
    counts["total"] = len(items)
    return counts

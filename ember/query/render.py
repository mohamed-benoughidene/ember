"""The display layer: pure formatters that return a JSON string.

`json.dumps` only — no click, no print. Sorting lives here, not in the core.
"""

from __future__ import annotations

import json

from ember.query.rows import CurrentStateRow, SearchHit, WhyResult


def render_current_state(rows: list[CurrentStateRow]) -> str:
    """Return the `current_state` envelope, `Challenged` items first.

    Order is `(Challenged first, then Active), item_id ascending`, computed
    from the row data so it never depends on the adapter's row order.
    """
    ordered = sorted(
        rows, key=lambda row: (0 if row.challenged else 1, row.id)
    )
    return json.dumps(
        {
            "mode": "current_state",
            "count": len(ordered),
            "items": [row.model_dump() for row in ordered],
        },
        ensure_ascii=False,
    )


def render_topic_search(hits: list[SearchHit], query: str) -> str:
    """Return the `topic_search` envelope in the score order the core gave."""
    return json.dumps(
        {
            "mode": "topic_search",
            "query": query,
            "count": len(hits),
            "results": [hit.model_dump() for hit in hits],
        },
        ensure_ascii=False,
    )


def render_why(result: WhyResult) -> str:
    """Return the `why` envelope in the `(depth, item_id)` order given."""
    return json.dumps(
        {
            "mode": "why",
            "item": result.item.model_dump(),
            "count": len(result.reasons),
            "reasons": [reason.model_dump() for reason in result.reasons],
        },
        ensure_ascii=False,
    )

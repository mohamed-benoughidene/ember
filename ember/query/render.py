"""The display layer: pure formatters that return a JSON string.

`json.dumps` only, with no click and no print. Sorting lives here, not in the
core.
"""

from __future__ import annotations

import json

from ember.query.rows import (
    CurrentStateRow,
    HistoryEvent,
    QueryItem,
    ShowItemResult,
    SearchHit,
    WhyResult,
)


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
            # The item keys are pinned to the pre-bridge set (byte-golden):
            # the read model grew `source` / `validated` additive fields for
            # the bridge reads, and `why`'s output must not change with it.
            "item": result.item.model_dump(
                include={
                    "id",
                    "type",
                    "statement",
                    "status",
                    "close_reason",
                    "status_origin",
                    "rationale",
                    "created_at",
                    "source_id",
                }
            ),
            "count": len(result.reasons),
            "reasons": [reason.model_dump() for reason in result.reasons],
        },
        ensure_ascii=False,
    )


def render_history(events: list[HistoryEvent], item_id: int | None) -> str:
    """Return the `history` envelope in the `(timestamp, id)` order given.

    `item_id` is `null` for the global view.
    """
    return json.dumps(
        {
            "mode": "history",
            "item_id": item_id,
            "count": len(events),
            "events": [event.model_dump() for event in events],
        },
        ensure_ascii=False,
    )


def render_list_items(total: int, items: list[QueryItem]) -> str:
    """Return the `list_items` envelope: every listed item in the id order given.

    Each item is the nine-field spec projection (bridge plan L2 §5.3): the
    read model's `status_origin` and `source_id` are internals a reader of
    this command never needs. `total` is the pre-page filtered count.
    """
    return json.dumps(
        {
            "total": total,
            "items": [
                {
                    "id": item.id,
                    "type": item.type,
                    "statement": item.statement,
                    "status": item.status,
                    "close_reason": item.close_reason,
                    "rationale": item.rationale,
                    "source": item.source,
                    "validated": item.validated,
                    "created_at": item.created_at,
                }
                for item in items
            ],
        },
        ensure_ascii=False,
    )


def render_show_item(result: ShowItemResult) -> str:
    """Return the `show_item` envelope in the order the core gave.

    The item is the full read-model row; `source` is the verbatim source
    text; the two link lists carry the far item's coordinates and the
    migration-011 `reversed_at` (`null` on a live link and on a v10 file).
    """
    return json.dumps(
        {
            "item": result.item.model_dump(),
            "source": result.source,
            "links_out": [link.model_dump() for link in result.links_out],
            "links_in": [link.model_dump() for link in result.links_in],
        },
        ensure_ascii=False,
    )

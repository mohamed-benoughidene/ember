"""`current_state` derivation: the pure core of Phase 2.

No I/O, no clock, no DB, no printing. It returns items in the order the port
gave them — the `Challenged`-first ordering is the display layer's job (L1).
"""

from __future__ import annotations

from ember.query.rows import CurrentStateRow, QueryItem

LIVE_STATUSES = ("Active", "Challenged")


def current_state(items: list[QueryItem]) -> list[CurrentStateRow]:
    """Keep the `Active` and `Challenged` items, drop `Closed`."""
    return [
        CurrentStateRow(
            id=item.id,
            type=item.type,
            statement=item.statement,
            status=item.status,
            created_at=item.created_at,
            source_id=item.source_id,
            status_origin=item.status_origin,
            challenged=item.status == "Challenged",
        )
        for item in items
        if item.status in LIVE_STATUSES
    ]

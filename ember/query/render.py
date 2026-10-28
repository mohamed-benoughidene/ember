"""The display layer: pure formatters that return a JSON string.

`json.dumps` only — no click, no print. Sorting lives here, not in the core.
"""

from __future__ import annotations

import json

from ember.query.rows import CurrentStateRow


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

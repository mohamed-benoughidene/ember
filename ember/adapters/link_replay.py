"""Reversal replay: rebuild `links.reversed_at` from the ledger (hardening 02).

L2 §6 D3 replay contract: `links.reversed_at` is a labelled, rebuildable copy.
The source of truth stays the reversal marker rows in `change_log` (master
plan rule 7). The reader rule (undo step 03, engine-undo-plan §5.4): a link
is reversed when its highest-id marker among `link_reversed` and
`link_unreversed` is a `link_reversed` — so an undo of a reversal (a later
`link_unreversed` row) reads the link live again, and a redo of that undo
(a still-later `link_reversed` row) reads it reversed again. This module is
pure logic in adapters (T9/B3): rows in, dict out, no clock, no I/O, and no
engine core may import it.
"""

from __future__ import annotations

from ember.query.rows import ChangeRow

REVERSED_FIELD = "link_reversed"
UNREVERSED_FIELD = "link_unreversed"

REVERSAL_FIELDS = (REVERSED_FIELD, UNREVERSED_FIELD)


def replay_reversals(entries: list[ChangeRow]) -> dict[int, str | None]:
    """Rebuild the `reversed_at` mapping from ledger rows.

    Return one entry per link id seen in `entries`: the `timestamp` of the
    highest-id `link_reversed` row for that link when that row is the
    link's latest reversal marker (a higher id is a later append, so append
    order breaks any clock tie), or `None` when the link has no reversal
    marker or its latest marker is `link_unreversed` (the undo of a
    reversal, undo step 03). Rows with no `link_id` are skipped.
    Deterministic and pure: no clock, no I/O.
    """
    seen: set[int] = set()
    markers: dict[int, ChangeRow] = {}
    for entry in entries:
        if entry.link_id is None:
            continue
        seen.add(entry.link_id)
        if entry.field_changed not in REVERSAL_FIELDS:
            continue
        best = markers.get(entry.link_id)
        if best is None or entry.id > best.id:
            markers[entry.link_id] = entry
    result: dict[int, str | None] = {}
    for link_id in seen:
        marker = markers.get(link_id)
        if marker is None or marker.field_changed == UNREVERSED_FIELD:
            result[link_id] = None
        else:
            result[link_id] = marker.timestamp
    return result

"""Reversal replay: rebuild `links.reversed_at` from the ledger (hardening 02).

L2 §6 D3 replay contract: `links.reversed_at` is a labelled, rebuildable copy.
The source of truth stays the `change_log` rows with
`field_changed = 'link_reversed'` (master plan rule 7). This module is pure
logic in adapters (T9/B3): rows in, dict out, no clock, no I/O, and no engine
core may import it.
"""

from __future__ import annotations

from ember.query.rows import ChangeRow

REVERSED_FIELD = "link_reversed"


def replay_reversals(entries: list[ChangeRow]) -> dict[int, str | None]:
    """Rebuild the `reversed_at` mapping from ledger rows.

    Return one entry per link id seen in `entries`: the `timestamp` of the
    highest-id `link_reversed` row for that link (a higher id is a later
    append, so append order breaks any clock tie), or `None` when the link has
    no reversal marker. Rows with no `link_id` are skipped. Deterministic and
    pure: no clock, no I/O.
    """
    seen: set[int] = set()
    markers: dict[int, ChangeRow] = {}
    for entry in entries:
        if entry.link_id is None:
            continue
        seen.add(entry.link_id)
        if entry.field_changed != REVERSED_FIELD:
            continue
        best = markers.get(entry.link_id)
        if best is None or entry.id > best.id:
            markers[entry.link_id] = entry
    result: dict[int, str | None] = {}
    for link_id in seen:
        marker = markers.get(link_id)
        result[link_id] = marker.timestamp if marker is not None else None
    return result

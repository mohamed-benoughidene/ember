"""Maintain Phase-1 load helper and the by-id item index.

Step 02 adds `MaintainPorts` / `MaintainRequest` / `MaintainResult` and the
`run_sweep` entry point here (it owns the store port). Step 03 adds the three
validators and their human entry points. This module only owns the read step.
"""

from __future__ import annotations

from ember.maintain.maintain_lookup import MaintainLookupPort
from ember.maintain.rows import ItemState, MaintainSnapshot


def _load(ports: MaintainLookupPort) -> MaintainSnapshot:
    """Read the whole world the Phase-2 derivation needs (Phase 1).

    Raises `MAINTAIN-010 ItemsReadFailed` when any of the three port reads
    fails. The engine core trusts what the port returns (I9).
    """
    return MaintainSnapshot(
        items=ports.list_items(),
        links=ports.list_confirmed_links(),
        reversed_link_ids=ports.list_reversed_link_ids(),
    )


def index_items(snapshot: MaintainSnapshot) -> dict[int, ItemState]:
    """Return the snapshot's items keyed by id (I4: a named dict, not a tuple).

    The validators and `merge_and_filter` use this to find one item by id, so
    no extra port method is needed.
    """
    return {item.id: item for item in snapshot.items}

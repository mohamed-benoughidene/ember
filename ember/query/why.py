"""The `why` traversal: walk the reasons behind one item (pure Phase 2).

`depends_on` points from the item to its premise, `supports` points from the
evidence to the item, so the two link types are followed in opposite
directions. Only `Confirmed` links count.
"""

from __future__ import annotations

from collections import deque

from ember.query.rows import QueryItem, WhyReason, WhyResult
from ember.relate.rows import Link

_REASON_EDGES = {"depends_on", "supports"}


def _reason_edges(links: list[Link]) -> dict[int, list[tuple[int, str, int]]]:
    """Map an item id to its `(reason_id, link_type, link_id)` edges.

    Only `Confirmed` links of a reason type produce an edge. Edges are sorted
    by `(reason_id, link_id)` so a walk with two routes to one node is
    deterministic.
    """
    edges: dict[int, list[tuple[int, str, int]]] = {}
    for link in links:
        if link.status != "Confirmed" or link.link_type not in _REASON_EDGES:
            continue
        if link.link_type == "depends_on":
            start, reason = link.source_item_id, link.target_item_id
        else:
            start, reason = link.target_item_id, link.source_item_id
        edges.setdefault(start, []).append(
            (reason, link.link_type, int(link.id))
        )
    for node_edges in edges.values():
        node_edges.sort(key=lambda edge: (edge[0], edge[2]))
    return edges


def why(items: list[QueryItem], links: list[Link], item_id: int) -> WhyResult:
    """Return the start item plus every reason reachable from it.

    The walk is the transitive closure of the two edge rules: no depth limit,
    and a visited set makes it terminate on a `depends_on` cycle. Each reason
    carries its `depth` (1 for a direct reason). The start item is not one of
    the reasons, it travels as `WhyResult.item`.

    The gatekeeper guarantees `item_id` exists, so a missing id here is an
    internal error, not a user error (I9).
    """
    by_id = {item.id: item for item in items}
    edges = _reason_edges(links)
    visited = {item_id}
    queue: deque[tuple[int, int]] = deque([(item_id, 0)])
    reasons: list[WhyReason] = []

    while queue:
        node_id, depth = queue.popleft()
        for reason_id, link_type, link_id in edges.get(node_id, []):
            if reason_id in visited:
                continue
            visited.add(reason_id)
            reason_item = by_id[reason_id]
            reasons.append(
                WhyReason(
                    item_id=reason_item.id,
                    type=reason_item.type,
                    statement=reason_item.statement,
                    status=reason_item.status,
                    rationale=reason_item.rationale,
                    depth=depth + 1,
                    via_link_type=link_type,
                    via_link_id=link_id,
                )
            )
            queue.append((reason_id, depth + 1))

    reasons.sort(key=lambda reason: (reason.depth, reason.item_id))
    return WhyResult(item=by_id[item_id], reasons=reasons)

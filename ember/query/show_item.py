"""The `show_item` derivation: one item, its source text, all its links (pure).

No I/O, no DB, no printing. Both directions are returned and every link
status is kept: a Rejected or reversed link is exactly what a reader of this
command needs to see (bridge plan L2 §5.3).
"""

from __future__ import annotations

from ember.query.errors import QueryItemNotFound, QueryLinkEndGone
from ember.query.rows import QueryItem, ShowItemResult, ShowLink
from ember.relate.rows import Link


def show_item(
    item_id: int,
    items: list[QueryItem],
    links: list[Link],
    source_text: str,
) -> ShowItemResult:
    """Return the item, its source text and its links, `links_out` then `links_in`.

    `links_out` holds the links whose source is the item, `links_in` the
    links whose target is it; each entry names the item at the other end.
    The gatekeeper validates the id, and the reads share one snapshot, so a
    missing start id would mean a race the gatekeeper read behind (it
    answers QUERY-001, the user-named id, like the gate). A link whose
    OTHER end is gone is a dangling row, not a user error: one named house
    code (`QUERY-010`), never a raw `KeyError` (finding 4.7 #2). Link order
    follows the id order the port gave.
    """
    by_id = {item.id: item for item in items}
    item = by_id.get(item_id)
    if item is None:
        raise QueryItemNotFound("item not found", item_id=item_id)

    def one_link(link: Link) -> ShowLink:
        other_id = (
            link.target_item_id
            if link.source_item_id == item_id
            else link.source_item_id
        )
        other = by_id.get(other_id)
        if other is None:
            raise QueryLinkEndGone(
                "link's other end is gone",
                link_id=int(link.id) if link.id is not None else None,
                item_id=other_id,
            )
        return ShowLink(
            id=int(link.id),
            type=link.link_type,
            status=link.status,
            other_item_id=other.id,
            other_item_type=other.type,
            other_item_statement=other.statement,
            other_item_status=other.status,
            reversed_at=link.reversed_at,
        )

    links_out = [
        one_link(link) for link in links if link.source_item_id == item_id
    ]
    links_in = [
        one_link(link) for link in links if link.target_item_id == item_id
    ]
    return ShowItemResult(
        item=item, source=source_text, links_out=links_out, links_in=links_in
    )

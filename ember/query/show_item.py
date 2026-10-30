"""The `show_item` derivation: one item, its source text, all its links (pure).

No I/O, no DB, no printing. Both directions are returned and every link
status is kept: a Rejected or reversed link is exactly what a reader of this
command needs to see (bridge plan L2 §5.3).
"""

from __future__ import annotations

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
    The gatekeeper guarantees `item_id` exists, so a missing id here is an
    internal error, not a user error (I9). Link order follows the id order
    the port gave.
    """
    by_id = {item.id: item for item in items}
    item = by_id[item_id]

    def one_link(link: Link) -> ShowLink:
        other_id = (
            link.target_item_id
            if link.source_item_id == item_id
            else link.source_item_id
        )
        other = by_id[other_id]
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

"""The read gate: what a query command accepts before the core sees it.

Two rules, one owner each (I9): the core assumes valid input and never
re-raises these.
"""

from __future__ import annotations

from ember.query.errors import QueryItemNotFound, QueryTextEmpty
from ember.query.lookup import QueryLookupPort
from ember.query.tokenize import tokenize


def validate_query_text(text: str) -> str:
    """Return the normalised text, or raise `QUERY-002` if it has no tokens.

    The error carries the text's *length*, never the text itself: user text can
    hold a newline (which would break the one-line log format) or a pasted
    secret.
    """
    normalised = text.strip()
    if not tokenize(normalised):
        raise QueryTextEmpty("query text empty", query_length=len(text))
    return normalised


def validate_query_item(lookup: QueryLookupPort, item_id: int) -> None:
    """Raise `QUERY-001` when `item_id` is not in `items`, else return."""
    if not lookup.item_exists(item_id):
        raise QueryItemNotFound("item not found", item_id=item_id)

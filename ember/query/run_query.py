"""One function per query entry point: validate, load, derive, render.

No mode argument and no boolean flag: the mode is the entry point (I2).
"""

from __future__ import annotations

from ember.query.current_state import current_state
from ember.query.history import history
from ember.query.lookup import QueryLookupPort
from ember.query.query_gatekeeper import validate_query_item, validate_query_text
from ember.query.render import (
    render_current_state,
    render_history,
    render_topic_search,
    render_why,
)
from ember.query.topic_search import topic_search
from ember.query.why import why


def run_current_state(lookup: QueryLookupPort) -> str:
    """Load every item, derive the live view, render the JSON document."""
    return render_current_state(current_state(lookup.list_items()))


def run_topic_search(lookup: QueryLookupPort, query: str) -> str:
    """Gate the query text, load every item, rank, render the JSON document."""
    normalised = validate_query_text(query)
    return render_topic_search(topic_search(lookup.list_items(), normalised), normalised)


def run_why(lookup: QueryLookupPort, item_id: int) -> str:
    """Gate the item id, load items and links, walk, render the JSON document."""
    validate_query_item(lookup, item_id)
    return render_why(why(lookup.list_items(), lookup.list_links(), item_id))


def run_history(lookup: QueryLookupPort, item_id: int | None) -> str:
    """Show one item's ledger events, or the whole ledger when id is `None`.

    The item check runs **only** when the user named an item: the global view
    makes no existence lookup and can never raise QUERY-001.
    """
    if item_id is not None:
        validate_query_item(lookup, item_id)
    events = history(lookup.list_change_log(), lookup.list_links(), item_id)
    return render_history(events, item_id)

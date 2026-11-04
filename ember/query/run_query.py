"""One function per query entry point: validate, load, derive, render.

No mode argument and no boolean flag: the mode is the entry point (I2).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ember.query.current_state import current_state
from ember.query.history import history
from ember.query.list_items import list_items
from ember.query.lookup import QueryLookupPort
from ember.query.query_gatekeeper import (
    validate_history_page,
    validate_list_page,
    validate_query_item,
    validate_query_text,
    validate_topic_filter,
)
from ember.query.render import (
    render_current_state,
    render_history,
    render_list_items,
    render_show_item,
    render_topic_search,
    render_why,
)
from ember.query.rows import HistoryPage, ListPage, TopicFilter
from ember.query.show_item import show_item
from ember.query.topic_search import topic_search
from ember.query.why import why


@contextmanager
def _one_read(lookup: QueryLookupPort) -> Iterator[None]:
    """Load inside one read transaction when the adapter offers one.

    `SqliteQueryContext.read_transaction` holds SQLite's one-instance
    snapshot across the joins (finding 4.7 #2). The in-memory test fakes
    have no transaction to offer, so they pass through untouched.
    """
    open_read = getattr(lookup, "read_transaction", None)
    if open_read is None:
        yield
    else:
        with open_read():
            yield


def run_current_state(lookup: QueryLookupPort) -> str:
    """Load every item, derive the live view, render the JSON document."""
    return render_current_state(current_state(lookup.list_items()))


def run_topic_search(
    lookup: QueryLookupPort,
    query: str,
    topic_filter: TopicFilter = TopicFilter(),
) -> str:
    """Gate the text and the filter, load every item, rank, render.

    The pipeline order is validate text (QUERY-002) then validate the filter
    (QUERY-006), both before any load, then load, derive, render. The core
    returns the pre-page match count beside the window, so the envelope's
    `total` names every match the page was cut from.
    """
    normalised = validate_query_text(query)
    validate_topic_filter(topic_filter)
    total, hits = topic_search(
        lookup.list_items(), normalised, topic_filter
    )
    return render_topic_search(hits, normalised, total)


def run_why(lookup: QueryLookupPort, item_id: int) -> str:
    """Gate the item id, load, walk, render the JSON document.

    The gate (QUERY-001) runs before any load, then items and links load in
    one read transaction (finding 4.7 #2), then derive, render.
    """
    validate_query_item(lookup, item_id)
    with _one_read(lookup):
        items = lookup.list_items()
        links = lookup.list_links()
    return render_why(why(items, links, item_id))


def run_history(
    lookup: QueryLookupPort,
    item_id: int | None,
    page: HistoryPage = HistoryPage(),
) -> str:
    """Show one item's ledger events, or the whole ledger when id is `None`.

    The pipeline order is validate the page (QUERY-006 / QUERY-007) before
    any load, then the item check **only** when the user named an item (the
    global view makes no existence lookup and can never raise QUERY-001),
    then load, derive (window inside), render.
    """
    page = validate_history_page(page)
    if item_id is not None:
        validate_query_item(lookup, item_id)
    events = history(lookup.list_change_log(item_id, page), lookup.list_links(), item_id, page)
    return render_history(events, item_id)


def run_list_items(
    lookup: QueryLookupPort,
    filter_: TopicFilter = TopicFilter(),
    page: ListPage = ListPage(),
) -> str:
    """List every item in any status, as JSON.

    Bridge step 02. The pipeline order is validate the filter (QUERY-006)
    and the page (QUERY-006), both before any load, then load, derive
    (filter then page inside), render.
    """
    validate_topic_filter(filter_)
    page = validate_list_page(page)
    total, window = list_items(lookup.list_items(), filter_, page)
    return render_list_items(total, window)


def run_show_item(lookup: QueryLookupPort, item_id: int) -> str:
    """Show one item, its verbatim source text and all its links, as JSON.

    Bridge step 02. The pipeline order is gate the item id (QUERY-001)
    before any load, then items, links and source in ONE read transaction
    (finding 4.7 #2), then derive (both link directions inside; a dangling
    other end answers QUERY-010), render.
    """
    validate_query_item(lookup, item_id)
    with _one_read(lookup):
        items = lookup.list_items()
        links = lookup.list_links()
        source_text = lookup.source_text_for(item_id)
    return render_show_item(show_item(item_id, items, links, source_text))

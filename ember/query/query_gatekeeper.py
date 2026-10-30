"""The read gate: what a query command accepts before the core sees it.

Two rules, one owner each (I9): the core assumes valid input and never
re-raises these.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ember.query.errors import (
    QueryFilterInvalid,
    QueryItemNotFound,
    QuerySinceInvalid,
    QueryTextEmpty,
)
from ember.query.lookup import QueryLookupPort
from ember.query.rows import HistoryPage, ListPage, TopicFilter
from ember.query.tokenize import tokenize

ACCEPTED_STATUSES = {"Active", "Challenged", "Closed"}
ACCEPTED_TYPES = {"Decision", "Assumption", "Finding", "Question"}


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


def _require_non_negative(value: int | None, field: str) -> None:
    """Raise `QUERY-006` with `field` when `value` is a negative integer.

    The one shared raising point for every non-negative filter check, so
    `QUERY-006` has a single site any later page validator can also call.
    """
    if value is not None and value < 0:
        raise QueryFilterInvalid(f"{field} must not be negative", field=field)


def validate_topic_filter(topic_filter: TopicFilter) -> None:
    """Raise `QUERY-006` when a `TopicFilter` value is illegal, else return.

    `status` and `type` must be exact-case members of the stored value sets,
    `limit` must not be negative. Returns `None` on valid input (the caller
    keeps the filter object it already holds).
    """
    if (
        topic_filter.status is not None
        and topic_filter.status not in ACCEPTED_STATUSES
    ):
        raise QueryFilterInvalid(
            "status is not a stored item status", field="status"
        )
    if topic_filter.type is not None and topic_filter.type not in ACCEPTED_TYPES:
        raise QueryFilterInvalid("type is not a stored item type", field="type")
    _require_non_negative(topic_filter.limit, "limit")


def validate_history_page(page: HistoryPage) -> HistoryPage:
    """Return the page with `since` normalised, or raise `QUERY-006` / `QUERY-007`.

    `limit` and `offset` go through the ONE shared non-negative helper, so
    `QUERY-006` keeps its single raising site. `since` follows the fixed
    order: parse with `datetime.fromisoformat`, reject a naive parse (no
    offset) before any `astimezone` call (on naive input `astimezone` would
    silently assume the local machine clock, which is non-deterministic),
    else replace `since` with `astimezone(timezone.utc).isoformat()` so the
    core compares the same ISO shape the ledger stores. The error carries
    `since_length`, never the raw text (a newline would break the one-line
    log, and user text can hold a secret).
    """
    _require_non_negative(page.limit, "limit")
    _require_non_negative(page.offset, "offset")
    if page.since is None:
        return page
    try:
        parsed = datetime.fromisoformat(page.since)
    except ValueError:
        raise QuerySinceInvalid(
            "since is not an ISO-8601 datetime", since_length=len(page.since)
        ) from None
    if parsed.tzinfo is None:
        raise QuerySinceInvalid(
            "since names no UTC offset", since_length=len(page.since)
        )
    return page.model_copy(
        update={"since": parsed.astimezone(timezone.utc).isoformat()}
    )


def validate_query_item(lookup: QueryLookupPort, item_id: int) -> None:
    """Raise `QUERY-001` when `item_id` is not in `items`, else return."""
    if not lookup.item_exists(item_id):
        raise QueryItemNotFound("item not found", item_id=item_id)


def validate_list_page(page: ListPage) -> ListPage:
    """Raise `QUERY-006` when a `ListPage` value is negative, else return.

    Bridge step 02: `list-items` pages exactly like `history`, so `limit`
    and `offset` go through the ONE shared non-negative helper (`_require_non_negative`),
    keeping `QUERY-006` single ownership of that rule (I9).
    """
    _require_non_negative(page.limit, "limit")
    _require_non_negative(page.offset, "offset")
    return page

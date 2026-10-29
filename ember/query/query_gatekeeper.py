"""The read gate: what a query command accepts before the core sees it.

Two rules, one owner each (I9): the core assumes valid input and never
re-raises these.
"""

from __future__ import annotations

from ember.query.errors import QueryFilterInvalid, QueryItemNotFound, QueryTextEmpty
from ember.query.lookup import QueryLookupPort
from ember.query.rows import TopicFilter
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


def validate_query_item(lookup: QueryLookupPort, item_id: int) -> None:
    """Raise `QUERY-001` when `item_id` is not in `items`, else return."""
    if not lookup.item_exists(item_id):
        raise QueryItemNotFound("item not found", item_id=item_id)

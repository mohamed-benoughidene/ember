"""Query engine errors. Codes are stable and never reused (I17)."""

from __future__ import annotations

from ember.errors import EmberError


class QueryError(EmberError):
    """Base error for every Engine D failure. Never raised directly."""

    code = "QUERY-000"
    name = "QueryError"


class QueryItemNotFound(QueryError):
    """The `--item` id the user named is not in `items`."""

    code = "QUERY-001"
    name = "QueryItemNotFound"


class QueryTextEmpty(QueryError):
    """The `--query` text has no tokens at all."""

    code = "QUERY-002"
    name = "QueryTextEmpty"


class DbOpenFailed(QueryError):
    """The database could not be read: missing, not SQLite, no version, journal."""

    code = "QUERY-003"
    name = "DbOpenFailed"


class SchemaOutdated(QueryError):
    """The applied schema version is below the required 10."""

    code = "QUERY-004"
    name = "SchemaOutdated"


class ItemsReadFailed(QueryError):
    """A read of `items`, `links` or `change_log` failed."""

    code = "QUERY-005"
    name = "ItemsReadFailed"


class QueryFilterInvalid(QueryError):
    """A filter value is outside its legal set, or a limit is negative."""

    code = "QUERY-006"
    name = "QueryFilterInvalid"


class QuerySinceInvalid(QueryError):
    """A `--since` value does not parse as an ISO-8601 datetime with an offset."""

    code = "QUERY-007"
    name = "QuerySinceInvalid"


class DbBusy(QueryError):
    """The database is locked by another process; it is healthy, just busy."""

    code = "QUERY-008"
    name = "DbBusy"


class DbRecoveryNeeded(QueryError):
    """The database file exists but cannot be read; it likely needs recovery."""

    code = "QUERY-009"
    name = "DbRecoveryNeeded"


class QueryLinkEndGone(QueryError):
    """A link names an item at its other end that `items` no longer holds.

    A dangling other end (finding 4.7 #2): a hand edit or a damaged file
    can delete the item row while the link row survives, and no foreign
    key sits between them. Neither reading half of the link nor pretending
    the item exists is honest, so the read answers with this code instead
    of crashing.
    """

    code = "QUERY-010"
    name = "QueryLinkEndGone"

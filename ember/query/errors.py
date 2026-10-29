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

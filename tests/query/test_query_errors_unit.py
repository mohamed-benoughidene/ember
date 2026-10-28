"""Unit tests for the stable error codes (I17 / I21)."""

from __future__ import annotations

import pytest

from ember.errors import EmberError
from ember.query.errors import (
    DbOpenFailed,
    ItemsReadFailed,
    QueryError,
    QueryItemNotFound,
    QueryTextEmpty,
    SchemaOutdated,
)

CODE_CASES = [
    (QueryError, "QUERY-000", "QueryError"),
    (QueryItemNotFound, "QUERY-001", "QueryItemNotFound"),
    (QueryTextEmpty, "QUERY-002", "QueryTextEmpty"),
    (DbOpenFailed, "QUERY-003", "DbOpenFailed"),
    (SchemaOutdated, "QUERY-004", "SchemaOutdated"),
    (ItemsReadFailed, "QUERY-005", "ItemsReadFailed"),
]


@pytest.mark.parametrize(("error_class", "code", "name"), CODE_CASES)
def test_code_and_name_are_stable(error_class, code: str, name: str) -> None:
    assert error_class.code == code
    assert error_class.name == name


@pytest.mark.parametrize(("error_class", "code", "name"), CODE_CASES)
def test_every_error_subclasses_query_error(error_class, code: str, name: str) -> None:
    assert issubclass(error_class, QueryError)
    assert issubclass(error_class, EmberError)


@pytest.mark.parametrize(("error_class", "code", "name"), CODE_CASES)
def test_no_subclass_defines_its_own_init(error_class, code: str, name: str) -> None:
    assert "__init__" not in error_class.__dict__

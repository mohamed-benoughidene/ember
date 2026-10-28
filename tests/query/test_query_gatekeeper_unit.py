"""Unit tests for the query gatekeeper (QUERY-001 / QUERY-002)."""

from __future__ import annotations

import pytest

from ember.query.errors import QueryItemNotFound, QueryTextEmpty
from ember.query.query_gatekeeper import validate_query_item, validate_query_text
from tests.query.fakes import FakeQueryLookup, make_item


@pytest.mark.parametrize("text", ["", "   ", "!!!", "???"])
def test_token_free_text_raises_002(text: str) -> None:
    with pytest.raises(QueryTextEmpty) as exc:
        validate_query_text(text)

    assert exc.value.code == "QUERY-002"


def test_002_carries_the_length_not_the_text() -> None:
    with pytest.raises(QueryTextEmpty) as exc:
        validate_query_text("!!!")

    assert exc.value.context["query_length"] == 3
    assert "!!!" not in str(exc.value.message)


def test_text_with_tokens_passes_and_is_stripped() -> None:
    assert validate_query_text("  sqlite  ") == "sqlite"


def test_text_check_makes_no_lookup_call() -> None:
    lookup = FakeQueryLookup()

    validate_query_text("sqlite")

    assert lookup.calls == []


def test_missing_item_raises_001_with_the_item_id() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    with pytest.raises(QueryItemNotFound) as exc:
        validate_query_item(lookup, 99)

    assert exc.value.code == "QUERY-001"
    assert exc.value.context["item_id"] == 99


def test_existing_item_passes_with_one_lookup_call() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    validate_query_item(lookup, 1)

    assert lookup.calls == ["item_exists:1"]

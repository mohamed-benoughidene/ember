"""Unit tests for the orchestration of the search and why entry points."""

from __future__ import annotations

import pytest

from ember.query.errors import QueryItemNotFound, QueryTextEmpty
from ember.query.run_query import run_topic_search, run_why
from tests.query.fakes import FakeQueryLookup, make_item


def test_run_topic_search_gates_the_text_before_any_read() -> None:
    lookup = FakeQueryLookup([make_item(1, statement="alpha")])

    with pytest.raises(QueryTextEmpty):
        run_topic_search(lookup, "!!!")

    assert lookup.calls == []


def test_run_topic_search_reaches_the_core_through_the_port() -> None:
    lookup = FakeQueryLookup([make_item(1, statement="alpha")])

    output = run_topic_search(lookup, "alpha")

    assert lookup.calls == ["list_items"]
    assert '"count": 1' in output


def test_run_why_gates_the_item_before_any_read() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    with pytest.raises(QueryItemNotFound):
        run_why(lookup, 99)

    assert lookup.calls == ["item_exists:99"]


def test_run_why_reaches_the_core_through_the_port() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    output = run_why(lookup, 1)

    assert lookup.calls == ["item_exists:1", "list_items", "list_links"]
    assert '"mode": "why"' in output

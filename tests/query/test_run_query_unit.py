"""Unit tests for the orchestration of the search and why entry points."""

from __future__ import annotations

import json

import pytest

from ember.query.errors import QueryItemNotFound, QueryTextEmpty
from ember.query.run_query import run_history, run_topic_search, run_why
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


def test_run_history_global_view_makes_no_item_lookup() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    run_history(lookup, None)

    assert lookup.calls == ["list_change_log", "list_links"]


def test_run_history_item_view_gates_the_item_first() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    run_history(lookup, 1)

    assert lookup.calls == ["item_exists:1", "list_change_log", "list_links"]


def test_run_history_global_view_never_raises_001_for_an_unknown_id() -> None:
    lookup = FakeQueryLookup([make_item(1)])

    output = run_history(lookup, None)

    assert json.loads(output)["item_id"] is None

"""Unit tests for the bridge read cores: `list_items` and `show_item`.

Bridge step 02. Everything here runs on the in-memory stand-ins in
`tests/query/fakes.py`; the real-database behaviour is covered by
`test_list_show_cli.py`.
"""

from __future__ import annotations

import json

import pytest

from ember.query.errors import QueryFilterInvalid, QueryItemNotFound
from ember.query.list_items import list_items
from ember.query.query_gatekeeper import validate_list_page
from ember.query.rows import ListPage, TopicFilter
from ember.query.run_query import run_list_items, run_show_item
from ember.query.show_item import show_item
from tests.query.fakes import FakeQueryLookup, make_item, make_link


def _items() -> list:
    """Items 1-4: Active, Challenged, Closed (expired), Active Finding."""
    return [
        make_item(1),
        make_item(2, status="Challenged"),
        make_item(3, status="Closed", close_reason="expired"),
        make_item(4, item_type="Finding", statement="Observed timeouts"),
    ]


def test_list_items_keeps_every_status_closed_included() -> None:
    total, window = list_items(_items(), TopicFilter(), ListPage())

    assert total == 4
    assert [item.id for item in window] == [1, 2, 3, 4]
    assert window[2].status == "Closed"
    assert window[2].close_reason == "expired"


def test_list_items_filter_narrows_before_the_count() -> None:
    total, window = list_items(
        _items(), TopicFilter(status="Closed"), ListPage()
    )

    assert total == 1
    assert [item.id for item in window] == [3]

    total, window = list_items(
        _items(), TopicFilter(status="Active", type="Finding"), ListPage()
    )

    assert total == 1
    assert [item.id for item in window] == [4]


def test_list_items_total_is_pre_page_and_window_composes() -> None:
    # Four match; --offset 1 skips the first, --limit 2 caps the window.
    total, window = list_items(
        _items(), TopicFilter(), ListPage(limit=2, offset=1)
    )

    assert total == 4
    assert [item.id for item in window] == [2, 3]

    # `limit` 0 is an explicit empty window, never an error.
    total, window = list_items(
        _items(), TopicFilter(), ListPage(limit=0)
    )

    assert total == 4
    assert window == []

    # No page at all: no cap, no skip (like `history`).
    total, window = list_items(
        _items(), TopicFilter(), ListPage()
    )

    assert total == 4
    assert len(window) == 4


def test_validate_list_page_negative_values_raise_006_with_field() -> None:
    with pytest.raises(QueryFilterInvalid) as limit_error:
        validate_list_page(ListPage(limit=-1))

    assert limit_error.value.code == "QUERY-006"
    assert limit_error.value.context["field"] == "limit"

    with pytest.raises(QueryFilterInvalid) as offset_error:
        validate_list_page(ListPage(offset=-3))

    assert offset_error.value.code == "QUERY-006"
    assert offset_error.value.context["field"] == "offset"

    # Zero and omitted are legal.
    assert validate_list_page(ListPage(limit=0, offset=None)) is not None


def test_run_list_items_rejects_a_bad_status_before_any_load() -> None:
    lookup = FakeQueryLookup(items=_items())

    with pytest.raises(QueryFilterInvalid) as error:
        run_list_items(lookup, TopicFilter(status="bogus"), ListPage())

    assert error.value.code == "QUERY-006"
    assert "list_items" not in lookup.calls


def _show_fixture() -> tuple[FakeQueryLookup, dict]:
    """Item 3 (Closed) with one out-link (Rejected) and one in-link (reversed)."""
    items = [
        make_item(1, statement="Premise"),
        make_item(2, statement="Rival"),
        make_item(
            3, status="Closed", close_reason="superseded", statement="Old plan"
        ),
    ]
    links = [
        make_link(7, 3, 1, link_type="depends_on", status="Rejected"),
        make_link(
            9, 2, 3, link_type="supersedes", status="Confirmed",
            reversed_at="2026-02-02T00:00:00+00:00",
        ),
    ]
    lookup = FakeQueryLookup(
        items=items,
        links=links,
        source_texts={3: "the verbatim note body"},
    )
    return lookup, items


def test_show_item_lists_rejected_and_reversed_links_both_ways() -> None:
    lookup, items = _show_fixture()

    result = show_item(
        3, lookup.list_items(), lookup.list_links(), "the verbatim note body"
    )

    assert result.source == "the verbatim note body"
    assert result.item.id == 3
    assert result.item.status == "Closed"

    # links_out: item 3 is the source; the OTHER item is 1 (Rejected kept).
    out = result.links_out
    assert [(link.id, link.type, link.status) for link in out] == [
        (7, "depends_on", "Rejected")
    ]
    assert out[0].other_item_id == 1
    assert out[0].other_item_type == "Decision"
    assert out[0].other_item_statement == "Premise"
    assert out[0].other_item_status == "Active"
    assert out[0].reversed_at is None

    # links_in: item 3 is the target; the OTHER item is 2 (reversed kept).
    inside = result.links_in
    assert [(link.id, link.type, link.status) for link in inside] == [
        (9, "supersedes", "Confirmed")
    ]
    assert inside[0].other_item_id == 2
    assert inside[0].other_item_statement == "Rival"
    assert inside[0].reversed_at == "2026-02-02T00:00:00+00:00"

    # An unrelated link between other items never appears.
    lookup_with_extra = FakeQueryLookup(
        items=items,
        links=[*lookup.list_links(), make_link(11, 1, 2, link_type="supports")],
        source_texts={3: "x"},
    )
    result = show_item(3, lookup_with_extra.list_items(), lookup_with_extra.list_links(), "x")
    assert [link.id for link in result.links_out] == [7]
    assert [link.id for link in result.links_in] == [9]


def test_run_show_item_renders_one_json_document() -> None:
    lookup, _ = _show_fixture()

    output = run_show_item(lookup, 3)

    document = json.loads(output)
    assert set(document) == {"item", "source", "links_out", "links_in"}
    assert document["source"] == "the verbatim note body"
    assert document["item"]["id"] == 3
    assert document["item"]["validated"] is None
    assert set(document["links_out"][0]) == {
        "id",
        "type",
        "status",
        "other_item_id",
        "other_item_type",
        "other_item_statement",
        "other_item_status",
        "reversed_at",
    }


def test_run_show_item_gates_an_unknown_id_as_001() -> None:
    lookup, _ = _show_fixture()

    with pytest.raises(QueryItemNotFound) as error:
        run_show_item(lookup, 99)

    assert error.value.code == "QUERY-001"
    # Gate first: no other read happened.
    assert lookup.calls == ["item_exists:99"]


def test_run_list_items_renders_total_and_spec_projection() -> None:
    lookup = FakeQueryLookup(items=_items())

    output = run_list_items(lookup, TopicFilter(), ListPage())

    document = json.loads(output)
    assert set(document) == {"total", "items"}
    assert document["total"] == 4
    assert len(document["items"]) == 4
    assert set(document["items"][0]) == {
        "id",
        "type",
        "statement",
        "status",
        "close_reason",
        "rationale",
        "source",
        "validated",
        "created_at",
    }
    assert document["items"][2]["close_reason"] == "expired"

"""Unit tests for the display layer (the renderer)."""

from __future__ import annotations

import json

from ember.query.render import (
    render_current_state,
    render_history,
    render_topic_search,
    render_why,
)
from ember.query.rows import (
    CurrentStateRow,
    HistoryEvent,
    QueryItem,
    SearchHit,
    WhyReason,
    WhyResult,
)
from tests.query.fakes import make_item, make_row


def test_challenged_rows_come_first_then_active_by_id() -> None:
    rows = [
        make_row(4, status="Active"),
        make_row(2, status="Challenged"),
        make_row(3, status="Active"),
        make_row(1, status="Challenged"),
    ]

    document = json.loads(render_current_state(rows))

    assert [item["id"] for item in document["items"]] == [1, 2, 3, 4]
    assert [item["status"] for item in document["items"]] == [
        "Challenged",
        "Challenged",
        "Active",
        "Active",
    ]


def test_document_round_trips_and_keys_match_the_model() -> None:
    document = json.loads(render_current_state([make_row(1)]))

    assert document["mode"] == "current_state"
    assert document["count"] == 1
    assert set(document["items"][0]) == set(CurrentStateRow.model_fields)


def test_empty_input_renders_count_zero_and_no_error() -> None:
    document = json.loads(render_current_state([]))

    assert document == {"mode": "current_state", "count": 0, "items": []}


def test_topic_search_document_round_trips_and_keys_match_the_model() -> None:
    hits = [SearchHit(item_id=1, score=0.5, type="Decision", statement="alpha", status="Active")]

    document = json.loads(render_topic_search(hits, "alpha"))

    assert document["mode"] == "topic_search"
    assert document["query"] == "alpha"
    assert document["count"] == 1
    assert set(document["results"][0]) == set(SearchHit.model_fields)


def test_why_document_round_trips_and_keys_match_the_models() -> None:
    result = WhyResult(
        item=make_item(1),
        reasons=[
            WhyReason(
                item_id=2,
                type="Assumption",
                statement="beta",
                status="Active",
                rationale=None,
                depth=1,
                via_link_type="depends_on",
                via_link_id=10,
            )
        ],
    )

    document = json.loads(render_why(result))

    assert document["mode"] == "why"
    assert document["count"] == 1
    # The `why` item block is pinned to the pre-bridge key set (the raw
    # byte-golden pins the same output): the read model grew the additive
    # `source` / `validated` fields for the bridge reads, and `why`'s
    # output must not change with it.
    assert set(document["item"]) == set(QueryItem.model_fields) - {
        "source",
        "validated",
    }
    assert set(document["reasons"][0]) == set(WhyReason.model_fields)


def test_why_document_with_no_reasons_is_count_zero() -> None:
    document = json.loads(render_why(WhyResult(item=make_item(1), reasons=[])))

    assert document["count"] == 0
    assert document["reasons"] == []


def test_history_document_round_trips_and_keys_match_the_model() -> None:
    event = HistoryEvent(
        timestamp="2026-01-01T00:00:00+00:00",
        kind="status_changed",
        cause="user_closed",
        field_changed="status",
        item_id=1,
        link_id=None,
        link_source_item_id=None,
        link_target_item_id=None,
        link_type=None,
        old_value="Active",
        new_value="Closed:expired",
        close_reason="expired",
    )

    document = json.loads(render_history([event], 1))

    assert document["mode"] == "history"
    assert document["item_id"] == 1
    assert document["count"] == 1
    assert set(document["events"][0]) == set(HistoryEvent.model_fields)


def test_history_document_for_the_global_view_has_a_null_item_id() -> None:
    document = json.loads(render_history([], None))

    assert document == {
        "mode": "history",
        "item_id": None,
        "count": 0,
        "events": [],
    }

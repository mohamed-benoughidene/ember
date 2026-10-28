"""Unit tests for the display layer (the renderer)."""

from __future__ import annotations

import json

from ember.query.render import render_current_state
from ember.query.rows import CurrentStateRow
from tests.query.fakes import make_row


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

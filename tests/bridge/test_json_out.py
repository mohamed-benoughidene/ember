"""Unit tests for the pure JSON renderer (bridge step 01, T1).

No I/O, no clock, deterministic: the same `OutputDocument` always renders
the same bytes.
"""

from __future__ import annotations

import json

from ember.bridge.json_out import OutputDocument, render_document
from ember.maintain.rows import EditChange, StatusChange


def test_document_has_the_pinned_top_level_keys_sorted() -> None:
    output = render_document(OutputDocument(command="edit-item", changes=[], summary={}))

    assert output == (
        '{"changes": [], "command": "edit-item",'
        ' "dry_run": false, "summary": {}}'
    )
    assert json.loads(output)["command"] == "edit-item"


def test_dry_run_is_a_model_field_stated_inside_the_document() -> None:
    document = OutputDocument(
        command="close-item", changes=[], summary={}, dry_run=True
    )

    assert document.dry_run is True
    assert '"dry_run": true' in render_document(document)


def test_changes_serialize_engine_models_whole() -> None:
    """D3: the result models ride the document unchanged, no second shape."""
    change = StatusChange(
        item_id=3,
        old_status="Active",
        new_status="Closed",
        close_reason="expired",
        trigger_cause="user_closed",
        link_id=None,
    )

    document = json.loads(
        render_document(
            OutputDocument(command="close-item", changes=[change], summary={"closed": 1})
        )
    )

    assert document["changes"] == [change.model_dump(mode="json")]
    assert document["summary"] == {"closed": 1}


def test_non_ascii_is_kept_verbatim() -> None:
    change = EditChange(
        item_id=1,
        field="rationale",
        old_value=None,
        new_value="café ☕",
        trigger_cause="user_edit_item",
    )

    output = render_document(
        OutputDocument(command="edit-item", changes=[change], summary={})
    )

    assert "café ☕" in output
    assert "\\u" not in output


def test_rendering_is_deterministic() -> None:
    document = OutputDocument(
        command="db-check",
        changes=[],
        summary={"result": "OK", "lines": ["version: 13"], "detail": None},
    )

    assert render_document(document) == render_document(document)

"""Unit tests for `validate_edit_item` (pure, no DB) plus the step-local E2E.

The unit half runs the validator against `FakeMaintainLookup` snapshots. The
E2E half drives the real `ember edit-item` then `ember history` CLIs against
one temp DB, asserting the ledger row renders `kind='unknown'` with raw
values visible and nothing crashing (Query is not modified in this phase).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.cli import main
from ember.maintain.errors import (
    EditFieldUnknown,
    EditTargetMismatch,
    MaintainItemNotFound,
)
from ember.maintain.human_actions import validate_edit_item
from ember.maintain.rows import ItemState, MaintainSnapshot
from tests.fakes import insert_item, insert_source
from tests.maintain.fakes import FakeMaintainLookup

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _item(
    item_id: int,
    item_type: str = "Decision",
    rationale: str | None = None,
    source: str | None = None,
) -> ItemState:
    return ItemState(
        id=item_id,
        type=item_type,
        status="Active",
        close_reason=None,
        status_origin="derived",
        rationale=rationale,
        source=source,
    )


def _snap(items: list[ItemState]) -> MaintainSnapshot:
    return MaintainSnapshot(items=items, links=[], reversed_link_ids=set())


def test_validate_edit_item_rationale_on_decision_returns_edit_change() -> None:
    changes = validate_edit_item(_snap([_item(3, "Decision")]), 3, "rationale", "why")

    assert len(changes) == 1
    assert changes[0].item_id == 3
    assert changes[0].field == "rationale"
    assert changes[0].old_value is None
    assert changes[0].new_value == "why"
    assert changes[0].trigger_cause == "user_edit_item"


def test_validate_edit_item_rationale_on_finding_raises_014() -> None:
    with pytest.raises(EditTargetMismatch) as exc:
        validate_edit_item(_snap([_item(4, "Finding")]), 4, "rationale", "why")

    assert exc.value.code == "MAINTAIN-014"


def test_validate_edit_item_source_on_finding_returns_edit_change() -> None:
    changes = validate_edit_item(
        _snap([_item(5, "Finding")]), 5, "source", "doi:10.1/x"
    )

    assert len(changes) == 1
    assert changes[0].field == "source"
    assert changes[0].new_value == "doi:10.1/x"


def test_validate_edit_item_source_on_decision_raises_014() -> None:
    with pytest.raises(EditTargetMismatch) as exc:
        validate_edit_item(_snap([_item(6, "Decision")]), 6, "source", "s")

    assert exc.value.code == "MAINTAIN-014"


def test_validate_edit_item_unknown_field_raises_013() -> None:
    with pytest.raises(EditFieldUnknown) as exc:
        validate_edit_item(_snap([_item(7, "Decision")]), 7, "bogus", "v")

    assert exc.value.code == "MAINTAIN-013"


def test_validate_edit_item_statement_under_option_a_raises_014() -> None:
    with pytest.raises(EditTargetMismatch) as exc:
        validate_edit_item(_snap([_item(8, "Decision")]), 8, "statement", "x")

    assert exc.value.code == "MAINTAIN-014"


def test_validate_edit_item_same_value_returns_empty_list() -> None:
    changes = validate_edit_item(
        _snap([_item(3, "Decision", rationale="why")]), 3, "rationale", "why"
    )

    assert changes == []


def test_validate_edit_item_old_value_is_observed() -> None:
    changes = validate_edit_item(
        _snap([_item(3, "Decision", rationale="prior text")]),
        3,
        "rationale",
        "new text",
    )

    assert changes[0].old_value == "prior text"
    assert changes[0].new_value == "new text"


def test_e2e_edit_item_then_history_renders_unknown_kind(db_path) -> None:
    Path(db_path).touch()
    conn = _open_seeded(db_path)
    conn.close()

    edit = CliRunner().invoke(
        main,
        [
            "edit-item",
            "--item",
            "1",
            "--field",
            "rationale",
            "--value",
            "chosen for the ceiling",
            "--db",
            db_path,
        ],
    )
    assert edit.exit_code == 0

    shown = CliRunner().invoke(main, ["history", "--item", "1", "--db", db_path])
    assert shown.exit_code == 0
    events = json.loads(shown.output)["events"]
    assert len(events) == 1
    assert events[0]["kind"] == "unknown"
    assert events[0]["field_changed"] == "rationale"
    assert events[0]["new_value"] == "chosen for the ceiling"


def _open_seeded(db_path: str):
    from ember.adapters.sqlite import open_maintain_database

    conn = open_maintain_database(db_path)
    source_id = insert_source(conn)
    insert_item(
        conn,
        source_id=source_id,
        item_id=1,
        item_type="Decision",
        statement="Choose SQLite",
    )
    conn.commit()
    return conn

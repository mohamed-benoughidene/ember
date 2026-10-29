"""Unit tests for `validate_remove_link` (pure, no DB) plus the combined E2E.

The unit half runs the validator against `FakeMaintainLookup` snapshots (the
snapshot is the whole world, and the Confirmed-only Phase-1 read applies). The
E2E half is this step's ONE combined end-to-end test (§12.8 as amended):
`ember edit-item` -> `ember remove-link` -> `ember history --item`, asserting
every new ledger row renders `kind='unknown'` with raw values visible, and
`ember db-check` stays exit 0 afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from ember.maintain.errors import RemoveLinkNotConfirmed
from ember.maintain.human_actions import validate_remove_link
from ember.maintain.rows import MaintainSnapshot
from ember.relate.rows import Link
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source
from tests.maintain.fakes import FakeMaintainLookup


def _link(
    link_id: int,
    source_item_id: int,
    target_item_id: int,
    link_type: str = "depends_on",
    status: str = "Confirmed",
    reversed_at: str | None = None,
) -> Link:
    return Link(
        id=link_id,
        source_item_id=source_item_id,
        target_item_id=target_item_id,
        link_type=link_type,
        status=status,
        created_at=FIXED_TIME,
        reversed_at=reversed_at,
    )


def _snap(links: list[Link]) -> MaintainSnapshot:
    return MaintainSnapshot(items=[], links=links, reversed_link_ids=set())


def test_validate_remove_link_confirmed_link_returns_link_change() -> None:
    snapshot = _snap([_link(7, 2, 5, "supersedes")])

    changes = validate_remove_link(snapshot, 7)

    assert len(changes) == 1
    assert changes[0].link_id == 7
    assert changes[0].old_status == "Confirmed"
    assert changes[0].new_status == "Rejected"
    assert changes[0].trigger_cause == "user_remove_link"
    assert changes[0].item_id == 2  # the link's source, Relate's convention


def test_validate_remove_link_missing_or_rejected_link_raises_015() -> None:
    # One code for both shapes: no such row, and a row that is not Confirmed
    # (Phase 1's Confirmed-only read cannot distinguish them, same as 005).
    with pytest.raises(RemoveLinkNotConfirmed) as missing:
        validate_remove_link(_snap([]), 99)
    assert missing.value.code == "MAINTAIN-015"
    assert missing.value.context["link_id"] == 99

    with pytest.raises(RemoveLinkNotConfirmed) as rejected:
        validate_remove_link(_snap([_link(7, 2, 5, status="Rejected")]), 7)
    assert rejected.value.code == "MAINTAIN-015"
    assert rejected.value.context["link_id"] == 7


def test_validate_remove_link_reversed_but_confirmed_link_passes() -> None:
    # Orthogonal to reversal: a reversed supersedes link still reads Confirmed
    # (Gap C), so removal accepts it, and the ledger ends with both markers.
    snapshot = MaintainSnapshot(
        items=[],
        links=[_link(7, 2, 5, "supersedes", reversed_at=FIXED_TIME)],
        reversed_link_ids={7},
    )

    changes = validate_remove_link(snapshot, 7)

    assert len(changes) == 1
    assert changes[0].link_id == 7
    assert changes[0].old_status == "Confirmed"
    assert changes[0].new_status == "Rejected"


def test_e2e_edit_item_then_remove_link_then_history_renders_unknown_kind(
    db_path,
) -> None:
    """The step's ONE combined E2E: both new CLIs plus the read-back.

    Item 1 (a Decision) is the source of confirmed link 1. The edit writes
    item 1's rationale, the removal writes a `link_removed` row carrying
    item_id=1 (the link's source), so `history --item 1` must render BOTH
    new rows as `kind='unknown'` with raw values visible. db-check then
    reports exit 0: the removal left no drift (no FK violation, replay
    untouched).
    """
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            item_type="Decision",
            statement="Choose SQLite",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Finding",
            statement="SQLite caps at 5000 items",
        )
        insert_link(conn, 1, 2, "depends_on")
        conn.commit()
    finally:
        conn.close()

    runner = CliRunner()

    edited = runner.invoke(
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
    assert edited.exit_code == 0

    removed = runner.invoke(main, ["remove-link", "--link", "1", "--db", db_path])
    assert removed.exit_code == 0
    assert removed.output.strip() == (
        "link 1: depends_on 1 -> 2 removed (Confirmed -> Rejected)"
    )

    shown = runner.invoke(main, ["history", "--item", "1", "--db", db_path])
    assert shown.exit_code == 0
    events = json.loads(shown.output)["events"]
    assert len(events) == 2
    assert all(event["kind"] == "unknown" for event in events)
    by_field = {event["field_changed"]: event for event in events}
    assert by_field["rationale"]["new_value"] == "chosen for the ceiling"
    assert by_field["rationale"]["item_id"] == 1
    assert by_field["link_removed"]["old_value"] == "Confirmed"
    assert by_field["link_removed"]["new_value"] == "Rejected"
    assert by_field["link_removed"]["link_id"] == 1

    checked = runner.invoke(main, ["db-check", "--db", db_path])
    assert checked.exit_code == 0
    assert "result: OK" in checked.output

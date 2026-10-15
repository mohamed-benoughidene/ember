"""Integration tests for phases 3 + 4 on a real SQLite temp DB."""

from __future__ import annotations

import sqlite3

from ember.adapters.sqlite import (
    SqliteItemGatekeeper,
    SqliteSourceStore,
    open_database,
)
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.item_gatekeeper import (
    GatekeeperRun,
    load_source_text,
    validate_add_item,
    validate_proposals,
)
from ember.capture.item_proposal import ItemProposal, ItemType
from ember.capture.source_storage import store_source
from tests.fakes import FakeConfirm

FIXED_TIME = "2026-01-01T00:00:00+00:00"
RAW_TEXT = (
    "We decided to use SQLite for local storage. "
    "We assume the team ships weekly. "
    "The benchmark ran in 12ms. "
    "The API key rotates monthly. "
    "The onboarding screen has two steps."
)


def proposal(item_type: ItemType, statement: str, quote: str) -> ItemProposal:
    return ItemProposal(
        type=item_type, statement=statement, source_quote=quote, confidence=0.9
    )


def run_pipeline(
    conn: sqlite3.Connection,
    proposals: list[ItemProposal],
    answers: list[str],
):
    """Wire step 1 -> step 3 -> step 4 on the real DB, like the CLI edge will."""
    sources = SqliteSourceStore(conn, clock=lambda: FIXED_TIME)
    stored = store_source(sources, RAW_TEXT)

    gatekeeper = SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME)
    run = GatekeeperRun(
        source_id=stored.source_id,
        source_text=load_source_text(sources, stored.source_id),
        existing=gatekeeper.statements(),
        next_id=gatekeeper.next_item_id,
        clock=lambda: FIXED_TIME,
    )

    gatekeeper_result = validate_proposals(proposals, run)
    confirm = FakeConfirm(answers)
    confirm_result = run_confirm_loop(
        gatekeeper_result.validated,
        confirm=confirm,
        commit=gatekeeper,
        revalidate=lambda draft: validate_add_item(draft, run),
    )
    return gatekeeper_result, confirm_result, confirm


def _rows(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    return conn.execute(query).fetchall()


def test_happy_path_writes_three_items_and_three_logs(db_path) -> None:
    conn = open_database(db_path)
    proposals = [
        proposal(ItemType.DECISION, "Use SQLite", "use SQLite"),
        proposal(ItemType.ASSUMPTION, "Team ships weekly", "ships weekly"),
        proposal(ItemType.FINDING, "Benchmark is 12ms", "12ms"),
    ]

    _, result, _ = run_pipeline(conn, proposals, ["y", "y", "y"])

    items = _rows(conn, "SELECT * FROM items ORDER BY id")
    logs = _rows(
        conn, "SELECT * FROM change_log WHERE field_changed = 'created' ORDER BY item_id"
    )
    assert len(items) == 3
    assert len(logs) == 3
    assert result.accepted_ids == [row["id"] for row in items]
    assert [row["item_id"] for row in logs] == [row["id"] for row in items]
    assert {row["trigger_cause"] for row in logs} == {"user_confirmed"}
    assert result.aborted is False


def test_rejection_path_logs_without_item_rows(db_path) -> None:
    conn = open_database(db_path)
    proposals = [
        proposal(ItemType.DECISION, "Use SQLite", "use SQLite"),
        proposal(ItemType.ASSUMPTION, "Team ships weekly", "ships weekly"),
        proposal(ItemType.FINDING, "Benchmark is 12ms", "12ms"),
    ]

    _, result, _ = run_pipeline(conn, proposals, ["n", "n", "y"])

    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    rejected = _rows(conn, "SELECT * FROM change_log WHERE trigger_cause = 'rejected'")
    created = _rows(conn, "SELECT * FROM change_log WHERE field_changed = 'created'")
    assert len(rejected) == 2
    assert len(created) == 1
    assert all(row["item_id"] is None for row in rejected)
    assert result.rejected_count == 2


def test_near_dup_warns_and_still_accepts(db_path) -> None:
    conn = open_database(db_path)
    first = [proposal(ItemType.DECISION, "Use SQLite", "use SQLite")]
    run_pipeline(conn, first, ["y"])

    _, result, confirm = run_pipeline(conn, first, ["y"])

    assert result.warning_count == 1
    assert any("near-duplicate" in line for line in confirm.written)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_edit_flow_writes_the_corrected_type(db_path) -> None:
    conn = open_database(db_path)
    proposals = [proposal(ItemType.FINDING, "Use SQLite", "use SQLite")]

    _, result, _ = run_pipeline(
        conn, proposals, ["e", "Decision", "Use SQLite", "y"]
    )

    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["type"] == "Decision"
    assert row["statement"] == "Use SQLite"
    assert result.accepted_ids == [row["id"]]


def test_abort_leaves_the_remaining_items_untouched(db_path) -> None:
    conn = open_database(db_path)
    proposals = [
        proposal(ItemType.DECISION, "Use SQLite", "use SQLite"),
        proposal(ItemType.ASSUMPTION, "Team ships weekly", "ships weekly"),
        proposal(ItemType.FINDING, "Benchmark is 12ms", "12ms"),
        proposal(ItemType.QUESTION, "Does the key rotate", "rotates monthly"),
        proposal(ItemType.FINDING, "Onboarding has two steps", "two steps"),
    ]

    _, result, _ = run_pipeline(conn, proposals, ["y", "y", "q"])

    assert result.aborted is True
    assert len(result.accepted_ids) == 2
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0] == 2


def test_assumption_row_carries_the_validated_flag(db_path) -> None:
    conn = open_database(db_path)
    proposals = [
        proposal(ItemType.ASSUMPTION, "Team ships weekly", "ships weekly"),
        proposal(ItemType.DECISION, "Use SQLite", "use SQLite"),
    ]

    run_pipeline(conn, proposals, ["y", "y"])

    rows = _rows(conn, "SELECT type, validated FROM items ORDER BY id")
    assert rows[0]["validated"] == 0
    assert rows[1]["validated"] is None

"""The undo engine's ONE end-to-end test (undo step 05, L2 §7 T4 / spec 12.6).

`ember capture`-equivalent (fake AI) -> `ember relate`-equivalent (fake AI
and fake user) -> `ember close-item` -> `ember undo` -> `ember redo` ->
`ember history`, the real house chain on one temp database. The invariants
asserted: undo restores the exact pre-close state, the ledger only grows,
no undo/redo event ever renders `unknown`, a redone close keeps its close
reason, and `ember db-check` reads the result healthy (exit 0).
"""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import (
    SqliteItemContext,
    SqliteItemGatekeeper,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteSourceStore,
    build_ai_response_store,
    open_database,
)
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.item_gatekeeper import (
    GatekeeperRun,
    load_source_text,
    validate_add_item,
    validate_proposals,
)
from ember.capture.item_proposal import (
    ContextMode,
    ItemProposal,
    ItemType,
    ProposalBatch,
    ProposalResponse,
    build_context,
    propose_items,
)
from ember.capture.source_storage import store_source
from ember.cli import main
from ember.relate.link_proposal import LinkProposal, LinkProposalResponse
from ember.relate.rows import NewItem, RankedCandidate, SignalKind
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate
from tests.fakes import FIXED_TIME, FakeConfirm, FakeItemProposer
from tests.relate.fakes import FakeLinkProposer

RAW_TEXT = (
    "We decided to use SQLite for local storage. "
    "We decided to use Postgres instead."
)

PROPOSALS = ProposalBatch(
    proposals=[
        ItemProposal(
            type=ItemType.DECISION,
            statement="Use SQLite for local storage",
            source_quote="decided to use SQLite for local storage",
            confidence=0.9,
        ),
        ItemProposal(
            type=ItemType.DECISION,
            statement="Use Postgres instead",
            source_quote="decided to use Postgres instead",
            confidence=0.9,
        ),
    ],
    dropped=[],
)


def _run_capture(conn) -> None:
    """Phases 1-4 for Capture, with the AI and the user faked."""
    sources = SqliteSourceStore(conn, clock=lambda: FIXED_TIME)
    stored = store_source(sources, RAW_TEXT)
    proposer = FakeItemProposer(
        [ProposalResponse(raw_response="raw", batch=PROPOSALS)]
    )
    response = propose_items(
        proposer,
        raw_text=stored.raw_text,
        context=build_context(SqliteItemContext(conn), ContextMode.B),
    )
    gatekeeper = SqliteItemGatekeeper(conn, clock=lambda: FIXED_TIME)
    run = GatekeeperRun(
        source_id=stored.source_id,
        source_text=load_source_text(sources, stored.source_id),
        existing=gatekeeper.statements(),
        next_id=gatekeeper.next_item_id,
        clock=lambda: FIXED_TIME,
    )
    outcome = validate_proposals(response.batch.proposals, run)
    run_confirm_loop(
        outcome.validated,
        confirm=FakeConfirm(["y", "y"]),
        commit=gatekeeper,
        revalidate=lambda draft: validate_add_item(draft, run),
    )


def _run_relate(conn) -> None:
    """Phases 3-4 for Relate, with the AI and the user faked."""
    ports = RelatePorts(
        link_lookup=SqliteLinkContext(conn),
        link_store=SqliteLinkStore(conn),
        link_proposer=FakeLinkProposer(
            [
                LinkProposalResponse(
                    raw_response="raw",
                    proposals=[LinkProposal(target_item_id=1, link_type="depends_on")],
                )
            ]
        ),
        ai_response_store=build_ai_response_store(conn),
        confirm=FakeConfirm(["y"]),
    )
    request = RelateRequest(
        new_item=NewItem(
            id=2,
            type="Decision",
            statement="Use Postgres instead",
            created_at=FIXED_TIME,
        ),
        ranked=[
            RankedCandidate(
                item=NewItem(
                    id=1,
                    type="Decision",
                    statement="Use SQLite for local storage",
                    created_at=FIXED_TIME,
                ),
                cosine=1.0,
                source=SignalKind.dense,
            )
        ],
        env={},
    )
    run_relate(ports, request)


def _ledger_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0])
    finally:
        conn.close()


def _item_status(db_path: str, item_id: int) -> tuple[str, str | None]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, close_reason FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0], row[1]


def test_capture_relate_close_undo_redo_history_db_check(db_path) -> None:
    conn = open_database(db_path)
    try:
        _run_capture(conn)
        _run_relate(conn)
        conn.commit()
    finally:
        conn.close()
    before_close = _ledger_count(db_path)

    # The undoable human action: close item 1; its dependent (item 2 via the
    # depends_on link) is challenged by the `dependency_closed` fan-out.
    runner = CliRunner()
    closed = runner.invoke(
        main, ["close-item", "--item", "1", "--reason", "invalidated", "--db", db_path]
    )
    assert closed.exit_code == 0, closed.output
    after_close = _ledger_count(db_path)
    assert after_close > before_close

    # Undo: the state goes back to exactly the pre-close state (status AND
    # close reason), and only the ledger grew.
    undone = runner.invoke(main, ["undo", "--db", db_path])
    assert undone.exit_code == 0, undone.output
    assert undone.output.startswith("undone group 1 as group 2 (close-item, item 1):")
    assert _item_status(db_path, 1) == ("Active", None)
    assert _item_status(db_path, 2) == ("Active", None)
    after_undo = _ledger_count(db_path)
    assert after_undo == after_close + 3  # two inverse rows + one pointer

    # Redo: the close is re-applied, close reason included.
    redone = runner.invoke(main, ["redo", "--db", db_path])
    assert redone.exit_code == 0, redone.output
    assert redone.output.startswith("redone group 2 as group 3 (close-item, item 1):")
    assert _item_status(db_path, 1) == ("Closed", "invalidated")
    assert _item_status(db_path, 2) == ("Challenged", None)
    assert _ledger_count(db_path) == after_undo + 3

    # History: the pointers read `undone` / `redone`, every inverse row keeps
    # its original kind (a status row stays `status_changed`), and nothing
    # the undo engine wrote renders as `unknown`.
    history = runner.invoke(main, ["history", "--db", db_path])
    assert history.exit_code == 0, history.output
    events = json.loads(history.output)["events"]
    assert all(event["kind"] != "unknown" for event in events)
    kinds = [event["kind"] for event in events]
    assert "undone" in kinds and "redone" in kinds
    inversions = [event for event in events if event["cause"] in
                  ("user_undo", "user_redo")]
    assert len(inversions) == 6  # 2 undo rows + pointer, 2 redo rows + pointer
    assert all(event["kind"] != "unknown" for event in inversions)
    undo_pointer = next(e for e in events if e["field_changed"] == "undo_of")
    redo_pointer = next(e for e in events if e["field_changed"] == "redo_of")
    assert (undo_pointer["kind"], undo_pointer["cause"]) == ("undone", "user_undo")
    assert (redo_pointer["kind"], redo_pointer["cause"]) == ("redone", "user_redo")
    redo_close = next(
        e for e in events
        if e["cause"] == "user_redo" and e["item_id"] == 1
    )
    assert redo_close["kind"] == "status_changed"
    assert redo_close["close_reason"] == "invalidated"

    # db-check reads the post-undo/redo ledger healthy, still read-only.
    check = runner.invoke(main, ["db-check", "--db", db_path])
    assert check.exit_code == 0, check.output
    assert check.output.splitlines()[-1] == "result: OK"

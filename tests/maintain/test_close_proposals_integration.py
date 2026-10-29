"""Engine-loop tests for `run_close_proposals` on a real temp DB, no AI.

Phase 5 with a `FakeCloseProposer` and a scripted confirm fake. Every write
asserts the existing vocabulary: the accept path is the human `run_close_item`
path, so an accepted close leaves exactly one `user_closed` ledger row.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.close_proposer import (
    CloseProposal,
    CloseProposalResponse,
    ProposalOutcome,
)
from ember.maintain.errors import (
    CloseAiSchemaInvalid,
    CloseAiStoreFailed,
    UserAbort as MaintainUserAbort,
)
from ember.maintain.run_maintain import CloseProposalPorts, run_close_proposals
from tests.fakes import (
    FakeConfirm,
    insert_item,
    insert_link,
    insert_source,
)
from tests.maintain.fakes import AiResponseStoreStub, FakeCloseProposer

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
T_ANSWER = "2026-01-01T00:00:00+00:00"  # answer link older than STALE_DAYS
T_CLEAR = "2026-01-02T00:00:00+00:00"  # the manual clear, after the link


def _insert_link_row(
    conn: sqlite3.Connection, link_id: int, source: int, target: int
) -> None:
    """Insert one Confirmed answers link with an explicit id (the pinned seed
    names links 11 and 12)."""
    conn.execute(
        "INSERT INTO links (id, source_item_id, target_item_id, link_type,"
        " status, created_at) VALUES (?, ?, ?, 'answers', 'Confirmed', ?)",
        (link_id, source, target, T_ANSWER),
    )


def _shield(conn: sqlite3.Connection, item_id: int) -> None:
    """Mark `items.status_origin='manual'` with its clear ledger row, dated
    after the answer link (the production shape the sweep cannot machine-
    close, L2 section 13)."""
    conn.execute(
        "UPDATE items SET status_origin = 'manual' WHERE id = ?", (item_id,)
    )
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, NULL, 'status_origin', 'derived', 'manual', ?,"
        " 'user_set_status')",
        (item_id, T_CLEAR),
    )


def _seed_stale_questions(
    db_path: str, spec: list[tuple[int, int, str]]
) -> None:
    """Seed stale shielded Questions: Finding 4 answers each Question with a
    Confirmed link at T_ANSWER (explicit link id), each question shielded by a
    manual clear dated after the link."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="measured",
        )
        for question_id, link_id, statement in spec:
            insert_item(
                conn, source_id=source_id, item_id=question_id,
                item_type="Question", statement=statement,
            )
            _shield(conn, question_id)
            _insert_link_row(conn, link_id, 4, question_id)
        conn.commit()
    finally:
        conn.close()


def _seed_pair(db_path: str) -> None:
    _seed_stale_questions(
        db_path,
        [
            (7, 11, "should we cache tokens?"),
            (9, 12, "which auth backend?"),
        ],
    )


def _decline(raw: str = "RAW-DECLINE") -> CloseProposalResponse:
    return CloseProposalResponse(raw_response=raw, proposal=None)


def _proposal(
    reason: str = "expired", raw: str = "RAW-PROPOSAL"
) -> CloseProposalResponse:
    return CloseProposalResponse(
        raw_response=raw,
        proposal=CloseProposal(
            reason=reason, confidence=0.8, rationale="answered long ago"
        ),
    )


def _open_ports(
    db_path: str, proposer, ai_response_store, confirm
) -> tuple[CloseProposalPorts, sqlite3.Connection]:
    conn = open_maintain_database(db_path)
    ports = CloseProposalPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        close_proposer=proposer,
        ai_response_store=ai_response_store,
        confirm=confirm,
    )
    return ports, conn


def _run(db_path: str, proposer, confirm) -> tuple[ProposalOutcome | None, Exception | None, sqlite3.Connection]:
    conn = open_maintain_database(db_path)
    ports = CloseProposalPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        close_proposer=proposer,
        ai_response_store=SqliteAiResponseStore(conn),
        confirm=confirm,
    )
    try:
        outcome = run_close_proposals(ports, now=NOW)
    except Exception as exc:
        return None, exc, conn
    return outcome, None, conn


def _count(db_path: str, query: str, params: tuple = ()) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(query, params).fetchone()[0])
    finally:
        conn.close()


def _row(db_path: str, query: str, params: tuple = ()) -> tuple | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(query, params).fetchone()
    finally:
        conn.close()
    return tuple(row) if row is not None else None


# --- the loop -------------------------------------------------------------


def test_empty_shortlist_proposer_is_never_called(db_path) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Finding")
        conn.commit()
    finally:
        conn.close()
    proposer = FakeCloseProposer([])
    confirm = FakeConfirm([], abort_error=MaintainUserAbort)

    outcome, _exc, _conn = _run(db_path, proposer, confirm)

    assert outcome == ProposalOutcome(
        stale=0, proposed=0, accepted=0, rejected=0, aborted=False
    )
    assert proposer.calls == []
    assert confirm.prompts == []


def test_accept_writes_via_validate_path_one_user_closed_row(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=2, proposed=1, accepted=1, rejected=0, aborted=False
    )
    assert _row(
        db_path,
        "SELECT status, close_reason FROM items WHERE id = 9",
    ) == ("Closed", "expired")
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 1
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM ai_responses") == 2
    )


def test_accept_invalidated_challenges_dependents_like_close_item(db_path) -> None:
    _seed_stale_questions(db_path, [(9, 12, "which auth backend?")])
    conn = open_maintain_database(db_path)
    try:
        # A Question can never be a `depends_on` target in a compat-legal
        # graph (nothing may depend_on a Question and relation's gatekeeper
        # would refuse the link), so the fan-out is unreachable for AI
        # closes in practice. To pin that the accept path fans out EXACTLY
        # like `ember close-item`, this one throwaway seed drops the insert
        # trigger and writes the pair raw. The engine logic under test is
        # unchanged: it is `validate_close_item`'s own fan-out.
        conn.execute("DROP TRIGGER links_compat_insert")
        insert_item(
            conn, source_id=1, item_id=10, item_type="Decision",
            statement="we chose backend A",
        )
        insert_link(conn, 10, 9, "depends_on")
        conn.commit()
    finally:
        conn.close()
    proposer = FakeCloseProposer([_proposal("invalidated")])
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=1, proposed=1, accepted=1, rejected=0, aborted=False
    )
    assert _row(
        db_path, "SELECT status, close_reason FROM items WHERE id = 9"
    ) == ("Closed", "invalidated")
    assert _row(db_path, "SELECT status FROM items WHERE id = 10") == (
        "Challenged",
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 1
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'dependency_closed'") == 1
    )


def test_accept_on_shielded_item_close_applies_origin_stays_manual(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome.accepted == 1
    assert _row(
        db_path, "SELECT status_origin FROM items WHERE id = 9"
    ) == ("manual",)
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'sweep_rearm'") == 0
    )


def test_reject_writes_nothing_and_counts(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    confirm = FakeConfirm(["n"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=2, proposed=1, accepted=0, rejected=1, aborted=False
    )
    assert _row(db_path, "SELECT status FROM items WHERE id = 9") == (
        "Active",
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 0
    )
    # The only writes are the seed's two manual-clear rows: a rejection
    # writes nothing (the propose evidence lives in ai_responses, D8).
    assert _count(db_path, "SELECT COUNT(*) FROM change_log") == 2


def test_quit_aborts_and_leftovers_get_no_call(db_path) -> None:
    _seed_stale_questions(
        db_path,
        [
            (7, 11, "question 7?"),
            (9, 12, "question 9?"),
            (10, 13, "question 10?"),
        ],
    )
    proposer = FakeCloseProposer([_proposal(), _proposal(), _proposal()])
    confirm = FakeConfirm(["q"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=3, proposed=1, accepted=0, rejected=0, aborted=True
    )
    assert len(proposer.calls) == 1
    assert _row(db_path, "SELECT status FROM items WHERE id = 7") == (
        "Active",
    )


def test_decline_counts_and_writes_nothing(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _decline()])
    confirm = FakeConfirm([], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=2, proposed=0, accepted=0, rejected=0, aborted=False
    )
    assert confirm.prompts == []
    assert _row(db_path, "SELECT status FROM items WHERE id = 9") == (
        "Active",
    )
    assert _count(db_path, "SELECT COUNT(*) FROM change_log") == 2


def test_raw_response_stored_by_item_id_verbatim(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline("RAW-SEVEN"), _proposal("expired", "RAW-NINE")])
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome.accepted == 1
    assert _row(
        db_path, "SELECT response_text FROM ai_responses WHERE item_id = 7"
    ) == ("RAW-SEVEN",)
    assert _row(
        db_path, "SELECT response_text FROM ai_responses WHERE item_id = 9"
    ) == ("RAW-NINE",)


def test_store_failure_raises_close_ai_store_failed(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)
    stub = AiResponseStoreStub(fail=RuntimeError("store down"))
    ports, conn = _open_ports(db_path, proposer, stub, confirm)

    try:
        with pytest.raises(CloseAiStoreFailed) as excinfo:
            run_close_proposals(ports, now=NOW)
    finally:
        conn.close()

    assert excinfo.value.code == "MAINTAIN-021"
    assert excinfo.value.context["item_id"] == 7
    assert _row(db_path, "SELECT status FROM items WHERE id = 7") == (
        "Active",
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 0
    )


def test_error_mid_loop_keeps_earlier_accepts(db_path) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer(
        [
            _proposal("expired"),
            CloseAiSchemaInvalid("bad schema", item_id=9),
            CloseAiSchemaInvalid("bad schema again", item_id=9),
        ]
    )
    confirm = FakeConfirm(["y"], abort_error=MaintainUserAbort)

    outcome, exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome is None
    assert isinstance(exc, CloseAiSchemaInvalid)
    assert exc.code == "MAINTAIN-019"
    assert _row(
        db_path, "SELECT status, close_reason FROM items WHERE id = 7"
    ) == ("Closed", "expired")
    assert _row(db_path, "SELECT status FROM items WHERE id = 9") == (
        "Active",
    )
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 1
    )


def test_truncated_shortlist_caps_calls_at_ten(db_path: str) -> None:
    _seed_stale_questions(
        db_path,
        [
            (item_id, 100 + item_id, f"question {item_id}?")
            for item_id in range(10, 22)
        ],
    )
    proposer = FakeCloseProposer([_decline()] * 12)
    confirm = FakeConfirm([], abort_error=MaintainUserAbort)

    outcome, _exc, conn = _run(db_path, proposer, confirm)
    conn.close()

    assert outcome == ProposalOutcome(
        stale=10, proposed=0, accepted=0, rejected=0, aborted=False
    )
    assert len(proposer.calls) == 10
    assert [candidate.item_id for candidate in proposer.calls] == list(
        range(10, 20)
    )

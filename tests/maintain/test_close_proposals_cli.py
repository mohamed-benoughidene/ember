"""CLI tests for `ember maintain` Phase 5 (faked close AI, real temp DB, no key).

The proposer is faked at the same seam production wires up: the
`ember.cli.build_close_proposer` import (the `tests/test_cli_capture.py`
pattern). No API key exists anywhere here, so every exit-0 path also proves
the no-key/no-call rule.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from ember.maintain.close_proposer import CloseProposal, CloseProposalResponse
from tests.fakes import insert_item, insert_source
from tests.maintain.fakes import FakeCloseProposer

T_ANSWER = "2026-01-01T00:00:00+00:00"
T_CLEAR = "2026-01-02T00:00:00+00:00"

OUTCOME_EMPTY = "stale: 0, proposed: 0, accepted: 0, rejected: 0, aborted: false"
OUTCOME_BASE = "stale: {}, proposed: {}, accepted: {}, rejected: {}, aborted: {}"


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
    close, the section-6 seed)."""
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


def _seed_plain(db_path: str) -> None:
    """Seed i: two items and no answers links at all (empty shortlist)."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=1, item_type="Decision",
            statement="use sqlite",
        )
        insert_item(
            conn, source_id=source_id, item_id=2, item_type="Finding",
            statement="tests pass",
        )
        conn.commit()
    finally:
        conn.close()


def _seed_pair(db_path: str) -> None:
    """The section-2 seed: Findings 4 and 5, Questions 7 and 9, confirmed
    answers links 11 (5 -> 7) and 12 (4 -> 9) at T_ANSWER, both questions
    shielded by a manual clear dated after the link."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="auth measured",
        )
        insert_item(
            conn, source_id=source_id, item_id=5, item_type="Finding",
            statement="tokens measured",
        )
        insert_item(
            conn, source_id=source_id, item_id=7, item_type="Question",
            statement="should we cache tokens?",
        )
        insert_item(
            conn, source_id=source_id, item_id=9, item_type="Question",
            statement="which auth backend?",
        )
        _shield(conn, 7)
        _shield(conn, 9)
        _insert_link_row(conn, 11, 5, 7)
        _insert_link_row(conn, 12, 4, 9)
        conn.commit()
    finally:
        conn.close()


def _seed_stale_one(db_path: str) -> None:
    """Seed ii: Question 9 stale (answered by Finding 4, link 12) and
    shielded, so it survives the sweep."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="auth measured",
        )
        insert_item(
            conn, source_id=source_id, item_id=9, item_type="Question",
            statement="which auth backend?",
        )
        _shield(conn, 9)
        _insert_link_row(conn, 12, 4, 9)
        conn.commit()
    finally:
        conn.close()


def _seed_truncated(db_path: str) -> None:
    """Twelve stale shielded questions answered by Finding 4: one over the cap."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="measured",
        )
        for question_id in range(10, 22):
            insert_item(
                conn, source_id=source_id, item_id=question_id,
                item_type="Question", statement=f"question {question_id}?",
            )
            _shield(conn, question_id)
            _insert_link_row(conn, 100 + question_id, 4, question_id)
        conn.commit()
    finally:
        conn.close()


def _decline(raw: str = "RAW-DECLINE") -> CloseProposalResponse:
    return CloseProposalResponse(raw_response=raw, proposal=None)


def _proposal(
    reason: str = "expired", raw: str = "RAW-PROPOSAL"
) -> CloseProposalResponse:
    return CloseProposalResponse(
        raw_response=raw,
        proposal=CloseProposal(
            reason=reason,
            confidence=0.8,
            rationale="answered long ago, no follow-up open",
        ),
    )


def _no_builder(env):
    raise AssertionError("the close proposer was constructed")


def _run_maintain(db_path: str, input_text: str = ""):
    return CliRunner().invoke(
        main, ["maintain", "--db", db_path], input=input_text
    )


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def _count(db_path: str, query: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(query).fetchone()[0])
    finally:
        conn.close()


# --- the CLI cases --------------------------------------------------------


def test_maintain_cli_empty_shortlist_needs_no_key_and_no_builder_call(
    db_path, monkeypatch
) -> None:
    _seed_plain(db_path)
    monkeypatch.setattr("ember.cli.build_close_proposer", _no_builder)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path)

    assert result.exit_code == 0
    assert "closed: 0, challenged: 0, reopened: 0, unchanged: 2" in result.output
    assert OUTCOME_EMPTY in result.output


def test_maintain_cli_accept_block_and_outcome_line(db_path, monkeypatch) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    monkeypatch.setattr("ember.cli.build_close_proposer", lambda env: proposer)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path, input_text="y\n")

    assert result.exit_code == 0
    lines = [
        "Proposal 1/2: item 7 [Question] should we cache tokens?",
        f"  newest answers link 11, confirmed {T_ANSWER}",
        "  no close proposed",
        "Proposal 2/2: item 9 [Question] which auth backend?",
        f"  newest answers link 12, confirmed {T_ANSWER}",
        "  reason: expired, confidence 0.8",
        "  rationale: answered long ago, no follow-up open",
        "[y]es / [n]o / [q]uit",
        "item 9: Active -> Closed (expired)",
        "closed: 1, challenged: 0, reopened: 0, unchanged: 3",
        OUTCOME_BASE.format(2, 1, 1, 0, "false"),
    ]
    # The pinned section-2/section-6 block, byte for byte. Under CliRunner the
    # user's typed answer is not echoed onto the prompt line (an interactive
    # terminal echoes it, so the line after the prompt starts on its own
    # line there), so the bytes either side of that one prompt line are
    # pinned separately and the prompt line itself as a substring.
    assert "\n".join(lines[:7]) in result.output
    assert lines[7] in result.output
    assert "\n".join(lines[8:]) in result.output
    assert _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM ai_responses") == 2


def test_maintain_cli_reject_counts_no_rows(db_path, monkeypatch) -> None:
    _seed_pair(db_path)
    proposer = FakeCloseProposer([_decline(), _proposal()])
    monkeypatch.setattr("ember.cli.build_close_proposer", lambda env: proposer)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path, input_text="n\n")

    assert result.exit_code == 0
    assert OUTCOME_BASE.format(2, 1, 0, 1, "false") in result.output
    assert _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 0
    # The only ledger rows remain the seed's two manual clears.
    assert _count(db_path, "SELECT COUNT(*) FROM change_log") == 2


def test_maintain_cli_quit_exits_2(db_path, monkeypatch) -> None:
    _seed_stale_one(db_path)
    proposer = FakeCloseProposer([_proposal()])
    monkeypatch.setattr("ember.cli.build_close_proposer", lambda env: proposer)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path, input_text="q\n")

    assert result.exit_code == 2
    assert OUTCOME_BASE.format(1, 1, 0, 0, "true") in result.output
    assert _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 0


def test_maintain_cli_decline_shows_no_close_proposed(db_path, monkeypatch) -> None:
    _seed_stale_one(db_path)
    proposer = FakeCloseProposer([_decline()])
    monkeypatch.setattr("ember.cli.build_close_proposer", lambda env: proposer)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path)

    assert result.exit_code == 0
    assert "  no close proposed" in result.output
    assert "[y]es / [n]o / [q]uit" not in result.output
    assert OUTCOME_BASE.format(1, 0, 0, 0, "false") in result.output


def test_maintain_cli_dry_run_lists_shortlist_no_key(db_path, monkeypatch) -> None:
    _seed_stale_one(db_path)
    monkeypatch.setattr("ember.cli.build_close_proposer", _no_builder)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = CliRunner().invoke(
        main, ["maintain", "--dry-run", "--db", db_path]
    )

    assert result.exit_code == 0
    assert (
        f"item 9: stale Question (newest answers link 12,"
        f" confirmed {T_ANSWER}) (dry-run)"
    ) in result.output
    assert OUTCOME_BASE.format(1, 0, 0, 0, "false") in result.output


def test_maintain_cli_missing_key_with_stale_shortlist_exits_1_close_ai_config_missing(
    db_path, monkeypatch
) -> None:
    _seed_stale_one(db_path)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path)

    assert result.exit_code == 1
    assert "MAINTAIN-020" in _error_text(result)
    assert _count(db_path, "SELECT COUNT(*) FROM change_log"
        " WHERE trigger_cause = 'user_closed'") == 0
    assert _count(db_path, "SELECT COUNT(*) FROM ai_responses") == 0


def test_maintain_cli_truncation_note(db_path, monkeypatch) -> None:
    _seed_truncated(db_path)
    proposer = FakeCloseProposer([_decline()] * 12)
    monkeypatch.setattr("ember.cli.build_close_proposer", lambda env: proposer)
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = _run_maintain(db_path)

    assert result.exit_code == 0
    assert "stale shortlist capped at 10 items (list truncated)" in result.output
    assert OUTCOME_BASE.format(10, 0, 0, 0, "false") in result.output
    assert len(proposer.calls) == 10

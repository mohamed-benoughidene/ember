"""CLI tests for the `capture` command (fake AI, real temp DB)."""

from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from ember.capture.item_proposal import (
    DroppedProposal,
    ItemProposal,
    ItemType,
    ProposalBatch,
    ProposalResponse,
)
from ember.cli import main
from tests.fakes import FakeItemProposer

SAMPLE = "We decided to use SQLite. We assume the team ships weekly."
RAW_ANSWER = "RAW-AI-ANSWER"


def _proposal(
    statement: str, quote: str, item_type: ItemType = ItemType.DECISION
) -> ItemProposal:
    return ItemProposal(
        type=item_type, statement=statement, source_quote=quote, confidence=0.9
    )


def _two_proposals() -> ProposalBatch:
    return ProposalBatch(
        proposals=[
            _proposal("Use SQLite", "use SQLite"),
            _proposal("Team ships weekly", "ships weekly", ItemType.ASSUMPTION),
        ],
        dropped=[],
    )


def _count(db_path: str, query: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(query).fetchone()[0]
    finally:
        conn.close()


def _run(tmp_path, db_path: str, batch: ProposalBatch, input_text: str, monkeypatch):
    response = ProposalResponse(raw_response=RAW_ANSWER, batch=batch)
    monkeypatch.setattr(
        "ember.cli.build_item_proposer", lambda: FakeItemProposer([response])
    )
    sample = tmp_path / "note.txt"
    sample.write_text(SAMPLE, encoding="utf-8")
    return CliRunner().invoke(
        main, ["capture", "--file", str(sample), "--db", db_path], input=input_text
    )


def test_accepting_writes_item_and_change_log_rows(db_path, tmp_path, monkeypatch) -> None:
    result = _run(tmp_path, db_path, _two_proposals(), "y\ny\n", monkeypatch)

    assert result.exit_code == 0
    assert _count(db_path, "SELECT COUNT(*) FROM items") == 2
    assert (
        _count(db_path, "SELECT COUNT(*) FROM change_log WHERE field_changed='created'")
        == 2
    )


def test_rejecting_writes_only_a_change_log_row(db_path, tmp_path, monkeypatch) -> None:
    batch = ProposalBatch(
        proposals=[_proposal("Use SQLite", "use SQLite")], dropped=[]
    )

    result = _run(tmp_path, db_path, batch, "n\n", monkeypatch)

    assert result.exit_code == 0
    assert _count(db_path, "SELECT COUNT(*) FROM items") == 0
    assert (
        _count(
            db_path, "SELECT COUNT(*) FROM change_log WHERE trigger_cause='rejected'"
        )
        == 1
    )


def test_summary_line_reports_the_counts(db_path, tmp_path, monkeypatch) -> None:
    result = _run(tmp_path, db_path, _two_proposals(), "y\nn\n", monkeypatch)

    assert result.exit_code == 0
    assert "accepted: 1, rejected: 1, warnings: 0, aborted: false" in result.output


def test_quitting_exits_2_and_leaves_the_rest(db_path, tmp_path, monkeypatch) -> None:
    result = _run(tmp_path, db_path, _two_proposals(), "y\nq\n", monkeypatch)

    assert result.exit_code == 2
    assert "aborted: true" in result.output
    assert _count(db_path, "SELECT COUNT(*) FROM items") == 1


def test_confirm_block_is_printed(db_path, tmp_path, monkeypatch) -> None:
    batch = ProposalBatch(proposals=[_proposal("Use SQLite", "use SQLite")], dropped=[])

    result = _run(tmp_path, db_path, batch, "n\n", monkeypatch)

    assert "- id: 1" in result.output
    assert 'type: "Decision"' in result.output
    assert "[y]es / [n]o / [e]dit / [q]uit" in result.output


def test_phase_2_drop_reason_is_printed(db_path, tmp_path, monkeypatch) -> None:
    batch = ProposalBatch(
        proposals=[_proposal("Use SQLite", "use SQLite")],
        dropped=[DroppedProposal(rule="type", payload={"type": "Risk"})],
    )

    result = _run(tmp_path, db_path, batch, "n\n", monkeypatch)

    assert "dropped proposal: type" in result.output


def test_zero_valid_proposals_line(db_path, tmp_path, monkeypatch) -> None:
    result = _run(
        tmp_path, db_path, ProposalBatch(proposals=[], dropped=[]), "", monkeypatch
    )

    assert result.exit_code == 0
    assert "0 valid proposals" in result.output


def test_raw_ai_answer_is_stored_verbatim(db_path, tmp_path, monkeypatch) -> None:
    batch = ProposalBatch(proposals=[_proposal("Use SQLite", "use SQLite")], dropped=[])

    result = _run(tmp_path, db_path, batch, "n\n", monkeypatch)

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT source_id, response_text FROM ai_responses"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 1
    assert row[1] == RAW_ANSWER


def test_editing_writes_the_corrected_type(db_path, tmp_path, monkeypatch) -> None:
    batch = ProposalBatch(
        proposals=[_proposal("Use SQLite", "use SQLite", ItemType.FINDING)], dropped=[]
    )

    result = _run(
        tmp_path, db_path, batch, "e\nDecision\n\ny\n", monkeypatch
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT type FROM items").fetchone()[0] == "Decision"
    finally:
        conn.close()


def test_missing_api_key_exits_1(db_path, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    sample = tmp_path / "note.txt"
    sample.write_text(SAMPLE, encoding="utf-8")

    result = CliRunner().invoke(
        main, ["capture", "--file", str(sample), "--db", db_path], input=""
    )

    assert result.exit_code == 1
    assert "CAPTURE-008" in result.output
    assert "ai api key missing" in result.output

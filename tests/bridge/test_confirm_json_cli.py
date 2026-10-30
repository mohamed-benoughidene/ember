"""Integration: the three interactive commands under `--confirm json`.

Scripted `{"answer": ...}` lines on stdin (CliRunner), faked AI/embedder at
the production seams, real temp DBs. Asserts that EVERY stdout line parses
as one JSON event object (including the lines that bypass the confirm port:
dropped proposals, gatekeeper rejections, relate rejection lines, the sweep
report), pins the event sequences, proves the capture DB state equals the
terminal run's on the same input (parity), and covers the usage error
(`capture --confirm json` without `--file`) and the no-key exits.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.bridge.confirm_scenarios import (
    capture_session,
    maintain_session,
    relate_rejections_session,
    relate_session,
)
from tests.bridge.harness import FROZEN_WRITE_TIME, sha

ANSWERS_ACCEPT_BOTH = '{"answer": "y"}\n{"answer": "n"}\n'


def _events(result) -> list[dict]:
    """Every line of the STDOUT stream (click 8.2+ mixes stderr into
    `result.output`; the event stream lives on stdout only)."""
    return [json.loads(line) for line in result.stdout.splitlines()]


# --- capture -----------------------------------------------------------------


def test_capture_json_every_line_parses_and_the_sequence_is_pinned(
    tmp_path: Path,
) -> None:
    result = capture_session(
        tmp_path, input_text=ANSWERS_ACCEPT_BOTH, extra_args=("--confirm", "json")
    )

    assert result.exit_code == 0
    events = _events(result)
    assert [event["event"] for event in events] == [
        "message",  # dropped proposal: type (bypasses the confirm port)
        "block",  # item 1
        "prompt",
        "block",  # item 2
        "prompt",
        "summary",
    ]
    assert events[0] == {"event": "message", "text": "dropped proposal: type"}
    assert events[1]["kind"] == "item"
    assert events[1]["fields"] == {
        "id": 1,
        "type": "Decision",
        "statement": "Use SQLite",
        "source_quote": "use SQLite",
        "confidence": 0.9,
        "metadata": "auth-network",
        "near_dup_warning": None,
    }
    assert events[1]["text"].startswith("- id: 1\n  type: \"Decision\"")
    assert events[2] == {
        "event": "prompt",
        "kind": "choice",
        "text": "[y]es / [n]o / [e]dit / [q]uit",
        "choices": ["y", "n", "e", "q"],
    }
    assert events[3]["kind"] == "item"
    assert events[3]["fields"]["type"] == "Assumption"
    assert events[5] == {
        "event": "summary",
        "accepted": 1,
        "rejected": 1,
        "warnings": 0,
        "aborted": False,
    }


def test_capture_json_db_equals_the_terminal_run_on_the_same_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("ember.adapters.sqlite._utc_now", lambda: FROZEN_WRITE_TIME)

    terminal = capture_session(tmp_path / "terminal", input_text="y\ny\n")
    json_run = capture_session(
        tmp_path / "json",
        input_text='{"answer": "y"}\n{"answer": "y"}\n',
        extra_args=("--confirm", "json"),
    )

    assert terminal.exit_code == json_run.exit_code == 0
    assert sha(str(tmp_path / "terminal" / "capture.db")) == sha(
        str(tmp_path / "json" / "capture.db")
    )


def test_capture_json_requires_file_stdin_conflict_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("ember.cli.build_item_proposer", _forbidden_builder)
    from click.testing import CliRunner

    from ember.cli import main

    result = CliRunner().invoke(
        main,
        ["capture", "--confirm", "json", "--db", str(tmp_path / "nope.db")],
        input="{}",
    )

    assert result.exit_code == 2
    assert "--confirm json requires --file" in result.stderr
    assert result.stdout == ""  # no stdin text consumed, no events sent


def _forbidden_builder() -> object:
    raise AssertionError("the AI must not be built for a usage error")


def test_capture_json_no_key_exits_1_before_any_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    note = tmp_path / "note.txt"
    note.write_text("We decided to use SQLite.", encoding="utf-8")
    from click.testing import CliRunner

    from ember.cli import main

    result = CliRunner().invoke(
        main,
        [
            "capture", "--file", str(note), "--confirm", "json",
            "--db", str(tmp_path / "nokey.db"),
        ],
        input='{"answer": "y"}\n',
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "CAPTURE-008" in result.stderr


def test_capture_json_bad_line_reasks_once_then_the_loop_continues(
    tmp_path: Path,
) -> None:
    result = capture_session(
        tmp_path,
        input_text='junk\n{"answer": "y"}\n{"answer": "q"}\n',
        extra_args=("--confirm", "json"),
    )

    assert result.exit_code == 2  # the final `q` aborts
    events = _events(result)
    prompts = [event for event in events if event["event"] == "prompt"]
    assert len(prompts) == 3  # item 1: ask + ONE re-ask, then item 2's ask
    summary = events[-1]
    assert summary["event"] == "summary"
    assert summary["accepted"] == 1
    assert summary["aborted"] is True


def test_capture_json_second_bad_line_aborts_with_exit_2(tmp_path: Path) -> None:
    result = capture_session(
        tmp_path,
        input_text='nope\n{"answer": 5}\n',
        extra_args=("--confirm", "json"),
    )

    assert result.exit_code == 2
    events = _events(result)
    assert [event["event"] for event in events] == [
        "message",  # dropped proposal: type
        "block",  # item 1
        "prompt",  # the ask
        "prompt",  # the ONE re-ask after `nope`
        "summary",  # the second bad line aborted
    ]
    assert events[-1]["aborted"] is True
    assert events[-1]["accepted"] == 0


def test_capture_json_edit_sub_prompts_are_prompt_events(tmp_path: Path) -> None:
    result = capture_session(
        tmp_path,
        input_text=(
            '{"answer": "e"}\n{"answer": "Finding"}\n{"answer": ""}\n'
            '{"answer": "new-label"}\n{"answer": "y"}\n{"answer": "n"}\n'
        ),
        extra_args=("--confirm", "json"),
    )

    assert result.exit_code == 0
    events = _events(result)
    kinds = [
        event.get("kind")
        for event in events
        if event["event"] == "prompt"
    ]
    assert kinds == ["choice", "type", "statement", "metadata", "choice", "choice"]
    summary = events[-1]
    assert summary == {
        "event": "summary",
        "accepted": 1,
        "rejected": 1,
        "warnings": 0,
        "aborted": False,
    }
    conn = sqlite3.connect(tmp_path / "capture.db")
    try:
        rows = conn.execute("SELECT type, metadata FROM items").fetchall()
    finally:
        conn.close()
    assert rows == [("Finding", "new-label")]


# --- relate ------------------------------------------------------------------


def test_relate_json_every_line_parses_and_the_sequence_is_pinned(
    tmp_path: Path,
) -> None:
    result = relate_session(
        tmp_path,
        input_text='{"answer": "y"}\n{"answer": "n"}\n{"answer": "s"}\n',
        extra_args=("--confirm", "json"),
    )

    assert result.exit_code == 0
    events = _events(result)
    assert [event["event"] for event in events] == [
        "block",  # link-preview 1
        "prompt",
        "block",  # link (the accepted write's YAML)
        "block",  # link-preview 2
        "prompt",
        "block",  # link-preview 3
        "prompt",
        "summary",
    ]
    assert events[0]["kind"] == "link-preview"
    assert events[0]["fields"] == {
        "index": 1,
        "total": 3,
        "source_item_id": 1,
        "target_item_id": 4,
        "link_type": "depends_on",
        "rationale": None,
    }
    assert events[2]["kind"] == "link"
    assert events[2]["fields"] == {
        "link_id": 3,
        "source_item_id": 1,
        "target_item_id": 4,
        "link_type": "depends_on",
        "status": "Confirmed",
        "rationale": None,
    }
    assert events[3]["fields"]["index"] == 2
    assert events[5]["fields"]["index"] == 3
    assert events[-1] == {
        "event": "summary",
        "accepted": 1,
        "rejected": 1,
        "skipped": 1,
        "aborted": False,
    }


def test_relate_json_rejection_lines_are_message_events(tmp_path: Path) -> None:
    result = relate_rejections_session(
        tmp_path, input_text="", extra_args=("--confirm", "json")
    )

    assert result.exit_code == 0
    events = _events(result)
    assert [event["event"] for event in events] == ["message", "message", "summary"]
    # Rule-8 gatekeeper rejects (a supersedes cycle), one line each, full
    # detail preserved as data.
    assert events[0]["text"].startswith("relate rejected: RELATE-028 | ")
    assert events[0]["text"] != events[1]["text"]
    assert events[-1] == {
        "event": "summary",
        "accepted": 0,
        "rejected": 2,
        "skipped": 0,
        "aborted": False,
    }


def test_relate_json_end_of_input_aborts_with_exit_2(tmp_path: Path) -> None:
    result = relate_session(
        tmp_path, input_text='{"answer": "y"}\n', extra_args=("--confirm", "json")
    )

    assert result.exit_code == 2  # second proposal never answered
    events = _events(result)
    summary = events[-1]
    assert summary["aborted"] is True
    assert summary["accepted"] == 1


def test_relate_json_no_key_exits_1_before_any_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # The optional embedder packages may be absent in CI; stub the boot check
    # so the FIRST error (before any event) is the missing key (RELATE-035).
    monkeypatch.setattr("ember.cli.validate_embedder_config", lambda: 120.0)
    from click.testing import CliRunner

    from ember.cli import main
    from tests.bridge.confirm_scenarios import seed_relate_pool

    seed_relate_pool(str(tmp_path / "relate.db"))

    result = CliRunner().invoke(
        main,
        [
            "relate", "--item", "1", "--db", str(tmp_path / "relate.db"),
            "--confirm", "json",
        ],
        input="",
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "RELATE-035" in result.stderr


# --- maintain ----------------------------------------------------------------


def test_maintain_json_every_line_parses_and_the_sequence_is_pinned(
    tmp_path: Path,
) -> None:
    result = maintain_session(
        tmp_path,
        input_text='{"answer": "y"}\n{"answer": "n"}\n',
        extra_args=("--confirm", "json"),
    )

    assert result.exit_code == 0
    events = _events(result)
    assert [event["event"] for event in events] == [
        "message",  # the sweep report's summary line
        "block",  # decline: no prompt follows
        "block",  # proposal 2/2
        "prompt",
        "message",  # accepted-close report line
        "message",  # accepted-close summary counts
        "summary",
    ]
    assert events[0] == {
        "event": "message",
        "text": "closed: 0, challenged: 0, reopened: 0, unchanged: 4",
    }
    assert events[1]["kind"] == "close"
    assert events[1]["fields"]["item_id"] == 7
    assert "reason" not in events[1]["fields"]  # a decline block
    assert events[2]["kind"] == "close"
    assert events[2]["fields"] == {
        "index": 2,
        "total": 2,
        "item_id": 9,
        "item_type": "Question",
        "statement": "which auth backend?",
        "newest_answers_link_id": 12,
        "newest_answer_created_at": "2026-01-01T00:00:00+00:00",
        "reason": "expired",
        "confidence": 0.8,
        "rationale": "answered long ago, no follow-up open",
    }
    assert events[3]["choices"] == ["y", "n", "q"]
    assert events[4] == {"event": "message", "text": "item 9: Active -> Closed (expired)"}
    assert events[5]["text"] == "closed: 1, challenged: 0, reopened: 0, unchanged: 3"
    assert events[-1] == {
        "event": "summary",
        "stale": 2,
        "proposed": 1,
        "accepted": 1,
        "rejected": 0,
        "aborted": False,
    }


def test_maintain_json_quit_answers_summarize_as_aborted(tmp_path: Path) -> None:
    result = maintain_session(
        tmp_path, input_text='{"answer": "q"}\n', extra_args=("--confirm", "json")
    )

    # Candidate 7 declines (no prompt); candidate 9 prompts and the user
    # quits, so nothing further is proposed and the exit is 2.
    assert result.exit_code == 2
    summary = _events(result)[-1]
    assert summary["event"] == "summary"
    assert summary["accepted"] == 0
    assert summary["proposed"] == 1
    assert summary["aborted"] is True


def test_maintain_json_document_mode_wraps_the_document_as_a_message(
    tmp_path: Path,
) -> None:
    """`--format json` + `--confirm json`: every stdout line still parses;
    the step-01 document rides the output sink as a message event (the
    event stream owns stdout when confirm is json)."""
    result = maintain_session(
        tmp_path,
        input_text='{"answer": "y"}\n{"answer": "n"}\n',
        extra_args=("--format", "json", "--confirm", "json"),
    )

    assert result.exit_code == 0
    events = _events(result)
    assert events[-1]["event"] == "message"
    document = json.loads(events[-1]["text"])
    assert document["command"] == "maintain"
    assert document["summary"]["accepted"] == 1
    assert document["summary"]["proposed"] == 1


def test_maintain_json_no_key_exits_1_after_the_sweep_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from click.testing import CliRunner

    from ember.cli import main
    from tests.bridge.confirm_scenarios import seed_two_stale_questions

    seed_two_stale_questions(str(tmp_path / "maintain.db"))

    result = CliRunner().invoke(
        main,
        [
            "maintain", "--db", str(tmp_path / "maintain.db"),
            "--confirm", "json",
        ],
        input="",
    )

    # The sweep report legitimately precedes Phase 5, so events are already
    # on stdout when the key check fails — the error itself rides stderr.
    assert result.exit_code == 1
    assert "MAINTAIN-020" in result.stderr
    assert all(json.loads(line) for line in result.stdout.splitlines())


# --- review fix, ticket 24: the dry-run shortlist lines ride the sink --------


def test_maintain_dry_run_json_shortlist_lines_are_message_events(
    tmp_path: Path,
) -> None:
    """The pre-apply shortlist lines bypass the confirm port, so under
    `--confirm json` each one is one `message` event (L2 §5.4), one per
    candidate — the same bytes the terminal echoes in text mode."""
    from click.testing import CliRunner

    from ember.cli import main
    from tests.bridge.confirm_scenarios import seed_two_stale_questions

    seed_two_stale_questions(str(tmp_path / "maintain.db"))
    result = CliRunner().invoke(
        main,
        [
            "maintain", "--dry-run", "--confirm", "json",
            "--db", str(tmp_path / "maintain.db"),
        ],
        input="",
    )

    assert result.exit_code == 0, result.output
    events = _events(result)
    shortlist = [
        event["text"]
        for event in events
        if event["event"] == "message" and event["text"].startswith("item ")
    ]
    assert shortlist == [
        "item 7: stale Question (newest answers link 11,"
        " confirmed 2026-01-01T00:00:00+00:00) (dry-run)",
        "item 9: stale Question (newest answers link 12,"
        " confirmed 2026-01-01T00:00:00+00:00) (dry-run)",
    ]
    summary = events[-1]
    assert summary["event"] == "summary"
    assert summary["stale"] == 2


# --- the choice itself -------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "session"),
    [
        (["capture", "--file", "note.txt"], "capture"),
        (["relate", "--item", "1"], "relate"),
        (["maintain"], "maintain"),
    ],
)
def test_unknown_confirm_value_is_a_click_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str], session: str
) -> None:
    from click.testing import CliRunner
    from ember.cli import main

    if session == "capture":
        (tmp_path / "note.txt").write_text("text", encoding="utf-8")
    if session == "relate":
        from tests.bridge.confirm_scenarios import seed_relate_pool

        seed_relate_pool(str(tmp_path / "relate.db"))
        argv = [*argv, "--db", str(tmp_path / "relate.db")]
    if session == "maintain":
        argv = [*argv, "--db", str(tmp_path / "maintain.db")]
    else:
        argv = [*argv, "--db", str(tmp_path / f"{session}.db")]

    result = CliRunner().invoke(
        main, [*argv, "--confirm", "xml"], input="", catch_exceptions=False
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.stderr

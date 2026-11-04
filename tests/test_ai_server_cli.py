"""CLI seams against a fake provider server (Batch 7 Chunk 15).

The spec's Testing Decisions seams 1, 3 and 4 on real temp databases: a real
`ember` CLI run, real `EMBER_AI_API_KEY` (a fake value) and the real AI
adapter pointed at the fake through `EMBER_AI_BASE_URL`. These are PIN-style
tests: they characterize behavior Chunks 1-3 (the ONE retry policy), Chunk 6
(input limits) and Chunk 8 (quote rule) already built — no code was written
for them — so their value is proving it holds together at the CLI edge.

Offline everywhere: the fake binds 127.0.0.1 only and answers from saved
fixtures; nothing outside this process is contacted.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.cli import main
from tests.fake_ai_server import start_fake_ai_server

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_responses"
# Small so the wait the retry policy sleeps is one real second at most.
RETRY_AFTER = 1.0

FAKE_KEY = "sk-fake-clitest"  # fake only — never a real key


def _real_ai_env(monkeypatch: pytest.MonkeyPatch, url: str, tmp_path: Path) -> None:
    """Point the real adapter at the fake with a fake key, nothing else."""
    monkeypatch.setenv("EMBER_AI_API_KEY", FAKE_KEY)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("EMBER_AI_MODEL", raising=False)
    monkeypatch.setenv("EMBER_AI_BASE_URL", url)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _count(db_path: str, query: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(query).fetchone()[0]
    finally:
        conn.close()


def test_429_twice_waits_then_the_family_rate_limit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two 429 replies: the ONE retry policy waits `Retry-After` between the
    two arrivals, then fails with the capture family rate-limit code (exit 1).
    """
    note = tmp_path / "note.txt"
    note.write_text(
        (FIXTURE_DIR / "case_01.raw_text.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # count_429 high: BOTH attempts hit the 429, so the fake sees 2 requests.
    fake = start_fake_ai_server(mode="429", count_429=99, retry_after=RETRY_AFTER)
    try:
        _real_ai_env(monkeypatch, fake.url, tmp_path)
        result = CliRunner().invoke(
            main, ["capture", "--file", str(note), "--db", str(tmp_path / "kb.db")]
        )
    finally:
        fake.close()

    assert len(fake.calls) == 2
    waited = fake.calls[1]["arrival"] - fake.calls[0]["arrival"]
    assert waited >= RETRY_AFTER
    assert result.exit_code == 1
    assert "CAPTURE-024" in result.stderr


def test_6mb_stdin_and_empty_file_make_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Oversized STDIN and an empty file are both refused before any AI
    call — the fake's request log stays empty after both refusals."""
    fake = start_fake_ai_server(mode="normal")
    try:
        _real_ai_env(monkeypatch, fake.url, tmp_path)
        db = str(tmp_path / "kb.db")
        big_input = "x" * (6 * 1024 * 1024)  # 6 MB > MAX_SOURCE_BYTES (5 MB)

        too_large = CliRunner().invoke(
            main, ["capture", "--db", db], input=big_input
        )
        empty = tmp_path / "note.txt"
        empty.write_text("", encoding="utf-8")
        empty_file = CliRunner().invoke(
            main, ["capture", "--file", str(empty), "--db", db], input=""
        )
    finally:
        fake.close()

    assert too_large.exit_code == 1
    assert "CAPTURE-002" in too_large.output
    assert empty_file.exit_code == 1
    assert "CAPTURE-026" in empty_file.output
    assert fake.calls == []


def test_one_letter_quote_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proposal whose quote is one letter fails the quote rule at the
    boundary: it is dropped (rule `quote`) and never becomes an item."""
    note = tmp_path / "note.txt"
    note.write_text(
        "We picked a direction today for the notes and will review it soon.",
        encoding="utf-8",
    )
    answer = json.dumps(
        [
            {
                "type": "Decision",
                "statement": "A direction was picked today",
                "source_quote": "a",
                "confidence": 0.9,
            }
        ]
    )
    fake = start_fake_ai_server(mode="normal", content=answer)
    try:
        _real_ai_env(monkeypatch, fake.url, tmp_path)
        db = str(tmp_path / "kb.db")
        result = CliRunner().invoke(
            main, ["capture", "--file", str(note), "--db", db], input=""
        )
    finally:
        fake.close()

    assert result.exit_code == 0
    assert "dropped proposal: quote" in result.output
    assert "0 valid proposals" in result.output
    assert _count(db, "SELECT COUNT(*) FROM items") == 0


@pytest.mark.slow
def test_hung_provider_ends_in_the_family_ai_timeout_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider that accepts the connection and never answers: the engine's
    own 60 s request timeout fires first, so the capture ends in the family
    AI-timeout code (CAPTURE-025) — well inside the app's 120 s idle limit,
    the engine timeout is what the user sees, never the app idle timeout."""
    note = tmp_path / "note.txt"
    note.write_text(
        (FIXTURE_DIR / "case_01.raw_text.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fake = start_fake_ai_server(mode="hang")
    try:
        _real_ai_env(monkeypatch, fake.url, tmp_path)
        started = time.monotonic()
        result = CliRunner().invoke(
            main, ["capture", "--file", str(note), "--db", str(tmp_path / "kb.db")]
        )
        elapsed = time.monotonic() - started
    finally:
        fake.close()

    assert len(fake.calls) == 1  # one request, never answered
    assert elapsed < 120.0  # the engine timeout fires, not the app idle limit
    assert result.exit_code == 1
    assert "CAPTURE-025" in result.stderr
    print(f"hung-provider elapsed: {elapsed:.1f}s")

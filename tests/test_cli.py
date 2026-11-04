"""CLI tests for the phase 1 `capture-source` command."""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from ember.adapters.sqlite import open_database
from ember.cli import main


def _seed_knowledge_base(db_path: str) -> None:
    """Create the file as `ember init` does (D-25: capture-source refuses
    a missing file; these tests pin phase-1 store/dedup, not creation)."""
    open_database(db_path).close()


def _rows(db_path: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT id, title FROM sources ORDER BY id").fetchall()
    finally:
        conn.close()


def _payload(result) -> dict:
    for line in result.output.splitlines():
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON line in output: {result.output!r}")


def test_file_mode_prints_source_reference(db_path, tmp_path) -> None:
    _seed_knowledge_base(db_path)
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(
        main, ["capture-source", "--file", str(sample), "--db", db_path]
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["source_id"] == 1
    assert payload["raw_text"] == "hello"
    assert len(_rows(db_path)) == 1


def test_stdin_mode_and_dedup_message(db_path) -> None:
    _seed_knowledge_base(db_path)
    runner = CliRunner()

    first = runner.invoke(main, ["capture-source", "--db", db_path], input="hello")
    second = runner.invoke(main, ["capture-source", "--db", db_path], input="hello")

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert _payload(first)["source_id"] == _payload(second)["source_id"]
    assert "source already stored" in second.output
    assert len(_rows(db_path)) == 1


def test_missing_file_exits_1(db_path, tmp_path) -> None:
    result = CliRunner().invoke(
        main, ["capture-source", "--file", str(tmp_path / "nope.txt"), "--db", db_path]
    )

    assert result.exit_code == 1
    assert "CAPTURE-001" in result.output
    assert "file not found" in result.output


def test_invalid_utf8_exits_1(db_path, tmp_path) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe")

    result = CliRunner().invoke(
        main, ["capture-source", "--file", str(bad), "--db", db_path]
    )

    assert result.exit_code == 1
    assert "CAPTURE-004" in result.output
    assert "invalid utf-8" in result.output


# --- D-20: the refused flag combinations (Batch 6 chunk 8) -------------------
# N6: a usage error keeps Click's own exit 2 and names the flag; no CODE.


def test_capture_refuses_format_json(db_path) -> None:
    """`capture --format json` is refused: the confirm loop's program-facing
    mode is the `--confirm json` event stream, not the document format."""
    result = CliRunner().invoke(
        main, ["capture", "--format", "json", "--db", db_path], input="hello"
    )

    assert result.exit_code == 2
    assert "--format" in result.stderr
    assert "CAPTURE-" not in result.stderr


def test_relate_refuses_format_json(db_path) -> None:
    """`relate --format json` is refused like `capture`'s, for the same
    reason (the event stream is the program mode)."""
    result = CliRunner().invoke(
        main, ["relate", "--latest", "--format", "json", "--db", db_path]
    )

    assert result.exit_code == 2
    assert "--format" in result.stderr
    assert "RELATE-" not in result.stderr


def test_capture_empty_file_name_exits_2_not_stdin(db_path) -> None:
    """`--file ""` must be refused: today the empty string is falsy, so the
    command falls back to reading STDIN (`ember/cli.py`, capture body)."""
    result = CliRunner().invoke(
        main, ["capture", "--file", "", "--db", db_path], input="hello"
    )

    assert result.exit_code == 2
    assert "--file" in result.stderr

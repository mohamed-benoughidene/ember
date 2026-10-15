"""CLI tests for the phase 1 `capture-source` command."""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from ember.cli import main


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
    assert "file not found" in result.output


def test_invalid_utf8_exits_1(db_path, tmp_path) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe")

    result = CliRunner().invoke(
        main, ["capture-source", "--file", str(bad), "--db", db_path]
    )

    assert result.exit_code == 1
    assert "invalid utf-8" in result.output

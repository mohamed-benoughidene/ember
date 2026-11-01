"""Chunk 2 (Batch 2): the CLI edge handler, EMBER-000, and the crash file.

Two tests: a forced unexpected exception gives exactly one `error: EMBER-000
InternalError | ...` house line on stderr, exit 1, and a crash file under
$XDG_STATE_HOME/ember/crashes/ that keeps the traceback but no secrets; a
broken pipe gives the house line only, exit 1, and no crash file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.cli import _handle_unexpected, main

_PLANTED_KEY = "sk-plant0987654321abcdef"
_STATE_ROOT = Path("/tmp/opencode/batch2/chunk2")


def _boom(store: object, raw_text: str) -> object:
    """The substitute raise site: patching this over `store_source` forces
    an unexpected exception whose innermost frame lives in THIS module."""
    raise RuntimeError("boom")


def test_forced_unexpected_exception_gives_one_ember_000_line_and_a_crash_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(_STATE_ROOT))
    monkeypatch.setenv("EMBER_AI_API_KEY", _PLANTED_KEY)
    monkeypatch.setattr("ember.cli.store_source", _boom)

    db_path = tmp_path / "x.db"
    result = CliRunner().invoke(main, ["capture-source", "--db", str(db_path)], input="hello")

    assert result.exit_code == 1
    stderr_lines = (result.stderr or "").splitlines()
    assert len(stderr_lines) == 1, stderr_lines
    line = stderr_lines[0]
    assert line.startswith("error: EMBER-000 InternalError"), line
    # names a `module.function`: the innermost traceback frame — the
    # substitute's raise site in this test module
    assert "test_cli_error_boundary._boom" in line, line
    assert "crash=" in line, line
    crash_id = line.split("crash=")[1].strip()

    crash_file = _STATE_ROOT / "ember" / "crashes" / f"{crash_id}.txt"
    assert crash_file.exists(), crash_file
    text = crash_file.read_text(encoding="utf-8")
    assert "Traceback (most recent call last):" in text
    assert "RuntimeError: boom" in text
    assert _PLANTED_KEY not in text


def test_broken_pipe_ends_with_a_house_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(_STATE_ROOT))

    with pytest.raises(SystemExit) as exc_info:
        _handle_unexpected(BrokenPipeError(), command="capture-source")

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    lines = err.splitlines()
    assert len(lines) == 1, lines
    assert lines[0].startswith("error: EMBER-000 InternalError"), lines[0]
    assert "output pipe closed" in lines[0], lines[0]
    assert "crash=" not in lines[0], lines[0]

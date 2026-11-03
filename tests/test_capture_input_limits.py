"""Capture input limits (Batch 7 chunk 6, stories 4/5, finding 4.5 #16).

Pins: STDIN is capped at the same MAX_SOURCE_BYTES as files (CAPTURE-002),
and empty input is refused with its own new code BEFORE any AI call —
the forbidden-builder pattern proves `build_item_proposer` is never used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.capture.errors import SourceEmpty, SourceFileTooLarge
from ember.capture.input_reader import InputMode, read_raw_text
from ember.cli import main


def _forbidden_builder() -> object:
    raise AssertionError("the AI must not be built for an input-limit error")


def _capture_argv(tmp_path: Path, file: str | None) -> list[str]:
    argv = ["capture", "--db", str(tmp_path / "kb.db")]
    if file is not None:
        argv.extend(["--file", file])
    return argv


def test_stdin_over_5_mb_exits_1_with_too_large_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ember.cli.build_item_proposer", _forbidden_builder)
    big_input = "x" * (6 * 1024 * 1024)  # 6 MB > MAX_SOURCE_BYTES (5 MB)

    result = CliRunner().invoke(main, _capture_argv(tmp_path, file=None), input=big_input)

    assert result.exit_code == 1
    assert "CAPTURE-002" in result.output
    assert "SourceFileTooLarge" in result.output


def test_empty_stdin_exits_1_with_empty_input_code_before_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ember.cli.build_item_proposer", _forbidden_builder)

    result = CliRunner().invoke(main, _capture_argv(tmp_path, file=None), input="")

    assert result.exit_code == 1
    # If the pipeline reached the AI, the forbidden builder raised and the
    # output would hold EMBER-000 InternalError, never the empty-input code.
    assert "CAPTURE-026" in result.output


def test_empty_file_exits_1_with_empty_input_code_before_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ember.cli.build_item_proposer", _forbidden_builder)
    note = tmp_path / "note.txt"
    note.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        main, _capture_argv(tmp_path, file=str(note)), input=""
    )

    assert result.exit_code == 1
    assert "CAPTURE-026" in result.output


def test_whitespace_only_stdin_refused_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ember.cli.build_item_proposer", _forbidden_builder)

    result = CliRunner().invoke(main, _capture_argv(tmp_path, file=None), input="\n\n")

    assert result.exit_code == 1
    assert "CAPTURE-026" in result.output


def test_read_raw_text_empty_file_direct(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("", encoding="utf-8")

    with pytest.raises(SourceEmpty) as excinfo:
        read_raw_text(mode=InputMode.FILE, path=str(note))

    assert excinfo.value.code == "CAPTURE-026"
    assert excinfo.value.name == "SourceEmpty"


def test_read_raw_text_stdin_returns_normal_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeStdin:
        class buffer:  # noqa: N801 - mirrors sys.stdin.buffer
            @staticmethod
            def read() -> bytes:
                return "hello".encode("utf-8")

    monkeypatch.setattr("sys.stdin", _FakeStdin())
    text = read_raw_text(mode=InputMode.STDIN)

    assert text == "hello"


def test_too_large_error_is_the_pinned_code() -> None:
    assert SourceFileTooLarge("file too large").code == "CAPTURE-002"

"""Tests for the CLI `--version` option."""

from __future__ import annotations

from click.testing import CliRunner

from ember import __version__
from ember.cli import main


def test_main_has_version_option() -> None:
    """`ember --version` exits 0 and prints the engine version."""
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output

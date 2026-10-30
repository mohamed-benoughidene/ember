"""Terminal-mode byte identity for the three interactive commands (step 03).

The goldens in `fixtures/bridge/confirm_goldens/` were captured from the
UNMODIFIED tree (before step 03 touched `ember/cli.py`) with the exact
session builders in `tests/bridge/confirm_scenarios.py`. This test replays
the same sessions on the current code with `--confirm` at its default
(terminal) and asserts the stdout bytes, line counts and exit codes are
unchanged — the `terminal` mode is byte-identical proof for capture, relate
and maintain, including the lines that bypass the confirm port.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.bridge.confirm_scenarios import (
    GOLDEN_DIR,
    capture_session,
    maintain_session,
    relate_session,
)

GOLDEN_LINES = {"capture.txt": 16, "relate.txt": 13, "maintain.txt": 11}


@pytest.mark.parametrize(
    "golden_name", ["capture.txt", "relate.txt", "maintain.txt"]
)
def test_terminal_session_is_byte_identical_to_the_pre_change_golden(
    tmp_path: Path, golden_name: str
) -> None:
    session = {
        "capture.txt": capture_session,
        "relate.txt": relate_session,
        "maintain.txt": maintain_session,
    }[golden_name]
    result = session(tmp_path)

    assert result.exit_code == 0
    golden = (GOLDEN_DIR / golden_name).read_text(encoding="utf-8")
    # stdout only (click 8.2+ mixes stderr into `result.output`).
    assert result.stdout == golden
    assert len(result.stdout.splitlines()) == GOLDEN_LINES[golden_name]

"""The measurement script's command line: `--help` starts, and an existing
database outside the temp directory is refused and never touched."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "measure_model_change.py"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the script exactly as an operator would, with no AI key set."""
    env = dict(os.environ)
    env.pop("EMBER_AI_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_help_exits_zero() -> None:
    result = run_script("--help")
    assert result.returncode == 0, result.stderr


def test_refuses_an_existing_db_outside_temp() -> None:
    target = Path(__file__).parent / "_measure_refusal_target.db"
    target.write_bytes(b"seed")
    digest_before = hashlib.sha256(target.read_bytes()).hexdigest()
    try:
        result = run_script("--db", str(target))
        assert result.returncode != 0, result.stdout
        digest_after = hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        target.unlink(missing_ok=True)
    assert digest_after == digest_before

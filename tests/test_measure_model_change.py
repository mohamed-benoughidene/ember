"""The measurement script's command line: `--help` starts, and an existing
database outside the temp directory is refused and never touched."""

from __future__ import annotations

import hashlib
import importlib.util
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


def test_failed_run_leaves_no_database(tmp_path: Path, monkeypatch) -> None:
    """An embedder failure mid-run must never leave a database behind.

    The script is loaded as a module (it already puts the repo on `sys.path`
    itself), its `SentenceTransformerEmbedder` is replaced with a class that
    raises on construction, and `main()` runs with `--db` inside this test's
    own temp folder. Whatever way the run fails (a non-zero return, or the
    error escaping as an exception), no `*.db`, `-wal`, `-shm`, `-journal`
    or `.bak-v*` file may remain in that folder.
    """
    spec = importlib.util.spec_from_file_location("measure_model_change_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class ExplodingEmbedder:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("embedder explodes on construction in this test")

    monkeypatch.setattr(module, "SentenceTransformerEmbedder", ExplodingEmbedder)
    monkeypatch.setattr(sys, "argv", ["measure_model_change.py", "--db", str(tmp_path / "failed-run.db")])

    try:
        return_value = module.main()
    except Exception:
        # Today the failure escapes `main()` before the cleanup `try`: the
        # escape itself is a failed run, so it counts as a non-zero outcome.
        return_value = 1
    assert return_value != 0

    leftovers = sorted(
        entry.name
        for entry in tmp_path.iterdir()
        if entry.name.endswith((".db", "-wal", "-shm", "-journal")) or ".bak-v" in entry.name
    )
    assert leftovers == [], leftovers


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

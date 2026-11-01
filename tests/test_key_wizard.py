"""Tests for scripts/ember-key-wizard.sh, run on a COPY inside a temp git repo.

The wizard derives its key-file path from its own location and writes .env
next to itself, so the tests must never run the real script in the real
repo: they always copy it into a throwaway git repo first.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest  # noqa: F401  (tmp_path fixture)

REPO_ROOT = Path(__file__).resolve().parent.parent
WIZARD_SCRIPT = REPO_ROOT / "scripts" / "ember-key-wizard.sh"

FAKE_KEY = "sk-or-v1-TESTKEY000000000000000000000000000"
# Piped answers: the banner pause, the key, an empty model line
# (verified working, check report §3).
PIPED_ANSWERS = f"yes\n{FAKE_KEY}\n\n"


def run_wizard_copy(
    tmp_path: Path, gitignore: str
) -> tuple[subprocess.CompletedProcess, bool]:
    """Copy the wizard into a fresh temp git repo and run the COPY there.

    Returns the completed run and whether an EMBER_AI_API_KEY= line was
    found on disk (checked BEFORE the folder is removed).
    """
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    # The helper owns the .gitignore content; callers choose whether it
    # covers .env or not.
    (repo / ".gitignore").write_text(gitignore, encoding="utf-8")
    # Same relative layout as the real repo (scripts/…): the wizard derives
    # its key-file root from its own location, so the copy must sit one
    # level below the repo root for the derivation to land inside the repo.
    shutil.copy2(WIZARD_SCRIPT, repo / "scripts" / "ember-key-wizard.sh")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    # Isolate git's ignore lookup from the machine's global/system config so
    # only this repo's .gitignore decides whether .env is ignored.
    empty_gitconfig = tmp_path / "empty-gitconfig"
    empty_gitconfig.touch()
    env = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "GIT_CONFIG_GLOBAL": str(empty_gitconfig),
        "GIT_CONFIG_SYSTEM": str(empty_gitconfig),
    }
    try:
        proc = subprocess.run(
            ["bash", str(repo / "scripts" / "ember-key-wizard.sh")],
            input=PIPED_ANSWERS,
            text=True,
            capture_output=True,
            cwd=repo,
            env=env,
        )
        wrote_key = key_on_disk(repo)
        return proc, wrote_key
    finally:
        # Removes the folder after the run, including any .env it wrote,
        # so a leaked key never survives the test.
        shutil.rmtree(repo)


def _script_copies(path: Path) -> bool:
    return path.is_file() and path.name == "ember-key-wizard.sh"


def key_on_disk(repo: Path) -> bool:
    """True when any file under the repo holds an EMBER_AI_API_KEY= line."""
    for path in repo.rglob("*"):
        if _script_copies(path) or ".git" in path.relative_to(repo).parts:
            continue
        try:
            if "EMBER_AI_API_KEY=" in path.read_text(encoding="utf-8"):
                return True
        except (UnicodeDecodeError, OSError):
            continue
    return False


def test_not_gitignored_refuses_and_writes_nothing(tmp_path: Path):
    """A key file that .gitignore does not cover is refused; nothing is written."""
    # The .gitignore deliberately does NOT cover .env.
    proc, wrote_key = run_wizard_copy(tmp_path, gitignore="__pycache__/\n")
    assert proc.returncode != 0, (
        f"expected non-zero exit, got 0. stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert not wrote_key, f"the key was written to disk. stderr:\n{proc.stderr}"

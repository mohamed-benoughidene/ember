"""Tests for scripts/ember-key-wizard.sh, run on a COPY inside a temp git repo.

The wizard derives its key-file path from its own location and writes .env
next to itself, so the tests must never run the real script in the real
repo: they always copy it into a throwaway git repo first.
"""

from __future__ import annotations

import os
import re
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
# A 29-character key of plain letters and digits, for the length test.
FAKE_KEY_29 = ("abc123" * 5)[:29]
# The wizard's open_url calls xdg-open, which would open the keys page in a
# real desktop browser on every test run. A stub xdg-open is put FIRST on
# PATH so the copy's open_url finds the stub and opens nothing.
STUB_DIR = Path("/tmp/opencode/batch0/chunk4/stub")


def _ensure_xdg_open_stub() -> None:
    """Create the no-op xdg-open stub if it is missing (idempotent)."""
    STUB_DIR.mkdir(parents=True, exist_ok=True)
    stub = STUB_DIR / "xdg-open"
    if not stub.exists():
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)


def run_wizard_copy(
    tmp_path: Path,
    gitignore: str,
    key: str = FAKE_KEY,
    pre_env_mode: int | None = None,
) -> tuple[subprocess.CompletedProcess, bool, int | None]:
    """Copy the wizard into a fresh temp git repo and run the COPY there.

    pre_env_mode: when set, pre-create an empty repo/.env with this mode
    before the run. Returns the completed run, whether an
    EMBER_AI_API_KEY= line was found on disk, and the .env mode after the
    run (None when .env does not exist) — all captured BEFORE the folder
    is removed.
    """
    _ensure_xdg_open_stub()
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
    if pre_env_mode is not None:
        env_file = repo / ".env"
        env_file.write_text("", encoding="utf-8")
        env_file.chmod(pre_env_mode)
    # Isolate git's ignore lookup from the machine's global/system config so
    # only this repo's .gitignore decides whether .env is ignored.
    empty_gitconfig = tmp_path / "empty-gitconfig"
    empty_gitconfig.touch()
    env = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "GIT_CONFIG_GLOBAL": str(empty_gitconfig),
        "GIT_CONFIG_SYSTEM": str(empty_gitconfig),
        "PATH": f"{STUB_DIR}:{os.environ.get('PATH', '')}",
    }
    try:
        proc = subprocess.run(
            ["bash", str(repo / "scripts" / "ember-key-wizard.sh")],
            input=f"yes\n{key}\n\n",
            text=True,
            capture_output=True,
            cwd=repo,
            env=env,
        )
        wrote_key = key_on_disk(repo)
        env_file = repo / ".env"
        env_mode = env_file.stat().st_mode & 0o777 if env_file.exists() else None
        return proc, wrote_key, env_mode
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
    proc, wrote_key, _env_mode = run_wizard_copy(tmp_path, gitignore="__pycache__/\n")
    assert proc.returncode != 0, (
        f"expected non-zero exit, got 0. stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert not wrote_key, f"the key was written to disk. stderr:\n{proc.stderr}"


def test_existing_env_file_644_ends_at_600(tmp_path: Path):
    """Regression pin: a pre-existing 644 .env ends as 600, key present."""
    proc, wrote_key, env_mode = run_wizard_copy(
        tmp_path, gitignore=".env\n", pre_env_mode=0o644
    )
    assert proc.returncode == 0, (
        f"expected zero exit, got {proc.returncode}. stderr:\n{proc.stderr}"
    )
    assert wrote_key, f"the key was not written to disk. stderr:\n{proc.stderr}"
    assert env_mode == 0o600, f"expected .env mode 600, got {oct(env_mode) if env_mode else env_mode}"


def test_reported_length_matches_the_key(tmp_path: Path):
    """The printed \"N chars\" number is the real key length (29)."""
    proc, wrote_key, _env_mode = run_wizard_copy(
        tmp_path, gitignore=".env\n", key=FAKE_KEY_29
    )
    assert proc.returncode == 0, (
        f"expected zero exit, got {proc.returncode}. stderr:\n{proc.stderr}"
    )
    assert wrote_key, f"the key was not written to disk. stderr:\n{proc.stderr}"
    match = re.search(r"(\d+) chars", proc.stdout)
    assert match, f"no \"N chars\" line in stdout:\n{proc.stdout}"
    assert int(match.group(1)) == len(FAKE_KEY_29) == 29, (
        f"reported {match.group(1)} chars for a 29-char key. stdout:\n{proc.stdout}"
    )


def test_banner_states_linux_only_and_no_other_openers(tmp_path: Path):
    """The wizard says it is Linux-only, and xdg-open is the only opener (D-22)."""
    proc, wrote_key, _env_mode = run_wizard_copy(tmp_path, gitignore=".env\n")
    assert proc.returncode == 0, (
        f"expected zero exit, got {proc.returncode}. stderr:\n{proc.stderr}"
    )
    assert wrote_key, f"the key was not written to disk. stderr:\n{proc.stderr}"
    assert "Linux only" in proc.stdout, (
        f"no Linux-only statement in the wizard output. stdout:\n{proc.stdout}"
    )
    assert "WSL" not in proc.stdout, f"output still mentions WSL. stdout:\n{proc.stdout}"
    assert "macOS" not in proc.stdout, (
        f"output still mentions macOS. stdout:\n{proc.stdout}"
    )
    # The opener branches only run on other systems, so the removal cannot be
    # observed here; pin it as text (same style as tests/test_architecture.py).
    text = WIZARD_SCRIPT.read_text(encoding="utf-8")
    # The warn fallback says "couldn't open a browser", so the plain `open`
    # command is matched by its `command -v` check instead.
    for gone in ("wslview", "explorer.exe", "command -v open "):
        assert gone not in text, f"the opener branch {gone!r} is still in the script"
    assert "xdg-open" in text, "the xdg-open opener is missing"

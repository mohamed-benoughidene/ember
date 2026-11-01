"""The crash report: where EMBER-000 keeps the full traceback.

Spec-Batch2, decision N4 — the crash file lives under
`$XDG_STATE_HOME/ember/crashes` (default `~/.local/state/ember/crashes`
when the variable is unset), named `<crash id>.txt`. The app resolves
the SAME folder with the SAME rule (`app/main/crash-file.js`), because
engine children inherit the app's environment.

Everything written here goes through `scrub_secrets` (Batch 2 Chunk 1),
so no key-shaped secret reaches the file. Per decision N7 the traceback
keeps FULL paths — this file is the one place a user may copy from, so
paths are not shortened.

Pure this module is not: `write_crash_file` creates the folder and the
file. `crash_id` and `crash_dir` are pure string/path rules.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ember import __version__
from ember.errors import scrub_secrets

_TIME_FORMAT = "%Y%m%dT%H%M%SZ"


def crash_id() -> str:
    """Return a fresh crash id: `<UTC timestamp>-<6 hex>`, e.g.
    `20261101T120000Z-a1b2c3`. The timestamp is UTC (the `Z` says so);
    the hex suffix keeps two crashes in the same second distinct."""
    stamp = datetime.now(timezone.utc).strftime(_TIME_FORMAT)
    return f"{stamp}-{secrets.token_hex(3)}"


def crash_dir() -> str:
    """Return the crash folder by the N4 XDG rule:
    `$XDG_STATE_HOME/ember/crashes`, default `~/.local/state/ember/crashes`."""
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = str(Path.home() / ".local" / "state")
    return str(Path(state_home) / "ember" / "crashes")


def write_crash_file(*, command: str, traceback_text: str) -> str:
    """Write one crash file and return its crash id.

    The file holds, in order: the engine version (from `ember/__init__.py`,
    Batch 1's ONE version source — the report §4.2 fix), the command name
    WITHOUT arguments (arguments may carry user text), the time, and the
    full traceback with full paths (N7). Every line passes through
    `scrub_secrets` before it is written.
    """
    cid = crash_id()
    header = "\n".join(
        [
            f"ember version: {__version__}",
            f"command: {command}",
            f"time: {datetime.now(timezone.utc).strftime(_TIME_FORMAT)}",
            "",
        ]
    )
    body = scrub_secrets(header + traceback_text.rstrip() + "\n")

    directory = Path(crash_dir())
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{cid}.txt").write_text(body, encoding="utf-8")
    return cid

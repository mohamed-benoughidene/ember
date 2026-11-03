"""Numbered SQLite schema migrations — the ONE source of the latest version.

`LATEST_VERSION` below is DERIVED from the `NN_*.sql` scripts shipped in
this directory (issue #45): adding the next migration `.sql` file is the
whole bump, with no by-hand version pin to update anywhere. The import-time
derivation reads THIS package's listing, not whatever module a test
monkeypatches script discovery to, so a sabotaged script directory is
still measured against the real shipped set (`ScriptSetInvalid`,
MIGRATION-001, checked in `ember.adapters.sqlite`).
"""

from __future__ import annotations

import importlib.resources


def _derive_latest_version() -> int:
    """Return the highest `NN` prefix among this package's `.sql` scripts."""
    package = importlib.resources.files(__name__)
    return max(
        int(entry.name.split("_", 1)[0])
        for entry in package.iterdir()
        if entry.name.endswith(".sql")
    )


LATEST_VERSION = _derive_latest_version()

"""Path guards shared by the utility adapters (L2 review: dedup of _same_file)."""

from __future__ import annotations

import os


def same_path(first: str, second: str) -> bool:
    """True when both paths name one existing file, or one canonical path.

    Used by the backup self-guard and the export self-overwrite guard:
    two spellings of one file must never be treated as two files.
    """
    if os.path.exists(first) and os.path.exists(second):
        try:
            return os.path.samefile(first, second)
        except OSError:
            return False
    return os.path.abspath(first) == os.path.abspath(second)

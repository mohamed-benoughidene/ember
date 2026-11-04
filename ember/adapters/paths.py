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
    # At least one path does not exist yet: resolve every symlink in the
    # directory spelling so a symlinked path names the same file as the
    # real path. Case stays the file system's own (Linux only).
    return os.path.realpath(first) == os.path.realpath(second)

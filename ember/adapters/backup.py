"""`ember backup`: one restorable snapshot of the knowledge base (L2 §5.1).

The whole job is a page-faithful copy (B1). It uses SQLite's online backup
API (`Connection.backup`) and never `shutil.copy`, so the copy stays a
consistent page image even if a writer was mid-transaction (S4: the
transfer mechanism is a page copy). The source is opened `mode=ro` and
never migrated, with no engine floors on purpose: an older file stays
restorable because boot upgrades it on restore (L2 §5.1 ruling). An
existing target is never destroyed: it rotates into `.old-<N>` files
beside it, newest `.old-1`, the newest 3 kept and older ones deleted, the
same retention convention the migration runner applies to its `.bak-v`
files. The rules live here in the adapter, not at the CLI edge (B3).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from ember.adapters.errors import (
    SourceInvalid,
    SourceOpenFailed,
    TargetWriteFailed,
    VerifyFailed,
)
from ember.adapters.paths import same_path
from ember.adapters.sqlite import _connect_readonly

_BACKUPS_TO_KEEP = 3


@dataclass
class BackupReport:
    """The verified snapshot: where it is, what it holds, what was rotated."""

    path: str
    schema_version: int
    item_count: int
    rotated: str | None


def create_backup(source_path: str, target_path: str) -> BackupReport:
    """Copy the knowledge base at `source_path` onto `target_path` and verify.

    Inputs: the live database path and the snapshot target path. Output: a
    `BackupReport` whose `schema_version` and `item_count` are read back
    from the written copy. Side effects: creates or replaces the target
    file, and when a target already exists renames it into `<target>.old-N`
    files beside it (newest `.old-1`, newest 3 kept, older deleted). The
    source file is never written. Raised codes: BACKUP-001 (source missing
    or not a SQLite file), BACKUP-002 (source opens but its
    `schema_version` is unreadable), BACKUP-003 (target not preparable or
    snapshot write failed, partial copy deleted), BACKUP-004 (the copy does
    not read back, copy deleted).
    """
    rotated = _precheck_and_rotate(source_path, target_path)
    conn = _open_source(source_path)
    try:
        _snapshot(conn, target_path)
    finally:
        conn.close()
    schema_version, item_count = _verify(target_path)
    return BackupReport(target_path, schema_version, item_count, rotated)


def _precheck_and_rotate(source_path: str, target_path: str) -> str | None:
    """Phase 1. Make the target preparable, rotating any existing one aside.

    Returns the `.old-1` path when an existing target was rotated, None
    when the target is fresh. Raises TargetWriteFailed (BACKUP-003) when
    the target is a directory, is the knowledge base itself, or cannot be
    renamed aside.
    """
    if same_path(source_path, target_path):
        raise TargetWriteFailed(
            "target is the knowledge base itself", target_path=target_path
        )
    if not os.path.exists(target_path):
        return None
    if os.path.isdir(target_path):
        raise TargetWriteFailed(
            "target path is a directory", target_path=target_path
        )
    rotated = f"{target_path}.old-1"
    try:
        oldest = f"{target_path}.old-{_BACKUPS_TO_KEEP}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for position in range(_BACKUPS_TO_KEEP - 1, 0, -1):
            current = f"{target_path}.old-{position}"
            if os.path.exists(current):
                os.rename(current, f"{target_path}.old-{position + 1}")
        os.rename(target_path, rotated)
    except OSError as exc:
        raise TargetWriteFailed(
            "rotation failed", target_path=target_path
        ) from exc
    return rotated


def _open_source(source_path: str) -> sqlite3.Connection:
    """Phase 2. Open the source read-only and prove it is a readable store.

    No engine floors here on purpose (L2 §5.1): a v9 file is backable, and
    `schema_version` is read, never advanced (D6). Raises SourceOpenFailed
    (BACKUP-001) when the file is missing or not a SQLite file, and
    SourceInvalid (BACKUP-002) when it opens but its `schema_version` table
    is missing or empty.
    """
    if not os.path.exists(source_path):
        raise SourceOpenFailed("db file missing", db_path=source_path)
    try:
        conn = _connect_readonly(source_path)
        conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.Error as exc:
        raise SourceOpenFailed(
            "db open fail", db_path=source_path
        ) from exc
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
    except sqlite3.Error as exc:
        raise SourceInvalid(
            "schema unreadable", db_path=source_path
        ) from exc
    if row is None or row["version"] is None:
        raise SourceInvalid(
            "schema_version is empty", db_path=source_path
        )
    return conn


def _snapshot(conn: sqlite3.Connection, target_path: str) -> None:
    """Phase 3. Write a page-faithful copy with the online backup API.

    On any write failure the partial copy is deleted first, then
    TargetWriteFailed (BACKUP-003) is raised, so a broken file never sits
    where safety is expected (I7).
    """
    try:
        dest = sqlite3.connect(target_path)
        try:
            conn.backup(dest)
        finally:
            dest.close()
    except (OSError, sqlite3.Error) as exc:
        _delete_quiet(target_path)
        raise TargetWriteFailed(
            "snapshot write failed", target_path=target_path
        ) from exc


def _verify(target_path: str) -> tuple[int, int]:
    """Phase 4. Re-open the copy and prove it reads back as a whole store.

    Reads the `schema_version` table and the `items` count (the db_check
    read pattern). On any read failure the copy is deleted first, then
    VerifyFailed (BACKUP-004) is raised.
    """
    try:
        conn = _connect_readonly(target_path)
        try:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None or row["version"] is None:
                raise sqlite3.OperationalError("schema_version is empty")
            schema_version = int(row["version"])
            item_count = int(
                conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            )
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        _delete_quiet(target_path)
        raise VerifyFailed(
            "copy does not read back", target_path=target_path
        ) from exc
    return schema_version, item_count


def _delete_quiet(path: str) -> None:
    """Remove a broken output file.

    Absence or a permission noise here must not mask the real failure,
    which is retained as the cause of the error already being raised.
    """
    try:
        os.remove(path)
    except OSError:
        pass

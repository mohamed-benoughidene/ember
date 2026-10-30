"""`ember backup` tests (utility step 01, L2 §5.1).

Every case builds a real database through the migration runner and the real
seed helpers, then runs the adapter function or the CLI on real temp files
(T3/T4, no mocks). The read-only proof is a file-hash comparison before and
after, the same pattern the read-only query commands use.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.adapters.backup import BackupReport, create_backup
from ember.adapters.errors import (
    SourceInvalid,
    SourceOpenFailed,
    TargetWriteFailed,
    VerifyFailed,
)
from ember.adapters.sqlite import open_database
from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_source
from tests.query.fakes import make_v9


@pytest.fixture
def target_path(tmp_path) -> str:
    """The snapshot target the tests write to."""
    return str(tmp_path / "backup.db")


def _seed(db_path: str) -> int:
    """Build a real v12 database and return its item count."""
    Path(db_path).touch()
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="first")
        insert_item(conn, source_id=source_id, item_id=2, statement="second")
        insert_link(conn, 1, 2, "depends_on")
        conn.commit()
        count = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
    finally:
        conn.close()
    return count


def _add_item(db_path: str, item_id: int, statement: str) -> None:
    """Add one item to the seeded live database between backups."""
    conn = open_database(db_path)
    try:
        insert_item(conn, source_id=1, item_id=item_id, statement=statement)
        conn.commit()
    finally:
        conn.close()


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# 1. Backup creates a usable copy


def test_backup_creates_usable_copy(db_path, target_path) -> None:
    count = _seed(db_path)

    report = create_backup(db_path, target_path)

    assert isinstance(report, BackupReport)
    assert report.path == target_path
    assert report.schema_version == 13
    assert report.item_count == count
    assert report.rotated is None
    conn = sqlite3.connect(target_path)
    try:
        version = int(conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0])
        rows = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
    finally:
        conn.close()
    assert version == 13
    assert rows == count


def test_cli_backup_success_line(db_path, target_path) -> None:
    count = _seed(db_path)

    result = CliRunner().invoke(main, ["backup", target_path, "--db", db_path])

    assert result.exit_code == 0
    expected = (
        f"backup written: {target_path}"
        f" (schema v13, {count} items)"
    )
    assert result.output.strip() == expected


# 2. Rotation: newest .old-1, depth 3, oldest deleted


def test_second_backup_rotates_to_old1(db_path, target_path) -> None:
    _seed(db_path)
    first = create_backup(db_path, target_path)
    first_copy_hash = _sha256(target_path)
    _add_item(db_path, 3, "third")

    second = create_backup(db_path, target_path)

    assert first.rotated is None
    assert second.rotated == f"{target_path}.old-1"
    assert os.path.exists(f"{target_path}.old-1")
    assert _sha256(f"{target_path}.old-1") == first_copy_hash
    conn = sqlite3.connect(target_path)
    try:
        rows = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
    finally:
        conn.close()
    assert rows == 3


def test_rotation_depth_three_oldest_deleted(db_path, target_path) -> None:
    _seed(db_path)
    snapshot_hashes: list[str] = []
    for run in range(1, 6):
        _add_item(db_path, 100 + run, f"run {run}")
        create_backup(db_path, target_path)
        snapshot_hashes.append(_sha256(target_path))

    kept = [
        _sha256(f"{target_path}.old-{n}") for n in (1, 2, 3)
    ]
    # The newest three survive, the first snapshot is gone.
    assert kept == [
        snapshot_hashes[3],
        snapshot_hashes[2],
        snapshot_hashes[1],
    ]
    assert snapshot_hashes[0] not in kept
    assert not os.path.exists(f"{target_path}.old-4")


def test_cli_backup_rotation_stderr_line(db_path, target_path) -> None:
    _seed(db_path)
    CliRunner().invoke(main, ["backup", target_path, "--db", db_path])
    _add_item(db_path, 3, "third")

    result = CliRunner().invoke(main, ["backup", target_path, "--db", db_path])

    assert result.exit_code == 0
    assert f"rotated to {target_path}.old-1" in (result.stderr or "")
    assert "backup written:" in result.output
    assert os.path.exists(f"{target_path}.old-1")


# 3. Source hash proof: the live file is never written


def test_source_bytes_unchanged_by_backup(db_path, target_path) -> None:
    _seed(db_path)
    before = _sha256(db_path)

    create_backup(db_path, target_path)

    assert _sha256(db_path) == before


# 4. Failure cleanup: broken output deleted, exit 1


def test_target_directory_refused(db_path, target_path) -> None:
    _seed(db_path)
    os.mkdir(target_path)

    with pytest.raises(TargetWriteFailed) as raised:
        create_backup(db_path, target_path)

    assert raised.value.code == "BACKUP-003"
    assert os.path.isdir(target_path)


def test_snapshot_failure_leaves_no_partial(db_path, tmp_path) -> None:
    _seed(db_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    target = str(outdir / "backup.db")
    os.chmod(outdir, 0o555)
    try:
        with pytest.raises(TargetWriteFailed) as raised:
            create_backup(db_path, target)
    finally:
        os.chmod(outdir, 0o755)

    assert raised.value.code == "BACKUP-003"
    assert not os.path.exists(target)


def test_verify_failure_deletes_copy(db_path, target_path) -> None:
    # A real SQLite file with a schema stamp but no items table: the copy
    # writes fine, then fails to read back as a whole store.
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (12)")
    conn.commit()
    conn.close()

    with pytest.raises(VerifyFailed) as raised:
        create_backup(db_path, target_path)

    assert raised.value.code == "BACKUP-004"
    assert not os.path.exists(target_path)


def test_cli_backup_target_directory_exit_1(db_path, target_path) -> None:
    _seed(db_path)
    os.mkdir(target_path)

    result = CliRunner().invoke(main, ["backup", target_path, "--db", db_path])

    assert result.exit_code == 1
    assert "BACKUP-003" in (result.stderr or "")


# 5. Source failures with stable codes


def test_source_missing_raises_001(db_path, target_path) -> None:
    with pytest.raises(SourceOpenFailed) as raised:
        create_backup(str(db_path) + ".absent", target_path)

    assert raised.value.code == "BACKUP-001"


def test_source_garbage_raises_001_not_sqlite(db_path, target_path) -> None:
    Path(db_path).write_bytes(b"this is not a sqlite database header")

    with pytest.raises(SourceOpenFailed) as raised:
        create_backup(db_path, target_path)

    assert raised.value.code == "BACKUP-001"


def test_source_without_schema_version_raises_002(db_path, target_path) -> None:
    # A valid SQLite file that is not an Ember store: no schema_version table.
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE other (id INTEGER)")
    conn.commit()
    conn.close()

    with pytest.raises(SourceInvalid) as raised:
        create_backup(db_path, target_path)

    assert raised.value.code == "BACKUP-002"


def test_cli_backup_missing_db_exit_1(db_path, target_path) -> None:
    missing = str(db_path) + ".absent"

    result = CliRunner().invoke(main, ["backup", target_path, "--db", missing])

    assert result.exit_code == 1
    assert "error:" in (result.stderr or "")
    assert "BACKUP-001" in (result.stderr or "")


# 6. No engine floors on the source: a v9 file backs up fine


def test_v9_file_backs_up_without_floors(db_path, target_path) -> None:
    make_v9(db_path)
    conn = sqlite3.connect(db_path)
    insert_source(conn)
    conn.execute(
        "INSERT INTO items (id, type, statement, source_id, status, created_at)"
        " VALUES (1, 'Decision', 'old key', 1, 'Active', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    before = _sha256(db_path)

    report = create_backup(db_path, target_path)

    assert report.schema_version == 9
    assert report.item_count == 1
    assert report.rotated is None
    assert _sha256(db_path) == before
    conn = sqlite3.connect(target_path)
    try:
        version = int(conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0])
    finally:
        conn.close()
    assert version == 9


def test_backup_help_ends_with_restore_warning() -> None:
    result = CliRunner().invoke(main, ["backup", "--help"])

    assert result.exit_code == 0
    # Click wraps the help text at the terminal width, so compare it
    # whitespace-normalized. The description paragraph ends with the
    # pinned restore warning, before the Options section.
    text = " ".join(result.output.split())
    description, _, _ = text.partition("Options:")
    assert description.rstrip().endswith(
        "Restore: copy the file back, or point Ember at it with `--db`."
        " There is deliberately no restore command (GLOSSARY)."
    )

"""Open failures are house errors with the file name only.

Story 7/8/23, plan Chunk 5: a `--db` Ember cannot open (missing directory,
or a file that is not a database at all) must produce exactly one house
error line — not a raw `sqlite3` traceback — and the detail on that line
names the file, never the full temp path (Chunk 3's rule).
"""

from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from ember.cli import main
from tests.bridge import harness

NOT_A_DATABASE = "this file is not a database!!"  # 29 bytes of plain text


def test_capture_source_missing_db_dir_is_one_capture_017_line(tmp_path) -> None:
    db = str(tmp_path / "nodir" / "x.db")  # parent missing: open cannot succeed

    result = CliRunner().invoke(main, ["capture-source", "--db", db], input="hello")

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: CAPTURE-017 DbOpenFailed |")
    assert "Traceback" not in (result.stderr or "")
    # Chunk 3: the detail names the file, never the full temp path.
    assert str(tmp_path) not in lines[0]
    assert "x.db" in lines[0]


def test_capture_source_text_file_db_is_one_capture_017_line(tmp_path) -> None:
    db = tmp_path / "text.db"
    db.write_text(NOT_A_DATABASE)
    assert db.stat().st_size == 29

    result = CliRunner().invoke(
        main, ["capture-source", "--db", str(db)], input="hello"
    )

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: CAPTURE-017 DbOpenFailed |")
    assert "Traceback" not in (result.stderr or "")
    assert str(tmp_path) not in lines[0]
    assert "text.db" in lines[0]


def test_backup_text_file_source_is_one_backup_001_line(tmp_path) -> None:
    db = tmp_path / "text.db"
    db.write_text(NOT_A_DATABASE)
    target = tmp_path / "out.db"

    result = CliRunner().invoke(
        main, ["backup", str(target), "--db", str(db)]
    )

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: BACKUP-001 ")
    assert "Traceback" not in (result.stderr or "")
    assert str(tmp_path) not in lines[0]


def test_current_state_missing_db_is_one_query_003_line(tmp_path) -> None:
    db = str(tmp_path / "missing" / "x.db")  # parent missing: open cannot succeed

    result = CliRunner().invoke(main, ["current-state", "--db", db])

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: QUERY-003 DbOpenFailed |")
    assert "Traceback" not in (result.stderr or "")
    assert "x.db" in lines[0]


def test_current_state_locked_db_is_one_query_008_db_busy_line(tmp_path) -> None:
    db = str(tmp_path / "locked.db")
    harness.seed_pair(db)
    holder = sqlite3.connect(db)
    holder.execute("BEGIN EXCLUSIVE")  # hold the write lock for the opener
    try:
        result = CliRunner().invoke(main, ["current-state", "--db", db])
    finally:
        holder.rollback()
        holder.close()

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: QUERY-008 DbBusy |")
    assert "Traceback" not in (result.stderr or "")


def test_current_state_recovery_needed_db_is_one_query_009_line(tmp_path) -> None:
    db = tmp_path / "text.db"
    db.write_text(NOT_A_DATABASE)
    assert db.stat().st_size == 29

    result = CliRunner().invoke(main, ["current-state", "--db", str(db)])

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: QUERY-009 DbRecoveryNeeded |")
    assert "Traceback" not in (result.stderr or "")
    assert str(tmp_path) not in lines[0]

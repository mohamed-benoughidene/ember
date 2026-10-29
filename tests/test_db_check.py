"""`ember db-check` tests (hardening step 02, L2 §2, §13).

Every healthy/drift case builds a real database through the writer paths, runs
the CLI once, and inspects stdout plus the exit code. The read-only proof is a
file-hash comparison before and after a full `db-check` run (I12: a check
reports, it never writes).
"""

from __future__ import annotations

import hashlib
import importlib.resources
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.cli import main
from ember.adapters.sqlite import (
    SqliteMaintainContext,
    SqliteMaintainStore,
    open_maintain_database,
)
from ember.maintain.run_maintain import (
    MaintainPorts,
    MaintainRequest,
    run_reverse_supersedes,
    run_sweep,
)
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source

_MIGRATIONS_TO_10 = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
    "010_add_item_close_reason.sql",
)


def _build_healthy_db(db_path: str) -> None:
    """Build a real v11 database with one reversal through the writer paths."""
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, statement="old")
        insert_item(conn, source_id=source_id, item_id=2, statement="new")
        insert_item(conn, source_id=source_id, item_id=3, statement="dependent")
        supersedes_id = insert_link(conn, 2, 1, "supersedes")
        insert_link(conn, 3, 1, "depends_on")
        conn.commit()
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn, clock=lambda: FIXED_TIME),
        )
        run_sweep(ports, MaintainRequest())
        run_reverse_supersedes(
            ports, MaintainRequest(item_id=1, link_id=supersedes_id)
        )
    finally:
        conn.close()


def _build_v10_db(db_path: str) -> None:
    """Build a real pre-011 database by hand (scripts 001-010, version 10)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_10:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    insert_source(conn)
    insert_item(conn, source_id=1, item_id=1, statement="old decision")
    conn.commit()
    conn.close()


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_db_check_healthy(db_path) -> None:
    _build_healthy_db(db_path)

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "version: 12" in lines
    assert (
        "floors: relate 11 ok, maintain 11 ok, query 10 ok, capture none"
        in lines
    )
    assert (
        "triggers: links_compat_insert, links_compat_update,"
        " items_closed_reason_insert, items_closed_reason_update - present"
        in lines
    )
    assert "link_compat: 16 rows, matches TYPE_COMPAT" in lines
    assert "foreign_key_check: 0 violations" in lines
    assert "reversal replay: 1 reversed links, column == ledger" in lines
    assert "result: OK" == lines[-1]


def test_db_check_drift_zeroed_column(db_path) -> None:
    _build_healthy_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE links SET reversed_at = NULL")
    conn.commit()
    conn.close()

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 1
    assert "result: DRIFT" == result.output.splitlines()[-1]


def test_db_check_drift_missing_compat_row(db_path) -> None:
    _build_healthy_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM link_compat WHERE source_type = 'Decision'"
        " AND target_type = 'Question' AND link_type = 'answers'"
    )
    conn.commit()
    conn.close()

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 1
    assert "result: DRIFT" == result.output.splitlines()[-1]


def test_db_check_drift_stale_version(db_path) -> None:
    _build_v10_db(db_path)

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 1
    lines = result.output.splitlines()
    assert "version: 10" in lines
    assert "floors: unmet - relate needs 11, maintain needs 11" in lines
    assert "result: DRIFT" == lines[-1]


def test_db_check_unreadable_missing_file(db_path) -> None:
    missing = str(db_path) + ".absent"

    result = CliRunner().invoke(main, ["db-check", "--db", missing])

    assert result.exit_code == 1
    assert "result: UNREADABLE" == result.output.splitlines()[-1]
    assert not Path(missing).exists()


def test_db_check_unreadable_corrupt_file(db_path) -> None:
    Path(db_path).write_bytes(b"this is not a sqlite database header")

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    assert result.exit_code == 1
    assert "result: UNREADABLE" == result.output.splitlines()[-1]


def test_db_check_readonly_hash_proof(db_path) -> None:
    _build_healthy_db(db_path)
    before = _sha256(db_path)

    result = CliRunner().invoke(main, ["db-check", "--db", db_path])

    after = _sha256(db_path)
    assert result.exit_code == 0
    assert before == after


def test_db_check_rejects_unknown_flag(db_path) -> None:
    result = CliRunner().invoke(main, ["db-check", "--nope", "--db", db_path])

    assert result.exit_code == 2

"""CLI tests for the `maintain` command (step 1: load + derive + report)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_source


def _seed_supersede(db_path: str) -> None:
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Decision")
        insert_link(conn, 2, 1, "supersedes")
        conn.commit()
    finally:
        conn.close()


def _row_counts(db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    finally:
        conn.close()
    return int(items), int(logs)


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def test_maintain_dry_run_prints_plan_and_writes_no_rows(db_path) -> None:
    Path(db_path).touch()
    _seed_supersede(db_path)
    before = _row_counts(db_path)

    result = CliRunner().invoke(main, ["maintain", "--dry-run", "--db", db_path])

    assert result.exit_code == 0
    assert "item 1: Active -> Closed (superseded)" in result.output
    assert "closed: 1, challenged: 0, reopened: 0, unchanged: 1" in result.output
    assert _row_counts(db_path) == before


def test_maintain_plain_run_also_writes_no_rows_in_step_1(db_path) -> None:
    Path(db_path).touch()
    _seed_supersede(db_path)
    before = _row_counts(db_path)

    result = CliRunner().invoke(main, ["maintain", "--db", db_path])

    assert result.exit_code == 0
    assert "closed: 1, challenged: 0, reopened: 0, unchanged: 1" in result.output
    assert _row_counts(db_path) == before


def test_maintain_missing_db_exits_1_with_007(tmp_path) -> None:
    missing = tmp_path / "missing.db"

    result = CliRunner().invoke(
        main, ["maintain", "--dry-run", "--db", str(missing)]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-007" in _error_text(result)
    assert not missing.exists()

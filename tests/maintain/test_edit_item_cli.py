"""CLI tests for `ember edit-item` (step 4, the exit-code contract).

Each test drives the real Click command against a freshly seeded SQLite temp
DB and asserts the stable error code (not the message) on failure, and the
real DB rows on success.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import insert_item, insert_source


def _seed(db_path: str) -> None:
    """Item 1 a Decision with a rationale, item 2 a Finding with a source."""
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            item_type="Decision",
            statement="Choose SQLite",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Finding",
            statement="SQLite caps at 5000 items",
        )
        conn.execute(
            "UPDATE items SET rationale = 'old why' WHERE id = 1"
        )
        conn.execute(
            "UPDATE items SET source = 'old source' WHERE id = 2"
        )
        conn.commit()
    finally:
        conn.close()


def _seeded(db_path: str) -> str:
    Path(db_path).touch()
    _seed(db_path)
    return db_path


def _row_counts(db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    finally:
        conn.close()
    return int(items), int(logs)


def _rationale(db_path: str, item_id: int) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT rationale FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0]


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def _invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def test_edit_item_cli_unknown_item_exits_1_maintain_001(db_path) -> None:
    _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "99", "--field", "rationale",
         "--value", "x", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-001" in _error_text(result)


def test_edit_item_cli_unknown_field_exits_1_maintain_013(db_path) -> None:
    _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "1", "--field", "bogus",
         "--value", "x", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-013" in _error_text(result)


def test_edit_item_cli_rationale_on_finding_exits_1_maintain_014(db_path) -> None:
    _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "2", "--field", "rationale",
         "--value", "x", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-014" in _error_text(result)


def test_edit_item_cli_success_exits_0_one_line(db_path) -> None:
    db = _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "1", "--field", "rationale",
         "--value", "new why", "--db", db]
    )

    assert result.exit_code == 0
    assert result.output == "item 1: rationale edited\n"
    assert _rationale(db, 1) == "new why"
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT field_changed, old_value, new_value, trigger_cause"
            " FROM change_log"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("rationale", "old why", "new why", "user_edit_item")


def test_edit_item_cli_same_value_exits_0_zero_rows(db_path) -> None:
    db = _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "1", "--field", "rationale",
         "--value", "old why", "--db", db]
    )

    assert result.exit_code == 0
    assert result.output == ""
    assert _row_counts(db) == (2, 0)
    assert _rationale(db, 1) == "old why"


def test_edit_item_cli_dry_run_writes_zero_rows(db_path) -> None:
    db = _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "1", "--field", "rationale",
         "--value", "new why", "--dry-run", "--db", db]
    )

    assert result.exit_code == 0
    assert result.output == "item 1: rationale: old why -> new why (dry-run)\n"
    assert _row_counts(db) == (2, 0)
    assert _rationale(db, 1) == "old why"


def test_edit_item_cli_missing_value_exits_2(db_path) -> None:
    _seeded(db_path)

    result = _invoke(["edit-item", "--item", "1", "--db", db_path])

    assert result.exit_code == 2


def test_edit_item_cli_non_integer_item_exits_2(db_path) -> None:
    _seeded(db_path)

    result = _invoke(
        ["edit-item", "--item", "abc", "--field", "rationale",
         "--value", "x", "--db", db_path]
    )

    assert result.exit_code == 2

"""CLI tests for the three human maintain commands (step 3).

Each test drives the real Click command against a freshly seeded SQLite temp
DB, and asserts the stable error code (not the message) on failure.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_source


def _seed(db_path: str) -> None:
    """Item 1 Active with a live dependent: item 2 `depends_on` item 1."""
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Decision")
        insert_link(conn, 2, 1, "depends_on")
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


def _item_status(db_path: str, item_id: int) -> tuple[str, str | None]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, close_reason FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()
    return row


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def _invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def test_close_item_invalidated_exits_0(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(
        ["close-item", "--item", "1", "--reason", "invalidated", "--db", db_path]
    )

    assert result.exit_code == 0
    assert _item_status(db_path, 1) == ("Closed", "invalidated")


def test_close_item_bogus_reason_exits_1_with_002(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(
        ["close-item", "--item", "1", "--reason", "bogus", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-002" in _error_text(result)


def test_close_item_superseded_reason_exits_1_with_003(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(
        ["close-item", "--item", "1", "--reason", "superseded", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-003" in _error_text(result)


def test_close_item_reversed_reason_exits_1_with_003(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(
        ["close-item", "--item", "1", "--reason", "reversed", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-003" in _error_text(result)


def test_close_item_twice_second_exits_1_with_004(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    first = _invoke(
        ["close-item", "--item", "1", "--reason", "invalidated", "--db", db_path]
    )
    assert first.exit_code == 0

    second = _invoke(
        ["close-item", "--item", "1", "--reason", "invalidated", "--db", db_path]
    )

    assert second.exit_code == 1
    assert "MAINTAIN-004" in _error_text(second)


def test_close_item_dry_run_prints_close_and_dependents_writes_nothing(
    db_path,
) -> None:
    Path(db_path).touch()
    _seed(db_path)
    before = _row_counts(db_path)

    result = _invoke(
        [
            "close-item",
            "--item",
            "1",
            "--reason",
            "invalidated",
            "--dry-run",
            "--db",
            db_path,
        ]
    )

    assert result.exit_code == 0
    assert "item 1: Active -> Closed (invalidated)" in result.output
    assert "item 2: Active -> Challenged" in result.output
    assert _row_counts(db_path) == before


def test_set_status_to_closed_exits_1_with_006(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(["set-status", "--item", "1", "--to", "Closed", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-006" in _error_text(result)


def test_set_status_to_bogus_exits_1_with_006(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(["set-status", "--item", "1", "--to", "Bogus", "--db", db_path])

    assert result.exit_code == 1
    assert "MAINTAIN-006" in _error_text(result)


def test_set_status_noop_active_exits_0_writes_nothing(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)
    before = _row_counts(db_path)

    result = _invoke(["set-status", "--item", "1", "--to", "Active", "--db", db_path])

    assert result.exit_code == 0
    assert _row_counts(db_path) == before
    assert _item_status(db_path, 1) == ("Active", None)


def test_reverse_supersedes_missing_item_exits_1_with_001(db_path) -> None:
    Path(db_path).touch()
    _seed(db_path)

    result = _invoke(
        ["reverse-supersedes", "--item", "99", "--link", "1", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-001" in _error_text(result)


def test_reverse_supersedes_happy_path_restores_item_and_marks_link(db_path) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            item_type="Decision",
            statement="Old",
            status="Closed",
            close_reason="superseded",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=2,
            item_type="Decision",
            statement="New",
        )
        link_id = insert_link(conn, 2, 1, "supersedes")
        conn.commit()
    finally:
        conn.close()

    result = _invoke(
        [
            "reverse-supersedes",
            "--item",
            "1",
            "--link",
            str(link_id),
            "--db",
            db_path,
        ]
    )

    assert result.exit_code == 0
    assert "item 1: Closed -> Active" in result.output
    assert "closed: 0, challenged: 0, reopened: 1, unchanged: 1" in result.output
    assert _item_status(db_path, 1) == ("Active", None)

    conn = sqlite3.connect(db_path)
    try:
        reversed_rows = conn.execute(
            "SELECT COUNT(*) FROM change_log WHERE field_changed = 'link_reversed'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert reversed_rows == 1

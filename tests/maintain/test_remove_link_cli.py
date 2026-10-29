"""CLI tests for `ember remove-link` (step 5, the exit-code contract).

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
from tests.fakes import insert_item, insert_link, insert_source


def _seed(db_path: str) -> int:
    """Item 1 (Decision) -> item 2 (Finding). Returns the confirmed link id."""
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
        link_id = insert_link(conn, 1, 2, "depends_on")
        conn.commit()
    finally:
        conn.close()
    return int(link_id)


def _seeded(db_path: str) -> int:
    Path(db_path).touch()
    return _seed(db_path)


def _link_status(db_path: str, link_id: int) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT status FROM links WHERE id = ?", (link_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _counts(db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        links = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    finally:
        conn.close()
    return int(links), int(logs)


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def test_remove_link_cli_unknown_link_exits_1_maintain_015(db_path) -> None:
    _seeded(db_path)

    result = CliRunner().invoke(
        main, ["remove-link", "--link", "99", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "MAINTAIN-015" in _error_text(result)
    assert "link_id=99" in _error_text(result)


def test_remove_link_cli_already_rejected_exits_1_maintain_015(db_path) -> None:
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        insert_link(conn, 1, 2, "depends_on", status="Rejected")
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(
        main, ["remove-link", "--link", "1", "--db", db_path]
    )

    # An error, not a silent no-op (the recorded I8 deviation).
    assert result.exit_code == 1
    assert "MAINTAIN-015" in _error_text(result)
    assert _link_status(db_path, 1) == "Rejected"
    assert _counts(db_path) == (1, 0)


def test_remove_link_cli_success_exits_0_one_line(db_path) -> None:
    link_id = _seeded(db_path)

    result = CliRunner().invoke(
        main, ["remove-link", "--link", str(link_id), "--db", db_path]
    )

    assert result.exit_code == 0
    assert result.output.strip() == (
        f"link {link_id}: depends_on 1 -> 2 removed (Confirmed -> Rejected)"
    )
    assert _link_status(db_path, link_id) == "Rejected"
    links, logs = _counts(db_path)
    assert links == 1  # never deleted
    assert logs == 1  # exactly one ledger row


def test_remove_link_cli_second_removal_exits_1_maintain_015(db_path) -> None:
    link_id = _seeded(db_path)
    runner = CliRunner()
    first = runner.invoke(
        main, ["remove-link", "--link", str(link_id), "--db", db_path]
    )
    assert first.exit_code == 0

    second = runner.invoke(
        main, ["remove-link", "--link", str(link_id), "--db", db_path]
    )

    assert second.exit_code == 1
    assert "MAINTAIN-015" in _error_text(second)
    assert _counts(db_path) == (1, 1)  # no second write


def test_remove_link_cli_dry_run_writes_zero_rows(db_path) -> None:
    link_id = _seeded(db_path)

    result = CliRunner().invoke(
        main, ["remove-link", "--link", str(link_id), "--dry-run", "--db", db_path]
    )

    # The pinned dry-run line (§12.3's final-run wording style).
    assert result.exit_code == 0
    assert result.output.strip() == f"link {link_id}: Confirmed -> Rejected (dry-run)"
    assert _link_status(db_path, link_id) == "Confirmed"
    assert _counts(db_path) == (1, 0)


def test_remove_link_cli_non_integer_link_exits_2(db_path) -> None:
    _seeded(db_path)

    result = CliRunner().invoke(
        main, ["remove-link", "--link", "abc", "--db", db_path]
    )

    assert result.exit_code == 2  # Click usage error, not a MAINTAIN code

"""Shared harness for the bridge step 01 tests (S2: `tests/bridge` isolated).

One deterministic seed per scenario, built with the shared `tests.fakes`
helpers (fixed clock stamps everywhere). Seeds are built ONCE and then
copied byte for byte, so the text run and the json run of a command start
from identical database files and the DB hashes are comparable.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import (
    insert_item,
    insert_link,
    insert_link_with_confirmation,
    insert_source,
)

# The frozen clock value the parity tests stamp on every ledger write
# (`ember.adapters.sqlite._utc_now` is monkeypatched to return this).
FROZEN_WRITE_TIME = "2026-01-02T03:04:05+00:00"


def _open(db_path: str):
    Path(db_path).touch()
    return open_maintain_database(db_path)


def seed_pair(db_path: str) -> None:
    """Items 1, 2: Active Decisions, 2 `depends_on` 1 (spanning a close)."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1)
        insert_item(conn, source_id=source_id, item_id=2)
        insert_link(conn, 2, 1, "depends_on")
        conn.commit()
    finally:
        conn.close()


def seed_superseded(db_path: str) -> None:
    """Item 1 Closed by `supersedes`, item 2 Active, link 2 -> 1 supersedes."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=1,
            statement="Old",
            status="Closed",
            close_reason="superseded",
        )
        insert_item(conn, source_id=source_id, item_id=2, statement="New")
        insert_link(conn, 2, 1, "supersedes")
        conn.commit()
    finally:
        conn.close()


def _seed_findings(db_path: str, *, target_status: str) -> None:
    """Items 3, 4: Active-or-Challenged Findings, 3 `contradicts` 4."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn,
            source_id=source_id,
            item_id=3,
            item_type="Finding",
            statement="Source",
        )
        insert_item(
            conn,
            source_id=source_id,
            item_id=4,
            item_type="Finding",
            statement="Contradicted",
            status=target_status,
        )
        insert_link_with_confirmation(conn, 3, 4, "contradicts")
        conn.commit()
    finally:
        conn.close()


def seed_contradicted_active(db_path: str) -> None:
    """`maintain` case: item 4 is Active, so the sweep challenges it."""
    _seed_findings(db_path, target_status="Active")


def seed_challenged(db_path: str) -> None:
    """`set-status` case: item 4 is seeded Challenged, so it can be cleared."""
    _seed_findings(db_path, target_status="Challenged")


def seed_rationale_item(db_path: str) -> None:
    """Item 1: a Decision carrying a `rationale` (for `edit-item`)."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, rationale="old why")
        conn.commit()
    finally:
        conn.close()


def seed_link_pair(db_path: str) -> None:
    """Items 1, 2 with one confirmed `contradicts` link and its ledger row."""
    conn = _open(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Finding")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Finding")
        insert_link_with_confirmation(conn, 2, 1, "contradicts")
        conn.commit()
    finally:
        conn.close()


def seed_closed(db_path: str) -> None:
    """`seed_pair`, then a real `close-item` (the ledger's undo group 1)."""
    seed_pair(db_path)
    result = CliRunner().invoke(
        main,
        ["close-item", "--item", "1", "--reason", "expired", "--db", db_path],
    )
    assert result.exit_code == 0, result.output


def seed_undone(db_path: str) -> None:
    """`seed_closed`, then a real `undo` (so `redo` has something to redo)."""
    seed_closed(db_path)
    result = CliRunner().invoke(main, ["undo", "--db", db_path])
    assert result.exit_code == 0, result.output


def copy_seed(source: str, target: str) -> None:
    """Copy a seeded database byte for byte so two runs start identical."""
    shutil.copyfile(source, target)


def sha(db_path: str) -> str:
    """The SHA-256 of one database file (the comparable DB state)."""
    return hashlib.sha256(Path(db_path).read_bytes()).hexdigest()


def invoke(args: list[str]) -> Any:
    """Run the real CLI in-process; stdout is `result.output`."""
    return CliRunner().invoke(main, args)

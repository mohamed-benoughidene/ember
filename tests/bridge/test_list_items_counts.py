"""`list-items --counts`: one call answers the four Home counts (N11).

The counts document's `summary` carries `active` / `challenged` / `closed` /
`total`, and each number equals the `total` of the matching per-status
`list-items --status S` call on the same knowledge base (chunk 10, step 1).
Real temp knowledge base, seeded the way `tests/bridge/harness.py` seeds its
databases (`tests.fakes` helpers, fixed clock stamps).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from ember.adapters.sqlite import open_maintain_database
from ember.cli import main
from tests.fakes import insert_item, insert_source


def _seeded_db(tmp_path: Any) -> str:
    """Items 1-6: 3 Active, 2 Challenged, 1 Closed — non-trivial numbers."""
    db_path = str(tmp_path / "counts.db")
    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        # One source per status group: `insert_source` hashes the text,
        # so the three inserts need three distinct texts.
        source_id = insert_source(conn)
        for item_id in (1, 2, 3):
            insert_item(conn, source_id=source_id, item_id=item_id)
        source_id = insert_source(conn, "body challenged")
        for item_id in (4, 5):
            insert_item(
                conn,
                source_id=source_id,
                item_id=item_id,
                item_type="Finding",
                statement="Contradicted",
                status="Challenged",
            )
        source_id = insert_source(conn, "body closed")
        insert_item(
            conn,
            source_id=source_id,
            item_id=6,
            statement="Old",
            status="Closed",
            close_reason="superseded",
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_counts_equal_the_per_status_cli_totals(tmp_path: Any) -> None:
    """One `--counts` call carries the same numbers as the per-status calls."""
    db_path = _seeded_db(tmp_path)

    result = CliRunner().invoke(main, ["list-items", "--counts", "--db", db_path])
    assert result.exit_code == 0, result.output

    counts = json.loads(result.output)["summary"]
    assert counts == {"active": 3, "challenged": 2, "closed": 1, "total": 6}

    for status, key in (
        ("Active", "active"),
        ("Challenged", "challenged"),
        ("Closed", "closed"),
    ):
        per_status = CliRunner().invoke(
            main, ["list-items", "--status", status, "--db", db_path]
        )
        assert per_status.exit_code == 0, per_status.output
        assert json.loads(per_status.output)["total"] == counts[key]


def test_without_counts_the_document_is_unchanged(tmp_path: Any) -> None:
    """Without the flag the command still prints the list envelope only."""
    db_path = _seeded_db(tmp_path)

    result = CliRunner().invoke(main, ["list-items", "--db", db_path])
    assert result.exit_code == 0, result.output

    document = json.loads(result.output)
    assert set(document) == {"total", "items"}
    assert document["total"] == 6

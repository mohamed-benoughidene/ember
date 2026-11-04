"""Raw-stdout golden compare for `current-state` and `why`.

The two outputs are pinned byte-for-byte in
`tests/fixtures/query/no_flags_golden.json`, captured from the pre-undo
build (before any undo-step code touched the query path; the capture
recipe mirrors the item-filter capture, plans/steps/query/04 §F). The
seed below must stay exactly the seed used for that capture, or the
byte compare fails.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ember.cli import main
from tests.fakes import FIXED_TIME, insert_item, insert_link, insert_source
from tests.query.fakes import make_v10

GOLDEN = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "query"
        / "no_flags_golden.json"
    ).read_text(encoding="utf-8")
)


def _seed(db_path: str) -> None:
    """Source 1, items 1-3 (Active, Challenged, Closed), 3 depends_on 2."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, status="Active")
        insert_item(conn, source_id=source_id, item_id=2, status="Challenged")
        insert_item(
            conn,
            source_id=source_id,
            item_id=3,
            status="Closed",
            close_reason="expired",
        )
        insert_link(conn, 3, 2, "depends_on")
        conn.execute(
            "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, None, "created", None, "Active", FIXED_TIME, "user_confirmed"),
        )
        conn.execute(
            "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
            " new_value, timestamp, trigger_cause)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (None, None, "proposed", None, "rejected", FIXED_TIME, "rejected"),
        )
        conn.commit()
    finally:
        conn.close()


def test_current_state_output_is_byte_identical_to_pre_undo(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["current-state", "--db", db_path])

    assert result.exit_code == 0
    assert result.output.encode() == GOLDEN["current_state"].encode()


def test_why_output_is_byte_identical_to_pre_undo(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["why", "--item", "3", "--db", db_path])

    assert result.exit_code == 0
    assert result.output.encode() == GOLDEN["why"].encode()

"""CLI integration tests for the history window on real temp DBs.

The no-flags golden test compares raw stdout bytes against
`tests/fixtures/query/no_flags_golden.json`, captured from the pre-amendment
build (commit before any filter code). The seed below must stay exactly the
seed used for that capture, or the byte compare fails.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
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

BOUNDARY = "2026-01-15T00:00:00+00:00"
# Ledger timestamps, `--since` cuts at row 4 (the boundary row is kept, >=).
FIVE_STAMPS = [
    "2026-01-10T00:00:00+00:00",
    "2026-01-12T00:00:00+00:00",
    "2026-01-14T00:00:00+00:00",
    BOUNDARY,
    "2026-01-16T00:00:00+00:00",
]


def _seed(db_path: str) -> None:
    """Source 1, items 1-3 (Active, Challenged, Closed), one link, two rows."""
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
        insert_link(conn, 1, 2, "depends_on")
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


def _seed_ledger(db_path: str) -> None:
    """Source 1, items 1-2, one link 1 -> 2, five ledger rows on item 1.

    Every row names item 1 as its subject and rows 2 and 5 also name link 1
    (which joins items 1 and 2), so `--item 1` reaches them through BOTH
    branches of the union rule yet shows five rows, and `--item 2` shows the
    two link rows only.
    """
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, status="Active")
        insert_item(conn, source_id=source_id, item_id=2, status="Active")
        insert_link(conn, 1, 2, "depends_on")
        for row_id, stamp in enumerate(FIVE_STAMPS, start=1):
            row_link_id = 1 if row_id in (2, 5) else None
            conn.execute(
                "INSERT INTO change_log (item_id, link_id, field_changed,"
                " old_value, new_value, timestamp, trigger_cause)"
                " VALUES (?, ?, 'status', 'Active', 'Active', ?, 'reversal')",
                (1, row_link_id, stamp),
            )
        conn.commit()
    finally:
        conn.close()


def _history(runner: CliRunner, db_path: str, *flags: str):
    return runner.invoke(main, ["history", *flags, "--db", db_path])


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_no_flags_output_is_byte_identical_to_pre_amendment(db_path) -> None:
    _seed(db_path)
    runner = CliRunner()

    assert (
        _history(runner, db_path).output.encode() == GOLDEN["history"].encode()
    )
    assert (
        _history(runner, db_path, "--item", "1").output.encode()
        == GOLDEN["history_item_1"].encode()
    )

    # The global byte stream still parses to the pre-amendment rows.
    document = json.loads(GOLDEN["history"])
    assert document["count"] == 2
    assert document["item_id"] is None


def test_cli_flags_never_touch_the_database_file(db_path) -> None:
    _seed(db_path)
    flag_sets = [
        ["--limit", "1"],
        ["--offset", "1"],
        ["--since", BOUNDARY],
        ["--limit", "2", "--offset", "1", "--since", BOUNDARY],
        ["--limit", "0"],
        ["--item", "1", "--limit", "1"],
        ["--item", "1", "--since", BOUNDARY],
        [],
        # The failure paths write nothing either.
        ["--offset", "-1"],
        ["--since", BOUNDARY[:-6]],
    ]
    before = _hash(db_path)

    for flags in flag_sets:
        result = _history(CliRunner(), db_path, *flags)
        assert result.exit_code in (0, 1), flags
        assert _hash(db_path) == before, flags


@pytest.mark.parametrize("view_flags", [[], ["--item", "1"]])
def test_limit_crops_a_five_row_ledger_and_count_names_what_was_printed(
    db_path, view_flags
) -> None:
    _seed_ledger(db_path)
    runner = CliRunner()

    full = _history(runner, db_path, *view_flags)
    cropped = _history(runner, db_path, *view_flags, "--limit", "2")

    assert full.exit_code == 0
    assert json.loads(full.output)["count"] == 5
    assert cropped.exit_code == 0
    document = json.loads(cropped.output)
    assert document["count"] == 2
    assert document["count"] == len(document["events"])
    # The cap keeps the earliest rows: the ledger order is untouched.
    assert [event["timestamp"] for event in document["events"]] == FIVE_STAMPS[:2]


@pytest.mark.parametrize("view_flags", [[], ["--item", "1"]])
def test_offset_skips_and_offset_past_the_end_is_empty(db_path, view_flags) -> None:
    _seed_ledger(db_path)
    runner = CliRunner()

    last = _history(runner, db_path, *view_flags, "--offset", "4")
    past_end = _history(runner, db_path, *view_flags, "--offset", "99")
    skip_then_cap = _history(
        runner, db_path, *view_flags, "--offset", "1", "--limit", "2"
    )

    assert last.exit_code == 0
    document = json.loads(last.output)
    assert document["count"] == 1
    assert document["events"][0]["timestamp"] == FIVE_STAMPS[4]
    assert past_end.exit_code == 0
    assert json.loads(past_end.output)["count"] == 0
    assert json.loads(past_end.output)["events"] == []
    assert skip_then_cap.exit_code == 0
    assert [event["timestamp"] for event in json.loads(skip_then_cap.output)["events"]] == FIVE_STAMPS[1:3]


@pytest.mark.parametrize("view_flags", [[], ["--item", "1"]])
def test_limit_zero_is_an_explicit_empty_exit_zero(db_path, view_flags) -> None:
    _seed_ledger(db_path)

    result = _history(CliRunner(), db_path, *view_flags, "--limit", "0")

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["count"] == 0
    assert document["events"] == []


def test_both_branches_of_the_item_union_rule_render_the_row_once(db_path) -> None:
    _seed_ledger(db_path)

    item_1 = _history(CliRunner(), db_path, "--item", "1")
    item_2 = _history(CliRunner(), db_path, "--item", "2")

    # Rows 2 and 5 match item 1 by subject AND by link, five rows total,
    # while item 2 sees only the two link rows.
    assert item_1.exit_code == 0
    assert json.loads(item_1.output)["count"] == 5
    assert item_2.exit_code == 0
    assert json.loads(item_2.output)["count"] == 2


@pytest.mark.parametrize("view_flags", [[], ["--item", "1"]])
def test_since_window_keeps_the_boundary_row_on_both_views(db_path, view_flags) -> None:
    _seed_ledger(db_path)
    runner = CliRunner()

    windowed = _history(runner, db_path, *view_flags, "--since", BOUNDARY)
    same_instant = _history(
        runner, db_path, *view_flags, "--since", "2026-01-15T02:00:00+02:00"
    )
    combined = _history(
        runner, db_path, *view_flags, "--since", BOUNDARY, "--limit", "1"
    )

    assert windowed.exit_code == 0
    document = json.loads(windowed.output)
    assert document["count"] == 2
    assert [event["timestamp"] for event in document["events"]] == FIVE_STAMPS[3:]
    # The +02:00 spelling normalises to the same UTC instant, so the two
    # documents are event-for-event identical.
    assert same_instant.exit_code == 0
    assert json.loads(same_instant.output)["events"] == document["events"]
    # The time cut runs first, the page then crops the windowed rows.
    assert combined.exit_code == 0
    cropped = json.loads(combined.output)
    assert cropped["count"] == 1
    assert cropped["events"][0]["timestamp"] == BOUNDARY


def test_naive_since_exits_1_with_query_007_and_length_only(db_path) -> None:
    _seed_ledger(db_path)

    result = _history(CliRunner(), db_path, "--since", "2026-01-15T00:00:00")

    assert result.exit_code == 1
    stderr = result.stderr or ""
    assert "error: QUERY-007 QuerySinceInvalid" in result.output + stderr
    assert "since_length=19" in result.output + stderr
    assert "2026-01-15" not in stderr


def test_garbage_since_exits_1_with_query_007_and_length_only(db_path) -> None:
    _seed(db_path)

    result = _history(CliRunner(), db_path, "--since", "yesterday")

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "error: QUERY-007 QuerySinceInvalid" in combined
    assert "since_length=9" in combined
    assert "yesterday" not in result.stderr


def test_naive_since_is_rejected_on_the_item_view_too(db_path) -> None:
    _seed_ledger(db_path)

    result = _history(CliRunner(), db_path, "--item", "1", "--since", "noon")

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "QUERY-007" in combined
    assert "since_length=4" in combined


@pytest.mark.parametrize(
    "flag,field", [("--limit", "limit"), ("--offset", "offset")]
)
def test_negative_page_flags_exit_1_with_query_006_and_field(
    db_path, flag, field
) -> None:
    _seed_ledger(db_path)

    result = _history(CliRunner(), db_path, flag, "-1")

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "error: QUERY-006 QueryFilterInvalid" in combined
    assert f"field={field}" in combined


def test_click_rejected_flag_exits_2_with_no_house_error_line(db_path) -> None:
    _seed(db_path)

    result = _history(CliRunner(), db_path, "--limit", "abc")

    assert result.exit_code == 2
    stderr = result.stderr or ""
    assert "error:" not in stderr
    assert "QUERY-" not in stderr


def test_unknown_item_with_flags_still_exits_1_query_001(db_path) -> None:
    _seed(db_path)

    result = _history(CliRunner(), db_path, "--item", "99", "--limit", "2")

    assert result.exit_code == 1
    assert "QUERY-001" in result.output + (result.stderr or "")

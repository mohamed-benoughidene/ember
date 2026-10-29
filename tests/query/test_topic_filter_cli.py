"""CLI integration tests for topic-search filters on a real temp DB.

The no-flags golden test compares raw stdout bytes against
`tests/fixtures/query/no_flags_golden.json`, captured from the pre-amendment
build (commit before the filter code). The seed below must stay exactly the
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


def _seed_four_active(db_path: str) -> None:
    """Four Active Decision items, so a filtered query has more rows than 2."""
    conn = make_v10(db_path)
    try:
        source_id = insert_source(conn)
        for item_id in range(1, 5):
            insert_item(conn, source_id=source_id, item_id=item_id, status="Active")
        conn.commit()
    finally:
        conn.close()


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_no_flags_output_is_byte_identical_to_pre_amendment(db_path) -> None:
    _seed(db_path)
    runner = CliRunner()

    assert (
        runner.invoke(
            main, ["topic-search", "--query", "sqlite", "--db", db_path]
        ).output.encode()
        == GOLDEN["topic_search"].encode()
    )
    assert (
        runner.invoke(main, ["history", "--db", db_path]).output.encode()
        == GOLDEN["history"].encode()
    )
    assert (
        runner.invoke(
            main, ["history", "--item", "1", "--db", db_path]
        ).output.encode()
        == GOLDEN["history_item_1"].encode()
    )

    # The same topic-search byte stream parses to the exact pre-amendment rows,
    # BM25 floats included.
    document = json.loads(GOLDEN["topic_search"])
    assert document["count"] == 3
    assert [hit["item_id"] for hit in document["results"]] == [1, 2, 3]
    assert [hit["score"] for hit in document["results"]] == [
        0.13353139262452257,
        0.13353139262452257,
        0.13353139262452257,
    ]


def test_cli_flags_never_touch_the_database_file(db_path) -> None:
    _seed(db_path)
    flag_sets = [
        ["--status", "Active"],
        ["--type", "Decision"],
        ["--status", "Closed", "--type", "Decision"],
        ["--limit", "0"],
        ["--limit", "2"],
        ["--status", "Active", "--limit", "2"],
        [],
    ]
    before = _hash(db_path)

    for flags in flag_sets:
        result = CliRunner().invoke(
            main, ["topic-search", "--query", "sqlite", *flags, "--db", db_path]
        )
        assert result.exit_code == 0, flags
        assert _hash(db_path) == before, flags


def test_status_flag_returns_only_the_matching_items(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--status", "Closed", "--db", db_path]
    )

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["mode"] == "topic_search"
    assert document["count"] == 1
    assert [hit["item_id"] for hit in document["results"]] == [3]
    assert document["results"][0]["status"] == "Closed"


def test_type_flag_filters_and_both_flags_combine(db_path) -> None:
    _seed(db_path)

    by_type = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--type", "Decision", "--db", db_path]
    )
    both = CliRunner().invoke(
        main,
        [
            "topic-search",
            "--query",
            "sqlite",
            "--status",
            "Active",
            "--type",
            "Decision",
            "--db",
            db_path,
        ],
    )

    assert by_type.exit_code == 0
    assert json.loads(by_type.output)["count"] == 3
    assert both.exit_code == 0
    assert [hit["item_id"] for hit in json.loads(both.output)["results"]] == [1]


def test_limit_zero_is_an_explicit_empty_exit_zero(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--limit", "0", "--db", db_path]
    )

    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["count"] == 0
    assert document["results"] == []


def test_limit_crops_behind_the_ranking_and_count_is_rows_returned(db_path) -> None:
    _seed_four_active(db_path)
    # All four items match, no filter: more than 2 rows before the crop.
    full = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--db", db_path]
    )
    assert json.loads(full.output)["count"] == 4

    cropped = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--limit", "2", "--db", db_path]
    )
    combined = CliRunner().invoke(
        main,
        [
            "topic-search",
            "--query",
            "sqlite",
            "--status",
            "Active",
            "--limit",
            "2",
            "--db",
            db_path,
        ],
    )

    # Four rows match, the cap keeps two, and count is the rows returned (2):
    # never a silent cap, because the count names exactly what was printed.
    assert cropped.exit_code == 0
    assert json.loads(cropped.output)["count"] == 2
    assert [hit["item_id"] for hit in json.loads(cropped.output)["results"]] == [1, 2]
    assert combined.exit_code == 0
    assert json.loads(combined.output)["count"] == 2


def test_bad_status_exits_1_with_query_006_and_field_context(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--status", "bogus", "--db", db_path]
    )

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "error: QUERY-006 QueryFilterInvalid" in combined
    assert "field=status" in combined
    assert "bogus" not in result.stderr


def test_negative_limit_exits_1_with_query_006_field_limit(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(
        main, ["topic-search", "--query", "sqlite", "--limit", "-1", "--db", db_path]
    )

    assert result.exit_code == 1
    assert "field=limit" in result.output + (result.stderr or "")


@pytest.mark.parametrize(
    "args",
    [
        ["--limit", "abc"],
        ["--pagesize", "2"],
    ],
)
def test_click_rejected_input_exits_2_with_no_house_error_line(db_path, args) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["topic-search", "--query", "sqlite", *args])

    assert result.exit_code == 2
    stderr = result.stderr or ""
    assert "error:" not in stderr
    assert "QUERY-" not in stderr

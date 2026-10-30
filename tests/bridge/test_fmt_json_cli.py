"""Bridge step 01 integration: `--format json` against the pinned text.

For every affected command the text run and the json run are driven on two
byte-identical copies of one seeded database, with the adapter clock frozen,
and the test proves the step-file Done-when items:

- the text output equals the "before" golden captured from the pre-change
  build (byte for byte);
- the resulting database state is byte-identical across the two formats (hash);
- the json document parses and carries exactly the pinned top-level keys;
- `--dry-run` + json writes zero rows;
- an unknown `--format` value is Click's usage error (exit 2);
- errors are unchanged in json mode (one stderr line, exit 1, empty stdout).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from ember.adapters import sqlite as sqlite_adapter
from tests.bridge import confirm_scenarios as cs
from tests.bridge import harness

GOLDENS = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "bridge" / "text_goldens"
)
TOP_LEVEL_KEYS = {"command", "changes", "dry_run", "summary"}

# One deterministic seed per command; the invocation is pinned below.
CASES: dict[str, Callable[[str], None]] = {
    "backup": harness.seed_pair,
    "close-item": harness.seed_pair,
    "db-check": harness.seed_pair,
    "edit-item": harness.seed_rationale_item,
    "maintain": harness.seed_contradicted_active,
    "remove-link": harness.seed_link_pair,
    "reverse-supersedes": harness.seed_superseded,
    "set-status": harness.seed_challenged,
    "undo": harness.seed_closed,
    "redo": harness.seed_undone,
}

DRY_RUN_CASES: list[tuple[str, Callable[[str], None], list[str]]] = [
    (
        "maintain",
        harness.seed_contradicted_active,
        ["maintain", "--dry-run", "--format", "json"],
    ),
    (
        "close-item",
        harness.seed_pair,
        [
            "close-item",
            "--item",
            "1",
            "--reason",
            "invalidated",
            "--dry-run",
            "--format",
            "json",
        ],
    ),
    (
        "edit-item",
        harness.seed_rationale_item,
        [
            "edit-item",
            "--item",
            "1",
            "--field",
            "rationale",
            "--value",
            "new why",
            "--dry-run",
            "--format",
            "json",
        ],
    ),
    (
        "remove-link",
        harness.seed_link_pair,
        ["remove-link", "--link", "1", "--dry-run", "--format", "json"],
    ),
    ("undo", harness.seed_closed, ["undo", "--dry-run", "--format", "json"]),
    ("redo", harness.seed_undone, ["redo", "--dry-run", "--format", "json"]),
]


def _args(name: str, db: str, target: str) -> list[str]:
    """The exact invocation each case runs (the golden capture uses this)."""
    return {
        "backup": ["backup", target, "--db", db],
        "close-item": [
            "close-item",
            "--item",
            "1",
            "--reason",
            "invalidated",
            "--db",
            db,
        ],
        "db-check": ["db-check", "--db", db],
        "edit-item": [
            "edit-item",
            "--item",
            "1",
            "--field",
            "rationale",
            "--value",
            "new why",
            "--db",
            db,
        ],
        "maintain": ["maintain", "--db", db],
        "remove-link": ["remove-link", "--link", "1", "--db", db],
        "reverse-supersedes": [
            "reverse-supersedes",
            "--item",
            "1",
            "--link",
            "1",
            "--db",
            db,
        ],
        "set-status": ["set-status", "--item", "4", "--to", "Active", "--db", db],
        "undo": ["undo", "--db", db],
        "redo": ["redo", "--db", db],
    }[name]


def _golden(name: str, target: str) -> str:
    expected = (GOLDENS / f"{name}.txt").read_text(encoding="utf-8")
    return expected.replace("<WORK>", target)


def test_golden_files_exist() -> None:
    assert sorted(p.name for p in GOLDENS.glob("*.txt")) == sorted(
        f"{name}.txt" for name in CASES
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_text_golden_json_document_and_db_hash(
    name: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step-file contract: text == golden, json parses, DB hashes equal."""
    monkeypatch.setattr(
        sqlite_adapter, "_utc_now", lambda: harness.FROZEN_WRITE_TIME
    )
    seed_db = tmp_path / "seed.db"
    CASES[name](str(seed_db))
    text_db = str(tmp_path / "text.db")
    json_db = str(tmp_path / "json.db")
    harness.copy_seed(str(seed_db), text_db)
    harness.copy_seed(str(seed_db), json_db)
    # `backup`'s golden embeds its target path (captured under a work
    # directory); give each run the same-named target in its own directory.
    (tmp_path / "text-run").mkdir()
    (tmp_path / "json-run").mkdir()
    text_target = str(tmp_path / "text-run" / "backup.backup.db")
    json_target = str(tmp_path / "json-run" / "backup.backup.db")

    text_result = harness.invoke(_args(name, text_db, text_target))
    json_result = harness.invoke(
        _args(name, json_db, json_target) + ["--format", "json"]
    )

    assert text_result.exit_code == 0, text_result.output
    assert json_result.exit_code == 0, json_result.output
    assert text_result.stdout == _golden(name, str(tmp_path / "text-run")), (
        f"{name}: text output drifted from the pre-change golden"
    )
    assert set(json.loads(json_result.stdout)) == TOP_LEVEL_KEYS
    document = json.loads(json_result.stdout)
    assert document["command"] == name
    assert isinstance(document["changes"], list)
    assert isinstance(document["summary"], dict)
    assert document["dry_run"] is False
    assert harness.sha(text_db) == harness.sha(json_db), (
        f"{name}: the json run left different database bytes"
    )


@pytest.mark.parametrize("name,seed,args", DRY_RUN_CASES)
def test_dry_run_json_writes_zero_rows(
    name: str,
    seed: Callable[[str], None],
    args: list[str],
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(db_path)
    before = harness.sha(db_path)

    result = harness.invoke(args + ["--db", db_path])

    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["dry_run"] is True
    assert set(document) == TOP_LEVEL_KEYS
    assert harness.sha(db_path) == before, f"{name}: a dry run wrote rows"


@pytest.mark.parametrize("name", sorted(CASES))
def test_unknown_format_value_exits_2(name: str, db_path: str) -> None:
    """`--format xml` is Click's own usage error (exit 2), before the
    command body runs."""
    result = harness.invoke(_args(name, db_path, db_path + ".bak") + ["--format", "xml"])
    assert result.exit_code == 2


def test_json_mode_error_is_one_stderr_line_empty_stdout(db_path: str) -> None:
    harness.seed_pair(db_path)

    result = harness.invoke(
        [
            "close-item",
            "--item",
            "99",
            "--reason",
            "expired",
            "--format",
            "json",
            "--db",
            db_path,
        ]
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: MAINTAIN-")
    assert result.stderr.count("\n") == 1


def test_step_file_cli_check_close_item_dry_run_json(db_path: str) -> None:
    """The step file's S1 sample: a planning close as one JSON document."""
    harness.seed_pair(db_path)
    before = harness.sha(db_path)

    result = harness.invoke(
        [
            "close-item",
            "--item",
            "1",
            "--reason",
            "expired",
            "--dry-run",
            "--format",
            "json",
            "--db",
            db_path,
        ]
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["command"] == "close-item"
    assert document["dry_run"] is True
    assert document["changes"][0]["item_id"] == 1
    assert set(document) == TOP_LEVEL_KEYS
    assert harness.sha(db_path) == before


def test_undo_json_pins_the_story_113_keys(db_path: str) -> None:
    """`undo` / `redo` documents pin source_group_id, source_action,
    target_label (L2 §5.1, story 113)."""
    harness.seed_closed(db_path)

    result = harness.invoke(["undo", "--format", "json", "--db", db_path])
    redo_result = harness.invoke(["redo", "--format", "json", "--db", db_path])

    assert result.exit_code == 0
    undo_doc = json.loads(result.stdout)
    assert undo_doc["summary"] == {
        "direction": "undo",
        "source_group_id": 1,
        "source_action": "close-item",
        "target_label": "item 1",
        "new_group_id": 2,
    }
    assert undo_doc["changes"], "the undo plan's changes carry the inverse rows"
    assert redo_result.exit_code == 0
    redo_doc = json.loads(redo_result.stdout)
    assert redo_doc["summary"]["direction"] == "redo"
    assert redo_doc["summary"]["source_group_id"] == 2
    assert redo_doc["summary"]["source_action"] == "close-item"
    assert redo_doc["summary"]["target_label"] == "item 1"


def test_backup_and_db_check_summaries_use_existing_report_fields(
    db_path: str,
) -> None:
    """The adapter reports reach the renderer only as plain dicts (T9)."""
    harness.seed_pair(db_path)

    result = harness.invoke(
        ["backup", db_path + ".bak", "--format", "json", "--db", db_path]
    )
    assert result.exit_code == 0
    backup_doc = json.loads(result.stdout)
    assert backup_doc["changes"] == []
    assert backup_doc["summary"] == {
        "path": db_path + ".bak",
        "schema_version": 13,
        "item_count": 2,
        "rotated": None,
    }

    check_doc = json.loads(
        harness.invoke(["db-check", "--format", "json", "--db", db_path]).stdout
    )
    assert check_doc["changes"] == []
    assert check_doc["summary"]["result"] == "OK"
    assert check_doc["summary"]["detail"] is None
    assert check_doc["summary"]["lines"][-1] == "result: OK"


def test_db_check_json_unreadable_exits_1_with_the_document(tmp_path) -> None:
    """The exit codes are unchanged in json mode: a report, not an error."""
    result = harness.invoke(
        ["db-check", "--format", "json", "--db", str(tmp_path / "missing.db")]
    )

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["command"] == "db-check"
    assert document["summary"]["result"] == "UNREADABLE"
    assert result.stderr == "detail: db file missing\n"


# --- review fix, ticket 24: the stale shortlist reaches document mode --------


def test_maintain_dry_run_json_document_carries_the_stale_candidates(
    db_path: str,
) -> None:
    """The shortlist lines are prints in text mode, so document mode used to
    drop them. The document's summary now carries the engine's own
    `StaleShortlist` whole (D3: no second definition), truncated included."""
    cs.seed_two_stale_questions(db_path)
    before = harness.sha(db_path)

    result = harness.invoke(
        ["maintain", "--dry-run", "--format", "json", "--db", db_path]
    )

    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    shortlist = document["summary"]["stale_candidates"]
    assert shortlist["truncated"] is False
    assert [c["item_id"] for c in shortlist["candidates"]] == [7, 9]
    assert shortlist["candidates"][0] == {
        "item_id": 7,
        "item_type": "Question",
        "statement": "should we cache tokens?",
        "newest_answers_link_id": 11,
        "answered_by_item_id": 5,
        "newest_answer_created_at": "2026-01-01T00:00:00+00:00",
    }
    assert harness.sha(db_path) == before


def test_maintain_json_document_carries_the_stale_candidates(tmp_path) -> None:
    """A real run with the faked proposer feed: the document still carries
    the pre-loop shortlist as data, and the text goldens are untouched
    (this run's stdout is exactly one document, no shortlist lines)."""
    result = cs.maintain_session(
        tmp_path, input_text="y\nn\n", extra_args=("--format", "json")
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout.splitlines()[-1])
    shortlist = document["summary"]["stale_candidates"]
    assert shortlist["truncated"] is False
    assert [c["item_id"] for c in shortlist["candidates"]] == [7, 9]
    assert document["summary"]["stale"] == 2
    # Document mode: the text shortlist lines are NOT on stdout — the
    # document carries the facts instead.
    assert "item 7: stale Question" not in result.stdout

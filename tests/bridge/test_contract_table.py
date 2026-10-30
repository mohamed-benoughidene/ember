"""The bridge contract table (bridge step 04, L2 §7.1): one row per command.

The table is ONE row per registered `ember` command (22 at this step). Per
row it pins:

- `sample_args`: one sample invocation (`{db}` / `{work}` are substituted
  with a temporary database / work directory per run);
- `json_keys`: the top-level keys of the ONE JSON document the command
  prints — under `--format json` for the eleven commands that changed
  output (the step-01 ten plus `maintain`), or the plain stdout document
  for the always-JSON commands (the six query reads, `capture-source`);
  `None` = the command prints no such document (`set-validated`,
  `clear-validated`, `export`, and — see below — `capture` / `relate`);
- `format_flag` / `confirm_flag`: whether `--format` / `--confirm` are on
  the command surface (asserted against Click's real params);
- `events`: under `--confirm json`, the set of event names on stdout
  (`None` = the command is not interactive);
- `exit_ok`: the exit code of the sample run (errors exit 1 line-by-line
  under the `tests/bridge/test_error_contract.py` rule; usage exits 2 —
  the second test runs every row).

Coverage test (`main.commands` vs the rows) FAILS when a command is
registered without a row, or a row names a command that does not exist —
the step file's "smallest reliable mechanism": Click's own command
registry.

Facts already pinned by earlier suites and NOT re-proven here in depth:

- text-vs-golden and DB-hash parity per write command —
  `tests/bridge/test_fmt_json_cli.py` (step 01);
- the event sequences per interactive command —
  `tests/bridge/test_confirm_json_cli.py` (step 03);
- the E2E of plan §7.4 (`capture --file note.txt --confirm json` scripted
  session == the terminal run's database) IS
  `tests/bridge/test_confirm_json_cli.py::test_capture_json_db_equals_the_terminal_run_on_the_same_input`
  — this table points at it and deliberately does not duplicate it.

Surface note (recorded in `archive/interface-deviations.md`): `capture` and
`relate` carry the `--format` flag (they moved onto the shared
`OutputOptions` bundle in step 03) but their bodies do not branch on it —
the flag row value is `True`, `json_keys` is `None`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from click.testing import CliRunner
import pytest

from ember.cli import main
from tests.bridge import confirm_scenarios as cs
from tests.bridge import harness

# The step-01 document shape (pinned by `test_fmt_json_cli.TOP_LEVEL_KEYS`).
FORMAT_JSON_KEYS = ("changes", "command", "dry_run", "summary")

NOTE = "We decided to use SQLite.\n"
JSON_ANSWERS_YES_NO = '{"answer": "y"}\n{"answer": "n"}\n'
JSON_ANSWERS_YES_NO_SKIP = '{"answer": "y"}\n{"answer": "n"}\n{"answer": "s"}\n'


def _seed_assumption(db_path: str) -> None:
    """Item 1 as an Assumption (the only kind `set-validated` may flag)."""
    from ember.adapters.sqlite import open_maintain_database
    from tests.fakes import insert_item, insert_source

    Path(db_path).touch()
    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Assumption")
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class Row:
    """One command's contract (see the module docstring)."""

    command: str
    sample_args: tuple[str, ...]
    seed: Callable[[str], None] | None = None
    stdin: str = ""
    format_flag: bool = False
    json_keys: tuple[str, ...] | None = None
    confirm_flag: bool = False
    events: tuple[str, ...] | None = None
    exit_ok: int = 0


ROWS: tuple[Row, ...] = (
    # --- Engine A: Capture ---
    Row(
        command="capture",
        sample_args=("capture", "--file", "{work}/note.txt"),
        format_flag=True,
        confirm_flag=True,
        events=("block", "message", "prompt", "summary"),
    ),
    Row(
        command="capture-source",
        sample_args=("capture-source", "--db", "{db}"),
        stdin=NOTE,
        json_keys=("content_hash", "raw_text", "source_id"),
    ),
    Row(
        command="set-validated",
        sample_args=("set-validated", "--item", "1", "--db", "{db}"),
        seed=_seed_assumption,
    ),
    Row(
        command="clear-validated",
        sample_args=("clear-validated", "--item", "1", "--db", "{db}"),
        seed=_seed_assumption,
    ),
    # --- Engine B: Relate ---
    Row(
        command="relate",
        sample_args=("relate", "--item", "1", "--db", "{db}"),
        format_flag=True,
        confirm_flag=True,
        events=("block", "prompt", "summary"),
    ),
    # --- Engine C: Maintain ---
    Row(
        command="maintain",
        sample_args=("maintain", "--db", "{db}"),
        seed=harness.seed_contradicted_active,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
        confirm_flag=True,
        events=("block", "message", "prompt", "summary"),
    ),
    Row(
        command="close-item",
        sample_args=("close-item", "--item", "1", "--reason", "expired", "--db", "{db}"),
        seed=harness.seed_pair,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="set-status",
        sample_args=("set-status", "--item", "4", "--to", "Active", "--db", "{db}"),
        seed=harness.seed_challenged,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="reverse-supersedes",
        sample_args=("reverse-supersedes", "--item", "1", "--link", "1", "--db", "{db}"),
        seed=harness.seed_superseded,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="edit-item",
        sample_args=(
            "edit-item",
            "--item",
            "1",
            "--field",
            "rationale",
            "--value",
            "new why",
            "--db",
            "{db}",
        ),
        seed=harness.seed_rationale_item,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="remove-link",
        sample_args=("remove-link", "--link", "1", "--db", "{db}"),
        seed=harness.seed_link_pair,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="undo",
        sample_args=("undo", "--db", "{db}"),
        seed=harness.seed_closed,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="redo",
        sample_args=("redo", "--db", "{db}"),
        seed=harness.seed_undone,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    # --- Engine D: Query (always one JSON document on stdout) ---
    Row(
        command="current-state",
        sample_args=("current-state", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("count", "items", "mode"),
    ),
    Row(
        command="topic-search",
        sample_args=("topic-search", "--query", "sqlite", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("count", "mode", "query", "results"),
    ),
    Row(
        command="why",
        sample_args=("why", "--item", "2", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("count", "item", "mode", "reasons"),
    ),
    Row(
        command="history",
        sample_args=("history", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("count", "events", "item_id", "mode"),
    ),
    Row(
        command="list-items",
        sample_args=("list-items", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("items", "total"),
    ),
    Row(
        command="show-item",
        sample_args=("show-item", "--item", "1", "--db", "{db}"),
        seed=harness.seed_pair,
        json_keys=("item", "links_in", "links_out", "source"),
    ),
    # --- Engine E: Utility ---
    Row(
        command="db-check",
        sample_args=("db-check", "--db", "{db}"),
        seed=harness.seed_pair,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="backup",
        sample_args=("backup", "{work}/backup.db", "--db", "{db}"),
        seed=harness.seed_pair,
        format_flag=True,
        json_keys=FORMAT_JSON_KEYS,
    ),
    Row(
        command="export",
        sample_args=("export", "--out", "{work}/export.txt", "--db", "{db}"),
        seed=harness.seed_pair,
    ),
)

# The three interactive commands run through the scripted step-03 sessions
# (AI and embedder faked at the production seams); `maintain`'s sample run
# is additionally the plain no-AI sweep (its empty shortlist needs no key).
SESSIONS = {
    "capture": (cs.capture_session, "y\nn\n"),
    "relate": (cs.relate_session, "y\nn\ns\n"),
    "maintain": (cs.maintain_session, "y\nn\n"),
}
JSON_ANSWERS = {
    "capture": JSON_ANSWERS_YES_NO,
    "relate": JSON_ANSWERS_YES_NO_SKIP,
    "maintain": JSON_ANSWERS_YES_NO,
}


def _invoke(args: list[str], stdin: str = "") -> Any:
    return CliRunner().invoke(main, args, input=stdin)


def _formatted(row: Row, tag: str, tmp_path: Any) -> tuple[list[str], str]:
    """The row's sample args with `{db}` / `{work}` substituted; returns
    the args and the database path used."""
    db = str(tmp_path / f"{tag}.db")
    work = tmp_path / tag
    work.mkdir(exist_ok=True)
    if row.seed is not None:
        row.seed(db)
    return [part.format(db=db, work=str(work)) for part in row.sample_args], db


def _session(command: str, work: Path, *, confirm_json: bool) -> Any:
    """One scripted run of an interactive command at the faked seams."""
    session, terminal_answers = SESSIONS[command]
    if confirm_json:
        return session(
            work,
            input_text=JSON_ANSWERS[command],
            extra_args=("--confirm", "json"),
        )
    return session(work, input_text=terminal_answers)


# --- the table vs the command registry ---------------------------------------


def test_every_registered_command_has_exactly_one_row() -> None:
    """Fails when a command is registered without a row, or a row names a
    command that no longer exists (the step file's hook on `main.commands`)."""
    registered = set(main.commands)
    rows = [row.command for row in ROWS]
    missing = sorted(registered - set(rows))
    unknown = sorted(set(rows) - registered)
    assert missing == [], f"commands without a contract-table row: {missing}"
    assert unknown == [], f"rows naming unregistered commands: {unknown}"
    assert len(rows) == len(set(rows)), "duplicate rows in the contract table"


def test_flags_on_the_surface_match_the_rows() -> None:
    """`--format` / `--confirm` presence in Click's real params equals the
    row's flag columns (I10: defaults keep the old behaviour)."""
    for row in ROWS:
        params = main.commands[row.command].params
        opts = {opt for param in params for opt in param.opts}
        assert ("--format" in opts) == row.format_flag, row.command
        assert ("--confirm" in opts) == row.confirm_flag, row.command


# --- the sample runs ----------------------------------------------------------


def _run_plain_row(row: Row, tmp_path: Any) -> None:
    """A non-interactive row: the sample run's exit code and, per column,
    the one JSON document's top-level keys (text vs `--format json`)."""
    args, _ = _formatted(row, "text", tmp_path)
    result = _invoke(args, stdin=row.stdin)
    assert result.exit_code == row.exit_ok, result.output

    if row.format_flag and row.json_keys is not None:
        json_args, _ = _formatted(row, "json", tmp_path)
        json_result = _invoke(json_args + ["--format", "json"])
        assert json_result.exit_code == row.exit_ok, json_result.output
        assert set(json.loads(json_result.stdout)) == set(row.json_keys)
    elif row.json_keys is not None:
        # The always-JSON commands: their only output IS the document.
        assert set(json.loads(result.stdout)) == set(row.json_keys)


def _run_interactive_row(row: Row, tmp_path: Any) -> None:
    """An interactive row: the scripted terminal session's exit code, the
    `--confirm json` session's event names (every stdout line must parse
    as one event object), and — for `maintain` — the `--format json`
    document of its plain sweep sample."""
    terminal = _session(row.command, tmp_path / "text", confirm_json=False)
    assert terminal.exit_code == row.exit_ok, terminal.output

    events_run = _session(row.command, tmp_path / "events", confirm_json=True)
    assert events_run.exit_code == row.exit_ok, events_run.output
    events = [json.loads(line) for line in events_run.stdout.splitlines() if line.strip()]
    assert {event["event"] for event in events} == set(row.events)

    if row.command == "maintain" and row.json_keys is not None:
        args, _ = _formatted(row, "json", tmp_path)
        document = _invoke(args + ["--format", "json"])
        assert document.exit_code == row.exit_ok, document.output
        assert set(json.loads(document.stdout)) == set(row.json_keys)


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row.command)
def test_sample_run_pins_exit_code_and_json_contract(row: Row, tmp_path: Any) -> None:
    if row.events is not None:
        _run_interactive_row(row, tmp_path)
    else:
        _run_plain_row(row, tmp_path)


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row.command)
def test_unknown_flag_is_a_usage_error_for_every_command(
    row: Row, tmp_path: Any
) -> None:
    """Exit 2 is the same for all 22 commands: Click rejects an unknown
    option before any command body runs (no seed, no fakes needed)."""
    args, db = _formatted(row, "usage", tmp_path)
    result = _invoke(args + ["--no-such-flag"], stdin=row.stdin)
    assert result.exit_code == 2, result.output

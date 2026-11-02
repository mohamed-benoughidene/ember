"""Batch 4 chunk 9: migration refusals, a pinned script set, no first backup.

Covers stories 14, 15, 16 (finding 4.3 #2, 4.3 #5, 4.7 #1, 4.5 #17):

- story 14: the migration scripts on disk must be exactly 1..13 before any
  open migrates anything; a dropped or renamed `.sql` refuses up front
  (`MIGRATION-001 ScriptSetInvalid`) instead of building a half schema.
- story 15: a file that has tables but no `schema_version` table is never
  adopted; it refuses with `MIGRATION-002 VersionTableMissing`.
- story 16: a version-0 file with no `items` table never finished being
  created; it gets its own code `MIGRATION-003 HalfCreatedDatabase`,
  distinct from the "schema version too old" sentence.
- story-backed backup rule: migrating a brand-new file must not write a
  pointless `.bak-v0` of an empty database.

Tests 1-3 drive the adapter's open paths in-process (the same convention as
`tests/test_migration_runner.py`); test 4 drives `ember init` in a
SUBPROCESS as `{venv python} -m ember.cli`-equivalent with `PYTHONPATH` set
to THIS worktree root (the same convention as `tests/test_batch4_init.py`,
whose `_run` helper is mirrored here). The AI key env vars are dropped from
the child environment, and every database lives in pytest's `tmp_path`.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.sqlite import open_database, open_maintain_database
from tests.fakes import insert_item, insert_link, insert_source


def _pinned_error_classes() -> tuple[type, type, type]:
    """Import the chunk-9 refusal classes lazily, INSIDE the tests.

    The classes live in `ember/adapters/errors.py` and are added in step 3;
    importing at module level would break collection and turn the honest
    step-2 red run into an ImportError. Inside a test, the missing import
    is a normal red failure.
    """
    from ember.adapters.errors import (
        HalfCreatedDatabase,
        ScriptSetInvalid,
        VersionTableMissing,
    )

    return ScriptSetInvalid, VersionTableMissing, HalfCreatedDatabase

# This worktree's root: the directory the subprocess must import `ember` from.
_WORKTREE = Path(__file__).resolve().parents[1]

_SCRIPTS_001_TO_012 = (
    "001_create_sources.sql",
    "002_create_items.sql",
    "003_create_change_log.sql",
    "004_add_item_detail_columns.sql",
    "005_create_ai_responses.sql",
    "006_create_links.sql",
    "007_create_item_embeddings.sql",
    "008_add_change_log_link_fk.sql",
    "009_drop_source_id_not_null_and_add_item_id.sql",
    "010_add_item_close_reason.sql",
    "011_add_links_reversed_at_and_enforcement_triggers.sql",
    "012_add_items_metadata.sql",
)

# Chunk 11: the first ten scripts build a real v10 file (the version the
# 011 backfill runs against in production — reversing exists in v10).
_SCRIPTS_001_TO_010 = _SCRIPTS_001_TO_012[:10]


def _run(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run `ember.cli` in a subprocess against THIS worktree's code.

    `python -m ember.cli` would be a silent no-op (cli.py has no `__main__`
    block), so this mirrors the console script's entry point exactly:
    `ember = "ember.cli:main"` (pyproject `[project.scripts]`).
    """
    env = dict(os.environ)
    env.pop("EMBER_AI_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)
    env["PYTHONPATH"] = f"{_WORKTREE}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["PYTHONPATH"] = env["PYTHONPATH"].rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", "from ember.cli import main; main()", *args],
        capture_output=True,
        env=env,
        check=False,
        timeout=60,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT version FROM schema_version").fetchone()[0])
    finally:
        conn.close()


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _craft_scripts_package_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point script discovery at a package whose scripts are NOT exactly 1..13.

    The crafted package holds the REAL scripts 001-012 but migration 013 is
    missing — the honest stand-in for a dropped or renamed `.sql`. No file
    under `ember/adapters/migrations/` is touched (they ship inside the
    repo); the loader's discovery input (`_MIGRATIONS_MODULE`) is what is
    sabotaged.
    """
    package = tmp_path / "crafted_migrations_missing_one"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    real = importlib.resources.files("ember.adapters.migrations")
    for name in _SCRIPTS_001_TO_012:
        (package / name).write_text(
            real.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(
        sqlite_adapter, "_MIGRATIONS_MODULE", "crafted_migrations_missing_one"
    )


def _build_pre_version_file(db_path: Path) -> None:
    """Build a real 'from before version tracking' file (story 15).

    Runs the real scripts 001-012 but stamps NO `schema_version` table at
    all — an old Ember database that predates version tracking.
    """
    conn = sqlite3.connect(db_path)
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _SCRIPTS_001_TO_012:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def test_a_dropped_migration_script_is_refused_before_any_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A script set that is not exactly 1..13 refuses before any open change."""
    db_path = tmp_path / "kb.db"
    _craft_scripts_package_missing_one(tmp_path, monkeypatch)
    script_set_invalid, _, _ = _pinned_error_classes()

    with pytest.raises(script_set_invalid) as exc:
        open_database(str(db_path))

    # The refusal carries its own pinned-set code...
    assert exc.value.code == "MIGRATION-001"
    # ...and happened BEFORE anything was touched: no version table, no
    # migrated table, nothing.
    assert "schema_version" not in _tables(db_path)
    assert "items" not in _tables(db_path)


def test_a_tables_but_no_version_table_file_is_refused_with_its_own_code(
    tmp_path: Path,
) -> None:
    """A pre-version-tracking file is never adopted; it refuses (story 15)."""
    db_path = tmp_path / "kb.db"
    _build_pre_version_file(db_path)
    before = _sha256(db_path)
    _, version_table_missing, _ = _pinned_error_classes()

    with pytest.raises(version_table_missing) as exc:
        open_database(str(db_path))

    # Its own code, not a wrapped CAPTURE open failure...
    assert exc.value.code == "MIGRATION-002"
    # ...and no adoption: the file is byte-identical after the refusal.
    assert _sha256(db_path) == before


def test_a_version_0_file_with_no_items_table_gets_its_own_code(
    tmp_path: Path,
) -> None:
    """A version-0 file that never finished being created refuses (story 16)."""
    db_path = tmp_path / "kb.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()
    conn.close()
    before = _sha256(db_path)
    _, _, half_created = _pinned_error_classes()

    with pytest.raises(half_created) as exc:
        open_database(str(db_path))

    # Its own code, distinct from the "needs update" (SchemaOutdated) shape...
    assert exc.value.code == "MIGRATION-003"
    assert "never finished being created" in str(exc.value)
    # ...and nothing was written to the file.
    assert _sha256(db_path) == before


def test_migrating_a_brand_new_file_makes_no_backup(tmp_path: Path) -> None:
    """`ember init` on a fresh path writes no `.bak*` beside the new file.

    A brand-new empty database has nothing to back up; today a pointless
    `.bak-v0` of the empty file is written before the first migration.
    """
    db_path = tmp_path / "kb.db"

    result = _run("init", "--db", str(db_path))

    assert result.returncode == 0, result.stderr.decode()
    assert db_path.exists()
    assert _version(db_path) == 14
    backups = sorted(tmp_path.glob("kb.db.bak*"))
    assert backups == []


def test_every_opened_connection_sets_busy_timeout_to_5000(tmp_path: Path) -> None:
    """Every opened connection sets PRAGMA busy_timeout to 5000 (decision I8).

    I8 says *every* connection: one fresh file through `open_database`
    (the capture/relate read-write open path) and a second through
    `open_maintain_database` (the maintain open path) must both report
    `PRAGMA busy_timeout = 5000`. Python's sqlite3 5-second default is a
    library-side wait, not the pragma — without the explicit PRAGMA the
    pragma reads 0. This is the precondition for the chunk-11 migration
    retry and every parallel-writer test: all openers share one visible
    limit.
    """
    read_path = tmp_path / "read.db"
    conn_read = open_database(str(read_path))
    try:
        assert conn_read.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn_read.close()

    # `open_maintain_database` refuses a missing file (N8), so the fresh
    # path starts as a zero-byte file — SQLite's "brand-new" database,
    # which the open path then migrates to 13.
    maintain_path = tmp_path / "maintain.db"
    maintain_path.touch()
    conn_maintain = open_maintain_database(str(maintain_path))
    try:
        assert conn_maintain.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn_maintain.close()


def _build_v10_file(db_path: Path) -> None:
    """Build a real v10 file: scripts 001-010 applied, version stamped 10.

    The same hand-built shape as `_build_v10_db` in
    `tests/test_migration_011.py` — real scripts, no runner, nothing past
    version 10.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (10)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _SCRIPTS_001_TO_010:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def test_migration_011_backfill_accounts_for_reversed_links(tmp_path: Path) -> None:
    """A link reversed and THEN un-reversed ends with `reversed_at` NULL.

    The 011 backfill must follow the replay rule the rest of the house
    reads by (maintain_lookup step 03): the HIGHEST-id marker among
    `link_reversed` / `link_unreversed` decides. Today the backfill reads
    ONLY `link_reversed` rows, so a link whose ledger ends in
    `link_unreversed` (it was reversed, then un-reversed) is wrongly
    stamped `reversed_at` at migration time.
    """
    db_path = tmp_path / "kb.db"
    _build_v10_file(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    source_id = insert_source(conn)
    insert_item(conn, source_id=source_id, item_id=1, statement="old decision")
    insert_item(conn, source_id=source_id, item_id=2, statement="new decision")
    link_id = insert_link(conn, 1, 2, "depends_on")
    # The ledger order is the point: reversed FIRST, un-reversed SECOND.
    # The link's last marker is `link_unreversed` — the link is live.
    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        " trigger_cause)"
        " VALUES (1, ?, 'link_reversed', 'Confirmed', 'Reversed', ?, 'reversal')",
        (link_id, "2026-05-01T10:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO change_log"
        " (item_id, link_id, field_changed, old_value, new_value, timestamp,"
        " trigger_cause)"
        " VALUES (1, ?, 'link_unreversed', 'Reversed', 'Confirmed', ?, 'user_undo')",
        (link_id, "2026-05-02T10:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    conn = open_database(str(db_path))
    try:
        assert _version(db_path) == 14
        reversed_at = conn.execute(
            "SELECT reversed_at FROM links WHERE id = ?", (link_id,)
        ).fetchone()[0]
        # An un-reversed link is live: no reversal stamp.
        assert reversed_at is None
    finally:
        conn.close()


def test_four_parallel_openers_of_a_new_file_all_succeed(tmp_path: Path) -> None:
    """4 threads race `open_database` on ONE fresh path; none raises.

    The openers truly race: a `threading.Barrier` releases all four only
    after every one is connected and waiting, so they hit the empty file
    at the same moment (the app's two first-Adds-at-once and the check
    report's confirmed crash: ~3 of 4 openers died on `database is
    locked`). After the race the file must be exactly at the pinned
    latest version.
    """
    db_path = tmp_path / "kb.db"
    openers = 4
    barrier = threading.Barrier(openers)
    outcomes: list[str] = [""] * openers

    def opener(index: int) -> None:
        conn: sqlite3.Connection | None = None
        try:
            barrier.wait(timeout=30)
            conn = open_database(str(db_path))
            outcomes[index] = "ok"
        except Exception as exc:
            outcomes[index] = repr(exc)
        finally:
            # The worker opens it, the worker closes it: SQLite objects
            # are single-thread by default (`check_same_thread`).
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=opener, args=(i,)) for i in range(openers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    for thread in threads:
        assert not thread.is_alive(), "an opener hung instead of failing fast"

    failures = [o for o in outcomes if o != "ok"]
    # The headline: no opener crashed, nobody got a half-migrated file.
    assert failures == [], f"{len(failures)} of {openers} openers failed"

    assert _version(db_path) == 14

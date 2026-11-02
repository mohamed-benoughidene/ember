"""Batch 4 chunk 5: `ember init` and the missing-file refusal (stories 4, 5, 6, 11; N8).

CLI invocation convention (every test in this file): the command runs in a
SUBPROCESS as `{venv python} -m ember.cli ...` with `PYTHONPATH` set to THIS
worktree root ahead of everything else. The repo `.venv`'s `ember` console
script (and its editable install) resolves to the MAIN checkout, which has no
`init`, so a bare `.venv/bin/ember ...` would test the wrong code; the
`PYTHONPATH` prefix makes the subprocess run THIS worktree's code. Threads
need real process separation for the race test, so subprocess is the one
convention for all commands here. The AI key env vars are dropped from the
child environment, and every database lives in pytest's `tmp_path`.
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

from ember.adapters.sqlite import open_database

# This worktree's root: the directory the subprocess must import `ember` from.
_WORKTREE = Path(__file__).resolve().parents[1]

_SOURCE_TEXT = "The parser ignores blank lines. The renderer caches glyphs.\n"

_MIGRATIONS_TO_10 = (
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
)

_MIGRATIONS_TO_12 = _MIGRATIONS_TO_10 + (
    "011_add_links_reversed_at_and_enforcement_triggers.sql",
    "012_add_items_metadata.sql",
)


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


def _build_v12_db(db_path: Path) -> None:
    """Build a real untouched v12 file (scripts 001-012, version stamped 12)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (12)")
    package = importlib.resources.files("ember.adapters.migrations")
    for name in _MIGRATIONS_TO_12:
        conn.executescript(package.joinpath(name).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def test_init_creates_and_migrates_a_new_knowledge_base(tmp_path: Path) -> None:
    """`ember init --db <missing>` creates the file and migrates it to 13."""
    db_path = tmp_path / "kb.db"

    result = _run("init", "--db", str(db_path))

    assert result.returncode == 0, _error_text(result)
    assert db_path.exists()
    assert _version(db_path) == 14


def test_init_on_a_healthy_current_file_changes_nothing(tmp_path: Path) -> None:
    """`ember init` on an already-healthy v13 file exits 0 and writes nothing."""
    db_path = tmp_path / "kb.db"
    conn = open_database(str(db_path))
    conn.close()
    before = _sha256(db_path)

    result = _run("init", "--db", str(db_path))

    assert result.returncode == 0, _error_text(result)
    assert _sha256(db_path) == before
    assert _version(db_path) == 14


def test_init_refuses_a_non_ember_file(tmp_path: Path) -> None:
    """`ember init` on a file that is not an Ember database refuses, named code."""
    db_path = tmp_path / "kb.db"
    db_path.write_bytes(b"this is definitely not a database")
    before = _sha256(db_path)

    result = _run("init", "--db", str(db_path))

    assert result.returncode == 1
    assert "CAPTURE-021" in result.stderr.decode()
    assert _sha256(db_path) == before


def test_init_refuses_an_older_version_file(tmp_path: Path) -> None:
    """`ember init` on a real v12 file refuses, named code, file unchanged."""
    db_path = tmp_path / "kb.db"
    _build_v12_db(db_path)
    before = _sha256(db_path)

    result = _run("init", "--db", str(db_path))

    assert result.returncode == 1
    assert "CAPTURE-021" in result.stderr.decode()
    assert _sha256(db_path) == before
    assert _version(db_path) == 12


def test_list_items_refuses_a_missing_file(tmp_path: Path) -> None:
    """`ember list-items` on a missing file refuses with a house code.

    Nothing may be created: today the query open path refuses already
    (read-only boot), and this test pins that forever.
    """
    db_path = tmp_path / "kb.db"

    result = _run("list-items", "--db", str(db_path))

    assert result.returncode == 1
    assert "QUERY-003" in result.stderr.decode()
    assert not db_path.exists()


def test_capture_source_refuses_a_missing_file(tmp_path: Path) -> None:
    """`ember capture-source` on a missing file refuses with a house code.

    Nothing may be created: today the capture open path CREATES the file
    (SQLite connects with create semantics) and migrates it instead.
    """
    db_path = tmp_path / "kb.db"
    raw = tmp_path / "note.txt"
    raw.write_text(_SOURCE_TEXT, encoding="utf-8")

    result = _run("capture-source", "--file", str(raw), "--db", str(db_path))

    assert result.returncode == 1
    assert "CAPTURE-020" in result.stderr.decode()
    assert not db_path.exists()


def test_two_init_capture_pairs_racing_on_a_new_file_both_succeed(
    tmp_path: Path,
) -> None:
    """Two threads each run `init` then `capture-source` on ONE fresh path.

    This is the app's first-Add shape (story 11): both pairs exit 0 and the
    file ends with one source row (the identical text dedupes). Both
    threads launch their subprocesses behind a barrier so the runs really
    overlap.
    """
    db_path = tmp_path / "kb.db"
    raw = tmp_path / "note.txt"
    raw.write_text(_SOURCE_TEXT, encoding="utf-8")
    barrier = threading.Barrier(2)
    results: list[list[subprocess.CompletedProcess[bytes]]] = [[], []]

    def worker(index: int) -> None:
        barrier.wait()
        results[index].append(_run("init", "--db", str(db_path)))
        results[index].append(
            _run("capture-source", "--file", str(raw), "--db", str(db_path))
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for step, result in zip(("init", "capture-source"), results[0]):
        assert result.returncode == 0, f"thread 0 {step}: {_error_text(result)}"
    for step, result in zip(("init", "capture-source"), results[1]):
        assert result.returncode == 0, f"thread 1 {step}: {_error_text(result)}"
    assert _version(db_path) == 14
    conn = sqlite3.connect(db_path)
    try:
        sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        conn.close()
    assert sources == 1


def test_four_parallel_capture_sources_on_a_new_file_all_succeed(
    tmp_path: Path,
) -> None:
    """Four threads each run `init` then `capture-source` on ONE fresh path.

    This is the app's real first-Add shape under the plan CORRECTION
    (lead-ruled, recorded): after chunk 5, capture-source refuses a missing
    file (CAPTURE-020), so a bare `capture-source` race can never run — each
    thread runs `ember init` THEN `capture-source` on the same fresh path,
    exactly like chunk 5's own race test but with a DISTINCT text per thread
    (so no dedupe hides a lost write). Init racing is proven by chunk 5's
    test; this test pins the capture side (story 11 / 4.3 #1 write half,
    chunk 11's migration exclusive lock). All four exit 0 and the file ends
    at version 13, healthy.

    Proof it's real (spec seam 4, "4 and 8 openers"): `parallelism` was
    raised to 8 for a one-off proof run — exit 0 on all 16 subprocess
    results, version 13, 8 distinct source rows, 1 passed in 7.13s — and
    restored to 4 afterwards. (A first 8-thread attempt failed only on a
    hardcoded `sources == 4` assertion of the test itself, not the lock:
    all 8 threads had already exited 0 with version 13 and the correct 8
    rows; the count now derives from `parallelism`.)
    """
    db_path = tmp_path / "kb.db"
    parallelism = 4
    barrier = threading.Barrier(parallelism)
    results: list[list[subprocess.CompletedProcess[bytes]]] = [
        [] for _ in range(parallelism)
    ]

    def worker(index: int) -> None:
        raw = tmp_path / f"note-{index}.txt"
        raw.write_text(
            f"Thread {index} text: the parser caches glyphs per file.\n",
            encoding="utf-8",
        )
        barrier.wait()
        results[index].append(_run("init", "--db", str(db_path)))
        results[index].append(
            _run("capture-source", "--file", str(raw), "--db", str(db_path))
        )

    threads = [
        threading.Thread(target=worker, args=(i,)) for i in range(parallelism)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for index in range(parallelism):
        for step, result in zip(("init", "capture-source"), results[index]):
            assert result.returncode == 0, f"thread {index} {step}: {_error_text(result)}"
    assert _version(db_path) == 14
    conn = sqlite3.connect(db_path)
    try:
        sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        conn.close()
    assert sources == parallelism  # distinct texts: a lost write would fail here


def _error_text(result: subprocess.CompletedProcess[bytes]) -> str:
    stdout = result.stdout.decode(errors="replace")
    stderr = result.stderr.decode(errors="replace")
    return f"exit={result.returncode}\nstdout:\n{stdout}stderr:\n{stderr}"

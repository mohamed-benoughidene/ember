"""CLI tests for the `relate` command."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

import ember.adapters.sqlite as sqlite_adapter
from ember.adapters.embedder import validate_embedder_config
from ember.adapters.sqlite import SqliteEmbedderStore, open_database
from ember.cli import main
from ember.relate.errors import EmbedderLoadFailed
from ember.relate.rows import Pool
from tests.fakes import FIXED_TIME, insert_item, insert_source
from tests.relate.fakes import FakeEmbedder


@pytest.fixture(autouse=True)
def _stub_boot_validation(monkeypatch) -> None:
    """Skip the boot-time embedder validation for every CLI test.

    `sentence-transformers` and `torch` live in the optional `.[relate]` extra
    and may be absent in CI, so the real probe would make these tests depend on
    an optional install. A test that exercises the failure path patches
    `ember.cli.validate_embedder_config` again with its own stub.
    """
    monkeypatch.setattr("ember.cli.validate_embedder_config", lambda: 120.0)


def _patch_phase2_ports(monkeypatch, *, embedder=None) -> FakeEmbedder:
    """Replace the real model and cache with fakes for CLI tests.

    Boot validation is stubbed by `_stub_boot_validation`, so only the two
    phase-2 ports are replaced here.
    """
    fake_embedder = embedder or FakeEmbedder()
    monkeypatch.setattr("ember.cli.build_embedder", lambda: fake_embedder)
    monkeypatch.setattr(
        "ember.cli.build_embedding_store", lambda conn: SqliteEmbedderStore(conn)
    )
    return fake_embedder


class _FakeLinkProposer:
    """Canned relate AI: proposes `depends_on` to every candidate."""

    def __init__(self, link_type: str = "depends_on") -> None:
        self._link_type = link_type
        self.calls = 0

    def propose_links(self, new_item, candidates):
        from ember.relate.link_proposal import LinkProposal, LinkProposalResponse

        self.calls += 1
        proposals = [
            LinkProposal(target_item_id=c.id, link_type=self._link_type)
            for c in candidates
        ]
        return LinkProposalResponse(raw_response="canned", proposals=proposals)


def _patch_phase34_ports(monkeypatch) -> None:
    """Stub the relate AI with a canned proposer (a real temp DB backs the rest)."""
    monkeypatch.setattr(
        "ember.cli.build_link_proposer", lambda env: _FakeLinkProposer()
    )


def _insert_link(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    link_type: str,
    status: str,
) -> None:
    conn.execute(
        "INSERT INTO links (source_item_id, target_item_id, link_type, status,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (source_id, target_id, link_type, status, FIXED_TIME),
    )


def _seed_six_items_two_links(db_path: str) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=1, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=2, item_type="Question")
        insert_item(conn, source_id=source_id, item_id=3, item_type="Question")
        insert_item(conn, source_id=source_id, item_id=4, item_type="Decision")
        insert_item(conn, source_id=source_id, item_id=5, item_type="Assumption")
        insert_item(conn, source_id=source_id, item_id=6, item_type="Finding")
        _insert_link(conn, 1, 2, "answers", "Confirmed")
        _insert_link(conn, 1, 3, "answers", "Rejected")
        conn.commit()
    finally:
        conn.close()


def _seed_item(
    conn: sqlite3.Connection,
    source_id: int,
    item_id: int,
    *,
    status: str = "Active",
) -> None:
    insert_item(conn, source_id=source_id, item_id=item_id)
    if status != "Active":
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))


def _error_text(result) -> str:
    stderr = getattr(result, "stderr", None) or ""
    return result.output + stderr


def test_relate_item_runs_phases_3_and_4(db_path, monkeypatch) -> None:
    _seed_six_items_two_links(db_path)
    _patch_phase2_ports(monkeypatch)
    _patch_phase34_ports(monkeypatch)

    result = CliRunner().invoke(
        main, ["relate", "--item", "1", "--db", db_path], input="y\ny\ny\n"
    )

    assert result.exit_code == 0
    assert result.output.count("- link_id:") == 3
    assert (
        "accepted: 3, rejected: 0, skipped: 0, aborted: false" in result.output
    )


def test_relate_prints_pool_warning_to_stderr(db_path, monkeypatch) -> None:
    _seed_six_items_two_links(db_path)
    _patch_phase2_ports(monkeypatch)
    monkeypatch.setattr(
        "ember.cli.build_candidate_pool",
        lambda *args, **kwargs: Pool(
            ranked=[],
            counts={"dense": 0, "graph": 0, "metadata": 0},
            warning="cache wiped",
        ),
    )

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 0
    assert "cache wiped" in result.stderr
    # The warning rides stderr only, so stdout stays pure JSON.
    assert json.loads(result.stdout) == {
        "phase": 2,
        "pool_size": 0,
        "signals": {"dense": 0, "graph": 0, "metadata": 0},
    }


def test_relate_missing_item_exits_1_with_code(db_path) -> None:
    conn = open_database(db_path)
    try:
        insert_source(conn)
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["relate", "--item", "999", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-001" in _error_text(result)
    assert "999" in _error_text(result)
    assert db_path in _error_text(result)


def test_relate_latest_soft_exit_when_nothing_eligible(db_path) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        _seed_item(conn, source_id, 1)
        _seed_item(conn, source_id, 2, status="Closed")
        _insert_link(conn, 1, 2, "supports", "Confirmed")
        conn.commit()
    finally:
        conn.close()

    result = CliRunner().invoke(main, ["relate", "--latest", "--db", db_path])

    assert result.exit_code == 0
    assert result.stdout.strip() == "no unrelated items"
    assert result.stderr == ""


def test_relate_latest_runs_phases_3_and_4(db_path, monkeypatch) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        _seed_item(conn, source_id, 1)
        _seed_item(conn, source_id, 2)
        conn.commit()
    finally:
        conn.close()
    _patch_phase2_ports(monkeypatch)
    _patch_phase34_ports(monkeypatch)

    result = CliRunner().invoke(
        main, ["relate", "--latest", "--db", db_path], input="y\n"
    )

    assert result.exit_code == 0
    assert result.output.count("- link_id:") == 1
    assert (
        "accepted: 1, rejected: 0, skipped: 0, aborted: false" in result.output
    )


def test_relate_empty_universe_skips_the_model(db_path, monkeypatch) -> None:
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        _seed_item(conn, source_id, 1)
        conn.commit()
    finally:
        conn.close()

    def _must_not_load():
        raise AssertionError("the embedder must not load for an empty universe")

    monkeypatch.setattr("ember.cli.build_embedder", _must_not_load)

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "phase": 2,
        "pool_size": 0,
        "signals": {"dense": 0, "graph": 0, "metadata": 0},
    }


def test_relate_embedder_load_failure_exits_1_with_relate_017(
    db_path, monkeypatch
) -> None:
    _seed_six_items_two_links(db_path)

    def _fail():
        raise EmbedderLoadFailed("model missing", model="fake")

    monkeypatch.setattr("ember.cli.build_embedder", _fail)

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-017" in _error_text(result)


def test_relate_boot_validation_failure_exits_1_with_relate_017(
    db_path, monkeypatch
) -> None:
    _seed_six_items_two_links(db_path)

    def _fail() -> float:
        raise EmbedderLoadFailed("torch is not installed", package="torch")

    # Override the suite-wide no-op: boot validation itself must surface.
    monkeypatch.setattr("ember.cli.validate_embedder_config", _fail)

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-017" in _error_text(result)
    assert "torch is not installed" in _error_text(result)


def test_relate_boot_validation_runs_before_the_db_open(
    tmp_path, monkeypatch
) -> None:
    missing = tmp_path / "missing.db"
    monkeypatch.setattr("ember.cli.validate_embedder_config", validate_embedder_config)
    monkeypatch.setenv("EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS", "soon")

    result = CliRunner().invoke(
        main, ["relate", "--item", "1", "--db", str(missing)]
    )

    assert result.exit_code == 1
    assert "RELATE-035" in _error_text(result)
    assert not missing.exists()


def test_relate_requires_exactly_one_selector(db_path) -> None:
    runner = CliRunner()

    missing = runner.invoke(main, ["relate", "--db", db_path])
    both = runner.invoke(main, ["relate", "--item", "1", "--latest", "--db", db_path])

    assert missing.exit_code == 2
    assert both.exit_code == 2


def test_relate_missing_db_exits_1_with_relate_012(tmp_path) -> None:
    missing = tmp_path / "missing.db"

    result = CliRunner().invoke(
        main, ["relate", "--item", "1", "--db", str(missing)]
    )

    assert result.exit_code == 1
    assert "RELATE-012" in result.output
    assert str(missing) in result.output
    assert not missing.exists()


def test_relate_corrupt_db_exits_1_with_relate_012(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not a sqlite database", encoding="utf-8")

    result = CliRunner().invoke(
        main, ["relate", "--item", "1", "--db", str(corrupt)]
    )

    assert result.exit_code == 1
    assert "RELATE-012" in result.output


def test_relate_migration_failure_exits_1_with_relate_013(db_path, monkeypatch) -> None:
    Path(db_path).touch()
    monkeypatch.setattr(
        sqlite_adapter,
        "_migration_scripts",
        lambda: [(1, "CREATE TABLE ok (id INTEGER);"), (6, "NOT SQL;")],
    )

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-013" in result.output


def test_relate_old_schema_exits_1_with_relate_014(db_path, monkeypatch) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(sqlite_adapter, "_apply_migrations", lambda conn: None)

    result = CliRunner().invoke(main, ["relate", "--item", "1", "--db", db_path])

    assert result.exit_code == 1
    assert "RELATE-014" in result.output

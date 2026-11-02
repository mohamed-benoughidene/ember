"""Batch 4 chunks 13 and 14: multi-writer adds and the id shown is the id saved.

The report's seam 5 (finding 4.3 #19/#20, 4.6 #4, 4.5 #11): a coding agent's
CLI and the user's app write one file at the same time. Two writers that add
at once must get distinct item ids and separate undo groups, and `undo` must
revert exactly one of the two actions — never both merged into one.

One round = one fresh v13 file, two threads, each running one full Add's
write through the REAL stores on that ONE file (the same connection-opening
path the capture accept uses): find-or-insert the `sources` row, allocate
the item id, insert the item, append its `created` ledger row, and read the
undo group id — every one of those steps inside ONE `unit_of_work`
(`BEGIN IMMEDIATE`) transaction.

Chunk 14 (N10) adds the id-story tests: a forced id conflict retries with
the next free id INSIDE the write transaction, and an edit never takes a
new item id — the id the confirm block shows is the id the item gets.

Real v13 files, real stores, no AI calls anywhere (delenv below).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteMaintainContext,
    SqliteSourceStore,
    open_database,
    open_existing_database,
    unit_of_work,
)
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.item_gatekeeper import ValidatedItem
from ember.capture.item_proposal import (
    ItemProposal,
    ItemType,
    ProposalBatch,
    ProposalResponse,
)
from ember.capture.source_storage import store_source
from ember.cli import main
from tests.fakes import FIXED_TIME, FakeConfirm, FakeItemProposer

_ROUNDS = 100


@dataclass(frozen=True)
class _Added:
    """What one writer's add left: the item id and the undo group id."""

    item_id: int
    group_id: int


def _adding_writer(
    db_path: Path, statement: str, ready: threading.Barrier
) -> _Added:
    """Run one writer's whole add on `db_path` and return its two ids.

    Mirrors the real capture write path: a connection per writer (two
    processes on one file), then ONE transaction that covers the
    source-reuse decision, the item-id allocation, the item insert, the
    `created` ledger row, and the undo group id read from inside it.
    """
    conn = open_database(str(db_path))
    try:
        gatekeeper = SqliteItemGatekeeper(
            conn, clock=lambda: FIXED_TIME, group_ids=SqliteGroupIdPort(conn)
        )
        ready.wait()
        with unit_of_work(conn):
            stored = store_source(SqliteSourceStore(conn), statement)
            item = ValidatedItem(
                id=gatekeeper.next_item_id(),
                type="Decision",
                statement=statement,
                source_quote=statement,
                confidence=0.9,
                source_id=stored.source_id,
                created_at=FIXED_TIME,
                status="Active",
                near_dup_warning=None,
                metadata=None,
            )
            # The undo group id is read INSIDE the write transaction, so two
            # concurrent writers can never both read the same next group.
            group_id = SqliteGroupIdPort(conn).next_group_id()
            gatekeeper.insert_item(item, validated=None)
            gatekeeper.log_created(item, group_id=group_id)
        return _Added(item_id=item.id, group_id=group_id)
    finally:
        conn.close()


def test_two_writers_adding_at_once_get_distinct_ids_and_separate_undo_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """100 rounds: two adds on one file, distinct ids, `undo` reverts one.

    Every round the two writers must both succeed, land distinct item ids,
    land distinct undo group ids, and leave a grouped ledger where undo
    steps back exactly ONE action (one group = one writer's item and its
    `created` row), never two merged actions.
    """
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for round_no in range(_ROUNDS):
        db_path = tmp_path / f"kb-{round_no}.db"
        ready: threading.Barrier = threading.Barrier(2)
        added: list[_Added | None] = [None, None]
        failures: list[BaseException | None] = [None, None]

        def worker(index: int) -> None:
            try:
                added[index] = _adding_writer(
                    db_path, f"writer {index} note {round_no}", ready
                )
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                failures[index] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for index, failure in enumerate(failures):
            if failure is not None:
                pytest.fail(
                    f"round {round_no}: writer {index} lost its write: {failure!r}"
                )

        assert added[0] is not None and added[1] is not None
        # Distinct item ids: no lost write took the other writer's id.
        item_ids = {added[0].item_id, added[1].item_id}
        assert len(item_ids) == 2, f"round {round_no}: duplicate item ids"
        # Distinct undo groups: the two actions can never merge into one.
        group_ids = {added[0].group_id, added[1].group_id}
        assert len(group_ids) == 2, f"round {round_no}: merged undo groups"

        # `undo` reverts exactly one group: the grouped ledger read (the
        # undo engine's own input) shows one group per action, each group
        # holding exactly that action's item + its `created` row.
        read_conn = open_existing_database(str(db_path))
        try:
            groups = SqliteMaintainContext(read_conn).list_grouped_ledger()
        finally:
            read_conn.close()
        assert len(groups) == 2, (
            f"round {round_no}: expected 2 undo groups, got {len(groups)}"
        )
        for group in groups:
            assert [row.field_changed for row in group.rows] == ["created"], (
                f"round {round_no}: group {group.group_id} holds more than"
                " one action"
            )
            assert group.rows[0].item_id in item_ids
        assert sorted(group.rows[0].item_id for group in groups) == sorted(
            item_ids
        ), f"round {round_no}: the groups do not match the two adds"


# --- chunk 14 (N10): the id shown is the id saved --------------------------

_SAMPLE = "We decided to use SQLite."
_RAW_ANSWER = "RAW-AI-ANSWER"

# One-shot trigger: the FIRST insert carrying id 1 is hijacked. Its `BEGIN`
# body lands another writer's row on id 1 first (the row survives the failed
# statement — RAISE(FAIL) backs nothing out), then the statement itself dies.
# So the insert of the pre-allocated id N=1 hits the table after MAX is
# already 1 — exactly the CLI race where the id was shown at validation time
# and another capture committed first. `WHEN NEW.id = 1` makes it one-shot:
# the retry (id 2) never fires it again.
_STEAL_FIRST_ID_TRIGGER = """
CREATE TRIGGER steal_first_id BEFORE INSERT ON items
WHEN NEW.id = 1
BEGIN
  INSERT INTO items (id, type, statement, source_id, status, created_at,
                     validated, metadata)
  VALUES (NEW.id, NEW.type, 'stolen', NEW.source_id, NEW.status,
          NEW.created_at, NEW.validated, NEW.metadata);
  SELECT RAISE(FAIL, 'forced: another writer took id 1');
END
"""


def test_a_forced_id_conflict_retries_with_the_next_free_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forced id conflict retries inside the lock; the item lands as N+1.

    The id was allocated before the write (like the real capture: shown in
    the confirm block at validation time), so the confirm block shows N —
    but another writer took N, and the write path must re-read `MAX+1`
    INSIDE the same `BEGIN IMMEDIATE` transaction and save the item as N+1
    (Spec-Batch4 D-03 / N10). The id the loop reports (what `accepted_ids`
    carries and what the summary shows) is re-read and equals the stored id.
    """
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    conn = open_database(str(tmp_path / "kb-conflict.db"))
    try:
        # The one-shot hijack: the first insert of id 1 aborts, and id 1 is
        # taken by the time the statement fails.
        conn.execute(_STEAL_FIRST_ID_TRIGGER)
        conn.commit()
        gatekeeper = SqliteItemGatekeeper(conn)
        stored = store_source(SqliteSourceStore(conn), _SAMPLE)
        item = ValidatedItem(
            id=gatekeeper.next_item_id(),  # 1 (MAX 0 + 1) — shown, then stolen
            type="Decision",
            statement=_SAMPLE,
            source_quote=_SAMPLE,
            confidence=0.9,
            source_id=stored.source_id,
            created_at=FIXED_TIME,
            status="Active",
            near_dup_warning=None,
            metadata=None,
        )
        assert item.id == 1
        confirm = FakeConfirm(["y"])  # the user accepts the block as shown

        result = run_confirm_loop(
            [item],
            confirm=confirm,
            commit=gatekeeper,
            revalidate=_never_called,
            # Chunk 8/13: one accepted item = ONE BEGIN IMMEDIATE transaction;
            # the retry on the id conflict happens inside this same lock.
            unit_of_work=lambda: unit_of_work(conn),
        )

        # The block was shown with the pre-allocated id N (it is printed
        # before the user answers — the write path cannot unprint it).
        shown_ids = [
            line.strip() for line in "\n".join(confirm.written).splitlines()
        ]
        assert "- id: 1" in shown_ids
        # The write retried and the item landed on the next free id, N+1.
        role = conn.execute(
            "SELECT id, statement FROM items WHERE statement = ?", (_SAMPLE,)
        ).fetchone()
        assert role is not None, "the item row is missing after the retry"
        saved_id = int(role["id"])
        assert saved_id == 2, f"expected the retry to save the item as 2, got {saved_id}"
        # The ledger row follows the final id: one `created` row, item N+1.
        log_ids = [
            int(r[0])
            for r in conn.execute(
                "SELECT item_id FROM change_log WHERE field_changed = 'created'"
            )
        ]
        assert log_ids == [saved_id]
        # The reported id (accepted_ids — what the confirm block's summary
        # line counts) was re-read after the retry and equals the stored id.
        assert result.accepted_ids == [saved_id], (
            "the loop must report the id actually saved, not the stale id"
        )
        # The other row on the file is the hijacking writer's stolen id 1.
        rows = conn.execute("SELECT id, statement FROM items ORDER BY id").fetchall()
        assert [int(r["id"]) for r in rows] == [1, saved_id]
        assert rows[0]["statement"] == "stolen"
    finally:
        conn.close()


def _never_called(draft):
    raise AssertionError("revalidate should not run")


def test_an_edit_never_takes_a_new_item_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two edit writes on the real `ember capture` path burn zero ids.

    Today (finding 4.5 #13) every `e` answer revalidates the draft through
    `validate_add_item`, which asks the gatekeeper for a fresh id — so each
    edit takes `MAX+1` even though the item shown is not yet written. N10 /
    story 33: the edit keeps the draft's id, so the id the confirm block
    shows is the id the item gets and `MAX(id)` never moves for an edit.
    """
    monkeypatch.delenv("EMBER_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    db_path = str(tmp_path / "kb-edit.db")
    batch = ProposalBatch(
        proposals=[
            ItemProposal(
                type=ItemType.DECISION,
                statement="Use SQLite",
                source_quote="use SQLite",
                confidence=0.9,
                metadata=None,
            )
        ],
        dropped=[],
    )
    monkeypatch.setattr(
        "ember.cli.build_item_proposer",
        lambda: FakeItemProposer(
            [ProposalResponse(raw_response=_RAW_ANSWER, batch=batch)]
        ),
    )
    sample = tmp_path / "note.txt"
    sample.write_text(_SAMPLE, encoding="utf-8")
    # Two full edit rounds (type default, statement default, metadata default),
    # then accept: the user re-answers `e` twice before confirming.
    answers = "e\n\n\n\ne\n\n\n\ny\n"

    result = CliRunner().invoke(
        main, ["capture", "--file", str(sample), "--db", db_path], input=answers
    )

    assert result.exit_code == 0, result.output
    # The same item id appears in every one of the three blocks (initial +
    # two post-edit reprints) and no other id was ever shown.
    assert result.output.count("- id: 1") == 3, result.output
    assert "- id: 2" not in result.output
    conn = sqlite3.connect(db_path)
    try:
        items = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM items").fetchone()
        assert items == (1, 1), (
            "an edit must never take a new item id: MAX(id) must be unchanged"
        )
    finally:
        conn.close()

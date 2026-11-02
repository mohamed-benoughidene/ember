"""Batch 4 chunk 13: two writers adding at once never collide (D-03).

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

Real v13 files, real stores, no AI calls anywhere (delenv below).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from ember.adapters.sqlite import (
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteMaintainContext,
    SqliteSourceStore,
    open_database,
    open_existing_database,
    unit_of_work,
)
from ember.capture.item_gatekeeper import ValidatedItem
from ember.capture.source_storage import store_source
from tests.fakes import FIXED_TIME

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

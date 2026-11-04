"""NEW (Batch 8 chunk 4, finding 4.7 #12): the change_log read stays bounded.

`history()` (the pure derivation, Batch 6 finding 4.7 #13) sorts the ledger
rows by `(timestamp, id)` DESCENDING and crops `events[:limit]`. The SQL read
behind it must therefore return only the NEWEST prefix — at most
`offset + limit` rows, ordered by that same key — so the in-memory sort and
crop of the prefix yield exactly today's view.

The test pins the bound with a progress counter
(`sqlite3.Connection.set_progress_handler`, one callback per bytecode step,
the cheap end): a page of 31 rows out of a 20,000-row ledger walks the
migration-016 index for a few hundred steps, while an unbounded read of the
same table costs at least 20,000 steps one way. A loose 2,000-step ceiling
keeps the pin honest without being brittle about the exact plan.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from ember.adapters.sqlite import SqliteQueryContext, open_database
from ember.query.rows import HistoryPage
from tests.fakes import insert_item, insert_source
from tests.query.fakes import make_v10

_LEDGER_ROWS = 20_000


def test_limited_read_scans_only_a_prefix(db_path) -> None:
    # Seed a real database the app's write path can open: schema v10 by
    # hand, then one source, 100 items that every ledger row can name.
    seed_conn = make_v10(db_path)
    source_id = insert_source(seed_conn, "seed note")
    for item_id in range(1, 101):
        insert_item(
            seed_conn,
            source_id=source_id,
            item_id=item_id,
            statement=f"item {item_id}",
            created_at="2026-01-02T00:00:00+00:00",
        )
    # 20,000 ledger rows over items 1-100, strictly increasing ISO
    # timestamps: the ledger row shape the writers use (`status` /
    # `user_set_status`), so nothing can refuse the seed.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    seeded = [
        ((i % 100) + 1, (start + timedelta(seconds=i)).isoformat())
        for i in range(_LEDGER_ROWS)
    ]
    seed_conn.executemany(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, NULL, 'status', NULL, 'Active', ?, 'user_set_status')",
        seeded,
    )
    ids = [
        row[0]
        for row in seed_conn.execute(
            "SELECT id FROM change_log ORDER BY id"
        ).fetchall()
    ]
    seed_conn.commit()
    seed_conn.close()

    # The row ids ride with the timestamps, so the seed dict is the whole
    # truth used for the expected crop below.
    all_rows = list(zip(ids, (ts for _, ts in seeded)))
    expected_newest_31 = sorted(
        all_rows, key=lambda pair: (pair[1], pair[0]), reverse=True
    )[:31]

    # Open through the normal write path so the file migrates (10 -> latest)
    # and carries the migration-016 index BEFORE the read happens.
    open_database(db_path).close()

    # Reopen STRICTLY read-only and count SQLite's progress steps during
    # the read — a counting handler fires once per `n` bytecode steps.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    counter = {"steps": 0}

    def _tick() -> int:
        counter["steps"] += 1
        return 0  # 0 = keep running

    conn.set_progress_handler(_tick, 1)
    context = SqliteQueryContext(conn)

    before = counter["steps"]
    started = time.monotonic()
    rows = context.list_change_log(item_id=None, window=HistoryPage(limit=31))
    elapsed = time.monotonic() - started
    steps = counter["steps"] - before

    # The 31 rows are exactly the NEWEST 31 by (timestamp, id): the same
    # crop the unknown-argument `history()` sort applies after the read.
    assert [
        (row.id, row.timestamp) for row in rows
    ] == [(id_, ts) for id_, ts in expected_newest_31]
    # The bounded read never scans the whole ledger: an unbounded sweep of
    # 20,000 rows costs 260,000+ steps (the plant proof below ran 260,284);
    # the indexed prefix costs a few hundred. The ceiling is deliberately
    # loose (session probe, n=1: bounded read ~720 steps).
    assert steps < 2_000, steps
    assert elapsed < 5.0, elapsed
    conn.close()

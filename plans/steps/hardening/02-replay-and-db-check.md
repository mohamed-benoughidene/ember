# L3 Hardening Step 2: Replay, One-Clock Pairing, `ember db-check`

Implements L2 Hardening §6 (D3 replay contract + pairing rule), §2 (the db-check CLI, this cluster's S1 artifact), Phase 3 + Phase 5 of the §3 pipeline. Steps 01's triggers are already in; this step makes the derived column provably equal to the ledger and makes drift inspectable.

## 0. Constitution rules this step enforces

- **D2** — `links.reversed_at` is rebuildable: named pure step `replay_reversals` + the replay-equals-live test (L2 §6, §Z D2).
- **D3 / pairing** — the column write and its ledger marker land in ONE transaction, one `commit()` — the L2 §6 pairing rule; `change_log` stays the single source (master plan rule 7 unchanged).
- **B2 / P4** — the pairing write goes through the existing `SqliteMaintainStore` port method; no second port method (two methods = two commits, L2 §6).
- **B3 / B6** — `ember/adapters/link_replay.py` is pure logic in adapters; engine cores never import it (L2 §Z T9).
- **I2 / I3** — db-check has no mode flags; one command, one job (L2 §Z).
- **I12** — db-check reports on stdout, exits 0/1, and a missing DB is reported (`UNREADABLE`), never raised (L2 §2).
- **I17 / I21** — zero new codes; `MAINTAIN-011`/`MAINTAIN-012` re-raised at the existing sites (L2 §12).
- **S1** — `ember db-check --db <db>` runs the cluster alone with the pinned report (L2 §2).
- **T1** — `replay_reversals` is pure: rows in, dict out, no clock, no I/O (L2 §6).

## 1. Job

Prove the column is the ledger: after this step every reversal writes column + marker atomically from one clock read, and `ember db-check` re-derives the column from `change_log` and compares. Exit 0 means replay equals live.

## 2. Steps

1. **`ember/adapters/link_replay.py` (new)** — `replay_reversals(entries: list[ChangeRow]) -> dict[int, str | None]` (L2 §6, shape from §4 Phase 5). Rule: for each link id, the `timestamp` of the **highest-id** `change_log` row with `field_changed='link_reversed'` and `link_id = <the link id>`; append order breaks clock ties; no marker → `None`. Input rows are already-validated shapes; deterministic; no clock, no I/O.
2. **`SqliteMaintainStore.apply_reversal` pairing** (`sqlite.py:842-908`+, L2 §6): inside the existing transaction, **before** the marker INSERT, add `UPDATE links SET reversed_at = ? WHERE id = ?`. The value is the SAME single clock read already taken at `sqlite.py:867` (`timestamp = self._clock()`) — one read shared by the column and the marker row; a second read makes `column == ledger` false by construction. Column-UPDATE `sqlite3.Error` → rollback + `MAINTAIN-011`; marker INSERT fail → rollback + `MAINTAIN-012`; single `commit()` at the end. **No new port method** — this widens "Maintain never writes links" by one column, already recorded at L2 §6 (mirrored in the relate §11 amendment).
3. **`ember db-check`** (L2 §2): new `ember/adapters/db_check.py` (reads `sqlite_master` + `PRAGMA` + rows — adapter-level work; no core module) + the `@click.command` in `ember/cli.py`. Opens `_connect_readonly` (`mode=ro`, quoted URI, `sqlite.py:65`) — never migrates, never writes. Report rows per L2 §2: `version`, `floors` (relate 11, maintain 11, query 10, capture none), `triggers` (the 4 from step 01), `link_compat` vs `TYPE_COMPAT` (16 pairs), `foreign_key_check`, `reversal replay` (`replay_reversals` over the ledger vs the live column), then `result: OK` (exit 0) / `result: DRIFT` (exit 1) / `result: UNREADABLE` (exit 1, missing or not-a-DB file — reported, no code).

## 3. Deferred settings resolved by this step (L2 §14)

- §14 #1 — CLI line wording: exactly the pinned key-value rows of L2 §2; no extra prose lines.
- §14 #4 — `--repair`: none; db-check stays report-only (repair = restore `.bak-v*` or re-run §6 by hand).

## 4. Errors (codes only, per L2 §12)

- `MAINTAIN-011` — `apply_reversal` column UPDATE fails.
- `MAINTAIN-012` — `apply_reversal` marker INSERT fails.
- db-check raises **no codes** — report + exit 1 (I12).

## 5. Test Targets (L2 §13)

This step owns, in new `tests/test_link_replay.py`:
- `test_replay_reversals_matches_live_column` — real DB, reversals driven through `reverse-supersedes`, `replay_reversals` over the ledger == live column for every link.
- `test_replay_last_marker_wins_on_clock_tie` — highest-id marker timestamp wins.

This step owns, in new `tests/test_db_check.py` (CLI, L2 §13):
- `test_db_check_healthy` — exit 0, `result: OK`, all pinned report rows present.
- `test_db_check_drift` — seeded drift fixture (e.g. column zeroed, or one `link_compat` row dropped) → exit 1, `result: DRIFT`.
- `test_db_check_unreadable` — missing file → exit 1, `result: UNREADABLE`, file still not created.
- `test_db_check_readonly` — **hash-proof**: the DB file's sha256 is identical before and after the run.
- `test_db_check_rejects_unknown_flag` — `ember db-check --nope` exits 2 (Click usage error, no code — L1 contract 5).

Pairing coverage (integration, extend the existing reversal tests in `tests/maintain/`): after `apply_reversal`, `links.reversed_at` == the marker row's `timestamp`, and a failure mid-write leaves **neither** the column nor the marker.

Steps 01 and 03 own the migration and reader tests (L2 §13).

## 6. CLI check (Rule S1)

Healthy DB (L2 §2, exact rows):

```
$ ember db-check --db <fixture>
version: 11
floors: relate 11 ok, maintain 11 ok, query 10 ok, capture none
triggers: links_compat_insert, links_compat_update, items_closed_reason_insert, items_closed_reason_update — present
link_compat: 16 rows, matches TYPE_COMPAT
foreign_key_check: 0 violations
reversal replay: 3 reversed links, column == ledger
result: OK
```

Exit 0. Drift fixture (seeded in the tests): same command → `result: DRIFT`, exit 1. Missing file: `result: UNREADABLE`, exit 1.

## 7. Pytest

```
python -m pytest tests/test_link_replay.py tests/test_db_check.py -q
python -m pytest -q            # full suite, must be green
```

## 8. Rollback

The pairing write is append-only ledger rows (never edited or deleted, L1 rule 7) plus one derived-column UPDATE that `replay_reversals` can rebuild — **No rollback — append-only by L1 rule 7**; a bad write is corrected by the next ledger row, and the column is restorable from the ledger via §2.1. db-check itself writes nothing (hash-proof test). Code undo: drop the commits.

## 9. Step invariant

After this step: the module runs and the suite passes; `ember db-check` exits 0 on a healthy DB and 1 on the seeded drift fixture.

## 10. Build Notes

(to be filled after implementation)

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
2. **`SqliteMaintainStore.apply_reversal` pairing** (`sqlite.py:842-908`+, L2 §6): inside the existing transaction, **before** the marker INSERT, add `UPDATE links SET reversed_at = ? WHERE id = ?`. The value is the SAME single clock read already taken at `sqlite.py:867` (`timestamp = self._clock()`) — one read shared by the column and the marker row; a second read makes `column == ledger` false by construction. Column-UPDATE `sqlite3.Error` → rollback + `MAINTAIN-011`; marker INSERT fail → rollback + `MAINTAIN-012`; single `commit()` at the end. **No new port method** — this widens "Maintain never writes links" by one column, already recorded at L2 §6 (mirrored in the relate §11 amendment). Also update the stale docstring at `ember/maintain/run_maintain.py:173-175` — "it never touches the `links` row" is false from this step.
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
- `test_db_check_drift` — seeded drift fixture (e.g. column zeroed, or one `link_compat` row dropped) → exit 1, `result: DRIFT`; plus the **stale-version case** from L2 §2's example report: a v10 DB → floors unmet → `result: DRIFT`, exit 1.
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

(2026-10-29, step 02 implemented on `feat/hardening`.)

What landed:
- `ember/adapters/link_replay.py` (new): pure `replay_reversals(entries: list[ChangeRow]) -> dict[int, str | None]`. Highest-id `link_reversed` marker wins regardless of input order (a higher id is a later append, so ties break by append order as §6 requires). Keys cover every link id seen in any input row, so a link with status rows but no marker maps to `None`. No clock, no I/O, no engine-core import (checked: only `ember/adapters/db_check.py` and `ember/cli.py` import it).
- `ember/adapters/sqlite.py`: `apply_reversal` now writes `UPDATE links SET reversed_at = ? WHERE id = ?` inside the existing transaction, keyed on `marker.link_id`, between the `status` INSERT and the marker INSERT, stamped from the SAME single `timestamp = self._clock()` read. Column-UPDATE failure rolls back and raises `MAINTAIN-011`, marker-INSERT failure rolls back and raises `MAINTAIN-012`, single `commit()` at the end. No new port method. Docstring updated (all three writes named, one-clock rule stated).
- Stale docstrings corrected: `ember/maintain/run_maintain.py` `run_reverse_supersedes` (the "never touches the `links` row" sentence is gone, the one-transaction one-clock pairing is described) and, in the same falseness, the `reverse-supersedes` command docstring in `ember/cli.py` ("Writes no `links` row" was also now false, that file was already being edited for the new command).
- `ember/adapters/db_check.py` (new): `check_database(db_path) -> DbCheckReport`. Opens via `_connect_readonly` (`mode=ro`, URI-quoted, imported from `ember/adapters/sqlite.py` as the step plan instructs), never migrates, never writes, no mode flags, no `--repair`. Report rows exactly per L2 §2: `version`, `floors`, `triggers` (the 4 step-01 triggers), `link_compat` (vs `TYPE_COMPAT`, 16 pairs), `foreign_key_check`, `reversal replay` (the ledger replayed and compared to the live column), `result`. Floors unmet stops the walk early with `result: DRIFT` (matches the pinned v10 example, and avoids querying tables older schemas do not have). Drift detail (missing trigger names, missing/extra compat pairs, mismatched link ids) is appended to the corresponding row. `UNREADABLE` (missing, corrupt, or any `sqlite3.Error`) carries one `detail: ...` line on stderr, stdout keeps the pinned rows.
- `ember/cli.py`: `@main.command("db-check")` with `--db` (default `ember.db`), prints the report to stdout, exits 0 on `OK`, 1 on `DRIFT`/`UNREADABLE`, unknown flags exit 2 via Click's normal path.

Tests (16 new, all named in §5 or its pairing paragraph):
- `tests/test_link_replay.py`: `test_replay_reversals_matches_live_column` (real v11 DB, sweep + reverse driven through the writer paths, replay == live column for every link), `test_replay_last_marker_wins_on_clock_tie`, plus `test_replay_highest_id_wins_regardless_of_input_order`, `test_replay_returns_none_for_link_without_marker`, `test_replay_skips_rows_without_a_link_id` (pure unit).
- `tests/test_db_check.py`: `test_db_check_healthy` (exit 0, all pinned rows), `test_db_check_drift_zeroed_column`, `test_db_check_drift_missing_compat_row`, `test_db_check_drift_stale_version` (hand-built v10 DB, scripts 001-010, `version: 10` -> floors unmet -> `DRIFT`), `test_db_check_unreadable_missing_file` (file still not created), `test_db_check_unreadable_corrupt_file`, `test_db_check_readonly_hash_proof` (sha256 identical before/after), `test_db_check_rejects_unknown_flag` (exit 2).
- Pairing coverage extended in `tests/maintain/test_maintain_reversal_integration.py`: `test_apply_reversal_writes_reversed_at_from_one_clock` (a counting clock proves exactly ONE read stamps column + marker), `test_apply_reversal_column_failure_leaves_neither_column_nor_marker` (injected `sqlite3.OperationalError` on the `reversed_at` UPDATE -> `MAINTAIN-011`, item/column/ledger all untouched), `test_apply_reversal_marker_failure_rolls_back_the_column` (marker INSERT dies on the `change_log.item_id` FK after the column UPDATE succeeded in-transaction -> `MAINTAIN-012`, column rolled back to NULL).

Numbers: baseline 616 passed, 4 deselected; after: 632 passed, 4 deselected. CLI checks run with the real `.venv/bin/ember` entry point: healthy -> exit 0 `result: OK`, drift (zeroed column) -> exit 1 `result: DRIFT` with the mismatched link named, missing file -> exit 1 `result: UNREADABLE`. Hash proof on disk: sha256 identical before/after.

Deviations (honest deltas from plan/code):
- The pinned report uses an em dash (`— present`, `unmet —`); agent rules this step ban em dashes in code, so the connector is a plain `-` (`triggers: ... - present`, `floors: unmet - ...`). Everything else in the report matches the L2 §2 rows exactly.
- Plan §2.2 cites the marker INSERT at `sqlite.py:842-908` and the clock read at `sqlite.py:867`; at implementation time `apply_reversal` actually sits at `sqlite.py:894-960` and the clock read at line 919. The pairing rule itself was implemented as specified (one read, UPDATE before the marker INSERT, one commit).
- The plan names an architecture-test extension but assigns it to step 03, so no line was added to `tests/test_architecture.py` here (T9 was checked by grep instead).
- `dict[int, str | None]` semantics for links absent from the ledger: db-check compares with `replay.get(link_id)` so an absent key reads as `None`, matching the live NULL default.

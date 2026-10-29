# L3 Hardening Step 3: Relate Reader Deltas (rules 8/9 see `reversed_at`, port method, details)

Implements L2 Hardening §9 (reader half of #20/#21) + §7 (gatekeeper unchanged; the trigger is the wall behind it) + the L2 §Z T9 architecture line. Phase 4 of the §3 pipeline. Migration, replay, and db-check already landed (steps 01–02).

## 0. Constitution rules this step enforces

- **B1** — the deltas live in named files: `ember/relate/rows.py`, `ember/relate/link_gatekeeper.py`, `ember/relate/link_lookup.py` (L2 §9).
- **B2** — relate reads the column only through its own `LinkLookupPort` methods; no reaching into maintain's store or change_log (L2 §9, L1 §2 boundary-crossing fix stays out).
- **D5 / I10** — every model change is an optional field: `Link.reversed_at: str | None = None`, `RejectedLink.detail: str | None = None`; zero renames (L2 §9).
- **T5** — the cycle **decision** stays `supersedes_ancestors`; the new method feeds message text only (L2 §9).
- **I11** — the new port method's docstring names its job and its read failure.
- **I17 / I21** — no new codes; `RELATE-028`/`RELATE-009` keep their values; tests assert codes and data, never prose wording (L2 §9, §12).
- **T3** — gatekeeper units reuse the existing fake `LinkLookupPort` in `tests/relate/fakes.py` (`FakeLinkLookup`); no mocks (L2 §13).
- **T9** — no engine core imports `ember.adapters.link_replay`; asserted by the architecture test this step extends (L2 §Z T9, L1 §5).
- **P3** — Phase 4 only: the read half; the write half landed in step 02.

## Deferred settings resolved by this step (L2 §14)

- §14 #2 — `supersedes_blocking_link` BFS tie-break: **first edge in id order** (the result feeds `detail` text only; no decision depends on it).
- §14 #3 — **no reader other than `find_existing` populates `reversed_at`** in this plan; anything wider is a new L2 amendment.

## 1. Job

Let relate's rules 8 and 9 see a reversal where it now lives — on the `links` row — so a reversed `supersedes` stops false-firing the cycle check, and every link rejection says exactly which row caused it.

## 2. Steps

1. **`ember/relate/rows.py::Link`** — add `reversed_at: str | None = None` (6 fields today → 7; verified `rows.py:27-33`).
2. **`SqliteLinkContext`** (`ember/adapters/sqlite.py:366`):
   - `find_existing` (`sqlite.py:416`) still returns the row — the UNIQUE triple stands (#15 pending, L2 §9) — and selects `reversed_at`.
   - `supersedes_ancestors` (`sqlite.py:541`) walks `status='Confirmed' AND reversed_at IS NULL` — **rule 8**: after a reversal, the corrective inverse no longer false-fires `RELATE-028`.
   - **Rule 9**: `find_existing` feeds `RELATE-009`, whose `detail` carries the duplicate's reversal state.
3. **New 12th port method** — `LinkLookupPort.supersedes_blocking_link(source_id: int, target_id: int) -> Link | None` (`ember/relate/link_lookup.py`: 11 methods today, verified; + `SqliteLinkContext` adapter). BFS in id order through live Confirmed `supersedes` edges; returns the first link row connecting the two sides, else `None` (tie-break per Deferred settings §14 #2). Read failure → `RELATE-021` (justified in §3). Used only for `RELATE-028`'s detail text — the decision stays `supersedes_ancestors` (T5). **Fake update (owned): `tests/relate/fakes.py::FakeLinkLookup` gains `supersedes_blocking_link`, and its `Link` rows carry `reversed_at` — existing cycle tests would `AttributeError` otherwise.**
4. **`RejectedLink` gains `detail`** — `RejectedLink(code, detail: str | None = None)` (`link_gatekeeper.py:57-59`, dataclass today). `validate_add_link` rule 8's rejection carries `"blocked by link {id} ({source} -> {target})"` (the blocking link's id + both endpoint ids — data); rule 9's carries `"link {id} exists"`, plus `" (reversed)"` when the duplicate has `reversed_at`.
5. **CLI (the missing print path)** — `_gatekeep` returns rejection objects; the relate CLI prints one `relate rejected: RELATE-028 | <link id, source -> target>` line per rejection (code, then detail). Today `SupersedesCycle` is never raised — it is returned as a `RejectedLink` and counted, with no print path; this step adds it. No new command, no flag (I2/I12 unchanged).
6. **Architecture test** (`tests/test_architecture.py`) — add one explicit test asserting no engine core module (`ember/relate/*.py`, `ember/maintain/*.py`, `ember/query/*.py`, `ember/capture/*.py`) references `link_replay` (adapters live outside every core's reach, L2 §Z T9). L2 records the existing `test_*_core_does_not_import_adapters` token scans already enforce this; the explicit line makes the `link_replay` contract named, per L1 §5. Glob note resolved: this phase adds no core subpackage, so the `*.py` globs stay as-is (L2 §Z T9).

## 3. Errors (codes only, per L2 §12)

- `RELATE-028` — code value unchanged; `detail` gained (rule 8).
- `RELATE-009` — code value unchanged; `detail` gained (rule 9).
- `RELATE-021` — port read failure from the new method. Chosen over `RELATE-016`: `supersedes_ancestors` keeps 016 at its dedicated site, while this method is a graph walk like `neighbors_of` (which already reports `RELATE-021 GraphReadFailed`, `sqlite.py:369-370`) — same class of read, same code. This row is an L2 §12 ratification the coordinator owed — ratified at review.

## 4. Test Targets (L2 §13, relate readers group)

This step owns:
- `test_reversed_supersedes_not_cycle` — after a reversal, the inverse `supersedes` passes rule 8 (no `RELATE-028`).
- `test_relate_028_names_blocking_link` — genuine cycle → code `RELATE-028`; the detail carries the link id + both endpoints (assert the data, not the wording — I21).
- `test_relate_009_duplicate_reports_reversed_state` — duplicate of a reversed row → `RELATE-009` with the reversed state in `detail`.
- Architecture test: the new `link_replay` core-imports test in `tests/test_architecture.py`.
- Gatekeeper units on the fake port: `detail` is `None` on every non-028/009 rejection; a reversed duplicate flips rule 9's detail only.
- CLI rejection-line test in `tests/relate/test_relate_cli.py` — via the existing patching route (`_patch_phase34_ports` as used at `tests/relate/test_relate_cli.py:121-124`, `test_relate_item_runs_phases_3_and_4`): seeds a cycle, invokes the relate CLI, and asserts one `relate rejected: RELATE-028 | <link id, source -> target>` line per rejection (§2.5's print path).
- Integration (real temp DB): reverse via `reverse-supersedes`, then `insert` the corrective inverse through the port path — commit succeeds where it failed before step 3.

Floors landed in step 01 (L2 §13 "Floors" line). Steps 01–02 own migration and replay tests (L2 §13).

## 5. CLI check (Rule S1)

No new CLI command ships here. The implementable check is the printed rejection line from §2.5, driven through the existing CLI-test patching route (`_patch_phase34_ports` as used at `tests/relate/test_relate_cli.py:121-124`; `SupersedesCycle` is never raised today — it comes back as a `RejectedLink` and is counted, so without §2.5's print step there is nothing to check):

```
$ relate --item <seeded cycle fixture> --db <db>   # fakes patched, per the test route
relate rejected: RELATE-028 | 4 | 2 -> 3
accepted: 0, rejected: 1, skipped: 0, aborted: false
```

Exit 1, code first, detail after — asserted via that test route by checking each rejection line contains `relate rejected:`, `RELATE-028`, and the link id + both endpoint ids (data, never the exact prose).

## 6. Pytest

```
python -m pytest tests/relate/ tests/test_architecture.py -q
python -m pytest -q            # full suite, must be green
```

## 7. Rollback

No rollback — read-only deltas. This step writes no rows and ships no migration; `find_existing`/`supersedes_ancestors`/`supersedes_blocking_link` change what is SELECTed, never what is stored. The new `Link`/`RejectedLink` fields are optional and default `None`, so older callers keep working. Code undo: drop the commits.

## 8. Step invariant

After this step: the module runs, the relate suite is green, and the full suite passes — with the DB from steps 01–02 untouched and db-check still exit 0.

## 9. Build Notes

Built on `feat/hardening` (no push). All six §2 steps landed as planned. T3/T5 honored: the cycle decision still runs on `supersedes_ancestors`, `supersedes_blocking_link` feeds `detail` text only.

Test counts: before **632 passed, 4 deselected in 3.17s**, after **646 passed, 4 deselected in 2.82s** (14 new tests, all watched red first). New test files: `tests/relate/test_blocking_link_integration.py` (5 tests). Extended: `test_link_gatekeeper_unit.py` (+4: the three L2 §13 named tests plus `detail is None outside rules 8/9`), `test_run_relate_unit.py` (+1), `test_relate_integration.py` (+1 corrective inverse through the real maintain store + sqlite ports), `test_relate_cli.py` (+2), `tests/test_architecture.py` (+1 `test_engine_core_does_not_reference_link_replay`, which passed on its first run because no core named `link_replay` before — a guard test, no red state possible).

CLI check (§5, real run, faked AI/embedder per the CLI-test route):

```
=== case 1: relate --item 11 (live supersedes chain 11 -> 33 -> 22) ===
relate rejected: RELATE-028 | blocked by link 2 (33 -> 22)
relate rejected: RELATE-028 | blocked by link 1 (11 -> 33)
accepted: 0, rejected: 2, skipped: 0, aborted: false
exit code: 0

=== case 2 step 1: reverse-supersedes --item 2 --link 1 ===
exit code: 0
=== case 2 step 2: relate --item 2 (corrective inverse 2 -> supersedes -> 1) ===
- link_id: 2
  source_item_id: 2
  ...
accepted: 1, rejected: 0, skipped: 0, aborted: false
exit code: 0
```

Deviations and deltas (plan intent kept, shapes recorded):

1. **Exit code (§5's "Exit 1" sketch) not implemented.** The pinned CLI contract (engine-relate-plan and the `relate` docstring) is exit 0 when every proposal is handled, 1 on a phase error, 2 on quit. A gatekeeper rejection is a handled proposal (counted, not raised), so the run above exits 0. The coordinator's check pins only exit 0 for the accepted corrective inverse, which holds. **Coordinator ruling (2026-10-29): A — exit 0 for handled rejections stands; the §5 sketch was a drafting error against the pinned contract. Ticket line ticked as resolved-by-ruling.**
2. **The rejection objects ride `ConfirmResult.gatekeeper_rejections`** (new optional field in `confirm_write.py`, default empty, I10-conformant) because `run_relate` returns `ConfirmResult`. `_gatekeep` now returns `list[RejectedLink]` and the CLI prints one `relate rejected: CODE | detail` line per rejection, exactly §2.5's print path.
3. **The duplicate CLI proposal is caught by rule 8, not rule 9.** In the seeded chain 11 -> 33 -> 22, re-proposing 11 -> 33 is both a duplicate and a cycle hit (33 is in 11's ancestors), and rule 8 runs first. So the CLI fixture prints two RELATE-028 lines and none for RELATE-009. Rule-9 detail coverage lives in the gatekeeper unit test and the integration test (duplicate reversed triple -> `link {id} exists (reversed)`), as §4 planned.
4. **Fake parity:** `FakeLinkLookup.supersedes_ancestors` gained the same `reversed_at is None` filter the adapter has (needed for `test_reversed_supersedes_not_cycle` to exercise rule 8 on the fake). Fake links carry ids here because `detail` names the blocking id.
5. **Integration test ordering:** the reversed-duplicate check must run BEFORE the corrective inverse is written, otherwise the corrective edge (2 -> 1) makes the duplicate a genuine 2-cycle and rule 8 (correctly) fires before rule 9.
6. **`supersedes_ancestors` keeps RELATE-016** at its site per §3 (`tests/test_relate_read_failures.py` still green). The new walk raises RELATE-021 like `neighbors_of`, with `source_id`/`target_id` context. BFS in id order (`ORDER BY id` per node, edges grouped by source) implements the §14 tie-break: first edge in id order.

Untouched (per the ruling and scope): the UNIQUE triple, rules 8/9 decision logic, all write paths, migration/scripts, db-check (its tests still pass), maintain human actions, topic/history filters.

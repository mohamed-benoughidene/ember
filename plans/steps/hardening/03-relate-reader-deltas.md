# L3 Hardening Step 3: Relate Reader Deltas (rules 8/9 see `reversed_at`, port method, details)

Implements L2 Hardening §9 (reader half of #20/#21) + §7 (gatekeeper unchanged; the trigger is the wall behind it) + the L2 §Z T9 architecture line. Phase 4 of the §3 pipeline. Migration, replay, and db-check already landed (steps 01–02).

## 0. Constitution rules this step enforces

- **B1** — the deltas live in named files: `ember/relate/rows.py`, `ember/relate/link_gatekeeper.py`, `ember/relate/link_lookup.py` (L2 §9).
- **B2** — relate reads the column only through its own `LinkLookupPort` methods; no reaching into maintain's store or change_log (L2 §9, L1 §2 boundary-crossing fix stays out).
- **D5 / I10** — every model change is an optional field: `Link.reversed_at: str | None = None`, `RejectedLink.detail: str | None = None`; zero renames (L2 §9).
- **T5** — the cycle **decision** stays `supersedes_ancestors`; the new method feeds message text only (L2 §9).
- **I11** — the new port method's docstring names its job and its read failure.
- **I17 / I21** — no new codes; `RELATE-028`/`RELATE-009` keep their values; tests assert codes and data, never prose wording (L2 §9, §12).
- **T3** — gatekeeper units reuse the existing fake `LinkLookupPort` in `tests/fakes.py`; no mocks (L2 §13).
- **T9** — no engine core imports `ember.adapters.link_replay`; asserted by the architecture test this step extends (L2 §Z T9, L1 §5).
- **P3** — Phase 4 only: the read half; the write half landed in step 02.

## 1. Job

Let relate's rules 8 and 9 see a reversal where it now lives — on the `links` row — so a reversed `supersedes` stops false-firing the cycle check, and every link rejection says exactly which row caused it.

## 2. Steps

1. **`ember/relate/rows.py::Link`** — add `reversed_at: str | None = None` (6 fields today → 7; verified `rows.py:27-33`).
2. **`SqliteLinkContext`** (`ember/adapters/sqlite.py:366`):
   - `find_existing` (`sqlite.py:416`) still returns the row — the UNIQUE triple stands (#15 pending, L2 §9) — and selects `reversed_at`.
   - `supersedes_ancestors` (`sqlite.py:541`) walks `status='Confirmed' AND reversed_at IS NULL` — **rule 8**: after a reversal, the corrective inverse no longer false-fires `RELATE-028`.
   - **Rule 9**: `find_existing` feeds `RELATE-009`, whose `detail` carries the duplicate's reversal state.
3. **New 12th port method** — `LinkLookupPort.supersedes_blocking_link(source_id: int, target_id: int) -> Link | None` (`ember/relate/link_lookup.py`: 11 methods today, verified; + `SqliteLinkContext` adapter). BFS in id order through live Confirmed `supersedes` edges; returns the first link row connecting the two sides, else `None`. Read failure → `RELATE-021` (existing house pattern, docstring states it). Used only for `RELATE-028`'s detail text — the decision stays `supersedes_ancestors` (T5). L2 §14 #2 resolved: tie-break is "first edge in id order", pinned here.
4. **`RejectedLink` gains `detail`** — `RejectedLink(code, detail: str | None = None)` (`link_gatekeeper.py:57-59`, dataclass today). `validate_add_link` rule 8's rejection carries `"blocked by link {id} ({source} -> {target})"` (the blocking link's id + both endpoint ids — data); rule 9's carries `"link {id} exists"`, plus `" (reversed)"` when the duplicate has `reversed_at`.
5. **CLI** — the relate rejection line prints `code` then `detail` when present (L2 §9). No new command, no flag (I2/I12 unchanged).
6. **Architecture test** (`tests/test_architecture.py`) — add one explicit test asserting no engine core module (`ember/relate/*.py`, `ember/maintain/*.py`, `ember/query/*.py`, `ember/capture/*.py`) references `link_replay` (adapters live outside every core's reach, L2 §Z T9). L2 records the existing `test_*_core_does_not_import_adapters` token scans already enforce this; the explicit line makes the `link_replay` contract named, per L1 §5. Glob note resolved: this phase adds no core subpackage, so the `*.py` globs stay as-is (L2 §Z T9).

## 3. Errors (codes only, per L2 §12)

- `RELATE-028` — code value unchanged; `detail` gained (rule 8).
- `RELATE-009` — code value unchanged; `detail` gained (rule 9).
- `RELATE-021` — port read failure from the new method (existing code).

## 4. Test Targets (L2 §13, relate readers group)

This step owns:
- `test_reversed_supersedes_not_cycle` — after a reversal, the inverse `supersedes` passes rule 8 (no `RELATE-028`).
- `test_relate_028_names_blocking_link` — genuine cycle → code `RELATE-028`; the detail carries the link id + both endpoints (assert the data, not the wording — I21).
- `test_relate_009_duplicate_reports_reversed_state` — duplicate of a reversed row → `RELATE-009` with the reversed state in `detail`.
- Architecture test: the new `link_replay` core-imports test in `tests/test_architecture.py`.
- Gatekeeper units on the fake port: `detail` is `None` on every non-028/009 rejection; a reversed duplicate flips rule 9's detail only.
- Integration (real temp DB): reverse via `reverse-supersedes`, then `insert` the corrective inverse through the port path — commit succeeds where it failed before step 3.

Floors landed in step 01 (L2 §13 "Floors" line). Steps 01–02 own migration and replay tests (L2 §13).

## 5. CLI check (Rule S1)

No new CLI command ships here (relate writes need an API key and the confirm loop — no non-AI link path exists, verified in the maintain step plans). The inspectable artifact is the suite plus the printed rejection line:

```
$ <relate CLI path that raises RELATE-028>
error: RELATE-028 SupersedesCycle | ... | blocked by link 4 (2 -> 3)
```

Exit 1, code first, detail after — asserted in the CLI test by checking the line contains `RELATE-028`, the link id, and both endpoint ids (never the exact prose).

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

(to be filled after implementation)

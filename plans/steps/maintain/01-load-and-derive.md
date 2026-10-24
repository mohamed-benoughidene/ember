# L3 Maintain Step 1: Load + Derive (Phase 1 + Phase 2)

Implements Phase 1 (Load) and Phase 2 (Derive) of the L2 Maintain plan. Read every item and every confirmed link, derive the status each item should have, and return the changes — without writing anything. Ships migration 010, the error namespace, the lookup port, the pure derivation, and a runnable `ember maintain --dry-run`.

## 0. Constitution rules this step enforces

- **B1** — `ember/maintain/derive.py` (pure rules) is a separate module from `ember/maintain/maintain_lookup.py` (the port).
- **B2** — engine core reads `items`, `links`, and `change_log` only through `MaintainLookupPort`; no direct table access.
- **B3** — the derivation depends on the snapshot value, not on the DB.
- **B4** — the four rules hide inside `derive_status_changes`; callers see one function.
- **B5** — the port has 3 methods for 3 reads, not one method per query shape.
- **D6** — migration 010 is a numbered script in `ember/adapters/migrations/`; the version is the `schema_version` table row.
- **I1** — functions are named by job (`derive_status_changes`, `merge_and_filter`).
- **I2** — no boolean behaviour flags. `load_item_candidates` / `load_latest_candidates` are separate functions, not one with a flag.
- **I3** — every public function takes at most 2 inputs.
- **I4** — every public function returns a named object (`MaintainSnapshot`, `StatusChange`), never a tuple.
- **I5** — each failure mode has its own code (L2 §6).
- **I6** — all MAINTAIN-NNN codes subclass `EmberError`.
- **I7** — fail fast; validate at the CLI edge; the core raises named errors.
- **I9** — the port is the trust boundary; the core trusts what it returns.
- **I10** — migration 010 is additive (two new columns), no rename.
- **I11** — each port method's docstring lists the codes it raises.
- **I12** — the CLI prints the report to stdout and errors to stderr.
- **I13** — `--db` and the schema check happen once at boot (`open_maintain_database`).
- **I17 / I21** — error codes are stable; tests assert the code, not the message.
- **P3** — this step is Phases 1 + 2 of the L2 §4 pipeline.
- **P4** — the DB access is a port; the adapter is the only thing that touches `sqlite3`.
- **T1** — Phase 2 is pure: no I/O, no clock, no DB.
- **T2** — side effects are pushed to the `MaintainLookupPort` adapter.
- **T3** — unit tests use a fake lookup, not mocks.
- **T9** — `ember/maintain/*.py` imports nothing from `ember.adapters.*`.
- **S1** — `ember maintain --dry-run` runs this step alone.
- **S2** — `tests/maintain/` is the dedicated suite.
- **S3** — input/output shapes in §2 and §3.

## 1. Job

Read the whole `items` table, the whole set of Confirmed `links`, and the set of reversed link ids; then compute, for each item that needs it, the status it should have. Pure derivation — no writes. The dry-run CLI prints what the sweep would do.

## 2. Inputs

From the CLI:
- `--db PATH` (default: `DEFAULT_DB_PATH` from `ember.cli`).
- The CLI opens the DB via **`open_maintain_database(db_path)`** (new, in `ember/adapters/sqlite.py`, mirroring `open_relate_database` at `sqlite.py:56-83`). It refuses a missing file, probes for corruption, applies migrations, and checks `schema_version >= 10`. A missing file raises `MAINTAIN-007`; a corrupt file raises `MAINTAIN-007`; a failed migration raises `MAINTAIN-008`; a stale version raises `MAINTAIN-009`.
- **Do not use `open_database`.** It creates a missing DB and wraps no errors, so a corrupt file would leak a raw `sqlite3.Error` past the CLI's `except EmberError`, and `MAINTAIN-007` would be unreachable.

From the port (`MaintainLookupPort`, L2 §4.5):
- `list_items() -> list[ItemState]` — every item: id, type, status, close_reason, status_origin. Raises `MAINTAIN-010`.
- `list_confirmed_links() -> list[Link]` — every `links` row with `status='Confirmed'`. Raises `MAINTAIN-010`.
- `list_reversed_link_ids() -> set[int]` — the `link_id`s carrying a `link_reversed` change_log row. Raises `MAINTAIN-010`.

`Link` is **imported from `ember.relate.rows`**, not redefined. `ember/adapters/sqlite.py:36` already does `from ember.relate.rows import ChangeLogEntry, Link, NewItem`; a second definition would put two shapes for one table in one file.

## 3. Outputs

- `ItemState(id: int, type: str, status: str, close_reason: str | None, status_origin: str)` — one item's lifecycle state.
- `MaintainSnapshot(items: list[ItemState], links: list[Link], reversed_link_ids: set[int])` — the whole world the derivation reads.
- `StatusChange(item_id: int, old_status: str, new_status: str, close_reason: str | None, old_close_reason: str | None, trigger_cause: str, link_id: int | None)` — one item's intended status change. 7 fields; the `change_log` encoding (`old_value` / `new_value`) is derived in the adapter, not carried here.

## 4. Steps

1. **Load the snapshot.** Call the three port methods and build `MaintainSnapshot`.
2. **Derive the closes.**
   - For each Confirmed `supersedes` link **not in `reversed_link_ids`**: the target item's desired close reason is `superseded`.
   - For each Confirmed `answers` link whose target is a `Question`: the desired reason is `answered`.
   - Tie-break: if the same target is hit by both, `superseded` wins.
3. **Derive the challenges.**
   - Every target of a Confirmed `contradicts` link → `Challenged`.
   - Plus every **source** of a Confirmed `depends_on` link whose target is a *flagging-closed* item. "Flagging-closed" = currently `Closed` with reason `invalidated`/`superseded`/`reversed`, **or** being closed in this same sweep with one of those reasons. `answered` and `expired` do **not** flag dependents (spec 3.5:103).
   - Single step only. A dependent-of-a-dependent is not challenged.
4. **Merge and filter.** `merge_and_filter(candidates, snapshot) -> list[StatusChange]`:
   - **One change per item.** The candidate list can hold several changes for one `item_id` (a `Decision` can be both superseded and contradicted — `ember/relate/compat.py:16` + `:21`). Keep exactly one: precedence `Closed > Challenged`.
   - Escalation-only: an item already `Challenged` is not re-written; an item already `Closed` is not re-closed. This is also why a human's `close_reason` is never overwritten by a machine close.
   - Skip any item with `status_origin='manual'` (the human-clear shield).
   - `old_status` is the item's status **read from the snapshot** — the observed prior status, never a constant.
5. **Return** `list[StatusChange]`.

The sweep's rules live in `derive_status_changes(snapshot)`. `merge_and_filter` is the shared Phase-2 boundary — step 3's three validators also run their output through it (except the manual-shield skip, which they bypass).

## 5. Errors (codes only, per L2 §6)

- `MAINTAIN-007` — DB file missing, corrupt, or permission denied.
- `MAINTAIN-008` — migration 010 crashed during apply.
- `MAINTAIN-009` — `schema_version.version` < 10 (defensive: `open_maintain_database` migrates before it checks).
- `MAINTAIN-010` — the `items`, `links`, or `change_log` read failed.
- `MAINTAIN-002` — `--reason` is not one of the 5 reasons. (Step 3's command; listed here for the namespace.)
- `MAINTAIN-003` — `--reason` is a machine-only reason. (Step 3's command.)
- `MAINTAIN-004` — `close-item` on an already-`Closed` item. (Step 3's command.)
- `MAINTAIN-005` — reversal precondition failed. (Step 3's command.)
- `MAINTAIN-006` — `set-status --to` invalid. (Step 3's command.)
- `MAINTAIN-001` — the `--item` id does not exist. (Step 3's command.)

**No `MAINTAIN-011` / `MAINTAIN-012` in this step.** This step writes nothing — those belong to step 2's write path.

## 6. Test Targets

Unit (in-memory `FakeMaintainLookup`, in-memory snapshot — no DB):
- Rule 1: Confirmed `supersedes` → target gets `Closed:superseded`.
- Rule 2: dependency `Closed` with reason `invalidated`/`superseded`/`reversed` → dependent gets `Challenged`; reason `answered`/`expired` → **not** challenged.
- Rule 2 single-step: a dependent-of-a-dependent is **not** challenged.
- Rule 3: Confirmed `contradicts` → target `Challenged`.
- Rule 4: Confirmed `answers` → target `Question` `Closed:answered`.
- Tie-break: `supersedes` beats `answers` for the same target.
- **One change per item:** a `Decision` both superseded and contradicted → exactly one change (`Closed:superseded` wins). Also rule-2-vs-rule-3 and rule-1-vs-rule-2.
- **A reversed link is not a live supersedes:** a `supersedes` link in `reversed_link_ids` → no rule-1 close.
- `Rejected` links are ignored by all four rules.
- Escalation-only: a `Challenged` item is not written back to `Active`; a `Closed` item is not re-closed. **This is also the test that a human's `close_reason` survives a later machine close.**
- Manual shield: an item with `status_origin='manual'` is skipped.
- `old_status` is the **observed** prior status (`Challenged`, not `Active`, for a challenged target closed by rule 1).
- Empty snapshot → empty change list (no raise).

Integration (real SQLite temp DB, migrations 001-010 applied):
- Migration 010 on a **non-empty** DB: pre-existing rows survive, their `close_reason` is NULL, `status_origin` is `'derived'`.
- The 5 existing tests migration 010 breaks are updated: `tests/test_migration_runner.py:83`, `tests/test_migrations.py:210`, `tests/test_source_storage_integration.py:66`, `tests/test_relate_db_open.py:110` (all `version == 9` → `10`), and `tests/test_migrations.py:19` (the exact `items` column list → append `close_reason`, `status_origin`). **Do NOT touch `tests/test_relate_db_open.py:79`** — it asserts Relate's `required == 9` and must keep passing.
- `open_maintain_database` on a missing file → `MAINTAIN-007`.
- `open_maintain_database` on a corrupt file → `MAINTAIN-007`.
- `open_maintain_database` with a failing migration → `MAINTAIN-008`.
- `open_maintain_database` with `schema_version` = 9 and migrations skipped → `MAINTAIN-009`.
- `SqliteMaintainContext` read failure → `MAINTAIN-010` (all 3 reads).
- A seeded DB sweep → the exact `StatusChange` list (item ids, statuses, reasons, trigger causes, link ids).

## 7. CLI check (Rule S1)

- `ember maintain --dry-run --db <fixture>` → prints the planned changes (one line per change + the summary) and **writes no `items` or `change_log` rows**; exit 0.
  - The dry-run still applies migrations, so it creates the file and schema on a fresh path. The guarantee is "writes no rows", not "touches no file".
  - The dry-run still fails on domain errors — the flag check happens **after** the validators.

## 8. Out of Scope (this step)

- Writing anything (Phase 3) — step 2.
- The store port and the atomic batch — step 2.
- `ember close-item` / `set-status` / `reverse-supersedes` — step 3.
- The human-clear shield's write path — step 3.
- The `link_reversed` marker write — step 3.

## 9. Next

Step 2 adds the write path (Phase 3 + Phase 4) and the `ember maintain` command. Step 3 adds the three human commands.

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #1) Whether `ember relate` chains `ember maintain` — step 2 confirms the seam. Step 1 does not pick.
- (L2 §9 #2) The report's exact wording and ordering — step 2 picks (the buckets are fixed: `closed`, `challenged`, `reopened`, `unchanged`).
- (L2 §9 #4) Whether the sweep reports the items it skipped because they were `manual` — step 2 picks.
- (L2 §9 #5) The `--dry-run` output shape — step 2 picks; it shares the real run's formatter.

## 11. Rollback

This step's writes are limited to migration 010, which is two `ALTER TABLE items ADD COLUMN` statements. `ALTER TABLE ADD COLUMN` cannot lose rows, and the runner applies each script plus its `schema_version` bump in one transaction, so a failed migration rolls back both.

No data rollback per L1 §4 rule 7. Undo before the first Maintain run on an existing DB: `cp ember.db ember.db.bak`.

**L2 amendment log entries recorded by this step** (folded into `plans/engine-maintain-plan.md` when the L2 is amended):
- None yet. If step 1 changes any port method, error trigger text, or the `StatusChange` shape, record it here and amend the L2 in the same commit.

## 12. Build Notes (post-implementation)

_Landed on `feat/maintain-engine`._

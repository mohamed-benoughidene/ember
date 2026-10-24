# L3 Maintain Step 2: Apply + CLI (Phase 3 + Phase 4)

Implements Phase 3 (Apply) and Phase 4 (Report) of the L2 Maintain plan, and ships the `ember maintain` command. Writes the derived status changes to `items` and `change_log` in one transaction, then prints what changed.

## 0. Constitution rules this step enforces

- **B1** — `ember/maintain/apply_status.py` (the write port) is separate from `ember/maintain/derive.py` (the pure rules).
- **B2** — engine core writes only through `MaintainStorePort`; no direct table access.
- **B3** — the store depends on the port shape, not on SQLite.
- **B4** — the atomic batch hides inside one method; callers see one call.
- **D1** — `change_log` is append-only; the batch never edits or deletes a log row.
- **D2** — `items.status` and `close_reason` are derived caches; `change_log` is the record of truth.
- **D3** — the `change_log` row and the `items` row are written in the **same transaction**, so they can never disagree.
- **D5** — no column rename, no schema change in this step.
- **P3** — this step is Phases 3 + 4 of the L2 §4 pipeline.
- **P4** — the write is a port; the adapter is the only thing that touches `sqlite3`.
- **I1** — the method is named by job (`apply_status_changes`).
- **I2** — no boolean behaviour flags. `--dry-run` never crosses into a function: the CLI omits the write call.
- **I3** — `apply_status_changes(changes)` takes 1 input.
- **I4** — returns a named value, not a tuple. The int is `len(changes)` or it raises.
- **I5** — the items UPDATE and the change_log INSERT have separate codes.
- **I7** — fail fast, roll back the whole batch, never swallow.
- **I11** — the port method's docstring lists the codes it raises.
- **I12** — the report goes to stdout; errors go to stderr with `error: {exc.log_line()}`.
- **I15** — no external service, no timeout.
- **I17 / I21** — error codes are stable; tests assert the code, not the message.
- **T1** — Phase 2 (step 1) stays pure; this step is the edge.
- **T2** — the transaction lives in the adapter.
- **T3** — unit tests use a fake store; the atomicity test uses the **real** adapter.
- **T4** — one integration test per write path.
- **T9** — `ember/maintain/*.py` imports nothing from `ember.adapters.*`.
- **S1** — `ember maintain` runs the whole pipeline.
- **S3** — input/output shapes in §2 and §3.

## 1. Job

Take the `list[StatusChange]` the derivation produced and write it: every item's status, then one log row per change, then one commit. All or nothing. Then print what changed.

## 2. Inputs

From the CLI:
- `--db PATH` (default: `DEFAULT_DB_PATH` from `ember.cli`).
- `--dry-run` — run Phases 1 + 2, print the plan, write nothing.
- The DB is opened via `open_maintain_database(db_path)` (from step 1).

From step 1:
- `MaintainSnapshot` and `derive_status_changes(snapshot) -> list[StatusChange]`.

From the port (`MaintainStorePort`, L2 §4.5 — in `ember/maintain/apply_status.py`):
- `apply_status_changes(changes: list[StatusChange]) -> int` — one transaction, all-or-nothing; returns the number applied. Raises `MAINTAIN-011` on the items UPDATE, `MAINTAIN-012` on the change_log INSERT (both roll back the batch).
- `apply_status_origin(item_id: int, origin: str) -> None` — writes `items.status_origin` **and** its `change_log` row (`field_changed='status_origin'`) in one transaction. Raises `MAINTAIN-011` / `MAINTAIN-012`. **Step 3's command uses this; step 2 defines it.**

## 3. Outputs

- `MaintainResult(changed: list[StatusChange], applied: int, reopened: int)` — the named object Phase 4 reports from.
- STDOUT: one line per change (`item 3: Active -> Closed (superseded)`) plus a summary (`closed: 1, challenged: 2, reopened: 0, unchanged: 38`).
- `unchanged` = total items − changed items. A `reopened` bucket exists because `reverse-supersedes` and `set-status --to Active` move `Closed → Active` / `Challenged → Active`.

## 4. Steps

1. **Build the ports.** The CLI builds `MaintainPorts(lookup=SqliteMaintainContext(conn), store=SqliteMaintainStore(conn))` once.
2. **Load.** `_load(ports) -> MaintainSnapshot` — the three port reads.
3. **Derive.** `derive_status_changes(snapshot) -> list[StatusChange]`.
4. **Apply** — unless `--dry-run`. `store.apply_status_changes(changes)`.
5. **Report.** One `format_report(changes, total_items) -> list[str]` used by **both** the dry-run and the real run. Otherwise the dry run and the real run describe the same batch differently, and the flag is worse than useless.

### 4.1 The write transaction — the transport is specified

**Copy `insert_link_with_log` (`ember/adapters/sqlite.py:655-708`), not `save_validated_flag` (`sqlite.py:572-596`).** The latter commits per method; the former is the only writer in the codebase with one commit and a rollback in every `except`. The rules:

- **Exactly one `commit()`, at the very end.** Never inside the loop.
- **An explicit `rollback()` in every `except` branch** — even though no commit has happened. sqlite3 leaves the implicit transaction open on exception, and the next `commit()` on that connection would commit the partial batch.
- **One `BEGIN` for the whole batch** — do not rely on the implicit transaction and do not let any helper commit.

The batch, in order:
1. For each `StatusChange`: `UPDATE items SET status=?, close_reason=? WHERE id=?`.
2. For each `StatusChange`: `INSERT INTO change_log (item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause) VALUES (...)`.
3. `COMMIT`.

**No `status_origin` in the sweep's UPDATE.** The sweep only writes items whose `status_origin` is `'derived'`, so writing it is a no-op that invites "can the sweep un-manual an item?" (it must not). The shield is written by `set-status` only, through `apply_status_origin`.

**The timestamp comes from the adapter's clock.** `change_log.timestamp` is `NOT NULL` and `StatusChange` does not carry it. `SqliteMaintainStore(conn, *, clock: Callable[[], str] | None = None)`, defaulting to `_utc_now`. This is the house pattern (`SqliteItemGatekeeper`, `SqliteSourceStore`, `SqliteEmbedderStore` all take `clock=`). Phase 2 stays clock-free.

**The `change_log` encoding is derived in the adapter**, not carried in `StatusChange`:
- `old_value` = `old_status` if the item was not closed, else `f"{old_status}:{old_close_reason}"`.
- `new_value` = `new_status` if not a close, else `f"{new_status}:{close_reason}"`.
- `field_changed` = `'status'` for every status write.
- `item_id` = the item whose status changed (this diverges from Relate's convention — see L2 §4.6).

### 4.2 Orchestration

`ember/maintain/run_maintain.py` holds the shape from L2 §4.7:

```python
@dataclass(frozen=True)
class MaintainPorts:
    lookup: MaintainLookupPort
    store: MaintainStorePort

@dataclass(frozen=True)
class MaintainRequest:
    command: str            # "sweep" | "close_item" | "set_status" | "reverse_supersedes"
    item_id: int | None = None
    reason: str | None = None
    to_status: str | None = None
    link_id: int | None = None
    dry_run: bool = False

@dataclass(frozen=True)
class MaintainResult:
    changed: list[StatusChange]
    applied: int
    reopened: int
```

Entry points: `run_sweep(ports, request) -> MaintainResult`, plus `run_close_item`, `run_set_status`, `run_reverse_supersedes` (step 3). All share a private `_load(ports)` and `_apply_and_report(ports, changes, request)`. The shared pipeline is a helper, not a phase engine — I2 holds and each command has its own named entry point.

**`run_maintain.py` lands in this step**, not step 1 — it needs both ports, and the store port arrives with the write path.

### 4.3 The CLI command

```
ember maintain [--dry-run] [--db <path>]
```

- `--dry-run` runs Phases 1 + 2, prints the plan, writes **no rows**. It is **not** "writes nothing" at the file level: `open_maintain_database` applies migrations, so a dry-run against a fresh path creates the file and schema. The guarantee is "writes no `items` or `change_log` rows."
- The dry-run still fails on domain errors — the flag check happens **after** the validators.
- Exit 0 on success, including "nothing to change".
- The report goes to stdout. Errors go to stderr as `error: {exc.log_line()}`.

## 5. Errors (codes only, per L2 §6)

- `MAINTAIN-011` — the `items` UPDATE failed; the whole batch rolled back.
- `MAINTAIN-012` — the `change_log` INSERT failed; the whole batch rolled back.
- `MAINTAIN-007` — DB file missing, corrupt, or permission denied.
- `MAINTAIN-008` — migration 010 crashed during apply.
- `MAINTAIN-009` — `schema_version.version` < 10.
- `MAINTAIN-010` — an `items`, `links`, or `change_log` read failed.

**No other code fires in this step.** `MAINTAIN-001` through `MAINTAIN-006` belong to step 3's commands.

## 6. Test Targets

Unit (fake store — the pipeline's shape, not the adapter's atomicity):
- The dry-run path calls the store **zero** times.
- The write path calls `apply_status_changes` exactly once with the derived list.
- `format_report` buckets the changes correctly: `closed`, `challenged`, `reopened`, `unchanged`.
- `unchanged` = total items − changed items.

Integration (real SQLite temp DB, migrations 001-010 applied):
- A full sweep on a seeded DB → exact `items.status` + `close_reason` values, exact `change_log` rows (correct `trigger_cause`/`old_value`/`new_value`/`link_id`/`timestamp`).
- Idempotence: run the sweep twice → the second run writes **zero** rows.
- **Atomicity — with a REAL connection and a REAL constraint violation, not a fake.** The vehicle: give one `StatusChange` a `link_id` with no `links` row → the `change_log.link_id REFERENCES links(id)` FK (migration 008) raises `FOREIGN KEY constraint failed` on the INSERT, because `_connect` sets `PRAGMA foreign_keys = ON` (`sqlite.py:45`). Assert: **zero** `items` rows changed and **zero** `change_log` rows written, and the error is `MAINTAIN-012`.
  - Trap: a test that builds its own connection with bare `sqlite3.connect` has FK **off** and the violation silently won't fire. Use `open_maintain_database` / `_connect`.
  - Trap: a fake store cannot observe the adapter's commit boundaries, so it cannot test this. The test must run against the real `SqliteMaintainStore`.
- The items UPDATE fails (a `StatusChange` whose `new_status` violates the `items.status` CHECK) → `MAINTAIN-011`, and the whole batch rolls back.
- The store stamps `timestamp` from its injected clock (`clock=lambda: FIXED_TIME`) — the same technique `tests/test_item_store_integration.py` uses.

CLI:
- `ember maintain --db <fixture>` exits 0 and prints the summary.
- `ember maintain --dry-run --db <fixture>` prints the plan and writes **no rows** (not "no file").
- `ember maintain --db <missing>` exits 1 with `MAINTAIN-007`.

## 7. CLI check (Rule S1)

- `ember maintain --db <fixture>` → prints one line per change + the summary; exit 0.
- `ember maintain --dry-run --db <fixture>` → prints the same lines; writes no rows; exit 0.

## 8. Out of Scope (this step)

- The three human commands — step 3.
- The `status_origin` shield write (`apply_status_origin` is defined here; step 3 calls it).
- The `link_reversed` marker write — step 3.
- The reversal itself — step 3.

## 9. Next

Step 3 adds `ember close-item`, `ember set-status`, and `ember reverse-supersedes`, plus their three pure validators.

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #1) Whether `ember relate` chains `ember maintain` at the end of its confirm loop (closes the stale window). L2 picks "no — separate commands"; **this step confirms the seam.** The `run_sweep` entry point is the place a future chain would call.
- (L2 §9 #2) The report's exact wording and ordering — **this step picks** (the buckets are fixed: `closed`, `challenged`, `reopened`, `unchanged`).
- (L2 §9 #4) Whether the sweep reports the items it skipped because they were `manual` — **this step picks.**
- (L2 §9 #5) The `--dry-run` output shape — **this step picks**; it shares the real run's `format_report`.

**L2 amendment log entries recorded by this step** (folded into `plans/engine-maintain-plan.md` when the L2 is amended):
- None yet. If step 2 changes any port method, error trigger text, the `StatusChange` shape, or the `change_log` encoding, record it here and amend the L2 in the same commit.

## 11. Rollback

Writes are append-only: `items.status`/`items.close_reason` are updated in place and `change_log` rows are inserted. There is no down-migration for migration 010, so the schema change is forward-only.

Undo before the first Maintain run on an existing DB: `cp ember.db ember.db.bak`.

No data rollback per L1 §4 rule 7. A `change_log` row is never edited or deleted — a mistaken status change is corrected by a new row, not by editing history.

## 12. Build Notes (post-implementation)

_Landed on `feat/maintain-engine`._

# L3 Maintain Step 3: Human Actions (close-item + set-status + reverse-supersedes)

Implements the three human commands of the L2 Maintain plan. Each one loads the snapshot, runs a pure validator, writes through the same atomic store, and prints its own one-liner. Ships the `status_origin` shield row and the `link_reversed` reversal marker.

## 0. Constitution rules this step enforces

- **B1** — the three validators live in `ember/maintain/human_actions.py`; the user loop is not a phase.
- **B2** — the validators read through `MaintainLookupPort`; the writes go through `MaintainStorePort`.
- **B3** — the validators depend on the snapshot value, not on the DB.
- **B4** — each command is one thin entry point over the shared pipeline.
- **D1** — `change_log` is append-only; the reversal appends, never edits.
- **D2** — `items.status`/`close_reason`/`status_origin` are derived caches; `change_log` is the record of truth.
- **D3** — the `change_log` row and the `items` row are written in the **same transaction**.
- **D4 / I9** — `--reason`, `--to`, and `--item` are outside data; validated at the CLI edge, then trusted inside.
- **I1** — named by job (`validate_close_item`, `validate_set_status`, `validate_reverse_supersedes`).
- **I2** — no boolean behaviour flags. `--to Active` and `--to Challenged` are values, not switches; the only boolean is `dry_run`, which never crosses into a function.
- **I3** — every validator takes at most 3 inputs.
- **I4** — every validator returns a named `list[StatusChange]`, never a tuple.
- **I5** — each failure mode has its own code (L2 §6).
- **I6** — all MAINTAIN-NNN codes subclass `EmberError`.
- **I7** — fail fast; the validator raises before any write.
- **I11** — the validator docstrings list the codes they raise.
- **I12** — one-liners to stdout; errors to stderr with `error: {exc.log_line()}`.
- **I17 / I21** — error codes are stable; tests assert the code, not the message.
- **P3 / P4** — the same Phase 1-4 pipeline as the sweep; DB access is a port.
- **T1** — the validators are pure.
- **T2** — side effects are pushed to the store port.
- **T3** — unit tests use a fake lookup.
- **T9** — `ember/maintain/*.py` imports nothing from `ember.adapters.*`.
- **S1** — each command runs alone.
- **S3** — input/output shapes in §2 and §3.

## 1. Job

Give the human three ways to change an item's status by hand: retire it (`close-item`), move it between Active and Challenged (`set-status`), and undo a supersedes (`reverse-supersedes`). Each one is deterministic, writes an audit row, and never deletes anything.

## 2. Inputs

From the CLI:
- `ember close-item --item <id> --reason <invalidated|expired> [--dry-run] [--db <path>]`
- `ember set-status --item <id> --to <Active|Challenged> [--db <path>]`
- `ember reverse-supersedes --item <id> --link <id> [--db <path>]`
- `--db PATH` (default: `DEFAULT_DB_PATH` from `ember.cli`).
- The DB is opened via `open_maintain_database(db_path)` (from step 1).

**`--reason` and `--to` are plain `str` options, NOT `click.Choice`.** The domain codes must fire from the command body; `click.Choice` would reject a bad value with exit 2 before the code could run.

**`--item` is `type=int`**; a non-integer exits 2 (Click's own error). **`MAINTAIN-001` is checked before `MAINTAIN-004`/`005`/`006`** — `reverse-supersedes --item 99 --link 1` → `MAINTAIN-001`, never `MAINTAIN-005`.

From the port (`MaintainLookupPort`, L2 §4.5): the same 3 methods as step 1.

From the port (`MaintainStorePort`, L2 §4.5):
- `apply_status_changes(changes: list[StatusChange]) -> int` — from step 2.
- `apply_status_origin(item_id: int, origin: str) -> None` — writes `items.status_origin` **and** its `change_log` row (`field_changed='status_origin'`) in one transaction. Raises `MAINTAIN-011` / `MAINTAIN-012`.

## 3. Outputs

- `list[StatusChange]` — the validated changes, ready for the store.
- `MaintainResult` — from step 2's orchestration.
- STDOUT one-liners: `item 5 closed: invalidated`, `item 5 challenged`, `item 5 active`, `item 7 reopened`.

## 4. Steps

### 4.1 `ember close-item --item N --reason R`

1. Load the snapshot.
2. **Validate** — `validate_close_item(snapshot, item_id, reason)`:
   - The item must exist → else `MAINTAIN-001`.
   - `--reason` must be one of the 5 enum values → else `MAINTAIN-002`.
   - `--reason` must be **human-settable**: only `invalidated` and `expired`. `superseded` and `answered` are machine reasons (rules 1 and 4); `reversed` is produced by the spec's reversal semantics, which restore an item rather than closing it. → else `MAINTAIN-003`.
   - The item must not already be `Closed` → else `MAINTAIN-004`.
   - **The close itself:** one `StatusChange(item_id=N, old_status=<observed>, new_status='Closed', close_reason=R, old_close_reason=<observed>, trigger_cause='user_closed', link_id=None)`.
   - **The rule-2 fan-out:** every direct `depends_on` dependent of N (the **source** of a Confirmed `depends_on` link whose **target** is N) becomes `Challenged` — one `StatusChange` each, with `trigger_cause='dependency_closed'` and `link_id` = that `depends_on` link id. This is the same shape as the sweep's rule 2, so the `answered`/`expired` exclusion and the single-step limit apply unchanged.
     - **A dependent that is already `Challenged` or `Closed` is not re-challenged** — the output goes through `merge_and_filter`'s escalation-only rule.
3. **Apply** — unless `--dry-run`. `store.apply_status_changes(changes)`. The close and the dependents' challenges land in **one transaction**.
4. **Report** — one line per change + the summary. The dry-run **shows the dependents it would challenge**.

`close-item` does **not** set the shield. A human close is a *derived* close (the sweep would produce it), so it must not freeze the item.

### 4.2 `ember set-status --item N --to S`

1. Load the snapshot.
2. **Validate** — `validate_set_status(snapshot, item_id, to)`:
   - The item must exist → else `MAINTAIN-001`.
   - `--to` must be `Active` or `Challenged` → else `MAINTAIN-006`.
   - The item must not be `Closed` → else `MAINTAIN-006` (only reversal reopens).
   - **No-op:** `--to` equal to the item's current status → return an **empty** change list. Exit 0, write nothing. **Do not set the shield.**
   - One `StatusChange(item_id=N, old_status=<observed>, new_status=S, close_reason=None, old_close_reason=<observed>, trigger_cause='user_set_status', link_id=None)`.
3. **Apply** — `store.apply_status_changes(changes)`.
4. **The shield** — only when the command is `--to Active` on a **`Challenged`** item (the human cleared the flag): also call `store.apply_status_origin(N, 'manual')`, which writes `items.status_origin` **and** a `change_log` row with `field_changed='status_origin'`, `old_value='derived'`, `new_value='manual'`, `trigger_cause='user_set_status'`, in one transaction.
   - `--to Challenged` does **not** set the shield. Challenging is not a resolution (spec 3.2:70 lists human-Challenged as a first-class state).
5. **Report** — `item 5 active` or `item 5 challenged`.

The shield is a **state lookup in the sweep's Phase 2 merge**: an item with `status_origin='manual'` is skipped. It suppresses re-deriving that item's status — that is its one job. It is **not** set by `close-item` and **not** set by `reverse-supersedes`.

### 4.3 `ember reverse-supersedes --item N --link L`

1. Load the snapshot.
2. **Validate** — `validate_reverse_supersedes(snapshot, item_id, link_id)`:
   - The item must exist → else `MAINTAIN-001`.
   - The item must be `Closed` → else `MAINTAIN-005`.
   - The item's `close_reason` must be `superseded` → else `MAINTAIN-005`.
   - The Confirmed `supersedes` link `L` must point **at** the item → else `MAINTAIN-005`.
     - **`--link` is required.** Two `X→supersedes→B` links can both be Confirmed (gatekeeper rule 8 rejects cycles, not fan-in), so the target alone does not identify the link to reverse.
3. **Apply** — the reversal writes **two** `change_log` rows and one item restore, in one transaction:
   - `StatusChange(item_id=N, old_status='Closed', new_status='Active', close_reason=None, old_close_reason='superseded', trigger_cause='reversal', link_id=L)` → the item UPDATE (`status='Active'`, `close_reason=NULL`) plus a `status` log row (`old_value='Closed:superseded'`, `new_value='Active'`).
   - **The marker:** a second `change_log` row with `field_changed='link_reversed'`, `old_value='Confirmed'`, `new_value='Reversed'`, `trigger_cause='reversal'`, `link_id=L`.
4. **Report** — `item 7 reopened`.

**The `links` row is NOT touched.** It stays `status='Confirmed'`. The `link_reversed` marker in `change_log` is what makes the reversal visible — to the sweep (rule 1 skips a reversed link) and to a reader of Engine D's `history` mode (join on `link_id`). It satisfies human spec 3.6:113 ("every change to a note **or link** adds a row to an audit ledger") — the link's change **is** logged.

**The reversal sets no shield.** After it, the item is `Active` with `close_reason=NULL`, and the sweep's rule 1 skips the reversed link — so the item is not re-closed. **A new supersedes from a different source onto the restored item closes it normally.** That is the difference from a shield: a shield would veto every future close.

**The dependents stay `Challenged`** (AI spec 3.5:111). The reversal does not clear them.

### 4.4 The three entry points

`ember/maintain/run_maintain.py` (from step 2) gains:

```python
def run_close_item(ports, request) -> MaintainResult
def run_set_status(ports, request) -> MaintainResult
def run_reverse_supersedes(ports, request) -> MaintainResult
```

All three share step 2's private `_load(ports)` and `_apply_and_report(ports, changes, request)`.

**The validators are authoritative and bypass the manual-shield skip** — `close-item` on a `manual` item must still work (a human close is not re-derived). Their output **does** pass through `merge_and_filter`'s escalation-only and one-per-item rules.

## 5. Errors (codes only, per L2 §6)

- `MAINTAIN-001` — the `--item` id does not exist.
- `MAINTAIN-002` — `--reason` is not one of the 5 reasons.
- `MAINTAIN-003` — `--reason` is a machine-only reason (`superseded`/`answered`/`reversed`).
- `MAINTAIN-004` — `close-item` on an item already `Closed`.
- `MAINTAIN-005` — reversal precondition failed (not `Closed`, wrong `close_reason`, or the named `--link` is not a Confirmed `supersedes` link pointing at it).
- `MAINTAIN-006` — `--to` is not `Active`/`Challenged`, or the item is `Closed`.
- `MAINTAIN-011` — the `items` UPDATE failed; the whole batch rolled back.
- `MAINTAIN-012` — the `change_log` INSERT failed; the whole batch rolled back.
- `MAINTAIN-007` / `008` / `009` / `010` — from the boot and load paths.

**Error precedence:** `MAINTAIN-001` is checked **before** `MAINTAIN-004`/`005`/`006`.

## 6. Test Targets

Unit (in-memory `FakeMaintainLookup` — pure validators, no DB):
- `validate_close_item`: `--reason invalidated` → one close change.
- `validate_close_item`: `--reason bogus` → `MAINTAIN-002`.
- `validate_close_item`: `--reason superseded` → `MAINTAIN-003`. `--reason answered` → `MAINTAIN-003`. `--reason reversed` → `MAINTAIN-003`.
- `validate_close_item`: an already-`Closed` item → `MAINTAIN-004`.
- `validate_close_item`: a missing item → `MAINTAIN-001`.
- `validate_close_item`: a dependent that is already `Challenged` is **not** re-challenged.
- `validate_close_item`: the fan-out challenges the **source** of a `depends_on` link whose **target** is the closed item (one `StatusChange` per dependent, `trigger_cause='dependency_closed'`).
- `validate_set_status`: `--to Bogus` → `MAINTAIN-006`. `--to Closed` → `MAINTAIN-006`.
- `validate_set_status`: a `Closed` item → `MAINTAIN-006`.
- `validate_set_status`: no-op (same status) → an **empty** change list, no raise.
- `validate_set_status`: a missing item → `MAINTAIN-001`.
- `validate_reverse_supersedes`: a missing item → `MAINTAIN-001`. An `Active` item → `MAINTAIN-005`. A `Closed` item with the wrong reason → `MAINTAIN-005`. A wrong `--link` → `MAINTAIN-005`.

Integration (real SQLite temp DB, migrations 001-010 applied):
- `close-item` on an item with dependents → the close + the dependents' `Challenged` in one transaction, both logged.
- `close-item` → the item is `Closed` but `status_origin` stays `'derived'` (it does **not** shield).
- `set-status --to Active` on a `Challenged` item → the item is `Active`, `status_origin='manual'`, a `status_origin` change_log row exists, and the **next sweep does not re-challenge it**.
- `set-status --to Challenged` on an `Active` item → the item is `Challenged`, `status_origin` stays `'derived'`, no shield row.
- `set-status` no-op → writes nothing, no `change_log` row.
- Reversal: Confirmed `supersedes` → sweep closes the old item → reverse → the old item is `Active` with `close_reason=NULL`, **two** `change_log` rows exist (`status` + `link_reversed`), the dependents **stay** `Challenged`, and the `links` row is unchanged (`status` still `Confirmed`).
- **The reversal does not veto future closes:** after a reversal, a NEW supersedes from a different source onto the restored item → the next sweep **closes** it.

CLI:
- `ember close-item --item 1 --reason invalidated` exits 0.
- `ember close-item --item 1 --reason bogus` exits 1 with `MAINTAIN-002`.
- `ember close-item --item 1 --reason superseded` exits 1 with `MAINTAIN-003`.
- `ember close-item --item 1 --reason reversed` exits 1 with `MAINTAIN-003`.
- `ember close-item --item 1 --reason invalidated` twice exits 1 with `MAINTAIN-004` on the second.
- `ember set-status --item 1 --to Closed` exits 1 with `MAINTAIN-006`.
- `ember set-status --item 1 --to Bogus` exits 1 with `MAINTAIN-006`.
- `ember set-status --item 1 --to Active` on an Active item exits 0 and writes nothing.
- `ember reverse-supersedes --item 99 --link 1` exits 1 with `MAINTAIN-001`.

## 7. CLI check (Rule S1)

- `ember close-item --item 1 --reason invalidated --db <fixture>` → `item 1 closed: invalidated` + the summary; exit 0.
- `ember set-status --item 2 --to Challenged --db <fixture>` → `item 2 challenged`; exit 0.
- `ember reverse-supersedes --item 3 --link 1 --db <fixture>` → `item 3 reopened`; exit 0.

## 8. Out of Scope (this step)

- The sweep's own rules (step 1) and its write path (step 2).
- `edit_item` and `remove_link` (human-only per spec 3.7, but no plan owns them — deferred issue per L2 §8).
- AI-proposed `close_item` (V1 uses a human-invoked command).

## 9. Next

The Maintain engine is complete. Next: the L2 amendments (L1, Relate, README, PROJECT_MAP), the GitHub issues, and the L3 plan for Engine D (Query).

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #3) Whether `close-item` should prompt for confirmation or stay flag-driven. **L2 picks flag-driven; this step keeps it.** If it is ever changed to a prompt, the step needs a `UserAbort` + exit 2 + an L2 §Z I12 update.

**L2 amendment log entries recorded by this step** (folded into `plans/engine-maintain-plan.md` when the L2 is amended):
- None yet. If step 3 changes any port method, error trigger text, the `StatusChange` shape, or the `change_log` encoding, record it here and amend the L2 in the same commit.

## 11. Rollback

Writes are append-only: `items.status`/`items.close_reason`/`items.status_origin` are updated in place and `change_log` rows are inserted. There is no down-migration for migration 010, so the schema change is forward-only.

Undo before the first Maintain run on an existing DB: `cp ember.db ember.db.bak`.

No data rollback per L1 §4 rule 7. A `change_log` row is never edited or deleted — a mistaken status change is corrected by a new row, not by editing history.

## 12. Build Notes (post-implementation)

_Landed on `feat/maintain-engine`._

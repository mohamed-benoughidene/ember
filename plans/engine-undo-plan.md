# L2 Plan: Undo and Redo (Maintain engine extension)

Status: DRAFT 2026-10-30, not yet through the review gate. Nothing is built.
Origin: `docs/ember-interface-spec.md` section 12 and user stories 111 to 123. Founder decisions: option A (undo appends ledger rows), grouping Option 2 (one group id column), rule amendments confirmed, all 2026-10-30.
L1: `plans/master-plan.md` §8, "Interface module amendment" items 5 and 6.
Branch: `ember-interface`.

## Plain words (for the founder)

Undo is not a new engine. It is a new human-only action inside Maintain. Every human change gets a "group number" in the ledger. `ember undo` finds the newest change not yet undone, checks nothing moved since, and writes the opposite change as new ledger rows. `ember redo` undoes the undo. Nothing is erased.

## §1 Purpose (one job)

Reverse the latest human change (and redo it), by appending ledger rows, refusing when anything it touched has changed since. Human-only: not on the L1 AI-callable list (L1 §4 rule 5 grows by `undo`, `redo`).

## §2 Facts this plan stands on (read from the code, 2026-10-30)

- `change_log` has columns `id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause`. No `group_id` today (`PROJECT_MAP.md` table list).
- Human writers: `SqliteMaintainStore.apply_status_changes` (close, set-status, and the sweep: the sweep must NOT get a group id), `apply_status_origin`, `apply_reversal`, `apply_item_edit`, `apply_remove_link` in `ember/adapters/sqlite.py`; `SqliteItemGatekeeper.save_validated_flag` (set/clear-validated, a Capture-side store).
- `run_set_status` writes the shield in a SECOND transaction (`ember/maintain/run_maintain.py`, `run_set_status`).
- `replay_reversals` (`ember/adapters/link_replay.py`) sets `reversed_at` to the timestamp of the highest-id `link_reversed` row, and `None` only when NO marker exists. It cannot express "un-reversed after a marker". Undo of a reversal needs a new marker meaning (§5.3).
- `classify_change_row` (`ember/query/history.py`) files unknown `(field, cause)` pairs as `unknown`. Undo rows need their own kinds.
- Last maintain error code in use: `MAINTAIN-022`. Last migration: 012. Engine floors: relate 12, maintain 11, query 10.
- Pure cores may not import adapters (T9, `tests/test_architecture.py`). The group-id source must therefore be injected (T1, T2).

## §3 Stack and module layout

No new package, no new dependency. Files (names at L3 discretion within the contracts):

```
ember/maintain/undo.py              (pure: derive the undo plan from ledger groups + current state)
ember/maintain/human_actions.py     (extended: validate_undo, validate_redo wrappers)
ember/maintain/apply_status.py      (port grows: next_group_id, apply_undo)
ember/maintain/run_maintain.py      (run_undo, run_redo; existing human entry points pass a group id)
ember/maintain/errors.py            (MAINTAIN-023 .. 027)
ember/adapters/sqlite.py            (group_id stamping; apply_undo; group read)
ember/adapters/migrations/013_add_change_log_group_id.sql
ember/adapters/link_replay.py       (marker meaning grows)
ember/adapters/db_check.py          (floor entry; group-id and replay checks)
ember/adapters/export.py            (group id printed per ledger row)
ember/query/history.py              (new kinds)
ember/cli.py                        (undo, redo commands)
```

## §4 CLI surface (Rule S1 samples, proposed)

```
$ ember close-item --item 3 --reason invalidated --db ember.db
item 3: Active -> Closed (invalidated) ...                       [exit 0]

$ ember undo --dry-run --db ember.db
undo group 7: close-item 3 -> item 3: Closed -> Active; item 5: Challenged -> Active (dry-run)   [exit 0]

$ ember undo --db ember.db
undone group 7 as group 8: item 3: Closed -> Active; item 5: Challenged -> Active   [exit 0]

$ ember undo --db ember.db            # item 5 was changed by a sweep meanwhile
error: MAINTAIN-025 UndoRefused | ember.maintain.run_maintain.run_undo | item changed since | item_id=5 group_id=7   [exit 1]

$ ember redo --db ember.db
redone group 7 as group 9: item 3: Active -> Closed (invalidated); ...   [exit 0]
```

Flags: `--dry-run` (the existing pattern, `close-item`) and `--db`. No other flags (I2). No `--group`: Undo always means "the newest". Output lines are final in L3 step 04.

## §5 Design

### §5.1 What a group is
One user action = one `group_id` shared by every ledger row the action wrote. The id is `MAX(group_id)+1`, allocated by the store port method `next_group_id()` (the pure core never invents it, T1). Rows from before migration 013 have `group_id = NULL` and are invisible to Undo (user story 123). Sweep rows, capture rows, relate rows and rejection rows stay `NULL` (spec 12.2 "Not covered").

Which actions stamp a group (the "undoable set", spec 12.2): `close-item` (item row + every `dependency_closed` row), `set-status` (status row + shield row, ONE group across its two transactions), `set-validated` / `clear-validated`, `edit-item`, `remove-link`, `reverse-supersedes` (status row + marker row).

### §5.2 Undo/redo markers (keeps "one column", spec 12.4)
Spec 12.4 requires the pointer from an undo to the group it reverses, and decided on ONE column. Chosen form: a marker row, like the existing `link_reversed` marker pattern. An undo is a new group U whose rows are the inverse changes plus one marker row `field_changed='undo_of', new_value='<G>', trigger_cause='user_undo'`. A redo is a new group R with its inverse-of-undo rows plus one marker `field_changed='redo_of', new_value='<U>', trigger_cause='user_redo'`. No second column.

### §5.3 The pure core (`undo.py`) — Phase 2
Input (typed): `UndoSnapshot { groups: list[LedgerGroup], items: list[ItemState], links: list[Link], origins: ... }` built in Phase 1 from the ledger grouped by `group_id` plus the current item/link state. Output: `UndoPlan { source_group, inverse_changes, marker }` or a named refusal.

Algorithm (rules from spec 12.6):
1. Build the stack: original-action groups in id order. A group is "done" unless a later `undo_of` marker names it and no later `redo_of` marker names that undo.
2. Undo target = the newest "done" original-action group. None → `MAINTAIN-023 NothingToUndo`.
3. Redo target = the newest undo group not yet redone, valid only if no original-action group was written after it ("a new human change clears Redo"). None → `MAINTAIN-024 NothingToRedo`.
4. **Refusal rule:** for every row of the group, the current value of the thing it changed must equal the row's recorded `new_value`. Any mismatch → `MAINTAIN-025 UndoRefused` with `item_id` / `link_id` / `group_id`. Nothing is written.
5. Inverse per row type (spec 12.2 table): status rows swap `old/new` (including `Closed:<reason>` encoding via the existing splitter), `validated` flips, `rationale`/`source` restore `old_value`, `link_removed` flips `Rejected -> Confirmed`, `status_origin` rows restore the earlier shield value exactly (spec 12.3 rule 3), `link_reversed` + `reversed_at` restore per §5.4.
6. An unrecognised row shape inside a group → `MAINTAIN-027 GroupRecordInvalid`, fail closed.

### §5.4 Reversal replay amendment
A reversal undo appends a `link_reversed` marker with `new_value='Confirmed'` (meaning "un-reversed"). `replay_reversals` is amended: the highest-id marker for the link wins; `new_value == 'Reversed'` → its timestamp, anything else → `None`. `db-check` replay stays consistent by construction. The `links.reversed_at` write and the marker go in the same transaction from one clock read (the existing pairing rule).

### §5.5 Store write
`apply_undo(plan)` — ONE transaction, ONE clock read: the `items` / `links` UPDATEs, the inverse `change_log` rows (each stamped with the new group id), and the marker row. Fails → full rollback. Reuses `MAINTAIN-012` for ledger insert failures; new `MAINTAIN-026 UndoWriteFailed` for the `items`/`links` UPDATE.

### §5.6 Read side
- `history`: new kinds `undone` (`undo_of` marker) and `redone` (`redo_of` marker); the inverse rows keep their normal kind (a status row is still `status_changed`) but show cause `user_undo` / `user_redo`. Existing `unknown` fallback unchanged.
- `export`: prints `group_id` for every ledger row (a new aligned field line, `-` when NULL). Existing byte-for-byte tests change; the golden is regenerated on purpose in step 05.
- `db-check`: add `("undo", 13)` to the floor table; add a group-id sanity check (every `undo_of`/`redo_of` marker names an existing group).

## §6 Error codes (new, stable, never reused, I17)

| Code | Name | Raised at |
|---|---|---|
| MAINTAIN-023 | NothingToUndo | §5.3 step 2 |
| MAINTAIN-024 | NothingToRedo | §5.3 step 3 |
| MAINTAIN-025 | UndoRefused | §5.3 step 4 (carries `group_id`, `item_id` or `link_id`) |
| MAINTAIN-026 | UndoWriteFailed | §5.5 UPDATE failure |
| MAINTAIN-027 | GroupRecordInvalid | §5.3 step 6 |

Reused with unchanged meaning: MAINTAIN-007/008/009 (boot), MAINTAIN-010 (read), MAINTAIN-011/012 (store). `MAINTAIN-023`'s detail says whether older changes exist that carry no group id (story 123).

## §7 Test targets (T1 to T4)

- **Unit, pure core:** one test per row of spec 12.2; the stack rules (undo, undo, redo, new change clears redo); the refusal rule; the shield cases (clear → undo restores `manual` exactly; sweep re-arm in between → refused); unrecognised group shape.
- **Integration, real temp DB:** every undoable action then `undo` then state equals the state before the action, ledger only grew; `redo` equals the state after the action; transaction rollback on injected failure (delegating-connection pattern from `test_edit_item_integration.py`); migration 013 on a copy of a real v12 file (rows preserved, new column NULL, safety copy `.bak-v12`, failed migration rolls back); `db-check` exit 0 after undo of a reversal.
- **CLI (S1):** the §4 samples with exit codes, `--dry-run` writes zero rows (hash proof).
- **E2E (one):** capture (fake AI) → relate (fake) → close-item → undo → redo → history, DB invariants asserted.
- **Not covered by tests:** behaviour with a v12 file written by an older Ember after a v13 upgrade (spec 12.8, unchecked). Manual check: open an upgraded file with the pre-013 build and run `ember history`.

## §8 Risks the maintainer must see (AGENTS.md section 2)

1. **Database structure change.** Migration 013 adds one nullable column. 0 existing rows change (no backfill). 0 database files are tracked in the repository. Rows in the maintainer's own local files: not counted (cannot be seen from here). Forward-only; the way back is the safety copy Ember writes before upgrading. **Before step 01 is built, the builder shows the then-current counts and asks for A or B again.**
2. **Rule 7 amendments** (L1 §8 item 5) — confirmed 2026-10-30, to be recorded in `engine-maintain-plan.md` §12 at step 03.
3. The set-validated writer lives in the Capture store (B2). Step 01 touches it with one optional parameter, nothing else.
4. Floors: relate 12 / maintain 11 / query 10 stay. A v12 file opened by `maintain` is migrated to 13 automatically by the existing runner.

## §9 Steps (L3), bottom-up, each commits separately

| # | File | Phase |
|---|---|---|
| 01 | `plans/steps/undo/01-migration-and-group-stamping.md` | Migration 013 + group id on the six human actions |
| 02 | `plans/steps/undo/02-undo-core.md` | Pure undo/redo derivation |
| 03 | `plans/steps/undo/03-store-and-replay.md` | `apply_undo`, replay amendment, rule 7 notes |
| 04 | `plans/steps/undo/04-cli-undo-redo.md` | `ember undo`, `ember redo`, docs |
| 05 | `plans/steps/undo/05-read-side-and-closeout.md` | history kinds, db-check, export, E2E, map |

## §10 Deferred to L3

- Final output wording of the undo/redo lines (step 04).
- Exact `group_id` column name check against `export` field labels (step 05).
- Whether `set-validated` stamping goes through a new optional argument or a small port (step 01; bounded by B2).
- Index on `group_id`: decide only if a measured read needs it (step 01).

## §Z Constitution compliance

- **B1** one job: undo/redo only. **B2** only public ports; the Capture store gets one optional argument, no reach-in. **B3** the rules (refusal, stack, shield) are pure logic, not in the CLI. **B5** one new pure module + one store method per direction.
- **D1** raw data untouched; no row is edited or deleted. **D2** `reversed_at` stays a rebuildable copy of the marker rows. **D3** the group pointer is a marker row, one fact one place. **D5** additive column only. **D6** migration 013, version stored. **D7** safety copy before upgrade.
- **P1** no decorative layer. **P3** pipeline: load → derive → apply → report. **P4** the DB sits behind the existing store/lookup ports.
- **I1** names by job (`derive_undo`, `run_undo`). **I2** `--dry-run` follows the existing pattern; no new behaviour flag. **I3** every function ≤ 4 inputs (`UndoSnapshot` wraps). **I4** named returns. **I5-I7** named errors, fail fast, handled at the CLI edge. **I10** additive only. **I11/I21** contracts list codes. **I12** exit 0/1, errors on stderr. **I17-I20** codes 023-027 new, entity ids carried, no secrets.
- **T1** core pure, group id injected. **T2** side effects in the store. **T3/T4** fakes + real temp DB. **T5/T6** observable behaviour and codes. **T9** `undo.py` imports no adapter.
- **S1** §4 samples. **S2** `tests/maintain/test_undo_*.py` run alone. **S3** shapes in §5. **S4** transfer = ledger rows.

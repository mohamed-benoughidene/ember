# L2 Plan: Undo and Redo (Maintain engine extension)

Status: BUILT (2026-10-30). Maintainer gate passed (2026-10-30: migration 013 = A, D3 dry-run = A). Steps 01-05 + code review (2 axes) + fix round 1. Commits `52e3e38..ba2c920` on `ember-interface`; suite 984 passed, 4 deselected. Known handoffs: deviation U3-3/U4-1 (all-links read), U5-1 new history kinds (`undone`/`redone`/`item_edited`/`link_unreversed`) feed the app's kind-label table; a v13 file opened by a pre-013 build stays unchecked (spec 12.8).
Origin: `docs/ember-interface-spec.md` section 12 and user stories 111 to 123. Founder decisions: option A (undo appends ledger rows), grouping Option 2 (one group id column), rule amendments confirmed, all 2026-10-30.
L1: `plans/master-plan.md` §8, "Interface module amendment" items 5 to 8.
Branch: `ember-interface`.

## Plain words (for the founder)

Undo is not a new engine. It is a new human-only action inside Maintain. Every human change gets a "group number" in the ledger. `ember undo` finds the newest change not yet undone, checks nothing moved since, and writes the opposite change as new ledger rows. `ember redo` undoes the undo. Nothing is erased.

## §1 Purpose (one job)

Reverse the latest human change (and redo it), by appending ledger rows, refusing when anything it touched has changed since. Human-only: L1 §4 rule 5 grows by `undo`, `redo` (L1 amendment item 6).

## §2 Facts this plan stands on (read from the code, 2026-10-30)

- `change_log` columns today: `id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause`. No group column.
- All `INSERT INTO change_log` statements are in `ember/adapters/sqlite.py`. The human, undoable writers are `SqliteMaintainStore` (`apply_status_changes`, `apply_status_origin`, `apply_reversal`, `apply_item_edit`, `apply_remove_link`) and `SqliteItemGatekeeper.save_validated_flag` (a Capture-side store). `apply_status_changes` is also the sweep's writer, and the sweep must NOT get a group id.
- `run_set_status` writes the shield in a SECOND transaction (`ember/maintain/run_maintain.py`).
- **Two readers treat a reversal as "any `link_reversed` row exists":** `SqliteMaintainContext.list_reversed_link_ids` (`SELECT DISTINCT link_id ... field_changed = 'link_reversed'`, feeds `derive.py` line 182) and `replay_reversals` (`ember/adapters/link_replay.py`, highest-id marker wins, `None` only when no marker exists). Existing tests build markers with `new_value=None` (`tests/test_link_replay.py`).
- **The shield reads exact rows:** `derive._latest_clear` and `SqliteMaintainContext.list_shield_log` accept only `field_changed='status_origin'`, `trigger_cause='user_set_status'`, `new_value='manual'` as a clear.
- A clear writes the OLD origin (normally `derived`) as `old_value` and `manual` as `new_value` (`apply_status_origin`).
- `classify_change_row` (`ember/query/history.py`) maps a `(field_changed, trigger_cause)` pair to a kind and files unknown pairs as `unknown`; `close_reason` is filled only for kind `status_changed`.
- The `Closed:<reason>` encoding is split by the PRIVATE `_close_reason` in `ember/query/history.py`.
- `open_query_database` is read-only and never migrates (floor 10). `export` and `history` use it. `db-check` is read-only; any `FLOORS` entry above the file's version prints `floors: unmet` and result `DRIFT` (`ember/adapters/db_check.py`).
- Migration 011 triggers fire on `links` INSERT, `links` UPDATE OF `source_item_id/target_item_id/link_type`, and `items` INSERT/UPDATE OF `status/close_reason` (when `Closed` without a reason). An UPDATE of `links.status` is NOT blocked by any trigger, but `links.status` has `CHECK IN ('Confirmed','Rejected')`.
- Last maintain error code in use: `MAINTAIN-022`. Last migration: 012. Floors: relate 12, maintain 11, query 10.
- Pure cores may not import adapters, and `tests/test_architecture.py` greps raw text of `ember/maintain/*.py` for forbidden words (including in docstrings).

## §3 Stack and module layout

No new package, no new dependency. Files (names at L3 discretion within the contracts):

```
ember/maintain/undo.py              (pure: derive the undo/redo plan from ledger groups + current state)
ember/maintain/rows.py              (public split_status_value, UndoSnapshot/UndoPlan/UndoResult row models)
ember/maintain/human_actions.py     (validate_undo, validate_redo wrappers)
ember/maintain/apply_status.py      (port grows: apply_inverse_group)
ember/maintain/maintain_lookup.py   (port grows: list_grouped_ledger; list_shield_log/list_reversed_link_ids semantics change, §5.4)
ember/maintain/derive.py            (reads the new reversal/shield semantics)
ember/maintain/run_maintain.py      (run_undo, run_redo; human entry points pass a group id)
ember/maintain/errors.py            (MAINTAIN-023 .. 027)
ember/relate/rows.py                (GroupIdPort, a tiny neutral port beside ChangeLogEntry, shared by Maintain and Capture)
ember/adapters/sqlite.py            (group_id stamping; apply_inverse_group; grouped read; reader changes)
ember/adapters/migrations/013_add_change_log_group_id.sql
ember/adapters/link_replay.py       (marker semantics grow)
ember/adapters/db_check.py          (group-id check, only when version >= 13)
ember/adapters/export.py            (group id printed when the column exists)
ember/query/history.py              (new kinds and pairs)
ember/cli.py                        (undo, redo commands)
```

## §4 CLI surface (Rule S1 samples, proposed)

```
$ ember close-item --item 3 --reason invalidated --db ember.db
...                                                              [exit 0]

$ ember undo --dry-run --db ember.db
undo group 7 (close-item, item 3): item 3: Closed -> Active; item 5: Challenged -> Active (dry-run)   [exit 0]

$ ember undo --db ember.db
undone group 7 as group 8 (close-item, item 3): item 3: Closed -> Active; item 5: Challenged -> Active   [exit 0]

$ ember undo --db ember.db            # item 5 was changed by a sweep meanwhile
error: MAINTAIN-025 UndoRefused | ember.maintain.run_maintain.run_undo | item changed since | item_id=5 group_id=7   [exit 1]

$ ember redo --db ember.db
redone group 7 as group 9 (close-item, item 3): item 3: Active -> Closed (invalidated); ...   [exit 0]
```

Flags: `--dry-run` and `--db` only. `--dry-run` is the existing precedent (`close-item`, `edit-item`, `remove-link`, `maintain`) but is a boolean flag, which Constitution I2 discourages. **Decision A/B for the maintainer (§11 D3):** A keep `--dry-run` as an I2 exception, same as the four existing commands; B add a separate read-only `ember undo-preview` / `redo-preview` (two more commands, no flag). Recommended: A. Output lines are final in L3 step 04.

## §5 Design

### §5.1 What a group is
One user action = one `group_id` shared by every ledger row the action wrote. The id is `MAX(group_id)+1`, allocated through the neutral `GroupIdPort.next_group_id()` (the pure core never invents it, T1). Maintain and Capture both take that port by injection, so neither reaches into the other (B2). Rows from before migration 013 have `group_id = NULL` and are invisible to Undo (story 123). Sweep, capture-confirm, relate-confirm and rejection rows stay `NULL` (spec 12.2 "Not covered").

Undoable set (spec 12.2): `close-item` (item row + every `dependency_closed` row), `set-status` (status row + shield row, ONE group across its two transactions), `set-validated` / `clear-validated`, `edit-item`, `remove-link`, `reverse-supersedes` (status row + marker row). An AI-proposed close accepted in `maintain` rides `run_close_item`, so it IS a human close and is stamped; the sweep part of the same command is not.

### §5.2 Undo/redo markers (keeps "one column", spec 12.4)
The pointer from an undo to the group it reverses is a marker row, like the existing `link_reversed` marker. An undo is a new group U: the inverse rows (cause `user_undo`) plus one marker `field_changed='undo_of', new_value='<G>', trigger_cause='user_undo'`. A redo is a new group R: the re-applied rows (cause `user_redo`) plus one marker `field_changed='redo_of', new_value='<U>', trigger_cause='user_redo'`. No second column.

### §5.3 The pure core (`undo.py`) — Phase 2
Input (typed): `UndoSnapshot { groups: list[LedgerGroup], items: list[ItemState], links: list[Link] }` built in Phase 1 by the new lookup read `list_grouped_ledger()` plus the existing reads. Output: `UndoResult { source_group_id, source_action, target_label, direction, changes, marker }`. `source_action` and `target_label` ("close-item", "item 3") carry what the Edit menu needs to say "Undo Close item 3" (story 113). **`derive_undo` and `derive_redo` return `UndoResult` or RAISE the named error. They never return a refusal.**

Rules (spec 12.6):
1. The stack is the original-action groups in id order. A group is "done" unless a later `undo_of` marker names it and no later `redo_of` marker names that undo.
2. Undo target = the newest "done" original-action group. None -> `MAINTAIN-023 NothingToUndo`.
3. Redo target = the newest undo group not yet redone, valid only if no original-action group was written after it. None -> `MAINTAIN-024 NothingToRedo`.
4. **Refusal rule:** for every row of the group, the current value of the thing it changed must equal the row's recorded `new_value`. Any mismatch -> `MAINTAIN-025 UndoRefused` with `group_id` and `item_id` or `link_id`. Nothing is written.
5. Inverse per row type (spec 12.2): status rows swap old/new (the `Closed:<reason>` value is split by a new PUBLIC `split_status_value` in `ember/maintain/rows.py`, next to the writer's encoding; `history.py` may call it; Maintain never imports a private function from Query), `validated` flips, `rationale`/`source` restore `old_value`, `link_removed` flips `Rejected -> Confirmed`, `status_origin` rows restore the old origin exactly (spec 12.3 rule 3), reversal rows per §5.4.
6. An unrecognised row shape inside a group -> `MAINTAIN-027 GroupRecordInvalid`, fail closed.

### §5.4 Reversal and shield semantics (corrects draft 1)
- **New marker field `link_unreversed`** (cause `user_undo`). Undoing a reversal appends `link_unreversed` and sets `links.reversed_at = NULL`; redoing it appends a `link_reversed` row (cause `user_redo`) and sets `reversed_at` to the new time. No existing row changes meaning (D5, I10): old builds that read only `link_reversed` simply do not know `link_unreversed` (see §8 risk 3).
- **Rule for every reader:** a link is reversed when its highest-id marker among `{link_reversed, link_unreversed}` is a `link_reversed`. This must be applied in BOTH `replay_reversals` and `list_reversed_link_ids` (else the sweep keeps skipping an un-reversed link). Existing tests keep passing because a `link_reversed` row with any `new_value` still counts as reversed when no `link_unreversed` follows it.
- **Shield:** a clear row is `status_origin` with `new_value='manual'` and cause `user_set_status` OR `user_redo`. `derive._latest_clear` and `list_shield_log` accept both, so a redo of a clear re-sets the shield boundary to the redo time. An undo of a clear writes `status_origin` back to the recorded OLD value (normally `derived`, cause `user_undo`) and the status back to `Challenged`; the old test text "restores `manual`" was wrong.

### §5.5 Store write
`apply_inverse_group(plan)` (named for the job; serves undo and redo) — ONE transaction, ONE clock read: the `items`/`links` UPDATEs, the inverse `change_log` rows (each stamped with the new group id), and the marker row. Failure -> full rollback. Reuses `MAINTAIN-012` for ledger insert failures; new `MAINTAIN-026 UndoWriteFailed` for the UPDATE. A redo of a close sets `status` and `close_reason` in the same UPDATE (migration 011 trigger). **B2 exception stated:** undo of `validated` writes `items.validated`, a Capture-owned column, through this Maintain store method; it is the only cross-module write and is covered by a test.

### §5.6 Read side (corrects draft 1)
- `history`: every existing human `(field, cause)` pair is added again with causes `user_undo` and `user_redo`, mapped to the SAME kind as the original (so a status row stays `status_changed` and keeps its `close_reason`); `undo_of` -> `undone`, `redo_of` -> `redone`, `link_unreversed` -> `link_reversed`'s sibling kind `link_unreversed`. A unit test loops every pair and asserts no undo/redo row is `unknown`.
- `export`: prints `group_id` per ledger row, but ONLY when the `change_log` table has the column (`PRAGMA table_info`); on a v12 file it prints `-` and does not fail. `export` never migrates.
- `db-check`: NO new floor (a floor of 13 would flag every healthy v12 file as `DRIFT`). Add one check that runs only when version >= 13 (every `undo_of`/`redo_of` marker names an existing group); on v12 print `group_id: not applicable (schema v12)`.

## §6 Error codes (new, stable, never reused, I17)

| Code | Name | Raised at |
|---|---|---|
| MAINTAIN-023 | NothingToUndo | §5.3 rule 2 (detail says whether older changes exist that carry no group id, story 123) |
| MAINTAIN-024 | NothingToRedo | §5.3 rule 3 |
| MAINTAIN-025 | UndoRefused | §5.3 rule 4 (`group_id`, `item_id` or `link_id`) |
| MAINTAIN-026 | UndoWriteFailed | §5.5 UPDATE failure |
| MAINTAIN-027 | GroupRecordInvalid | §5.3 rule 6 |

Reused with unchanged meaning: MAINTAIN-007/008/009 (boot), 010 (read), 011/012 (store).

## §7 Test targets (T1 to T4)

- **Unit, pure core:** one test per row of spec 12.2; stack rules (undo, undo, redo, new change clears redo); the refusal rule; shield cases (§5.4); unrecognised shape; pre-013 rows invisible. `undo.py` must not even mention forbidden words in a docstring (architecture grep).
- **Integration, real temp DB:** each undoable action then `undo` -> state equals the state before, ledger only grew; `redo` -> state after; rollback on injected failure (delegating-connection pattern); migration 013 on a copy of a real v12 file; **reverse -> undo -> sweep treats the link as live**; **clear -> undo -> relate confirm -> redo -> sweep keeps the item shielded**; `db-check` exit 0 after every undo kind; **`export`, `history`, `db-check` on a v12 file all succeed** (never migrate).
- **History:** loop over every existing pair x `user_undo`/`user_redo`, none `unknown`.
- **CLI (S1):** the §4 samples with exit codes; `--dry-run` writes zero rows (hash).
- **E2E (one):** capture (fake AI) -> relate (fake) -> close-item -> undo -> redo -> history.
- **Goldens:** only `topic_search`, `history`, `history_item_1` are pinned today (`tests/fixtures/query/no_flags_golden.json`). The first commit of step 01 captures raw-stdout fixtures for `current-state` and `why` BEFORE any change.
- **Not covered:** a v13 file opened by a pre-013 build (spec 12.8). Manual check: open an upgraded file with the old build and run `ember history`. Known effect: the old build does not know `link_unreversed`.

## §8 Risks the maintainer must see (AGENTS.md section 2)

1. **Database structure change.** Migration 013 adds one nullable column. 0 existing rows change (no backfill). 0 tracked database files. Rows in the maintainer's own local files: not counted (cannot be seen from here). Forward-only; the way back is the safety copy before upgrade. **Step 01 shows the then-current counts and asks A or B again.**
2. **Written-rule amendments** (L1 amendment items 5 and 6) — confirmed 2026-10-30; recorded in `engine-maintain-plan.md` §1 and §12 at step 03.
3. **Old builds:** a v13 file opened by an older Ember is unchecked (spec 12.8). Until checked, treat v13 as one-way.
4. **Cross-module write:** §5.5 B2 exception.
5. Floors do not change. A v12 file opened by any write command is migrated to 13 by the existing runner with a `.bak-v12` copy.

## §9 Steps (L3), bottom-up, each commits separately

| # | File | Phase |
|---|---|---|
| 01 | `plans/steps/undo/01-migration-and-group-stamping.md` | Migration 013 + group id on the six human actions |
| 02 | `plans/steps/undo/02-undo-core.md` | Pure undo/redo derivation |
| 03 | `plans/steps/undo/03-store-and-replay.md` | `apply_inverse_group`, reversal/shield reader changes, rule notes |
| 04 | `plans/steps/undo/04-cli-undo-redo.md` | `ember undo`, `ember redo`, docs |
| 05 | `plans/steps/undo/05-read-side-and-closeout.md` | history, db-check, export, E2E, map |

## §10 Deferred to L3
- Final wording of the undo/redo lines (step 04).
- Index on `group_id`: only if a measured read needs it (step 01).
- Whether `GroupIdPort` lives in `ember/relate/rows.py` or a new neutral module (step 01; bounded by B2).

## §11 Decisions for the maintainer at the L2 gate
- **D3 (above, §4):** `--dry-run` flag (I2 exception) or separate preview commands.

## §Z Constitution compliance

- **B1** one job: undo/redo. **B2** Capture and Maintain share only the neutral `GroupIdPort`; the one cross-module write (§5.5) is declared. **B3** rules (refusal, stack, shield) are pure logic, not in the CLI. **B5** one new pure module + one store method.
- **D1** no row edited or deleted. **D2** `reversed_at` stays a rebuildable copy of the marker rows. **D3** the group pointer is a marker row; the status-value encoding is split in one public place. **D5** additive column and a NEW marker field, no existing meaning changed. **D6** migration 013. **D7** safety copy before upgrade.
- **P1** no decorative layer. **P3** pipeline load -> derive -> apply -> report. **P4** the DB sits behind store/lookup ports.
- **I1** names by job. **I2** `--dry-run` is an acknowledged exception (§4, decision D3). **I3** ≤ 4 inputs (`UndoSnapshot` wraps). **I4** named returns (`UndoResult`), refusals raised not returned. **I5-I7** named errors, fail fast, handled at the CLI edge. **I10** additive. **I11/I21** contracts list codes. **I12** exit 0/1. **I17-I20** codes 023-027 new, ids carried, no secrets.
- **T1** core pure, group id injected. **T2** side effects in the store. **T3/T4** fakes + real temp DB. **T5/T6** observable behaviour and codes. **T9** `undo.py` imports no adapter and mentions no forbidden word.
- **S1** §4 samples. **S2** `tests/maintain/test_undo_*.py` run alone. **S3** shapes in §5. **S4** transfer = ledger rows.

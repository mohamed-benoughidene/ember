# L3 Maintain Step 4: edit-item (hardening cluster 2 — issue #19 half 1, closes #1)

Adds the human `edit_item` write to the Maintain engine: a pure validator, one store method writing `items.rationale` / `items.source` **and** its ledger row in one transaction, and the `ember edit-item` command. Rule-7 answer lands first — see Gates.

## Gates

| Gate | Artifact | Rule |
|---|---|---|
| **Gate 1 — the rule-7 ADR** | The filled `Decision:` line in `plans/engine-maintain-plan.md` **§12.0** — the maintainer signs Option A (text edits forbidden; rationale/source only) or Option B (statement allowed too). Today the line reads `Decision: PENDING (maintainer)`. | **This step must not start until the gate artifact exists.** §12.0: "The filled line is the artifact that unblocks implementation (gate 1 closes)." The plan is written now; the build waits. |

Under Option A this step ships the §12.4 table's `rationale`/`source` rows only. Under Option B the conditional bullets marked **[option B only]** activate with it (§12.8 option-B bullet, §12.9 item 5). Either way #1 gets its writer — the ruling changes only the flags and the gatekeeper's width (§12.0).

## 0. Constitution rules this step enforces

- **B1** — `validate_edit_item` lives in `ember/maintain/human_actions.py` beside its three peers (§12.6). The B6 watch (`human_actions.py` growing) is recorded in §12.8, not split.
- **B2** — reads through `MaintainLookupPort`, writes through `MaintainStorePort`; no direct SQL in the core.
- **B3 / T1** — the validator is pure: the snapshot is the whole world; the observed `old_value` is read in Phase 1, never invented (§12.4).
- **D1** — per the Gate-1 ADR: under Option A, `rationale`/`source` are the designated human-writable authorial slots; `statement` and every raw table (`sources.full_text` et al.) stay immutable. The prior value survives in `change_log.old_value` even when blanked (`--value ""` is legal, §12.3).
- **D3** — the `items` UPDATE and its one `change_log` INSERT land in **one transaction** (the `apply_status_origin` pattern, `ember/adapters/sqlite.py:805-840`; §12.4 Phase 3). For `rationale`/`source` the column is the primary authored fact and the ledger row is its history — no rebuild claim (§12.10a).
- **I3** — `validate_edit_item(snapshot, item_id, field, value)` = exactly 4 inputs, the stated ceiling (§12.6).
- **I4** — returns `list[EditChange]` (a named model, §12.6); the no-op is an **empty list**, never `None`.
- **I5 / I17** — one code per failure; `MAINTAIN-001` is **reused** (same failure, same code — never a new number, §12.7).
- **I2** — no boolean flags; `--dry-run` omits the store call, never crosses into a function.
- **I9 / D4** — `--field`/`--value` are outside data, validated at the CLI edge then trusted inside (§12.10c).
- **I12** — exit 0 success (incl. no-op), 1 on a `MAINTAIN-*` code, 2 on Click usage errors; stdout data, `error: {exc.log_line()}` to stderr.
- **I11** — the validator and store docstrings list their raised codes.
- **I21** — every code fired here has a test asserting the code (§12.7, §12.8).
- **T3 / T5 / T9** — fakes not mocks; tests assert DB state and codes; no new modules (`tests/test_architecture.py` globs already cover the grown files, §12.8 architecture bullet).
- **S1** — `ember edit-item` runs this step alone.
- **P2 / P3 / P4** — CLI → pure validator → store adapter; same §4 four-phase pipeline (§12.4 diagram).

## 1. Job

Let a human write `items.rationale` (on a `Decision`) or `items.source` (on a `Finding`) — the master-plan §5 slots issue #1 designated — with a ledger row per edit. No AI, no confirm loop: the human invoking the command IS the confirmation (§12.3, the close-item precedent). Step invariant: **step finish → every module in `ember/maintain/` imports and runs; the full `tests/maintain/` suite passes.**

## 2. Inputs / boundaries (shapes per §12.6, cites)

- `ItemState` **gains** `rationale: str | None` and `source: str | None` — Phase 1's item read grows (`SqliteMaintainContext.list_items()` SELECT + the model in `ember/maintain/rows.py`, additive, I10). Under Option B, `statement` joins the read (§12.4, §12.6). `MaintainSnapshot` shape otherwise unchanged.
- **`validate_edit_item(snapshot: MaintainSnapshot, item_id: int, field: str, value: str) -> list[EditChange]`** — pure, joins `ember/maintain/human_actions.py` (§12.6). Checks, in order:
  1. the item exists → else `MAINTAIN-001` (reused, §12.7);
  2. `field` is one of the three known names (`rationale`/`source`/`statement`) → else `MAINTAIN-013`;
  3. the field is writable on that item's type — `rationale` on `Decision`, `source` on `Finding` → else `MAINTAIN-014` (§12.4 table). Under Option A, `--field statement` is known-but-rejected → **`MAINTAIN-014`** too, not 013 (§12.7 013 row);
  4. same-value edit (value equals the observed value) → **empty list**, no raise, nothing applied — the `set-status` B3 precedent (§12.3);
  5. otherwise one `EditChange(item_id, field, old_value=<observed, NULL stays NULL>, new_value=value, trigger_cause='user_edit_item')`.
- **`EditChange(item_id: int, field: str, old_value: str | None, new_value: str, trigger_cause: str)`** — pydantic, in `ember/maintain/rows.py` next to `StatusChange` (§12.6).
- **`MaintainStorePort.apply_item_edit(change: EditChange) -> int`** — int = 1 or raise; joins `ember/maintain/apply_status.py` (§12.6). One transaction: `UPDATE items SET <field> = ? WHERE id = ?` + `INSERT INTO change_log (item_id, link_id=NULL, field_changed='rationale'|'source', old_value=<observed>, new_value, timestamp, trigger_cause='user_edit_item')`, the `insert_link_with_log` discipline — one `commit()`, `rollback()` in every `except` (§12.4 Phase 3, L2 §4 Phase 3). Raises `MAINTAIN-016` on the UPDATE, `MAINTAIN-012` on the INSERT (its name is generic — reused honestly; §12.7).
- **`run_edit_item(ports, request) -> list[EditChange]`** — joins `ember/maintain/run_maintain.py` (§12.6): `_load(ports.lookup)` (the SAME Phase-1 snapshot the sweep uses — §12.4's boundary paragraph) → `validate_edit_item` → store → return the changes. Reads `request.field` / `request.value` — **`MaintainRequest` gains `field: str | None = None`, `value: str | None = None`** (§12.6). The entry-point return type is an L2 gap (§12.6 never states it; `MaintainResult` describes the sweep's buckets and must not be stretched) — recorded as this step's L2 §12.6 amendment in §10: return the change list; the CLI prints one line per change.
- **CLI** — `ember edit-item --item <id> --field <rationale|source> --value <text> [--dry-run] [--db <path>]` (§12.3). `--item` is `type=int`; `--field` and `--value` are **plain `str`, `required=True`, NOT `click.Choice`** — 013/014 fire from the command body; a missing `--field`/`--value` is a Click usage error, exit 2 (§12.3). Joins the four maintain commands in `ember/cli.py`; same `open_maintain_database` boot (I13, unchanged — §12 preamble: no new migration).

## 3. Outputs

- `list[EditChange]` from the validator and the entry point; `1` (or raise) from the store.
- STDOUT, one line (§12.3's sample is the final wording — §12.9 item 1 resolved):
  `item 3: rationale edited`
- A no-op (same value) prints **nothing** and exits 0.
- `--dry-run` STDOUT, one line, pinned: `item 3: rationale: <old> -> <new> (dry-run)` — §12.3's final-run wording style; writes zero rows, exit 0.

## 4. Steps

1. Gate-1 ADR is filled (see Gates) — else no build.
2. `ItemState` (ember/maintain/rows.py) gains `rationale: str | None = None` and `source: str | None = None` (I10 defaults — required fields would break every existing constructor), and the Phase-1 read (`rationale`, `source`) grows with it (§12.8 unit bullet 1). `FakeMaintainLookup` needs no shape change — do not extend it with the new fields.
3. Add `EditChange`, `validate_edit_item`, `apply_item_edit`, `run_edit_item`, `MaintainRequest.field`/`.value`, the CLI command.
4. Error-code audit before numbering: verify nothing after `MAINTAIN-012` exists in any branch (`git log -p ember/maintain/errors.py` is the receipt, §12.7) — verified at plan time: `errors.py` ends at 012.
5. Apply the plan amendments listed in §10 in the same commit.

## 5. Errors (codes only, cross-ref L2 §12.7)

- `MAINTAIN-001` — `MaintainItemNotFound` — reused (§12.7).
- `MAINTAIN-013` — `EditFieldUnknown` — `--field` not one of the three known names.
- `MAINTAIN-014` — `EditTargetMismatch` — field not writable on the item's type; under Option A also `--field statement`.
- `MAINTAIN-016` — `ItemEditWriteFailed` — the `items` UPDATE failed; rolled back.
- `MAINTAIN-012` — `ChangeLogWriteFailed` — reused, the ledger INSERT (§12.6).
- Boot path unchanged: `MAINTAIN-007` / `008` / `009` / `010` (I13).

Precedence: `001` → `013` → `014` (the step-03 pattern; §12.7). Context (I19): 013/014/016 carry `item_id` + `field`.

## 6. Test targets (names owned by this step, per L2 §12.8)

Unit — `tests/maintain/test_edit_item.py` (FakeMaintainLookup, pure):
- `test_validate_edit_item_rationale_on_decision_returns_edit_change` — §12.8 unit bullet 1.
- `test_validate_edit_item_rationale_on_finding_raises_014` — bullet 2.
- `test_validate_edit_item_source_on_finding_returns_edit_change` — bullet 3.
- `test_validate_edit_item_source_on_decision_raises_014` — bullet 4.
- `test_validate_edit_item_unknown_field_raises_013` — bullet 5 (a missing `--field` is Click's exit 2, never 013).
- `test_validate_edit_item_statement_under_option_a_raises_014` — §12.7 013-row note. **[option B: this test flips — §12.8 option-B bullet, a declared churn point.]**
- `test_validate_edit_item_same_value_returns_empty_list` — bullet 6 (no-op).
- `test_validate_edit_item_old_value_is_observed` — bullet 7 (NULL stays NULL; prior text survives).

Integration — `tests/maintain/test_edit_item_integration.py` (real temp DB, `open_maintain_database`):
- `test_apply_item_edit_update_and_ledger_row_one_transaction` — §12.8 integration bullet 1.
- `test_apply_item_edit_sqlite_error_injection_raises_016_and_rolls_back` — bullet 1 + the I21 named row for 016. **Vehicle (precisely): a test-local delegating connection proxy that raises `sqlite3.Error` only when the SQL matches the `items` UPDATE under test; it delegates everything else — including `rollback()` — to the real connection. A fake per T3, not a mock: there is no in-repo write-side precedent (`BrokenConnection` is read-side all-or-nothing; real-constraint routes cannot fire for these columns). The MAINTAIN-016 assertions stay as written: assert the rollback (no column change, no ledger row) plus the code.** Real store, not a fake — the step-02 T10 trap applies.
- `test_apply_item_edit_insert_failure_raises_012_and_rolls_back` — the I21 named row for the reused 012.
- `test_item_state_read_carries_rationale_and_source` — §12.6 ItemState growth, §12.4 Phase-1 read.
- `test_sweep_never_reads_rationale_or_source` — §12.8 integration last bullet.
- **[option B only]** `test_validate_edit_item_statement_happy_path_writes_ledger_row` + `test_014_narrows_to_type_mismatch_only_under_option_b` — §12.8 option-B bullet.

CLI — `tests/maintain/test_edit_item_cli.py` (§12.8 CLI bullets):
- `test_edit_item_cli_unknown_item_exits_1_maintain_001` — bullet 1.
- `test_edit_item_cli_unknown_field_exits_1_maintain_013` — bullet 2.
- `test_edit_item_cli_rationale_on_finding_exits_1_maintain_014` — bullet 3.
- `test_edit_item_cli_success_exits_0_one_line` — bullet 6.
- `test_edit_item_cli_same_value_exits_0_zero_rows` — bullet 7 (the `--to Active` no-op precedent, §5).
- `test_edit_item_cli_dry_run_writes_zero_rows` — bullet 8.
- `test_edit_item_cli_missing_value_exits_2` + `test_edit_item_cli_non_integer_item_exits_2` — §12.3 + L1 CLI contract: Click errors tested by exit code, not error code.

E2E — `tests/maintain/test_edit_item.py` (this step's file; step-local half only):
- `test_e2e_edit_item_then_history_renders_unknown_kind` — §12.8 E2E, the step-local half: `ember edit-item` then `ember history --item <id>` asserts the row renders `kind='unknown'` **with raw values visible and nothing crashing** — Query is NOT modified in this phase; the unknown rendering IS the contract. Caveat: holds **until §12.9 item 4** (the classifier extension) lands — Engine D work, not ours. Note: §12.8's "one E2E test drives both shipped CLIs" is owned by step 05 as one combined test (`ember edit-item` → `ember remove-link` → `ember history --item <id>`, in step 05's file); this step keeps only these step-local half-assertions — see §10.

## 7. CLI check (Rule S1)

```
$ ember edit-item --item 3 --field rationale --value "SQLite chosen — 5000-item ceiling, local file" --db research.db
item 3: rationale edited          # exit 0
$ ember edit-item --item 3 --field statement --value "x" --db research.db
error: MAINTAIN-014 ...           # option A; exit 1
$ ember edit-item --item 99 --field rationale --value "x" --db research.db
error: MAINTAIN-001 ...           # exit 1
```

`--dry-run` prints the pinned one line `item 3: rationale: <old> -> <new> (dry-run)` (§12.3's final-run wording style), writes zero rows, exit 0; missing DB → exit 1 `MAINTAIN-007`; missing `--value` → exit 2 (§12.3).

## 8. Out of scope (this step)

- `remove_link` — step 05.
- The Query classifier extension (`kind` for `rationale`) — §12.9 item 4, Engine D work.
- Any `statement` write under Option A — forbidden by the ADR.
- Migration — none; this step adds no migration (§12 preamble), both writes land on existing columns (`items.rationale`/`source`, migration 004).

## 9. Next

Step 05 (`05-remove-link.md`) — gated on Gate 2, per §12.1.

## 10. Deferred settings + L2 amendment log

- (§12.9 item 1) Report wording — **resolved**: §12.3's sample lines verbatim.
- (§12.9 item 2) Several `--field`s per invocation — **v1: one** (§12.9 defaults to one; additive later).
- (§12.9 item 5) The statement widening — **conditional, Option B only**; ItemState read, §4.6 vocabulary row, and the rule-7 amendment change together (§12.2 item 2).
- Plan amendments this step applies (same commit): the **rule-7 scoping amendment to master-plan rule 7** per the ADR outcome (§12.2 item 2); **query-plan §0's #19 owner cell** → Maintain §12 (§12.5 vs §12.2 item 3); the **`rationale`/`source` writer-side rows appended to the frozen L2 §4.6 vocabulary table** (§12.4).
- **L2 §12.9 amendment recorded:** the L2 names ONE step plan (`04-edit-and-remove.md`); the coordinator split it into `04-edit-item.md` + `05-remove-link.md` (this file + step 05). Recorded here; fold into the L2 when amended.
- **L2 §12.6 amendment recorded:** `run_edit_item` / `run_remove_link` return types are unspecified; recorded as `list[EditChange]` / `list[LinkChange]` (empty list = no-op, I4; `MaintainResult` stays the sweep's shape).
- **L2 §12.8 amendment recorded (§12.8 as amended at review):** §12.8's single both-CLIs E2E is owned by step 05 as one combined test; step 04 owns only step-local assertions (mirrored in step 05 §10; fold into the L2 when amended).
- **L2 §12.9 amendment recorded:** §12.9's both-gates-before-authoring rule is superseded by the split: 04 proceeds on Gate 1 alone, 05 on Gate 2 alone (plus Gate 1 only if the ADR touches links) (mirrored in step 05 §10; fold into the L2 when amended).
- **Test-file ownership:** step 04's tests land in `tests/maintain/test_edit_item.py` / `test_edit_item_integration.py` / `test_edit_item_cli.py` (all new files); step 05's in `tests/maintain/test_remove_link.py` / `test_remove_link_integration.py` / `test_remove_link_cli.py` (all new files); the combined E2E lives in step 05's file — identical test names can never shadow one file.

## 11. Rollback

One in-place `items` column UPDATE + one append-only `change_log` INSERT, one transaction, rollback in every `except` (I7). No down-migration; no data rollback. A wrong edit is corrected by a further edit — the prior value survives in `change_log.old_value` (D3); the ledger row is never edited or deleted. Undo before the first edit on an existing DB: `cp ember.db ember.db.bak`.

## 12. Build Notes (post-implementation)

Built 2026-10-29 on `feat/hardening`. Gate 1 was CLOSED before any code: the §12.0 ADR reads "Option A — text edits forbidden (maintainer, 2026-10-28)". **Option A only; no Option-B conditional was built.**

**What landed** (one commit):

- `ember/maintain/human_actions.py` — `validate_edit_item(snapshot, item_id, field, value) -> list[EditChange]`, the 4-input ceiling (I3). Order: `MAINTAIN-001` (item missing) -> `MAINTAIN-013` (field not in `rationale`/`source`/`statement`) -> `MAINTAIN-014` (writability gate `EDITABLE = {"rationale": "Decision", "source": "Finding"}`, which catches `statement` too). Same-value -> `[]`. `old_value` is the observed Phase-1 value, NULL stays NULL.
- `ember/maintain/rows.py` — `ItemState` gains `rationale` / `source` (`str | None = None` defaults, I10), `EditChange` model added. `FakeMaintainLookup` needed no shape change, as planned.
- `ember/maintain/run_maintain.py` — `MaintainRequest` gains `field` / `value`; `run_edit_item(ports, request) -> list[EditChange]` (`[]` = no-op, per the recorded §10 L2 §12.6 amendment).
- `ember/maintain/apply_status.py` — the `MaintainStorePort` gains `apply_item_edit(change) -> int`.
- `ember/adapters/sqlite.py` — the Phase-1 `list_items` SELECT grows `rationale`, `source`. `SqliteMaintainStore.apply_item_edit` follows the `apply_status_origin` pattern: one `items` UPDATE + one `change_log` INSERT (`field_changed` = the change's field, `old_value` = observed, `trigger_cause` from the change, `link_id` NULL), one `commit()`, `rollback()` in every `except`. `MAINTAIN-016` on the UPDATE, `MAINTAIN-012` on the INSERT. A module-level `_EDIT_COLUMNS` whitelist guards the f-string column name (the validator is the primary gate).
- `ember/cli.py` — `ember edit-item --item N --field F --value V [--dry-run] [--db P]`. `--field`/`--value` are plain `required=True` `str`, not `click.Choice` — 013/014 fire from the command body. Success prints `item N: <field> edited`. Dry-run prints the pinned `item N: <field>: <old> -> <new> (dry-run)` and writes nothing. A no-op prints nothing, exit 0.
- `ember/maintain/errors.py` — `EditFieldUnknown` (`MAINTAIN-013`), `EditTargetMismatch` (`MAINTAIN-014`), `ItemEditWriteFailed` (`MAINTAIN-016`). `MAINTAIN-001` reused; `MAINTAIN-012` reused. `015` / `017` left for step 05.

**Option-B conditionals skipped** (Gate 1 landed Option A): §2's `statement` read growth, §4's `statement` writability, §6's `test_validate_edit_item_statement_happy_path_writes_ledger_row` and `test_014_narrows_to_type_mismatch_only_under_option_b` (both are step-05-conditional, never authored), §10's option-B widening. The `test_validate_edit_item_statement_under_option_a_raises_014` test exists in its Option-A form as planned.

**Deviations / decisions recorded:**

- `errors.py` is non-contiguous this step: it ends `...012, 013, 014, 016`. `015` (`RemoveLinkNotConfirmed`) and `017` (`RemoveLinkWriteFailed`) arrive with step 05 per §12.7. Error-code audit receipt: `git log -p ember/maintain/errors.py` shows nothing beyond 012 existed before this commit.
- The dry-run rendering of a NULL `old_value` was not pinned by L2 §12.3 — chose `<null>` (`item 3: rationale: <null> -> x (dry-run)`). `""` (a prior blanking) renders as an empty string between the colons.
- `tests/fakes.py::insert_item` was NOT extended (kept shared-seed-helper churn at zero): integration/CLI seeds set `rationale`/`source` with a direct `UPDATE` after `insert_item`.
- The store raises `MAINTAIN-016` (not a bare `ValueError`) from the `_EDIT_COLUMNS` guard, so an unvalidated field can never surface as a non-`MAINTAIN-*` error at the CLI edge.

**Plan amendments applied in this commit (per §10):** the rule-7 scoping line in `plans/master-plan.md` rule 7 (Option A wording); `plans/engine-query-plan.md` §0's `#19` owner cell -> Maintain §12 (`edit_item` landed, `remove_link` on Gate 2); the two writer-side `rationale`/`source` rows appended to the frozen §4.6 vocabulary table (the `link_removed` row waits for step 05). The §10 recorded L2 amendments (split into 04/05, return types, §12.8 combined-E2E ownership, gates rule) stay recorded here until an L2 amendment pass folds them in.

**Test counts:** before 646 passed / 4 deselected. After: 668 passed / 4 deselected in 3.19s — 22 named tests added, all watched red at collection (`ImportError: cannot import name 'ItemEditWriteFailed'`) then green: 9 in `tests/maintain/test_edit_item.py` (8 unit + the step-local E2E), 5 in `tests/maintain/test_edit_item_integration.py`, 8 in `tests/maintain/test_edit_item_cli.py`. Integration failure vehicle exactly as §12.8 dictates: a test-local `DelegatingConnection` proxy that raises `sqlite3.Error` only on the target SQL and delegates everything else, including `rollback()`, to the real connection — a fake per T3, both injection tests assert the full rollback (column unchanged, zero `change_log` rows) **plus** the code (`016`, `012`).

**CLI check (Rule S1, real run, real temp DB):**

```
$ ember edit-item --item 1 --field rationale --value "SQLite chosen - 5000-item ceiling, local file" --db cli-check.db
item 1: rationale edited                     exit 0
$ ember edit-item --item 1 --field bogus --value x ...
error: MAINTAIN-013 EditFieldUnknown | ... | item_id=1 field=bogus    exit 1
$ ember edit-item --item 1 --field statement --value x ...
error: MAINTAIN-014 EditTargetMismatch | ... | item_id=1 field=statement   exit 1   (Option A)
$ ember edit-item --item 1 --field rationale  (no --value)
Error: Missing option '--value'.             exit 2
$ ember edit-item --item 1 --field rationale --value "a brand new why" --dry-run ...
item 1: rationale: SQLite chosen - 5000-item ceiling, local file -> a brand new why (dry-run)   exit 0, change_log count unchanged
$ ember edit-item --item 1 --field rationale --value "SQLite chosen - ..." (the current value)
                                             exit 0, no output, change_log count unchanged (zero rows)
```

**Ledger proof (real `ember history --item 1` after the real edit):** the new row renders `kind='unknown'`, `cause='user_edit_item'`, `field_changed='rationale'`, `old_value='old why'` (the prior text survives), `new_value='SQLite chosen - 5000-item ceiling, local file'`, and `items.rationale` itself carries the new text. Nothing crashed and no value was hidden — the unknown rendering IS the contract until Engine D's classifier extension (§12.9 item 4). Combined both-CLIs E2E owned by step 05 per §10.

**Not done here:** `remove_link` and everything with it (step 05, Gate 2); the Query classifier extension; any migration (both writes land on migration 004's existing columns).

**Implementation review (ticket 08, 2026-10-29):** APPLIED — the em dash this step's diff added in the `human_actions.py` module docstring is reworded out (punctuation rule). ADJUDICATED (kept): `ItemState`/`EditChange` reuse; the per-command request-object refactor the reviewer flagged as a data clump (`MaintainRequest` grows one field pair per command) is deliberately deferred — it is a cross-cutting reshape of the maintain module outside this phase's scope, and each command reads only its own fields.

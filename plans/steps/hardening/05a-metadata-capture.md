# L3 Hardening Step 5a: Migration 012 + Capture Label Write Path (ticket 11, #5)

Implements the migration pin in §2 and L2 capture §9 ("V1.x Amendment: capture proposes the project label"). Ships the schema and the capture writer, nothing else. The relate reader is `05b-metadata-relate.md`. Together the two steps close #5.

## 0. Constitution rules this step enforces

- **D6 / D7** — one numbered migration, 012. The runner owns the transaction, the version bump and the pre-migration backup (`<db>.bak-v11`, keep newest 3). Step 01 pattern, unchanged, no runner edit.
- **D5 / I10** — new optional column, additive only. Zero renames, zero rebuilds, existing writers untouched.
- **D3** — the ledger stays the source of item history. The column needs no backfill and no ledger pairing: NULL = unlabeled is not a fact change.
- **D4 / I9** — the AI label is outside data: checked and normalized at the boundary (`item_proposal.py`), core sees only `str | None`.
- **D8 / I16** — raw answer still stored verbatim; the label rides the existing `propose_items` call (L2 capture §9, L1 rule 3 amendment line there).
- **I4 / I12 / S1** — capture CLI contract unchanged except one block line; exit codes 0/1/2 unchanged.
- **I17 / I21** — zero new error codes (§4).
- **T4 / T5** — acceptance on real temp DBs at the Phase 4 write boundary.
- **P1** — the writer exists because #5 was ruled build. Nothing else is added.

## 1. Job

Move the schema to version 12 and give capture the label write path: the AI proposes an optional 5th proposal key, the confirm loop shows and re-asks it, the accepted item insert carries it. NULL is written whenever the label is absent or blank.

## 2. The pin

- `ember/adapters/migrations/012_add_items_metadata.sql`, content pinned (paste exactly):

```sql
-- #5: optional project-area label, written by capture (L2 capture plan section 9).
-- Additive only: nullable TEXT, no default, no rebuild, no backfill. NULL means
-- unlabeled, and the 30-day proxy keeps covering those rows (L2 relate plan section 13).
ALTER TABLE items ADD COLUMN metadata TEXT;
```

- Verified free to run: SQLite permits `ADD COLUMN` for nullable TEXT with no default unconditionally (rows are not rewritten, old rows read NULL). Trigger interplay verified: `items_closed_reason_insert` fires on any INSERT but aborts only when `status='Closed' AND close_reason IS NULL` (capture inserts Active), and `items_closed_reason_update` fires only `OF status, close_reason`, never on a metadata write. No view exists on any table (grepped all 11 migration files). Every existing writer uses an explicit column list, so all keep running unchanged.
- No guard table: the migration claims and changes nothing existing (rows touched: 0), unlike 011 which changed semantics.
- Everything else per L2 capture §9: `ItemProposal.metadata: str | None = Field(default=None)`; normalization (absent/null -> None, non-string -> entry dropped with rule `metadata`, trim, blank -> None, no length cap); the prompt sentence; `format_block` gains `  metadata:` between `confidence` and `near_dup_warning`, JSON-quoted like `statement`; `ask_metadata` (prompt `new metadata? (default <label|none>)`, blank keeps default, lone `-` clears to None); `insert_item` gains the column bound to `item.metadata`.

## 3. Steps

1. Paste the 012 SQL above. No runner change (backup, version bump, retention all exist since step 01).
2. `ember/capture/item_proposal.py`: the `ItemProposal` field, boundary normalization, `_rule_for` gains the `metadata` mapping, `SYSTEM_PROMPT` gains the §9 sentence.
3. `ember/capture/item_gatekeeper.py`: `ProposalDraft` and `ValidatedItem` gain `metadata: str | None = None` (the I10 default is required, every existing constructor must stay valid); `_to_draft` and `validate_add_item` carry it (no new check).
4. `ember/capture/confirm_write.py`: the `format_block` line, `edit_item` asks `ask_metadata` after `ask_statement`, new `ask_metadata` helper (single prompt, no retry loop: every answer is valid).
5. `ember/adapters/sqlite.py`: `SqliteItemGatekeeper.insert_item` adds `metadata` to the explicit column list, bound to `item.metadata`. `log_created`, `log_rejected` and `_proposal_text` untouched (L2 §9).
6. `tests/fakes.py`: `make_item` and `insert_item` gain an optional `metadata` kwarg, default None (additive). No `proposal(...)` helper exists there: the per-file local builders (`test_capture_pipeline_integration.py:32`, `test_cli_capture.py:23`, `test_item_gatekeeper_unit.py:61`) gain the same additive kwarg. (Review fix 4.)

## 4. Errors (codes only)

**Zero new error codes.** `CAPTURE-009` AiSchemaFail for whole-answer JSON failures, unchanged. `metadata` is a per-entry drop rule, not a code. `CAPTURE-013` DbWriteFail wraps item write failures as today. `CAPTURE-014` UserAbort behavior unchanged.

## 5. Test targets

Owned (names checked against `tests/`, no collisions):

- `tests/test_migration_012.py` (new file): `test_migration_012_adds_nullable_metadata_column`, `test_migration_012_preserves_all_rows_and_values` (compare explicit columns: `SELECT *` gains a NULL key), `test_migration_012_preserves_existing_schema`, `test_migration_012_items_triggers_still_active` (011's Closed trigger still rejects after 012), `test_fresh_install_applies_all_migrations_through_012`, `test_failed_migration_leaves_intact_prior_database_012` (renamed so the 011-file original cannot shadow it, review fix 7).
- `tests/test_item_proposal_unit.py`: `test_metadata_key_is_read_when_present`, `test_metadata_absent_or_null_is_none`, `test_metadata_non_string_drops_the_entry`, `test_metadata_blank_or_whitespace_becomes_none`.
- `tests/test_confirm_write_unit.py`: `test_format_block_shows_the_metadata_line`, `test_edit_re_asks_metadata_with_the_ai_default`, `test_edit_dash_clears_metadata_to_none`.
- `tests/test_capture_pipeline_integration.py`: `test_accepted_label_lands_in_items`, `test_items_without_a_label_store_null`, `test_wrong_metadata_correctable_via_edit`.
- `tests/test_item_store_integration.py`: `test_insert_item_persists_metadata`.

Declared churn (part of this step's diff): `tests/test_migrations.py::test_items_table_has_expected_columns` gains `metadata`. Applied-version pins `== 11` become `== 12` (recount by grepping `== 11` under `tests/` before editing): `tests/test_source_storage_integration.py:66`, `tests/test_migrations.py:215`, `tests/test_migration_runner.py:83`, `tests/maintain/test_migration_010.py:43`, `tests/maintain/test_maintain_boot.py:122`, `tests/test_migration_011.py:332` (rename that test to `test_fresh_install_applies_all_migrations_through_012`, review fix 8), `tests/test_relate_db_open.py:110`. The two `required == 11` floor pins (`tests/test_relate_db_open.py:79`, `tests/maintain/test_maintain_boot.py:105`) are NOT touched here: relate's floor moves in 05b, maintain's never moves. `tests/test_db_check.py::test_db_check_healthy` asserts `version: 11` and must become `version: 12` (the migration runs in this step). Saved AI fixtures without the key keep passing (the field is optional, T7 fixtures need no edit). (Review fix 1.)

## 6. CLI check (Rule S1)

Runner route (`CliRunner`, patched proposer, the `tests/test_cli_capture.py` pattern), input `y`:

```
- id: 1
  type: "Decision"
  statement: "Move auth behind the service"
  source_quote: "move auth"
  confidence: 0.9
  metadata: "auth-network"
  near_dup_warning: null
[y]es / [n]o / [e]dit / [q]uit
accepted: 1, rejected: 0, warnings: 0, aborted: false
```

Exit 0. Edit sequence `e / blank / blank / payments / y` reprints the block with `metadata: "payments"`. A real-binary `ember capture` run with the maintainer's key (the existing deselected live check) must show the same block.

## 7. Rollback

In-DB rollback is automatic: the runner wraps 012 in one transaction. File rollback: restore `<db>.bak-v11` per the 011 pattern. Appends only: no `change_log` row is rewritten, no existing value changes; no down-migration exists, the column is forward-only. Code undo: drop the commits.

## 8. Step invariant

After this step: the module runs, migration 012 applies on a fresh DB and on a migrated v11 DB, capture writes the label with NULL for absent or blank, the declared churn is applied, and the full suite is green with real numbers recorded in Build Notes.

## 9. Out of Scope

- No relate reader, no floor bump, `_metadata_signal` untouched (05b owns all three).
- No Maintain or `edit-item` path for `metadata`. No bulk labeling. No length cap.

## 10. Build Notes

Filled 2026-10-29 (step 05a, branch `feat/hardening`).

**What landed vs section 3:** all six steps as pinned. The 012 SQL is the exact
pasted pin. `item_proposal.py` gained the `Field(default=None)` key, the trim
validator (blank to None), the `metadata` mapping in `_rule_for` (per-entry
drop, per-entry, no whole-answer failure) and the prompt sentence.
`item_gatekeeper.py` gained `metadata: str | None = None` on `ProposalDraft`
and `ValidatedItem`, carried by `_to_draft` and `validate_add_item`.
`confirm_write.py` gained the `format_block` line (between `confidence` and
`near_dup_warning`, JSON-quoted) and `ask_metadata` (single prompt, blank keeps
default, lone `-` clears to None, no retry loop). `sqlite.py` `insert_item`
gained the column bound to `item.metadata`. `tests/fakes.py` `make_item` and
`insert_item` gained the additive kwarg.

**TDD red first:** baseline 745 passed, 4 deselected. Tests written first: red
run showed 46 failed, 718 passed (all 19 new tests failing for missing
migration/field, plus the declared churn pins). After implementation: 764
passed, 4 deselected, 0 failed (745 + 19 new).

**Section 6 output evidence:** real `.venv/bin/ember` CLI entry on a real temp
DB (fresh DB, real Click command, real confirm loop on real stdin, real
migrations) with only `build_item_proposer` faked per section 6 (the runner
route). Input `y` printed the exact block:

```
- id: 1
  type: "Decision"
  statement: "Move auth behind the service"
  source_quote: "move auth"
  confidence: 0.9
  metadata: "auth-network"
  near_dup_warning: null
[y]es / [n]o / [e]dit / [q]uit
accepted: 1, rejected: 0, warnings: 0, aborted: false
```

Exit 0. Edit sequence `e / blank / blank / payments / y` reprinted the block
with `metadata: "payments"`. The lone `-` edit sequence landed the row with
metadata NULL. Two new CLI tests pin both routes.

**Migration proof:** fresh DB lands at version 12
(`test_fresh_install_applies_all_migrations_through_012` plus a real `ember
db-check` run). A hand-built v11 DB upgrades with items rows and values
preserved and metadata NULL (`test_migration_012_preserves_all_rows_and_values`)
and its prior file is intact with a `.bak-v11` backup on a failed 012.
011's Closed trigger still rejects after 012, and a metadata write does not
fire the status/close_reason update trigger
(`test_migration_012_items_triggers_still_active`).

**Confirmed state:** `ember db-check` after this step reports
`version: 12`, `floors: relate 11 ok, maintain 11 ok, query 10 ok, capture
none`, `result: OK`. Relate's boot floor stays 11 (05b moves it).

**Deviations from the pin:**

1. The section 9 prompt sentence contains a semicolon in the plan prose. This
   repo's work rule bans semicolons in code, so the sentence landed with a
   period: `An item may also carry an optional fifth key, metadata: one short
   project-area label. Omit the key when unsure.` Meaning unchanged.
2. Undeclared churn: five existing edit-loop tests gained one blank answer
   where the new metadata question is asked (three in
   `test_confirm_write_unit.py`, `test_edit_flow_writes_the_corrected_type` in
   `test_capture_pipeline_integration.py`, `test_editing_writes_the_corrected_type`
   in `test_cli_capture.py`). The edit loop is one question longer, so the
   scripted answers had to match. Intent of each test unchanged.
3. Undeclared churn: `test_migration_011.py` preservation tests now exempt
   `items` the way they already exempted `links`, because opening a v10 DB
   applies 011 and 012 in one run (`SELECT *` gains one trailing NULL key).
4. `tests/fakes.py` `insert_item` writes the metadata column only when a label
   is given, so the v10 and v11 hand-built databases (no column yet) stay
   insertable.
5. `test_item_gatekeeper_unit.py:61` `_proposal(**overrides)` needed no edit:
   `metadata` already flows through its overrides path unchanged.
6. Two new CLI tests beyond section 5's owned list
   (`test_label_block_and_summary_line`, `test_edit_sequence_relabels_metadata`)
   to pin the section 6 runner-route behavior in the suite.

Suites in the exact expected state: 764 passed, 4 deselected.

## 11. Issue closure

- Half of #5 via ticket 11: this step lands the column and the writer. 05b lands the reader. Comment with §6 evidence, as the 011 step did.
- #18 left alone: plain-text export stays with its separate plan.

# L3 Capture Step 3: Gatekeeper + User Confirm + Write (Phases 3 + 4)

Implements Phase 3 (gatekeeper validates + generates id) and Phase 4 (user confirms + write) of L2 Capture plan. Folded into one L3 plan per L2 Section 7.

## 1. Job

Take proposals from Step 2, run each through gatekeeper (validate + generate id/timestamp/Active), then prompt user to accept/reject/edit each, and write to DB on confirm.

Also exposes the human-only `validated` flag change on an Assumption (added in review, section 4.3).

## 2. Inputs

From Step 2: `[{type, statement, source_quote, confidence}]`.
From Step 1: `{source_id, raw_text, content_hash}` (still in scope for source quote verification).

## 3. Outputs

- `accepted_ids: [int]` — ids of items written to `items` table.
- `rejected_count: int` — count of rejected proposals (logged to change_log only).
- `warning_count: int` — count of near-dup warnings shown to user.
- `aborted: bool` — `true` if user issued `q` (or STDIN closed mid-prompt). Remaining proposals not written, not logged.

## 4. Steps

### 4.1 Phase 3: Gatekeeper per proposal

For each proposal:

1. Call gatekeeper port `validate_add_item` with `{type, statement, source_quote, source_id}`.
2. Gatekeeper runs 4 checks (L2 L42-45):
   - `type` ∈ {Decision, Assumption, Finding, Question}.
   - `statement` non-empty.
   - `source_quote` substring of `sources.full_text` for `source_id`.
   - Near-dup scan: text similarity vs existing items. If > threshold, attach `near_dup_warning = {matching_item_id, similarity}`. Threshold per L2 Section 8 item 3.
3. If all checks pass, gatekeeper returns: `{id, created_at, status='Active', near_dup_warning}` (id/timestamp/Active generated per L2 §3 L46).
4. If any check fails, gatekeeper returns reason. Caller drops proposal, logs reason to STDOUT (info).
5. `validated` is null in gatekeeper output. Caller (Phase 4 write) sets it on the items row only when `type='Assumption'` (spec 3.5 line 110). For other 3 types, `validated=null`.

### 4.2 Phase 4: User confirm loop

For each surviving proposal `{id, created_at, status='Active', near_dup_warning, validated}`:

1. Print YAML block to STDOUT:
   ```yaml
   - id: <proposed id>
     type: <type>
     statement: <statement>
     source_quote: <quote>
     confidence: <0.0-1.0>
     near_dup_warning: <{matching_item_id, similarity} | null>
   ```
2. If `near_dup_warning` non-null, print warning line to STDOUT before prompt.
3. Prompt user: `[y]es / [n]o / [e]dit / [q]uit`.
4. User response:
   - `y`:
     1. Write to `items` table via gatekeeper commit port: `{id, type, statement, source_id, status='Active', created_at, validated}`. Uses id/timestamp/Active gatekeeper generated in Phase 3.
     2. Write to `change_log` table via gatekeeper commit port: `{item_id=<new id>, link_id=null, field_changed='created', old_value=null, new_value=<statement>, timestamp=<now>, trigger_cause='user_confirmed'}`.
     3. Append `id` to `accepted_ids`.
   - `n`:
     1. Write to `change_log` table via gatekeeper commit port: `{item_id=null, link_id=null, field_changed='proposed', old_value=null, new_value=<proposal>, timestamp=<now>, trigger_cause='rejected'}`.
     2. NOT inserted into `items`.
     3. Increment `rejected_count`.
   - `e`:
     1. Prompt: "new type? (default <AI guess>)". Validate type ∈ {Decision, Assumption, Finding, Question} (same rule as Phase 3 check #1, L2 L42).
     2. Prompt: "new statement?". Validate non-empty.
     3. Re-run Phase 3 gatekeeper with edited values (new id, timestamp, warnings).
     4. Treat as fresh proposal in the confirm loop.
   - `q`:
     1. Stop loop. Skip remaining proposals (do not write them, do not log to change_log).
     2. Exit 2 = user abort.
5. Repeat until all proposals handled or user quits.

### 4.3 Human flag change: `set_validated` / `clear_validated` (added in review)

Not part of the 4-phase pipeline. This is the human-only operation L1 §3.7 names `set_validated`. Phase 4 writes `validated = False` on a new Assumption, so without this no code path could ever write `True`.

1. Command `ember set-validated --item <id>` writes `True`.
2. Command `ember clear-validated --item <id>` writes `False`.
3. Both call the gatekeeper check `validate_set_validated` with `{item_id}`:
   - `item_id` exists in `items`, else fail `CAPTURE-015`.
   - `items.type = 'Assumption'`, else fail `CAPTURE-016` (spec 3.5: only Assumptions carry the flag).
4. On pass, the gatekeeper commit port sets the flag and appends one `change_log` row: `{item_id, link_id=null, field_changed='validated', old_value, new_value, timestamp, trigger_cause='user_set_validated'}`.
   - `old_value` and `new_value` are the text `"true"` / `"false"`. `old_value` is null when the flag was empty.
5. Print `item <id> validated: true|false` to STDOUT. Exit 0.

## 5. Errors

- Gatekeeper fail (Phase 3): exit 1 with reason.
- DB write fail (gatekeeper commit): exit 1 with reason.
- User abort (q or STDIN closed mid-prompt): exit 2.
- Invalid user input on `[y/n/e/q]`: re-prompt, no error.
- Flag change on a missing item (4.3): exit 1, `CAPTURE-015 ItemNotFound`.
- Flag change on a non-Assumption item (4.3): exit 1, `CAPTURE-016 NotAnAssumption`.

## 6. Test Targets

Unit (mocked gatekeeper ports):
- Phase 3: 4 checks all pass -> output has generated id/timestamp/Active.
- Phase 3: bad type -> proposal dropped.
- Phase 3: bad quote -> proposal dropped.
- Phase 3: near-dup -> warning attached, not blocked.
- Phase 4: `y` -> items write + change_log write. Rejects ok.
- Phase 4: `n` -> change_log write only, items write skipped.
- Phase 4: `e` -> re-prompts, validates new type, re-runs gatekeeper.
- Phase 4: `q` -> exits loop, returns 2, asserts `aborted=true` in output.

Integration (real SQLite temp DB):
- Happy path: 3 proposals, all `y` -> 3 rows in `items`, 3 rows in `change_log` with `field_changed='created'`, each `item_id` matches one `items` row. Asserts `aborted=false` in output.
- Rejection: 3 proposals, 2 `n` + 1 `y` -> 1 row in `items`, 2 rows in `change_log` with `trigger_cause='rejected'` and `item_id=null`, 1 row with `field_changed='created'`.
- Near-dup: existing item, paste similar text, AI proposes -> warning shown, accept still works.
- Edit flow: AI proposes wrong type, user `e` -> corrected type validates, accepted, written.
- Abort: 5 proposals, user `q` after 2 -> 2 rows in `change_log` (or `items` if accepted), 3 not touched.

Flag change (unit, `validate_set_validated`):
- Missing item -> `CAPTURE-015`. Non-Assumption -> `CAPTURE-016`. Assumption -> passes and the item comes back.

Flag change (integration, real SQLite temp DB):
- Set then clear -> `items.validated` goes null -> 1 -> 0, and 2 rows land in `change_log` with `field_changed='validated'` and the old/new text pair.
- Missing item id -> `find_item` returns None.

Flag change (CLI):
- `set-validated` / `clear-validated` -> exit 0, flag flips, 1 log row, line printed.
- Missing item and non-Assumption -> exit 1 with the code in the output.

## 6.5 Moved in from Step 2

Step 2's plan left three things undone on purpose. This step owns them. Until they exist, the L3 plan is incomplete.

1. **Create the `items` and `change_log` tables.** Numbered migrations: `002_create_items.sql` and `003_create_change_log.sql`. Columns and foreign keys per `plans/master-plan.md` §3 and the L2 plan §4 step 4.2. Existing data: the DB file does not exist yet, so 0 rows in either table.
2. **Add the SQL reader behind `ItemContextPort`.** Reads the newest 50 items for Phase 2 context mode B. The port is defined in Step 2 (`ember/capture/item_proposal.py`); only the SQLite adapter is new.
3. **Print Phase 2's drop reasons and the "0 valid proposals" line.** Step 2 carries the dropped proposals in its result; this step is where they are printed. Core must stay pure, so printing lives in the CLI edge.

## 7. Out of Scope (this step)

- Source storage (Step 1, Phase 1).
- AI port call (Step 2, Phase 2).
- Gatekeeper script bodies (L3 owns these; this step just calls the port).

## 8. Next

All 3 L3 Capture steps written. After approval, implementation starts: Step 1 (source storage + gatekeeper source script), Step 2 (AI port + adapter), Step 3 (gatekeeper validate + commit + UI).

## 9. Deferred Settings (from L2 Section 8)

- `trigger_cause` vocabulary for confirm path (item 4) — L3 picks exact string. Picked here: `user_confirmed` for accept path (y). `rejected` for reject path (n) is inherited from L2 §3 L58, restated for clarity.
- Phase 3 fold decision (item 6) — folded into this step per L2 Section 7.
- `trigger_cause` word for the human flag change (4.3, new — not from L2) — picked here: `user_set_validated` for both set and clear; `old_value` / `new_value` carry the text `"true"` / `"false"`.

## 10. L3 Extensions (beyond L2)

- `q` quit branch added to Phase 4 prompt (L2 §3 L52 has only y/n/e). `q` = explicit abort = exit 2, with `aborted=true` flag in output. STDIN close mid-prompt also still triggers exit 2 (L2 §3 L64 unchanged).

## 11. Build Notes (Phases 3 + 4 implemented)

Built and tested: migrations 002/003, the 4 Phase 3 checks, the Phase 4
`y/n/e/q` loop, the SQLite gatekeeper (items + change_log writes), the
`ItemContextPort` SQL reader, and the `capture` CLI edge that wires all 4
phases and prints the Phase 2 drop reasons.

Section 6.5 items: all 3 done. `items` + `change_log` exist (002, 003), the
`ItemContextPort` reader is `SqliteItemContext`, and the drop-reason lines print
from the `capture` command.

Picked settings (from L2 section 8):
- Near-duplicate threshold: `0.85`, on `difflib.SequenceMatcher.ratio` over the
  item statement. Warning only, never a block.
- Confirm-path `trigger_cause`: `user_confirmed` (accept). `rejected` (reject)
  is unchanged from L2 section 3.
- Phase 3 folded into this step (L2 section 8 item 6).

Extra decisions this step had to make:
- `validated` on a new Assumption row is `False` (unvalidated at creation); the
  other 3 types get `NULL`. Spec 3.5.
- A rejection `change_log` row has `item_id` and `link_id` both `NULL`; the
  proposal goes in `new_value` as a small JSON object.
- `ItemProposerPort.propose` now returns `ProposalBatch` instead of a bare list,
  so the Phase 2 drops survive to the CLI edge (section 6.5.3).
- The AI adapter (`ember/adapters/llm.py`) and the `capture` command were built
  here, although section 7 lists the Phase 2 AI call as out of scope: section
  6.5.3 needs a CLI edge that runs Phase 2, and that needs a provider adapter.
  Adds the `openai` dependency (L1 section 0).

### 11.1 Constitution alignment pass (after review)

- `ItemProposerPort.propose` now returns `ProposalResponse` (raw answer +
  batch), and the CLI stores the raw answer through `SqliteAiResponseStore` into
  the new `ai_responses` table (migration 005). Rules D8 / I16. Keyed by
  `source_id` because no item exists yet at Phase 2 (L1 section 3 now agrees; it
  previously said `item_id`).
- `items` gains `rationale` and `source` (migration 004), per L1 section 5.
  Capture writes neither (the AI returns no rationale or evidence text).
- Rule I15: the OpenAI client now gets `timeout=60s` and `max_retries=0`, so the
  SDK's own retries do not multiply the plan's "1 retry, 0s backoff".
- Rule B4: the CLI reads `sources.full_text` by id, so `SourceTextPort` /
  `load_source_text` / `full_text_for` are no longer dead code.
- Rule I4: `ExistingItem` replaces the `(id, statement)` tuples.
- Rule I10 / T6: `to_draft`, `similarity`, `find_near_dup` are private and are
  covered through `validate_add_item`.
- Rules I11 / I21: public functions name the error codes they raise, and the CLI
  error tests assert the stable code.
- Rule T9: `.github/workflows/test.yml` runs pytest (architecture test included)
  on push and pull requests.

### 11.2 Follow-up resolutions

- **`set_validated` (item 1).** The Assumption flag can now be set and cleared,
  so the `validated` column written in Phase 4 is reachable. Two commands:
  `ember set-validated --item <id>` and `ember clear-validated --item <id>`.
  The check `validate_set_validated` (the L1 section 3 gatekeeper name) refuses
  a missing item (CAPTURE-015) and any item that is not an Assumption
  (CAPTURE-016). Each change writes one `change_log` row with
  `field_changed='validated'`, `old_value` and `new_value` as "true"/"false",
  and `trigger_cause='user_set_validated'`.
- **Raw AI answer on a parse failure (item 4).** Left as is, on purpose. L2
  section 5 and step 2 section 5 both say "AI response unparseable: treat as
  call fail, retry", so a broken answer is consumed by the retry and not stored.
  D8's "save raw model response verbatim" is read as covering the answer we use.
  L1 section 3 has been corrected: it cited "Spec 3.7 I16, D8", but the V1 spec
  holds no such rule, and it named `item_id` as the key, which cannot exist when
  the AI is called. It now cites Constitution D8 / I16 and keys by `source_id`.
- **Printed summary (item 5).** `capture` now prints
  `accepted: N, rejected: N, warnings: N, aborted: true|false`, which is this
  step's section 3 output list.
- **Deferred to later engines.** Writing `items.rationale` / `items.source`
  (waits on the step that stores rationale and evidence text), and the
  `change_log.link_id` foreign key (waits on the `links` table, Engine B).
  Recorded as GitHub issues labelled `deferred`.


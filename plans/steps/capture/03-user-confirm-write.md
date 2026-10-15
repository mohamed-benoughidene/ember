# L3 Capture Step 3: Gatekeeper + User Confirm + Write (Phases 3 + 4)

Implements Phase 3 (gatekeeper validates + generates id) and Phase 4 (user confirms + write) of L2 Capture plan. Folded into one L3 plan per L2 Section 7.

## 1. Job

Take proposals from Step 2, run each through gatekeeper (validate + generate id/timestamp/Active), then prompt user to accept/reject/edit each, and write to DB on confirm.

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

## 5. Errors

- Gatekeeper fail (Phase 3): exit 1 with reason.
- DB write fail (gatekeeper commit): exit 1 with reason.
- User abort (q or STDIN closed mid-prompt): exit 2.
- Invalid user input on `[y/n/e/q]`: re-prompt, no error.

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

## 7. Out of Scope (this step)

- Source storage (Step 1, Phase 1).
- AI port call (Step 2, Phase 2).
- Gatekeeper script bodies (L3 owns these; this step just calls the port).

## 8. Next

All 3 L3 Capture steps written. After approval, implementation starts: Step 1 (source storage + gatekeeper source script), Step 2 (AI port + adapter), Step 3 (gatekeeper validate + commit + UI).

## 9. Deferred Settings (from L2 Section 8)

- `trigger_cause` vocabulary for confirm path (item 4) — L3 picks exact string. Picked here: `user_confirmed` for accept path (y). `rejected` for reject path (n) is inherited from L2 §3 L58, restated for clarity.
- Phase 3 fold decision (item 6) — folded into this step per L2 Section 7.

## 10. L3 Extensions (beyond L2)

- `q` quit branch added to Phase 4 prompt (L2 §3 L52 has only y/n/e). `q` = explicit abort = exit 2, with `aborted=true` flag in output. STDIN close mid-prompt also still triggers exit 2 (L2 §3 L64 unchanged).

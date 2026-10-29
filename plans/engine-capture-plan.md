# L2 Capture Engine Master Plan

Terse caveman style. Source: L1 (`plans/master-plan.md`) + V1 spec 3.7 line 124. No invention.

**Stack:** see L1 §0. Capture-specific deviation: none. Capture does not import embedders (Engine B only).

## 1. Engine Job

Turn raw human input (pasted text OR saved file) into typed item proposals. User confirms each. Confirmed items go to DB. Rejected items logged to change_log only (no item row).

## 2. CLI Interface (Rule S1)

Two entry points. Both run the same 4-phase pipeline. Difference: source of raw text.

| Command | Input source | End signal |
|---|---|---|
| `ember capture` | STDIN (paste) | `Ctrl-D` |
| `ember capture --file <path>` | File at path | EOF (auto) |

Inspectable output: each item proposal printed as YAML block to STDOUT. Errors to STDERR. Exit code 0 on success (all proposals handled by user), 1 on phase 1/2/3 error, 2 on user abort mid-prompt.

## 3. Pipeline (4 Phases)

### Phase 1: Receive Raw Input
- Input: STDIN text OR file contents.
- Action: read full text into memory. Compute `content_hash` (SHA-256) of raw bytes. Check if hash already exists in `sources` table.
- Branch A (new source): insert row into `sources` table. Get `source_id`.
- Branch B (existing source): reuse existing `source_id`. Log "source already stored" to STDERR.
- Output: `{source_id, raw_text, content_hash}`.
- Error: file path not found (exit 1), STDIN read fail (exit 1).

### Phase 2: AI Proposes Typed Items
- Input: `{raw_text, source_id}` + last 50 existing items (B mode default, A mode = no context).
- Context mode flag: `EMBER_CAPTURE_CONTEXT_MODE` env var. Default = `B`. Set to `A` to disable context.
- Action: send raw text + context to AI via an AI port (Capture-specific name fixed in L3; port pattern fixed here).
- AI returns: list of proposals, each = `{type, statement, source_quote}`. Type is one of: `Decision`, `Assumption`, `Finding`, `Question`. Source quote must be exact substring of `raw_text`.
- Output: list of proposals. Each proposal has confidence score (AI self-rate 0-1).
- Error: AI call fail (timeout, parse fail, schema fail) -> exit 1 with reason (retry policy decided in L3).

### Phase 3: Gatekeeper Validates + Generates ID
- Input: list of proposals from Phase 2.
- Action: run each proposal through `validate_add_item` gatekeeper (gatekeeper script = L1 boundary rule, L1 line 68).
- Gatekeeper checks (per L1 + spec 3.7 line 124):
  1. Type in allowed set (4 types).
  2. `statement` non-empty.
  3. `source_quote` exists as substring in `sources.full_text` for given `source_id`.
  4. Near-duplicate scan: text similarity vs existing items. If similarity > threshold, attach `near_dup_warning` flag with matching item ID. Threshold decided in L3. Warning only, does NOT block.
- Gatekeeper generates for each valid proposal (per spec 3.7 line 124): `id`, `created_at` timestamp, `status='Active'`.
- Output: validated proposals (now with generated id, timestamp, Active status) + warnings. Invalid proposals dropped with reason logged to STDERR.
- Error: gatekeeper script fail (exit 1).

### Phase 4: User Confirms + Write
- Input: validated proposals + warnings.
- Action: for each proposal, print YAML block. Prompt user: `[y]es / [n]o / [e]dit`. Loop until all proposals handled.
- Per-item write (L1 rule: write after each confirm, not batch):
  - User says `y` (yes):
    1. Insert into `items` table using the id, timestamp, Active status that gatekeeper already generated (Phase 3 output).
    2. Insert `change_log` row: `item_id=<new id>`, `link_id=null`, `field_changed='created'`, `new_value=<statement>`, `trigger_cause=<value decided in L3>`.
  - User says `n` (no, reject):
    1. Insert `change_log` row: `item_id=null` (no item exists yet), `link_id=null`, `field_changed='proposed'`, `new_value=<proposal>`, `trigger_cause='rejected'`. NOT inserted into `items`.
  - User says `e` (edit):
    1. Prompt for new type (default = AI guess). Validate type ∈ {Decision, Assumption, Finding, Question} (same rule as Phase 3 check #1, L42).
    2. Prompt for new statement. Validate non-empty.
    3. Same as `y` flow with edited values.
- Output: list of accepted item IDs. Rejected count. Warning count.
- Error: STDIN closed mid-prompt (exit 2 = user abort).

## 4. Data Shapes (Phase Boundaries)

```
Phase 1 -> Phase 2:
  { source_id: int, raw_text: str, content_hash: str }

Phase 2 -> Phase 3:
  [{ type: enum, statement: str, source_quote: str, confidence: float }]

Phase 3 -> Phase 4:
  [{ type: enum, statement: str, source_quote: str, confidence: float,
     near_dup_warning: { matching_item_id: int, similarity: float } | null }]

Phase 4 -> DB writes:
  items: (id, type, statement, source_id, status='Active', created_at,
          validated=null)  # validated only for Assumption rows (spec 3.5 line 110); null for other 3 types
  change_log: (item_id, link_id=null, field_changed, old_value=null,
               new_value, timestamp, trigger_cause)  # item_id nullable for rejection rows
```

## 5. Test Targets (Rule T1-T4, T6-T7)

- Unit tests on pure core logic:
  - Phase 1 hash dedup logic (mock sources table).
  - Phase 3 gatekeeper checks (mock proposals).
  - Phase 4 confirm flow logic (mock STDIN).
- Integration tests on real SQLite temp DB:
  - Full happy path: paste -> 3 items proposed -> user accepts all -> 3 rows in `items`, 3 rows in `change_log`.
  - Rejection path: paste -> 3 items -> reject 2, accept 1 -> 1 row in `items`, 2 rows in `change_log` with cause='rejected'.
  - Near-dup warning: paste near-duplicate of existing item -> warning shown, accept still works.
  - Source dedup: paste same text twice -> second run reuses first source.
- Architecture test (Rule T9, run in CI):
  - Engine core never imports adapter (no direct SQLite, no direct AI SDK).
  - All DB writes go through gatekeeper port. DB reads (e.g. Phase 1 source dedup by hash) are normal app reads, not gatekeeper-bound.
  - All AI calls go through `*Port` interface.
- AI testing (Rule T7):
  - Use saved fixtures (real past AI responses) as test inputs.
  - Assert output schema + types. Never assert exact prose.
  - Test parser, validation, retry-on-fail logic.
- CLI check (Rule S1):
  - `ember capture` on sample input produces inspectable YAML output.
  - `ember capture --file test.txt` produces same.
  - Exit codes 0/1/2 verified.

## 6. Out of Scope (Capture Only)

- Multi-user concurrent writes (V1 is single-user).
- Streaming very large files (V1 rejects with error, L3 sets exact threshold).
- AI auto-accept (no user confirmation) (V1 always requires confirm).
- Bulk import of past items (separate workflow, L2+).
- AI proposing link types (Engine B job, not Capture).

## 7. Next Step

Human approves L2 Capture. Then 3 L3 step plans (one per pipeline phase that needs coding: Phase 1 source storage, Phase 2 AI port + call, Phase 4 user confirm + write). Phase 3 = thin wrapper around gatekeeper, can be folded into Phase 4 L3 if small. L3 step plans in `plans/steps/capture/`.

## 8. Deferred to L3 (Reminder)

Settings that L2 leaves for L3 to decide. Do NOT forget these when writing L3 step plans.

1. **AI port name for Capture** (Phase 2) — generic "AI port" used in L2, L3 picks the concrete name (Capture-specific, distinct from any other engine's port).
2. **AI retry policy** (Phase 2) — count and backoff when AI call fails. L2 just says "retry policy decided in L3."
3. **Near-duplicate similarity threshold** (Phase 3) — exact number L3 picks. L2 says "threshold decided in L3."
4. **`trigger_cause` vocabulary for confirm path** (Phase 4) — exact string for accepted items. L2 just says "value decided in L3."
5. **Large-file rejection threshold** (§6) — file size limit. L2 just says "L3 sets exact threshold."
6. **Phase 3 fold decision** (§7) — whether Phase 3 is its own L3 step plan or folded into Phase 4. L3 author decides.

## 9. V1.x Amendment: capture proposes the project label (ticket 11, #5 build)

Added 2026-10-29, implementation pending. Source: `plans/hardening-decisions.md` #5 ("Decision: build", maintainer, 2026-10-29: writer = capture AI proposes, human corrects inline in the [e]dit path) and `.scratch/hardening/issues/11-metadata-column.md`. Implementer: `plans/steps/hardening/05a-metadata-capture.md` (schema) and `plans/steps/hardening/05b-metadata-relate.md` (reader). Relate side: `plans/engine-relate-plan.md` §13.

**Proposal schema.** `ItemProposal` gains `metadata: str | None = Field(default=None)`. The 4-key check becomes 4 required + 1 optional, pinned exactly:
- absent key or JSON `null` -> None. No label proposed.
- present must be a string. Any other type fails `model_validate`, `_rule_for` maps field `metadata` to drop rule `metadata`, the whole entry is dropped and logged like today's type/statement/confidence drops. Per-entry drop, never a whole-answer failure.
- trimmed at the boundary. Blank (`""` or whitespace only) becomes None.
- no length cap (pinned: none). `statement` already has `min_length=1` and no max (D4 checked at the boundary only).
- a 6th unknown key keeps today's behavior, which is verified pydantic 2.14 default `extra='ignore'`: silently ignored. The old "exactly four keys" reading was never a reject in code; this amendment invents no new reject.

**Prompt and L1 rule 3.** `SYSTEM_PROMPT`'s "Each item has four keys" becomes "Each item has these keys", and gains one sentence: `An item may also carry an optional fifth key, metadata: one short project-area label; omit the key when unsure.` L1 rule 3 amendment recorded here: the `add_item` proposal gains the optional `metadata` field; the AI-callable list itself (`add_item`, `add_link`) is unchanged and the call count does not change, the label rides the existing `propose_items` call. Raw answer still stored verbatim (D8).

**Confirm loop.** `ValidatedItem` and `ProposalDraft` gain `metadata: str | None`. `format_block` gains a `  metadata:` line between `confidence` and `near_dup_warning`, JSON-quoted like `statement` (`metadata: "auth-network"` or `metadata: null`). `edit_item` re-asks it after `ask_statement` via a new `ask_metadata(confirm, default=item.metadata)` helper, the `ask_type`/`ask_statement` pattern: prompt `new metadata? (default <label|none>)`, blank input keeps the default, a lone `-` clears to None, no retry loop (every answer is valid, nothing to check). The AI-proposed label is shown in the block before the prompt, so a wrong label is correctable before confirm. Metadata never produces `RejectedProposal`.

**Write path.** `SqliteItemGatekeeper.insert_item` adds `metadata` to its explicit column list, bound to `item.metadata`; NULL when absent or blank (already normalized to None in Phase 2), no forcing. `log_created` unchanged: exactly one `created` ledger row. Transaction pattern unchanged (verified reality: `insert_item` commits, then `log_created` commits; the ticket's "one transaction" line binds as "no new transaction machinery"). `_proposal_text` (the `proposed` ledger row on rejection) unchanged: the raw AI answer in `ai_responses` already carries any label verbatim (D8).

**Zero new error codes.** `CAPTURE-009` for whole-answer failures unchanged; `metadata` is a drop rule, not a code; `CAPTURE-013` wraps write failures as today; `CAPTURE-014` abort behavior unchanged.

- **Normalization asymmetry caution (round-2 review, ruled):** capture's write path normalizes with `strip()` only, relate's read path compares with `strip().casefold()`. The asymmetry is load-bearing and intentional: the write stores the human's casing, the read compares case-insensitively (D4). Any future second writer of `items.metadata` must keep storing the raw trimmed string, never a pre-casefolded one.

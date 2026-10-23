# L3 Relate Step 3: AI Propose + Phase 3.5 + Confirm Write (Phases 3 + 4)

Implements Phase 3 (AI proposes link types via `LinkProposerPort`), Phase 3.5 (raw AI response save via `AiResponseStorePort`), and Phase 4 (gatekeeper validates + user confirms + atomic write via `LinkStorePort`) of L2 Relate plan. Folded into one L3 step per L2 §9 #1.

## 0. Constitution rules this step enforces

- **B1** — three modules, three purposes: `link_proposal.py` (Phase 3), `link_gatekeeper.py` (pure gatekeeper), `confirm_write.py` (user loop).
- **B2 / B3** — engine core uses the 5 ports; no direct adapter import.
- **B4** — `LinkProposerPort` hides the AI provider; `LinkStorePort` hides the SQL write.
- **B5 / B6** — gatekeeper is a single deep function `validate_add_link`; orchestrator `run_relate` is the only entry point; gatekeeper never sees the store.
- **D1** — `links`, `change_log`, `ai_responses` are append-only.
- **D4** — adapter validates AI response with Pydantic; gatekeeper re-validates at Phase 4 edge.
- **D8 / I16** — raw AI response is stored verbatim through `AiResponseStorePort` in Phase 3.5.
- **I1 / I3** — every public function in `link_proposal.py`, `link_gatekeeper.py`, `confirm_write.py` has strict type hints and names its error codes.
- **I4** — returns are named objects (`ConfirmResult`, `ValidatedLink`, `RejectedLink`, `LinkProposalResponse`), never tuples.
- **I5 / I7 / I8** — gatekeeper returns `RejectedLink` (designed-away expected error) vs. bugs crash; fail-fast at CLI start.
- **I6** — every RELATE-NNN error subclasses `EmberError` (L1 §0 / L2 §6).
- **I9** — adapter validates the AI response; gatekeeper re-validates at Phase 4 edge.
- **I10** — public surface only; `RejectedLink` is the only return shape.
- **I11 / I12 / I13 / I21** — public functions name the RELATE-NNN codes they raise (§4, §5); CLI exits 0/1/2 per L2 §5.1; env loaded once at startup, fail fast.
- **I15** — OpenAI SDK gets `timeout=60s`, `max_retries=0`; engine-core retry = 1 retry on transport failure, 0s backoff (parse failures do NOT retry).
- **I17 / I19** — stable RELATE-NNN codes with stable names; errors carry `target_item_id`.
- **P3 / P4** — Phases 3 + 4 of the L2 §4 pipeline; all I/O via ports.
- **S1 / S3 / S4** — CLI check in §7; shapes in §2/§3; passing via the orchestrator's port list.
- **T1 (gatekeeper only) / T2 / T9** — `link_gatekeeper.py` is pure (no I/O); `link_proposal.py` and `confirm_write.py` are engine-core's impure exceptions (`confirm_write.py` reads STDIN + writes STDOUT for the y/n/s/q prompt loop; `link_proposal.py` calls `ai_response_store.save`); side effects are pushed to the `LinkStorePort` / `AiResponseStorePort` adapters; `link_proposal.py`, `link_gatekeeper.py`, `confirm_write.py` import nothing from `ember.adapters.*`, `openai`, `sentence_transformers`, `sqlite3`, `numpy`, `anthropic` (canonical L2 §7.3 forbidden set).

## 1. Job

Take `Pool.ranked` from Step 2, send the candidates to the AI, save the raw response, validate each `LinkProposal` through the 9-rule gatekeeper, prompt the user to accept/reject/skip/abort, and on accept or reject write the link + change_log row atomically.

## 2. Inputs

From Step 2: `Pool.ranked` (`list[RankedCandidate]`).
From Step 1: `NewItem`.
From ports (L2 §4.5):
- `LinkProposerPort.propose_links(new_item, candidates) -> LinkProposalResponse`
- `AiResponseStorePort.save(item_id, raw_response) -> None`
- `LinkLookupPort.item_exists / item_status / item_type / item_statement / supersedes_ancestors / find_existing` (Step 1's protocol amendment to `ember/relate/link_lookup.py` already added these signatures; the `SqliteLinkContext` adapter implements `item_status` and `supersedes_ancestors` in Step 3's adapter work, and `neighbors_of` for Step 2)
- `LinkStorePort.insert_link_with_log(link_row, change_log_row) -> int`
- `LinkLookupPort` is passed as a single object; the orchestrator holds it.

## 3. Outputs

- `ConfirmResult(accepted: list[int], rejected: int, skipped: int, aborted: bool)` — Phase 4 result.
- A side-effect: 1 row in `ai_responses` (per Phase 3.5, keyed by `item_id = new_item.id`).
- A side-effect: K + M rows in `links` (K = accepted, M = rejected) and K + M rows in `change_log` (one per link row), all in atomic transactions.

YAML output per accepted link (L2 §5.1, mirrors Capture's confirm path; **a new `format_link_block(link: ValidatedLink) -> str` helper in `ember/relate/confirm_write.py`** follows the same `json.dumps(ensure_ascii=False)` convention as Capture's `format_block` in `ember/capture/confirm_write.py:95-106`, but is independent code (no import, no shared helper — Relate has no `_warning_text` analog because its field set has no `NearDupWarning`-like nested structure). The two helpers are parallel: their field sets are disjoint — Capture emits `id/type/statement/source_quote/confidence/near_dup_warning`; Relate emits `link_id/source_item_id/target_item_id/link_type/status/rationale`):
```yaml
- link_id: <int>
  source_item_id: <int>
  target_item_id: <int>
  link_type: <supports|contradicts|depends_on|supersedes|answers>
  status: <Confirmed>
  rationale: <str | null>
```

Plus the summary line `accepted: N, rejected: N, skipped: N, aborted: true|false`.

## 4. Steps

### 4.1 Phase 3: AI propose

1. Build the AI request: `ranked` -> a list of `{id, statement, type}` (no vector sent; the AI gets the human-readable statement only).
2. Build the system prompt. The prompt names the 5 link_types, names the 4 type compatibility rules from `compat.py`, and names the 2 directionality rules (e.g. `supports` from `Assumption` is forbidden; use `depends_on`). Few-shot examples: 0 (zero-shot; the model is told to return strict JSON). Temperature: 0.0.
3. Call `link_proposer.propose_links(new_item, candidates)` via the port. The adapter lives in `ember/adapters/llm.py` (same file as Capture's `OpenAiItemProposer`; L2 §5.4 line 316). **Retry policy: 1 retry on transport failure only** (network, auth, rate limit, timeout — lumped per Capture convention), 0s backoff. **Parse failures do NOT retry**; they raise `RELATE-033 AiResponseSchemaInvalid` on the first failure (matches Capture pattern). If the retry is also exhausted, raise `RELATE-032 AiCallFailed`.
4. The adapter returns `LinkProposalResponse(raw_response, proposals)` where `proposals: list[LinkProposal(target_item_id, link_type, rationale | None)]`. The adapter parses the model's JSON and instantiates the Pydantic models. After parsing, the adapter validates each proposal: `target_item_id` is in the candidates list (else the engine core raises `RELATE-024 TargetNotInCandidates`); the proposal's implicit source matches `new_item.id` (else `RELATE-025 ProposalSourceMismatch`).

### 4.2 Phase 3.5: save raw AI response (D8 / I16)

5. After the port returns and before returning to Phase 4, call `ai_response_store.save(item_id=new_item.id, raw_response=raw_response)`. Engine core catches `ValueError` (both/neither of `source_id`/`item_id` set) and re-raises as `RELATE-030 SchemaValidationFailed`. Any other exception (disk full, FK violation) is caught and re-raised as `RELATE-036 AiResponseWriteFailed`. The `ai_response_store.save` adapter is widened per L2 §3.4 / §5.4: `source_id: int` becomes `source_id: int | None`, an `item_id: int | None` parameter is added, and the INSERT body SQL widens from `(source_id, response_text, timestamp)` to `(source_id, item_id, response_text, timestamp)`. The ValueError guard is also added by the adapter widening. (Step 1 already landed this widening at `ember/adapters/sqlite.py:545-573`; the precondition is satisfied.) Engine core never imports the adapter directly.

### 4.3 Phase 4: gatekeeper + confirm loop

6. **Gatekeeper per proposal** (pure, no I/O; `validate_add_link(draft, lookup)`). The 9 rules match L2 §4 Phase 4 lines 234-243 verbatim, in order, with the L2 codes:

   | # | Rule | Code |
   |---|---|---|
   | 1 | `source_item_id` exists in `items` (via `link_lookup.item_exists(source_id)`) | `RELATE-026 SourceItemNotFound` |
   | 2 | `target_item_id` exists in `items` (via `link_lookup.item_exists(target_id)`) | `RELATE-027 TargetItemNotFound` |
   | 3 | `source_item_id != target_item_id` | `RELATE-010 SelfLink` |
   | 4 | `link_type` ∈ closed set of 5 | `RELATE-005 LinkTypeNotInClosedSet` |
   | 5 | `(source_type, target_type)` is in the compat table for this `link_type` (V1 spec 3.3) | `RELATE-006 SourceTargetTypeIncompatible` |
   | 6 | If `link_type == 'supersedes'`, target's status ≠ `Closed` (via `link_lookup.item_status(target_id)`) | `RELATE-007 SupersedesTargetClosed` |
   | 7 | Premise rule: source.type != 'Assumption' OR link_type != 'supports' (Decision→supports is blocked by rule 5 already) | `RELATE-008 PremiseRuleViolated` |
   | 8 | **Supersedes cycle** (symmetric): source in target's `supersedes_ancestors` OR target in source's `supersedes_ancestors` (BFS via `link_lookup.supersedes_ancestors(id)`) | `RELATE-028 SupersedesCycle` |
   | 9 | No existing link (any status) of the same `(source, target, link_type)` (via `link_lookup.find_existing(source, target, link_type)`) | `RELATE-009 DuplicateLink` |

   On pass: return `ValidatedLink(link_row, change_log_row)` — gatekeeper fills the link `status='Confirmed'`, `created_at=now`, and the change_log row per §10 (link_confirmed template). On fail: return `RejectedLink(code)`. (`reason` is dropped per M10; the CLI maps code→prose at print time.)

7. **User confirm loop** (per surviving proposal; gatekeeper-rejected proposals are not shown to the user and counted as `rejected`):
   - Print the YAML block to STDOUT using `format_link_block(link)` (defined in `ember/relate/confirm_write.py` per §3; parallel to Capture's `format_block`, not imported from it).
   - Prompt: `[y]es / [n]o / [s]kip / [q]uit` (L2 §4 Phase 4 line 207 verbatim). `s` = skip this one (count as `skipped`, no DB write). `q` = abort the run (set `aborted=true`, raise `RELATE-031 UserAbort` for exit-2 plumbing).
   - `y`: call `link_store.insert_link_with_log(link_row, change_log_row)`. On success, append `link_id` to `accepted`. If the link INSERT fails, raise `RELATE-029 LinkWriteFailed`. If the change_log INSERT fails after a successful link INSERT, the atomic transaction rolls back the link row; raise `RELATE-011 ChangeLogWriteFailed`. (Per L2 §4 Phase 4 line 212: a new pattern for Relate, distinct from Capture's per-method autocommit.)
   - `n`: call `link_store.insert_link_with_log(link_row, change_log_row)` with the link row's `status='Rejected'` and the change_log row per §10 (link_rejected template). On success, increment `rejected`. This is the **negative-memory persistence** path (L2 §1 line 9 + L2 §4 Phase 4 lines 222-231).
   - `s`: increment `skipped`. No DB write.
   - `q`: raise `RELATE-031 UserAbort`. The CLI maps it to exit 2 and prints the summary with `aborted=true`. Pending proposals are neither confirmed nor rejected nor skipped.
8. Build `ConfirmResult` and return to the orchestrator.

### 4.4 CLI edge wiring

9. The CLI builds:
   - `conn = open_database(DEFAULT_DB_PATH)` (from `ember/adapters/sqlite.py:24-30`, which sets `PRAGMA foreign_keys=ON` at line 28 and runs migrations via `_apply_migrations`)
   - `lookup = SqliteLinkContext(conn)`
   - `store = SqliteLinkStore(conn)`
   - `link_proposer = build_link_proposer(env)`
   - `ai_response_store = build_ai_response_store(conn)`
   - `--db` default imports `DEFAULT_DB_PATH` from `ember.cli` (no string-literal drift).
   - `PRAGMA foreign_keys=ON` is set **once at connection open** by `open_database` at `ember/adapters/sqlite.py:28`. No `try/finally` per-init; the pragma is per-connection and lives for the connection's lifetime.
10. The CLI passes two named objects to `run_relate(ports: RelatePorts, request: RelateRequest) -> ConfirmResult` (engine-core entry point; not a port itself). This keeps the public function at 2 inputs (Constitution I3: maximum 4). Shapes:
   - `RelatePorts(link_lookup, link_store, link_proposer, ai_response_store)` — the four ports Phase 3+4 use.
   - `RelateRequest(new_item, ranked, env)` — the data for this run; `ranked` is `Pool.ranked` from Step 2.
   `LinkRun` (L2 §5.5) stays **dropped**; the new bundle is an input object required by I3, not the read/write pair M8 removed.

## 5. Errors (codes only, per L2 §6)

Codes raised in this step, in L2 §6 order:

- `RELATE-005` — `link_type` not in the 5 closed set (gatekeeper rule 4).
- `RELATE-006` — `(source_type, target_type, link_type)` violates V1 spec 3.3 compat table (gatekeeper rule 5).
- `RELATE-007` — `supersedes` target's status is `Closed` (gatekeeper rule 6).
- `RELATE-008` — premise rule violated (Assumption + supports) (gatekeeper rule 7).
- `RELATE-009` — existing link of same `(source, target, link_type)` (gatekeeper rule 9).
- `RELATE-010` — `source_item_id == target_item_id` (gatekeeper rule 3).
- `RELATE-011` — change_log INSERT failed inside the atomic `insert_link_with_log` transaction.
- `RELATE-024` — AI returned `target_item_id` not in the candidates list.
- `RELATE-025` — AI returned a proposal with wrong `source_item_id`.
- `RELATE-026` — `source_item_id` not in `items` (gatekeeper rule 1).
- `RELATE-027` — `target_item_id` not in `items` (gatekeeper rule 2).
- `RELATE-028` — supersedes cycle (gatekeeper rule 8).
- `RELATE-029` — `links` row INSERT failed inside the atomic `insert_link_with_log` transaction.
- `RELATE-030` — Phase 3.5 `ai_response_store.save` raised `ValueError` (both/neither of `source_id`/`item_id` set).
- `RELATE-031` — user abort (`q`); exit 2.
- `RELATE-032` — adapter call raised (timeout / network / auth / rate limit) on the 2nd attempt; 1 retry already burned.
- `RELATE-033` — AI response not JSON, or wrong shape, on the 1st parse attempt (no retry).
- `RELATE-035` — boot phase: a required env var is missing (e.g., no `OPENAI_API_KEY`). Surfaces from `build_link_proposer(env)` in §4.4 step 9 at CLI startup per Constitution I13.
- `RELATE-036` — Phase 3.5 `ai_response_store.save` raised (other than `ValueError`).

## 6. Test Targets

Unit (in-memory / fake ports, per T3; pure gatekeeper):
- Gatekeeper rule 1: `item_exists(source_id)` returns false -> `RejectedLink(code='RELATE-026')`.
- Gatekeeper rule 2: `item_exists(target_id)` returns false -> `RejectedLink(code='RELATE-027')`.
- Gatekeeper rule 3: `source == target` -> `RejectedLink(code='RELATE-010')`.
- Gatekeeper rule 4: bad link_type -> `RejectedLink(code='RELATE-005')`.
- Gatekeeper rule 5: source=Decision, target=Decision, link_type=`answers` -> `RejectedLink(code='RELATE-006')`.
- Gatekeeper rule 6: target status=Closed, link_type=`supersedes` -> `RejectedLink(code='RELATE-007')`. target status=Active + `supersedes` -> passes.
- Gatekeeper rule 7: source.type=Assumption, link_type=`supports` -> `RejectedLink(code='RELATE-008')`. source.type=Decision + `supports` -> passes (already blocked by rule 5 if compat table excludes it).
- Gatekeeper rule 8: source in target's ancestors (BFS) -> `RejectedLink(code='RELATE-028')`. target in source's ancestors -> `RejectedLink(code='RELATE-028')`. (Both directions tested.)
- Gatekeeper rule 9: `find_existing` returns a row -> `RejectedLink(code='RELATE-009')`.
- On pass: `ValidatedLink` has `status='Confirmed'`, `trigger_cause='user_confirmed'`, `field_changed='link_confirmed'`.
- Phase 3 transport retry: 1st adapter call raises transport error, 2nd call succeeds -> port returns the 2nd response. 1st and 2nd both raise -> `RELATE-032 AiCallFailed` propagates, exit 1.
- Phase 3 parse failure: adapter returns unparseable response on the 1st call -> `RELATE-033 AiResponseSchemaInvalid` propagates immediately, no retry. (Distinct from the transport retry path.)
- Phase 3.5: `ai_response_store.save` raises `ValueError` -> engine core raises `RELATE-030`. Raises `OperationalError` -> engine core raises `RELATE-036`.
- Phase 3.4: AI returns a target not in candidates -> `RELATE-024`. AI returns wrong source -> `RELATE-025`.
- Confirm loop: `y` -> 1 call to `link_store.insert_link_with_log` with the link_confirmed template; 1 link_id appended. `n` -> 1 call to `link_store.insert_link_with_log` with the link_rejected template (`status='Rejected'`); `rejected` incremented. `s` -> no DB call, `skipped` incremented. `q` -> `RELATE-031` raised, CLI exits 2.

Integration (real SQLite temp DB, migrations 001-009 applied, fake AI adapter returning canned JSON):
- Happy path: 3 candidates, all `y` -> 3 rows in `links` (all `status='Confirmed'`), 3 rows in `change_log` with `field_changed='link_confirmed'`, `trigger_cause='user_confirmed'`, `link_id=<matching links.id>`. 1 row in `ai_responses` (Phase 3.5) keyed by `item_id=new_item.id`.
- Rejection (negative memory): 3 candidates, 2 `n` + 1 `y` -> 3 rows in `links` (1 Confirmed + 2 Rejected), 3 rows in `change_log` (1 `link_confirmed` + 2 `link_rejected`); each `change_log.link_id` matches the corresponding `links.id`. **Re-running Relate on the same item must not re-suggest the 2 rejected pairs** (verifies negative-memory persistence; this is the L2 §1 line 9 contract).
- Abort: 5 candidates, user `q` after 2 -> 2 change_log rows + 2 link rows (one Confirmed, one Rejected), 3 candidates not touched.
- Gatekeeper rejection: 3 candidates, one fails rule 4 (bad link_type from the AI) -> that one is `RejectedLink` with code `RELATE-005`, not shown to the user, counted in `rejected`. Other 2 pass.
- Phase 3.5 failure: fake `ai_response_store.save` to raise `OperationalError` mid-transaction -> engine core raises `RELATE-036`, exit 1, no link written (transaction rolled back; the `links` table is empty).
- Atomicity: fault-inject the change_log INSERT to raise after the link INSERT succeeds -> transaction rolls back; both `links` and `change_log` are empty; raise `RELATE-011`.

CLI (smoke, fake AI):
- `ember relate --item <id>` -> exit 0, YAML block per accept (emitted by `format_link_block`), summary line.
- `q` mid-loop -> exit 2, summary `aborted: true`.
- Missing migrations (or `schema_version.version` < 8) -> `RELATE-014`, exit 1. (Step 1's check is the source of truth; Step 3 inherits.)
- `OPENAI_API_KEY` not set at CLI startup -> `RELATE-035`, exit 1 (raised by `build_link_proposer(env)` in §4.4 step 9, matching Capture's `CAPTURE-001` ConfigMissing pattern).

Architecture (T9):
- L2 §7.3 line 416: extends `tests/test_architecture.py` with a second function `test_relate_core_does_not_import_adapters` that scans `ember/relate/*.py` for the canonical forbidden set: `("sentence_transformers", "numpy", "sqlite3", "openai", "anthropic", "ember.adapters")`. The existing `test_capture_core_does_not_import_adapters` is untouched. Both run in CI.

## 7. CLI check (Rule S1)

- `ember relate --item <id>` with 3 candidates and all `y` -> exit 0, 3 YAML blocks, summary `accepted: 3, rejected: 0, skipped: 0, aborted: false`.
- `ember relate --item <id>` then `q` after 1 -> exit 2, 1 YAML block, summary `accepted: 1, rejected: 0, skipped: 0, aborted: true`.
- `ember relate --latest` with no unlinked active items -> **exit 0**, prints "no unrelated items" to STDOUT (per L2 §4 Phase 1 line 153 + L2 §6 line 385: soft exit 0, no code). Step 1 owns this path.
- `ember relate --item 9999` -> exit 1, `RELATE-001`, message includes the id and the DB path.
- `ember relate --item 1` on a DB where migrations 001-005 ran but 006-009 did not (or `schema_version.version` < 8) -> exit 1, `RELATE-014 SchemaOutdated`. Step 1 owns this check; Step 3 inherits.

## 8. Out of Scope (this step)

- Phases 1 and 2 (Step 1 + Step 2).
- Live AI round-trip test (separate `tests/test_relate_live.py`, opt-in via `@pytest.mark.live`, mirrors Capture's pattern).
- `change_log.link_id` FK constraint (set by migration 008; the integration test must run with it).
- Embedder revalidation at scale (L2 §0 deferral; scale test is a `deferred` GitHub issue).

## 9. Next

All 3 L3 Relate steps written. After approval, implementation starts. Bottom-up order: Step 1 (load + filter + compat table), Step 2 (3 signals + cosine + embedder port), Step 3 (gatekeeper + AI propose + Phase 3.5 + confirm + write). Each step ends with the architecture test green and the CLI check passing for the prior step (per L1 invariant #2: engine works standalone before next).

## 10. Deferred Settings (from L2 §9 + L2 §4 Phase 4 + new L3 picks)

- (L2 §9 #1) Phase 3 + 4 fold — **folded** into this step. Step 3 covers both.
- (L2 §9 #5) Live AI prompt format for `LinkProposerPort` — Step 3 picks:
  - System prompt: names the 5 link_types, names the 4 type compatibility rules, names the 2 directionality rules.
  - Few-shot examples: 0.
  - Temperature: 0.0.
  - JSON output: strict `{"proposals": [{"target_item_id": int, "link_type": str, "rationale": str | null}]}`.
- (L2 §9 #6) CLI confirm prompt format — **L2 §4 Phase 4 line 207 is `[y]es / [n]o / [s]kip / [q]uit`**. Step 3 uses this verbatim. `s` is per-proposal skip (increments `skipped`, no DB write, continues the loop). `q` is per-run abort (raises `RELATE-031`, sets `aborted=true`, exits 2). **Correction:** a previous draft of this paragraph claimed `s` was new in L3; that was wrong, L2 §4 Phase 4 line 207 already has it.
- (L2 §9 #8) `trigger_cause` vocabulary — Step 3 codifies per L2 §4 Phase 4 lines 217, 227:
  - Accept (`y`): `field_changed='link_confirmed'`, `trigger_cause='user_confirmed'`, `link_id=<new link id>`, `item_id=new_item.id`, `old_value=NULL`, `new_value='<link_type>:<target_item_id>'` (e.g. `supports:42`), `timestamp=<now>`.
  - Reject (`n`): `field_changed='link_rejected'`, `trigger_cause='rejected'`, `link_id=<new Rejected link id>`, `item_id=new_item.id`, `old_value=NULL`, `new_value='<link_type>:<target_item_id>'`, `timestamp=<now>`. (Capture's `field_changed='proposed'` for items is NOT used here; that vocabulary is items-rejected, not links-rejected.)
- Step 3 picks itself: Phase 4 `q` raises `RELATE-031 UserAbort` (matches L2 §4 Phase 4 line 233 + Capture's `CAPTURE-014` pattern). The CLI catches it and maps to exit 2.
- Step 3 picks itself: gatekeeper rule 6 (supersedes-Closed) is **narrow** — only `supersedes` link_type to a `Closed` target. `Active` and `Challenged` are allowed targets for ALL 5 link_types (including `supersedes`). This is the literal L2 §4 Phase 4 rule 6 reading; L3 does NOT tighten it.
- Step 3 picks itself: Phase 3 retry is **transport-only** (per Capture convention). Parse failures raise `RELATE-033` on the first occurrence; no silent retry budget doubling. (B9 fix.)
- **L2 amendment log entries recorded by this step** (for the next Relate plan revision to fold in):
  - L2 §5.5 line 333 `RejectedLink(reason: str, code: str)` — the `reason` field is dropped; new shape is `RejectedLink(code: str)` (CLI maps code→prose at print time). See Step 3 §4.3 step 6 (M10).
  - L2 §5.5 line 336 `LinkRun(lookup: LinkLookupPort, store: LinkStorePort)` — the dataclass is dropped; the orchestrator takes `lookup` and `store` as 2 separate args. See Step 3 §4.4 step 10 (M8).
  - **I3 supersedes M8 at the `run_relate` boundary:** `run_relate` takes `RelatePorts(link_lookup, link_store, link_proposer, ai_response_store)` and `RelateRequest(new_item, ranked, env)` (2 inputs). This is an input object required by I3, not the `LinkRun` read/write pair that M8 dropped. Record for the next Relate plan revision.

## 11. Rollback

Steps 4.3.7 `y` and 4.3.7 `n` both write to `links` and `change_log`. Both are append-only. Per L1 §4 rule 7, rollback is impossible. The framework v2 L3 rule says: state "No rollback — append-only by L1 §4 rule 7." The Phase 3.5 save (`ai_response_store.save`) is also append-only; a partial row cannot exist because SQLite rolls back the transaction on `RELATE-036` before commit, so the row is never persisted. No orphan cleanup needed.

## 12. Build Notes (post-implementation)

### What landed

- 5 new/changed relate core files: `ember/relate/link_proposal.py` (Phase 3), `ember/relate/ai_response_store.py` (Phase 3.5 port), `ember/relate/link_gatekeeper.py` (Phase 4 pure gatekeeper), `ember/relate/confirm_write.py` (Phase 4 confirm loop), `ember/relate/run_relate.py` (engine-core entry point).
- `SqliteLinkStore` (atomic `insert_link_with_log`); `SqliteLinkContext.item_status` / `supersedes_ancestors`; `build_ai_response_store`.
- `OpenAiLinkProposer` + `build_link_proposer` in `ember/adapters/llm.py`.
- The `relate` CLI wiring in `ember/cli.py`; `RelateTerminalConfirm` (raises the relate `UserAbort` on end of input).

### Test result

Full suite green: `349 passed, 2 deselected` (live tests excluded). Command: `./.venv/bin/python -m pytest -q`.

### Implementation decisions / deviations

1. Gatekeeper rule 5 (premise) runs BEFORE rule 6 (compat) so `(Assumption, supports) -> RELATE-008` is reachable (the compat table has no Assumption-source `supports`); `(Assumption, Finding, supports)` returns 008 not 006.
2. `ValidatedLink` carries a third field `rationale` (the links table has no rationale column) so `format_link_block` can print it.
3. `confirm_links` prints a non-YAML preview line before the prompt and the §3 YAML block only after an accepted write, so the §7 counts (3 accepted -> 3 blocks; 1 accept then `q` -> 1 block) hold; the §4.3 step-7 "print the block then prompt" wording is superseded.
4. `q`/end-of-input returns `ConfirmResult(aborted=True)` (mirrors Capture) instead of raising `RELATE-031`; the CLI prints the summary and exits 2.
5. `RelatePorts` gains a fifth port `confirm` (the loop needs the user-I/O boundary; the plan's four-tuple omitted it).
6. `RelateRequest.env` is carried but unread (the proposer is injected as a port).
7. `run_relate` lives in the new `ember/relate/run_relate.py`.
8. A raw-answer save failure maps to `RELATE-036` for the real adapter (its write error is a Capture `EmberError`, so only `RelateError` is re-raised).
9. The missing AI key surfaces when candidates exist (lazy `build_link_proposer`), not at command startup, so an empty pool still soft-exits 0.

### Known gaps

- No live AI round-trip test (out of scope, §8).
- The CLI happy path requires the optional `.[relate]` extra + an API key, so it is verified through tests, not a live run.

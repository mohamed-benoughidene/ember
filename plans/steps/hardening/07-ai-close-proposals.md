# L3 Hardening Step 07: AI-proposed closes, pre-filtered (ticket 13, #16)

Implements L2 maintain §14 ("V1.x Amendment: AI-proposed closes, pre-filtered"), which pins the one pre-filter rule, the first Maintain AI port, the confirm loop, five error codes (018–022), and the L1 amendment lines. No migration, no floor move. Closes #16 (#18 untouched — plain-text export keeps its separate plan). Blocked by ticket 12 (step 06, landed).

## 0. Constitution rules this step enforces

- **B3 / B4 / P4** — the provider SDK hides behind `CloseProposerPort` in the engine core; the adapter owns the SDK, the prompt wire format and the boundary parse (L2 §14.3).
- **B2** — the engine imports only public interfaces (`CloseProposerPort` is its own; `AiResponseStorePort` from `ember.relate.ai_response_store`, one shape, D3; `HUMAN_SETTABLE_REASONS` from `human_actions.py`, one fact, one place).
- **D8 / I16** — the raw answer is stored verbatim in `ai_responses` keyed by `item_id` (D8 exactly-one-of owner, `save()` verified at `ai_response_store.py:13` + `sqlite.py:1451`), before anything is judged.
- **D4 / I9** — the AI answer is untrusted outside data: checked at the boundary (adapter raises 018/019), core sees only checked `CloseProposal` objects.
- **D3** — accepted closes reuse `validate_close_item` → `user_closed` ledger rows, the §4.6 vocabulary unchanged; rejected proposals write nothing (L2 §14.4 ruling).
- **D5 / I10** — additive only: `ItemState.statement: str | None = None`, one dataclass subclass, no renames, no schema.
- **T1 / T2** — `stale_close_candidates` and `parse_close_proposal` are pure; `now` is injected; I/O sits at the adapter and the CLI.
- **T7** — parser/retry/loop tests run on recorded fixtures under `tests/fixtures/maintain/`; no live AI anywhere in the suite (L2 §14.9).
- **T9** — `close_proposer.py` imports stdlib + pydantic only; the existing `test_architecture.py` glob over `ember/maintain/*.py` covers it, no test edit.
- **I2 / I3 / I4** — separate entry points (`run_sweep` untouched; `run_close_proposals(ports, now)`, 2 inputs); `StaleShortlist` / `ProposalOutcome` are named objects.
- **I15** — timeout 60 s, `max_retries=0`, the ONE retry belongs to the engine (`propose_close_with_retry`).
- **I17 / I21** — five new codes, contiguous, each with a per-code test asserting the code (§4).
- **I12 / S1** — exit 0/1/2; `ember maintain` runs alone with inspectable output; the empty-shortlist case needs no key (proven by CLI check).
- **P1** — only the ruled scope: one pre-filter rule, one cap, one port, one loop, one reused write path.

## 1. Job

After this step, `ember maintain` does what it does today plus one Phase 5: it deterministically names stale questions (Active Questions whose newest confirmed `answers` link is at least 30 days old, capped at 10), asks the AI to propose a close (`invalidated`/`expired`) for that shortlist only, shows each proposal for y/n/q confirmation, and writes an accepted close through the existing human `close-item` path. An empty shortlist means zero AI calls and no key needed. The AI never closes anything.

## 2. The pin

- **Constants** (L2 §14.2): `STALE_DAYS = 30` (`now - newest answers link created_at >= timedelta(days=30)`, boundary inclusive); `MAX_CLOSE_PROPOSALS = 10` (first 10 by `item_id` ascending, `truncated=True` when more existed). Malformed/naive `created_at` → not a candidate, never raises (totality, step-06 precedent).
- **`ember/maintain/close_proposer.py`** (new): constants; `StaleCandidate`; `StaleShortlist`; `stale_close_candidates(snapshot, *, now: datetime) -> StaleShortlist`; `CloseProposal`; `CloseProposalResponse`; `CloseProposerPort`; `ConfirmPort` (maintain-local ask/write protocol, third sibling); `ProposalOutcome`; `parse_close_proposal(ai_response: str) -> CloseProposal | None`; `propose_close_with_retry(proposer, *, candidate) -> CloseProposalResponse` (retry ONCE on 018 or 019, second failure propagates — the capture `propose_items` shape, chosen over relate's schema-no-retry because the ticket requires the empty answer to be retried); `format_proposal_block(candidate, proposal | None) -> list[str]`; `SYSTEM_PROMPT` below; a ~10-line fence-strip helper (the `item_proposal.py:198-206` precedent; copy, do not import the private one).
- **`SYSTEM_PROMPT`, pinned word-for-word (no semicolons — work rule):**

```
You judge whether one stale Question from a project-knowledge graph can be retired.
You see the question and the confirmation date of the link that answered it.
Propose a close only when the question is clearly settled. Use reason
"invalidated" when the question's premise is wrong or was disproven. Use reason
"expired" when the answer is old and the question no longer matters.
Return close=false when the question may still be open.
Return ONLY a JSON object, no Markdown fence and no text before or after it:
{"close": <true|false>, "reason": "<invalidated|expired>", "confidence": <0.0-1.0>, "rationale": <short string or null>}
```

  User message, one candidate per call: `Item <item_id> [Question]: <statement>` / `Newest answers link: link <id> from item <answered_by>, confirmed <newest_answer_created_at>` / `Return the judgment as strict JSON.`
- **Parse rules** (each deviation raises `MAINTAIN-019`): whole answer is a JSON object; `close` boolean; `false` → `CloseProposalResponse(raw_response, None)` (other keys ignored); `true` requires `reason in HUMAN_SETTABLE_REASONS`, `confidence` float in [0.0, 1.0], `rationale` str-or-null.
- **Adapter** (`ember/adapters/llm.py`, third section next to `build_link_proposer`): `OpenAiCloseProposer`, `build_close_proposer(env=None)`. Key missing → `MAINTAIN-020` (the `build_link_proposer` spine: openai import, `DEFAULT_BASE_URL`, `REQUEST_TIMEOUT_SECONDS`, `max_retries=0`, `EMBER_AI_MODEL`/`EMBER_AI_BASE_URL` envs, `temperature=0.0`), parse inside the adapter, provider error details redacted through the existing `_without_secret` helper.
- **Engine** (`ember/maintain/run_maintain.py`): `ItemState.statement: str | None = None` (rows.py, additive); `@dataclass(frozen=True) class CloseProposalPorts(MaintainPorts)` with `close_proposer`, `ai_response_store`, `confirm`; `run_close_proposals(ports: CloseProposalPorts, now: datetime) -> ProposalOutcome` — fresh `_load(ports.lookup)` → `stale_close_candidates` → loop per candidate: `propose_close_with_retry` → `ports.ai_response_store.save(item_id=..., raw_response=...)` (ValueError propagates raw — engine-constructed argument, code bug crashes loudly, I5; storage failure → `MAINTAIN-021`) → decline counts / proposal displays `format_proposal_block` + `PROMPT = "[y]es / [n]o / [q]uit"` (unknown answer re-asks) → `y`: `run_close_item(MaintainPorts(ports.lookup, ports.store), MaintainRequest(item_id=c.item_id, reason=p.reason))`, then `for line in format_report(result.changed, result.total_items): ports.confirm.write(line)` (the engine loop prints through the injected port — the relate `confirm.write` pattern, no `print` in core), accepted += 1; `n`: rejected += 1, no write; `q` or `UserAbort` (MAINTAIN-022): return `ProposalOutcome(..., aborted=True)`.
- **CLI** (`ember/cli.py`): the `maintain` command keeps phases 1–4 exactly as today, then: fresh snapshot via `_load(ports.lookup)`; `shortlist = stale_close_candidates(snapshot2, datetime.now(timezone.utc))`; on `--dry-run` print one `item <id>: stale Question (newest answers link <id>, confirmed <ts>) (dry-run)` per candidate + the outcome line and exit 0 **without building the proposer**; non-dry-run with an empty shortlist prints the outcome line and exits 0 without building the proposer; otherwise `proposer = build_close_proposer(os.environ)` (this import line is the fake seam, `tests/test_cli_capture.py` pattern), `ConfirmPort` = `MaintainTerminalConfirm` (new tiny class mirroring `RelateTerminalConfirm`, raising `from ember.maintain.errors import UserAbort as MaintainUserAbort` — alias needed, capture's `UserAbort` is already imported at `cli.py:32`), `run_close_proposals(...)`, print one `stale: N, proposed: N, accepted: N, rejected: N, aborted: <bool>` line, `sys.exit(2)` when aborted. The report lines of accepted closes print inside the loop (per accept), before the outcome line — block display, y answer, report lines, next proposal.
- **Truncation note** (when `shortlist.truncated`): `stale shortlist capped at 10 items (list truncated)` — before the loop.

### Exact output blocks (the §6 pins build on these)

Real run, 2 candidates, decline first, then an accepted proposal (the `y` report lines print inside the loop, per accept, before the outcome line):

```
Proposal 1/2: item 7 [Question] should we cache tokens?
  newest answers link 11, confirmed 2026-01-01T00:00:00+00:00
  no close proposed
Proposal 2/2: item 9 [Question] which auth backend?
  newest answers link 12, confirmed 2026-01-01T00:00:00+00:00
  reason: expired, confidence 0.8
  rationale: answered long ago, no follow-up open
[y]es / [n]o / [q]uit
item 9: Active -> Closed (expired)
closed: 1, challenged: 0, reopened: 0, unchanged: 2
stale: 2, proposed: 1, accepted: 1, rejected: 0, aborted: false
```

(The seed is items 4, 7, 9 plus a second Finding source for link 11 (compat-legal Finding->Question), Confirmed with `created_at=T_ANSWER`: item 9's newest answers link is 12, item 7's is 11, one confirmed answers link per target. `total_items = 4`, one changed, `unchanged: 3`. `run_close_item`'s fresh load counts the whole DB.) (Review fix 2.)

The outcome line is exactly five fields: `stale: N, proposed: N, accepted: N, rejected: N, aborted: <bool>`. `proposed` counts AI proposals made; `accepted`/`rejected` are the `y`/`n` answers; a decline is proven by `stale − proposed` and prints no reason line. On `--dry-run` with 1 stale candidate:

```
item 9: stale Question (newest answers link 12, confirmed 2026-01-01T00:00:00+00:00) (dry-run)
stale: 1, proposed: 0, accepted: 0, rejected: 0, aborted: false
```

Empty shortlist (real or dry): only the sweep report (unchanged, `format_report`) plus:

```
stale: 0, proposed: 0, accepted: 0, rejected: 0, aborted: false
```

## 3. Steps

1. `ember/maintain/rows.py`: `ItemState.statement: str | None = None` (additive, I10). `ember/adapters/sqlite.py` `SqliteMaintainContext.list_items`: SELECT gains `statement`, row gains the field. `MAINTAIN-010` unchanged.
2. `ember/maintain/close_proposer.py`: constants, models, `stale_close_candidates`, `SYSTEM_PROMPT`, `parse_close_proposal`, `propose_close_with_retry`, `format_proposal_block`, `ConfirmPort` (all pure or protocol).
3. `ember/maintain/errors.py`: the five classes (§4).
4. `ember/adapters/llm.py`: `OpenAiCloseProposer` + `build_close_proposer` (imports 018/019/020 from `ember.maintain.errors`).
5. `ember/maintain/run_maintain.py`: `CloseProposalPorts`, `run_close_proposals`, the raw-save helper mapping storage failure → `MAINTAIN-021`; docstring lists raised codes (I11).
6. `ember/cli.py`: the maintain-command tail (§2), `MaintainTerminalConfirm`, imports (`build_close_proposer`, `stale_close_candidates`, `run_close_proposals`, `CloseProposalPorts`, aliased `UserAbort`, `SqliteAiResponseStore` already imported).
7. `tests/fixtures/maintain/`: the five T7 fixtures (`close_proposal_valid.json`, `close_proposal_decline.json`, `close_proposal_bad_reason.json`, `close_proposal_not_object.json`, `close_proposal_empty.txt` — all recorded snap-shapes, no prose assertions).
8. `tests/maintain/fakes.py`: `FakeCloseProposer` (queue of `CloseProposalResponse`s + a `calls` list) and a raising `AiResponseStoreStub` for M021. `FakeMaintainLookup` / `FakeMaintainStore` untouched.

## 4. Errors (codes only, per L2 §14.8)

`MAINTAIN-018 CloseAiCallFailed` — call failed after the one retry. `MAINTAIN-019 CloseAiSchemaInvalid` — answer unreadable / rule-breaking after the one retry. `MAINTAIN-020 CloseAiConfigMissing` — non-empty shortlist, no API key. `MAINTAIN-021 CloseAiStoreFailed` — `ai_responses` INSERT failed. `MAINTAIN-022 UserAbort` — end of input → `aborted=True`, exit 2. Reused on the accept path, same failure = same code: `MAINTAIN-001/002/003/004` (validate), `MAINTAIN-010` (reads), `MAINTAIN-011/012` (batch write). No other code changes.

## 5. Test targets

Owned (names grepped against `tests/` — zero collisions for `close_proposer`, `stale_close`, `propose_close`):

- Pure, `tests/maintain/test_close_proposer_unit.py` (fake lookup + synthetic `Link`s, fixed `now`s):
  `test_prefilter_names_active_question_with_old_answers_link`, `test_prefilter_ignores_challenged_and_closed_questions`, `test_prefilter_ignores_answers_to_non_question`, `test_prefilter_uses_newest_answers_link_when_two_exist`, `test_prefilter_boundary_exactly_stale_days_is_candidate`, `test_prefilter_fresh_answers_link_within_stale_days_is_not_candidate`, `test_prefilter_malformed_created_at_is_not_candidate_and_never_raises`, `test_prefilter_rejected_links_are_invisible`, `test_prefilter_caps_at_ten_and_sets_truncated`, `test_prefilter_carries_statement_for_display`, `test_parser_reads_valid_proposal_fixture`, `test_parser_decline_fixture_yields_none`, `test_parser_bad_reason_fixture_raises_close_ai_schema_invalid`, `test_parser_not_object_fixture_raises_close_ai_schema_invalid`, `test_parser_empty_answer_raises_close_ai_schema_invalid`, `test_parser_confidence_out_of_range_raises_close_ai_schema_invalid`, `test_retry_once_on_call_failure`, `test_retry_once_on_schema_failure`, `test_second_failure_propagates_coded_error`, `test_format_block_decline_shape`.
- Adapter, `tests/maintain/test_close_proposer_adapter.py`: `test_build_close_proposer_missing_key_raises_close_ai_config_missing`, `test_build_close_proposer_uses_env_overrides` (base URL/model picked up — config surface, no call), `test_openai_close_proposer_maps_openaierror_to_close_ai_call_failed` (fake client raising `OpenAIError`), `test_openai_close_proposer_passes_temperature_zero` (fake client records the request).
- Engine loop, `tests/maintain/test_close_proposals_integration.py` (real temp DB via `open_maintain_database`, `FakeCloseProposer`, recorded confirm fake): `test_empty_shortlist_proposer_is_never_called`, `test_accept_writes_via_validate_path_one_user_closed_row`, `test_accept_invalidated_challenges_dependents_like_close_item`, `test_accept_on_shielded_item_close_applies_origin_stays_manual` (the accepted close is the exempt primary — it applies over the §13 shield and is never stamped `rearm`; `items.status_origin` stays `'manual'`, asserted), `test_reject_writes_nothing_and_counts`, `test_quit_aborts_and_leftovers_get_no_call`, `test_decline_counts_and_writes_nothing`, `test_raw_response_stored_by_item_id_verbatim`, `test_store_failure_raises_close_ai_store_failed`, `test_error_mid_loop_keeps_earlier_accepts`, `test_truncated_shortlist_caps_calls_at_ten`.
- CLI, `tests/maintain/test_close_proposals_cli.py` (CliRunner, real temp DB, seeded SQL, monkeypatched `ember.cli.build_close_proposer` — no key anywhere): `test_maintain_cli_empty_shortlist_needs_no_key_and_no_builder_call`, `test_maintain_cli_accept_block_and_outcome_line`, `test_maintain_cli_reject_counts_no_rows`, `test_maintain_cli_quit_exits_2`, `test_maintain_cli_decline_shows_no_close_proposed`, `test_maintain_cli_dry_run_lists_shortlist_no_key`, `test_maintain_cli_missing_key_with_stale_shortlist_exits_1_close_ai_config_missing`, `test_maintain_cli_truncation_note`.

Declared churn (part of this step's diff): unchanged `run_sweep` means engine-level tests are untouched; **no existing assertion breaks:** every maintain-summary pin in `tests/maintain/test_maintain_cli.py` and `test_maintain_commands_cli.py` is a substring `in` check, so the new trailing `stale:` line breaks nothing and NO existing test is edited. New `stale:`-line pins live only in the new `test_close_proposals_cli.py` (review fix 4); `tests/maintain/test_maintain_read_failures.py` unchanged (`list_items` read failure path is the same query's error branch; its docstring promise still holds). `ItemState` constructor sites keep compiling (additive default — grep confirms no positional-constructor pattern: `ItemState(...)` is keyword-built everywhere).

## 6. CLI check (Rule S1)

Real `.venv/bin/ember` on real temp DBs (`T_ANSWER = 2026-01-01T00:00:00+00:00`, deterministic). Two seed shapes: **(i)** a plain DB with a few items and NO `answers` links at all — the sweep has nothing to derive and the shortlist is empty; **(ii)** a stale question that SURVIVES the sweep: item 9 `Question` "which auth backend?" `Active`, item 4 `Finding`, Confirmed `answers` link 12 (4 → 9, `created_at=T_ANSWER`), AND item 9 `status_origin='manual'` with its manual-clear ledger row dated AFTER the link (the only shape an old answers link can't machine-close — the shield eats the sweep's own `answered` close, L2 §14.2's emergence note).

**Case A — empty shortlist, no API key, unpatched binary** (seed i):

```
$ ember maintain --db /tmp/empty.db
closed: 0, challenged: 0, reopened: 0, unchanged: 2
stale: 0, proposed: 0, accepted: 0, rejected: 0, aborted: false
```

Exit 0, **no `EMBER_AI_API_KEY` set, and the run must not construct the adapter** — proving the no-key/no-call rule at the binary level. Then on seed (ii), real unpatched binary `ember maintain --db /tmp/stale.db --dry-run` (dry-run never builds the proposer, so no key is needed even with a non-empty shortlist):

```
item 9: stale Question (newest answers link 12, confirmed 2026-01-01T00:00:00+00:00) (dry-run)
stale: 1, proposed: 0, accepted: 0, rejected: 0, aborted: false
```

Exit 0. **Case B — non-empty shortlist, faked proposer, no API key** (runner route: the CliRunner tests in §5's CLI file, monkeypatching `ember.cli.build_close_proposer` exactly like `tests/test_cli_capture.py:59` does): queue = [decline for item 7, proposal(expired, 0.8) for item 9], input `y` on the second proposal → the §2 block byte-for-byte, exit 0, and `SELECT status, close_reason FROM items WHERE id = 9` → `Closed / expired`, one `user_closed` `change_log` row, and two `ai_responses` rows (one per AI call, keyed `item_id=7` and `item_id=9`). Same queue, input `n` on the second → `stale: 2, proposed: 1, accepted: 0, rejected: 1, aborted: false`, item 9 still `Active`, zero `change_log` rows. Input `q` on the only proposal → `stale: 1, proposed: 1, accepted: 0, rejected: 0, aborted: true`, exit 2. Seed (ii) with NO fake and no key → `error: MAINTAIN-020 CloseAiConfigMissing ...` on stderr, exit 1, nothing written.

## 7. Rollback

Code revert only — no schema, no down-migration, nothing to un-backfill. `ai_responses` rows written meanwhile are append-only raw answers keyed by item; under the old binary they are unread, unrendered by every command (query never reads the table), and harmless. Accepted closes leave real `user_closed` ledger rows — those are legitimate human-confirmed closes, restorable only through the existing reopen semantics (they were confirmed by a human `y`), stated honestly: a revert does not reopen them. Undo procedure: revert the commits; zero DB steps.

## 8. Step invariant

After this step: the module runs; `stale_close_candidates` and `parse_close_proposal` are total (never raise on any snapshot/answer input — malformed answers raise coded 019, malformed timestamps skip); the empty shortlist makes zero AI calls and needs zero keys (proven by test AND by real-binary run); every accepted close went through the existing `validate_close_item` → `apply_status_changes` chain with zero new write code; all owned tests pass; the declared churn is applied; the full suite is green with real numbers in Build Notes; `ember db-check` still reports `version: 12`, `floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none`, `result: OK`.

## 9. Out of scope

No `--no-ai` flag, no TTY-only gating (capture precedent: the loop always runs; an unattended run over a non-empty shortlist aborts exit 2, capped waste). No second pre-filter rule (`items.created_at` is not in the snapshot — L2 §14.2). No ledger row for proposals/rejections. No T8 benchmark. No `statement` display work beyond the block. No change to `run_sweep`, the four human commands, Query, or the §4.6 vocabulary. No prompt-tuning, no model change.

## 10. Build Notes

Filled 2026-10-29, after the build (agent, ticket 13).

**What landed vs §3 (all eight steps):** (1) `ItemState.statement: str | None = None` (additive) and the `list_items` SELECT gaining `statement`. (2) `ember/maintain/close_proposer.py` — constants, models, `stale_close_candidates`, `SYSTEM_PROMPT` (pinned §2 text verified word-for-word in the build), `parse_close_proposal`, `propose_close_with_retry`, `format_proposal_block`, `ConfirmPort`, `PROMPT`. (3) The five error classes 018-022 (017 verified as errors.py's tail via `git log -p` before adding). (4) `OpenAiCloseProposer` + `build_close_proposer` in `ember/adapters/llm.py` (the `build_link_proposer` spine: key vars, `MAINTAIN-020` fail-fast, timeout 60, `max_retries=0`, `temperature=0.0`), parse inside the adapter, `_without_secret` redaction. (5) `CloseProposalPorts` + `run_close_proposals` + the D8 save helper (`ValueError` propagates raw, storage failure → `MAINTAIN-021`) in `run_maintain.py`; `run_sweep` untouched. (6) The `maintain` command tail, `MaintainTerminalConfirm`, imports; the sweep report now prints at phase 4 (inside the try) so the proposal blocks appear after it, matching the §2 block order. (7) The five T7 fixtures. (8) `FakeCloseProposer` + `AiResponseStoreStub` in `tests/maintain/fakes.py`; `FakeMaintainLookup` / `FakeMaintainStore` untouched.

**TDD red/green (real numbers):** baseline full suite **793 passed, 4 deselected**. All 43 owned tests written first, run red: 4 collection errors (`ModuleNotFoundError: No module named 'ember.maintain.close_proposer'`, then the `ember.cli.build_close_proposer` seam missing), then, climbing dependency order: unit file 20/20 green, adapter 4/4, integration 11/11, CLI 8/8. Final full suite **836 passed, 4 deselected** (793 + 43, zero churn; no existing test edited — the churn list holds).

**§6 evidence (real `.venv/bin/ember`, no `EMBER_AI_API_KEY` / `OPENROUTER_API_KEY` in env):**

- Case A (seed i, plain DB, no answers links): `closed: 0, challenged: 0, reopened: 0, unchanged: 2` + `stale: 0, proposed: 0, accepted: 0, rejected: 0, aborted: false`, exit 0 — with no key, adapter construction is impossible (`build_close_proposer` fails fast `MAINTAIN-020`), so the run provably built no proposer.
- Seed (ii) stale question that survives the sweep (manual shield + clear ledger row dated after the link), `--dry-run`: `item 9: stale Question (newest answers link 12, confirmed 2026-01-01T00:00:00+00:00) (dry-run)` + the outcome line, exit 0, no key, no proposer built (also asserted by test with a poisoned builder).
- No fake and no key on seed (ii), real run: `error: MAINTAIN-020 CloseAiConfigMissing | ...` on stderr, exit 1, nothing written (0 `ai_responses` rows, 0 `user_closed` rows, item 9 untouched).
- Case B (faked proposer, CliRunner route, `tests/test_cli_capture.py:59` monkeypatch pattern): the §2 block byte-for-byte (see the CliRunner note below), item 9 → `Closed/expired`, 1 `user_closed` row, 2 `ai_responses` rows; `n` → `stale: 2, proposed: 1, accepted: 0, rejected: 1, aborted: false`, item 9 still Active, 0 `user_closed` rows; `q` → exit 2, `aborted: true`.
- `ember db-check` on a temp DB: `version: 12`, `floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none`, `reversal replay: 0 reversed links, column == ledger`, `result: OK`.

**Deviations, all recorded here (none silent):**

1. **`format_proposal_block` signature** — §2's sketch omitted index/total; the pinned block's first line is `Proposal 1/2: ...`, so the helper takes `*, index, total` keyword-only. One pure helper, same bytes.
2. **§2 block line `unchanged: 2` vs review fix 2's arithmetic** — with the corrected 4-item seed (items 4, 5, 7, 9), `run_close_item`'s fresh load gives `total_items = 4`, one changed, `unchanged: 3`. The review-fix parenthetical governs; the tests pin `unchanged: 3`.
3. **CliRunner vs the pinned `[y]es / [n]o / [q]uit` line** — under CliRunner the typed answer is not echoed onto the prompt line (an interactive terminal echoes it and its Enter supplies the newline, which is the view the §2 block depicts), so the accept test pins the bytes on both sides of that one prompt line separately, and the prompt line itself as a substring. Nothing else about the block is loosened.
4. **`test_accept_invalidated_challenges_dependents_like_close_item`** — a Question can never be a `depends_on` target in a compat-legal graph (`TYPE_COMPAT` has no such pair; migration 011's `links_compat_insert` trigger refuses it), so the close fan-out is unreachable for AI-proposed closes in practice (the pre-filter only proposes Questions). That test's one throwaway seed drops `links_compat_insert` on its temp DB and writes `Decision 10 depends_on Question 9` raw, to pin that the accept path fans out through `validate_close_item` exactly like `ember close-item` (`user_closed` primary + `dependency_closed` challenge). Production behavior is unchanged and the finding is recorded: AI accepts can never challenge a dependent on a legal graph.
5. **`stale` count on a truncated shortlist** — `ProposalOutcome.stale` is the capped list length (max 10); the truncated remainder is reported by the `stale shortlist capped at 10 items (list truncated)` note, not by inflating the count. `StaleShortlist` (the pinned shape) carries no pre-cap total.
6. **Reject-case `change_log` count** — the §6 seed legitimately contains manual-clear ledger rows, so "zero `change_log` rows" is pinned as "zero rows beyond the seed, 0 `user_closed`".
7. **Truncation note in dry-run too** — printed before the dry-run candidate lines as well; §2 pins it "before the loop" without naming a branch, and both branches honor it.

**Plan edits made (L2 §14.7 word-for-word, same commit series):**

- `plans/master-plan.md` rule 3 — from `3. AI-callable mutations (each requires user confirm): `add_item`, `add_link`.` to `3. AI-callable mutations (each requires user confirm): `add_item`, `add_link`, `propose_close`. A `propose_close` proposal writes nothing: the human confirms it in `ember maintain`'s confirm loop and the close is written only through the human validate path (`validate_close_item`).`
- `plans/master-plan.md` §5 — from `AI-proposed `close_item` deferred to V1.x (issue #16). V1 ships `ember close-item` human-invoked; the human running the command is the confirmation.` to `AI-proposed `close_item` (issue #16) ships pre-filtered (V1.x, 2026-10-29): a deterministic pre-filter names stale candidates (capped at 10), the AI proposes a close with reason `invalidated` or `expired` for that shortlist only, and the human confirms through the existing `ember close-item` validate path (`validate_close_item`) inside `ember maintain`'s confirm loop. The AI never writes a close itself; raw answers are stored in `ai_responses` keyed by `item_id` (D8).`
- `plans/engine-maintain-plan.md` §14.1 lines moved recorded → applied (the §12.2 pattern, step-05 line-46 annotation precedent): the stack header (line 5), the preamble "Maintain calls no AI" pointer, §4.0 narrowed (with the Phase-5 box added to the pipeline diagram), §5 "No environment variables", §5 exit codes (maintain now exits 2 on abort), §7.7 Live ("None required, one available"), §8's bullet closed, and §Z rows D8/I15/I16/T7 moved from (b) to (a), T8 staying (b). Each edited line carries the "(Amended in hardening step 07 ...)" annotation. §3 line 81 and §8's step-03 note intentionally not amended (§14.7's "Lines intentionally NOT amended").

**Manual check left open:** none for code; the Case B byte-for-byte block on a real interactive terminal (a human typing `y` after the prompt line) is the one view the CliRunner cannot reproduce — the runner-side bytes are pinned by test as described in deviation 3.

## 11. Issue closure

- **Build-time plan edits owned by THIS step (not pre-applied):** `plans/master-plan.md` rule 3 (line 117) and §5 (line 131), the word-for-word from/to lines are pinned in L2 §14.7 — apply them in the same commit series as the code so L1 is never stale against a landed feature. Also one §8 sentence in `plans/engine-maintain-plan.md`'s own preamble/§4.0 apply-at-build: the §14.1 amended lines move from "recorded" to "applied" when §3 lands (the §12.2 pattern of recording-then-applying).
- Closes #16 via ticket 13: comment with §6 evidence and the test count. The #16 trigger line in `plans/hardening-decisions.md` goes stale on the landed decision line — the Decision is the record.
- Ticket-wording note (review fix 6): the ticket says "Human reject logs and moves on, exactly like relate's confirm loop". L2 §14.4 rules the reject path deliberately DIVERGES from relate: no rejected-proposal ledger row is written, the rejection lives in `ai_responses` and the outcome count only. Read the checklist with this ruling, not the relate wording.
- #18 untouched: plain-text export stays with its separate plan.
- Update `PROJECT_MAP.md` rows for `ember/maintain/close_proposer.py`, the `llm.py` third section, and the amended `ember maintain` command line (one line each, per AGENTS.md).

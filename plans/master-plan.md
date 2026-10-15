# L1 System Master Plan

Terse caveman style. Source: `docs/ai version/project-context-system-v1-ai.md` V1 spec. No invention.

## 0. Stack Decisions (V1)

Locked at L1. All L2 + L3 step plans assume this stack. Changes to stack = new L1 amendment.

- **Language:** Python 3.12+. Stdlib `sqlite3` for DB.
- **CLI:** Click (per-engine CLI commands).
- **Tests:** pytest. TDD per Rule T4.
- **Validation:** Pydantic. Validates outside data at the edge (Constitution I9), trusted inside.
- **LLM adapter:** OpenAI Python SDK pointing at OpenRouter base URL. Model name in config (env var). Default model: `anthropic/claude-3.5-sonnet`. Future-proof: native Anthropic SDK can be added as 2nd adapter behind same `*Port` contract; engine core does not change.
- **Embedder:** `sentence-transformers` Python lib, model `bge-base-en-v1.5` (384d). Local, no API cost.

Engine core imports only stdlib + Pydantic + Click + pytest. Adapters (LLM, embedder) are siblings, not dependencies of engine core (architecture test Rule T9).

## 1. System Job

Store durable knowledge about project. 4 item types: `Decision`, `Assumption`, `Finding`, `Question`. Each item has status: `Active`, `Challenged`, `Closed`. Close reasons: `answered`, `invalidated`, `superseded`, `reversed`, `expired`. History immutable. Deletion forbidden.

## 2. Engines

Four engines. Each one job. Each runs alone via its own CLI command on sample input, producing inspectable output (Rule S1).

### Engine A: Capture
- Job: turn raw human input into typed item proposals.
- Input: pasted text OR saved source file path. Pasted text first stored in `sources` table, then `add_item` references it via `source_id`.
- Output: item proposal with type, statement, source quote (must exist as substring in `sources.full_text`).
- Gatekeeper script scans near-duplicates via text similarity warning before save.
- Status: `Active`.

### Engine B: Relate
- Job: find candidate typed links between items.
- Input: new item ID.
- Output: ranked candidate pairs with link type guess.
- Signals: dense vector + graph traversal + metadata filter. Embedding uses an `EmbedderPort` socket. The model name (e.g. `bge-base-en-v1.5`) is the plug, not the engine.
- Rule: AI proposes pairs only via `LinkProposerPort`. Never selects candidates, never invents link types.
- BM25 keyword search excluded from candidate pool.
- Top-10 cosine-similarity cap on initial candidate pool.
- Status: `Active`.

### Engine C: Maintain
- Job: keep graph coherent after item or link changes.
- Input: any state change event (link confirmed, item closed, etc.).
- Output: derived state changes on dependent items.
- Four fixed triggers (via `validate_close_item` script):
  1. `supersedes` confirmed -> old target `Closed` reason `superseded`.
  2. item `Closed` reason `invalidated`/`superseded`/`reversed` -> direct `depends_on` dependents set `Challenged`.
  3. `contradicts` confirmed -> target set `Challenged`. Link direction chosen by user at accept time.
  4. `answers` confirmed -> target `Question` `Closed` reason `answered`.
- Flag spread: single step only. No cascade.
- Self-fix for typos: user creates a new item with `supersedes` link to the typo'd one. Old typo gets `Closed` reason `superseded`. New corrected item is live.
- Reversal path: reversing a `supersedes` link restores the old item to `Active`. Already-flagged Challenged dependents stay Challenged until human clears them (Spec 3.5). Reversal writes a `change_log` row with `trigger_cause='reversal'`.
- Status: `Active`.

### Engine D: Query
- Job: return context views.
- Four modes:
  1. `current_state`: `Active` + `Challenged`. `Closed` omitted.
  2. `topic_search`: BM25 keyword search over item statements. Returns ranked item IDs.
  3. `why`: backward traversal of `depends_on` and `supports` links, plus read of `Decision.rationale` text field.
  4. `history`: append-only change log, shows chronological field mutations and causes.
- Sorting by `Challenged` first happens at the display layer. Core returns unsorted.
- Output format: structured lists. Zero AI prose.
- Status: `Active`.

## 3. Shared Storage + Data Flow

All engines share one local SQLite DB file (Spec 3.6). Foreign keys ON. Each engine is an independent CLI invocation against this DB. Engine-to-engine flow goes through DB rows, not direct function calls. There is no shared memory or runtime call graph between engines.

Storage architecture (Spec 3.6):
- `items`: Decision, Assumption, Finding, Question rows. Foreign key `source_id` references `sources.id`.
- `links`: typed directional edges. Status values `Confirmed` or `Rejected` (stored permanently).
- `change_log`: append-only ledger. Columns: `item_id`, `link_id` (nullable, for link-driven mutations), `field_changed`, `old_value`, `new_value`, `timestamp`, `trigger_cause`. Immutable, append-only.
- `sources`: full source texts. Columns: `id`, `title`, `full_text`, `timestamp`, `content_hash` (for tamper detection).
- AI raw responses table (`ai_responses`): stores AI responses verbatim, keyed by `source_id` + `timestamp` (Constitution D8, I16; `source_id` because no item exists yet when the AI is called).
- Embedding table + metadata table: implementation detail, decided in L2 (do not invent in L1).

Boundary rule: gatekeeper scripts are the castle gate. Engine core is the clean inside. Engine core trusts what gatekeeper gives it. Gatekeeper scripts:
- For AI mutations: `validate_add_item`, `validate_add_link`, `validate_close_item`.
- For AI reads: `validate_query`.
- For human-only operations: `validate_edit_item`, `validate_set_status`, `validate_set_validated`, `validate_remove_link`.

### Dependency Chain

```
[Human input]
   |
   v
Engine A (Capture)  --writes-->  items, sources
                                  |
                                  v
                        Engine B (Relate) --reads new item, items graph-->
                                          --proposes (not stored)--> candidate pairs
                                                            |
                                                            v
                                          [Human accept/reject]
                                                            |
                                          --writes--> links (status Confirmed or Rejected)
                                                            |
                                                            v
                                          Engine C (Maintain) --reads links, items-->
                                                               --writes--> items.status, change_log
                                                                                  |
                                                                                  v
                                                                       Engine D (Query) --reads items, links, change_log-->
                                                                                         --returns--> structured lists to caller
```

Dependency order, not runtime order. Each engine invoked independently.

## 4. Global Rules (Apply All Engines)

1. AI direct DB write: PROHIBITED (Spec 3.7).
2. All mutations pass gatekeeper validation scripts.
3. AI-callable mutations (each requires user confirm): `add_item`, `add_link`, `close_item`.
4. AI-callable reads (no confirm needed, raw data only): `query`.
5. Human-only operations: `edit_item`, `set_status` (only `Active` <-> `Challenged`), `set_validated`, `remove_link`.
6. `Challenged` resolution: human only via `set_status` (Spec 3.5, 3.2).
7. Raw input immutable. Historical items immutable (Spec 3.2 + 3.6).

## 5. Out of Scope (V1)

Deferred item types: `Constraint`, `Issue`, `Evidence` standalone, `Rationale` standalone, `Reasoning` standalone. Storage mappings for non-deferred types:
- `Rationale` text lives on `Decision` row as a field (Spec 3.1).
- `Evidence` text lives on `Finding` row as the `source` field (Spec 3.1).

Deferred link types: `informs`, `constrained_by`, `invalidates`, `raises`, `derived_from`. Handling note: `invalidates` is achieved by creating a `contradicts` link plus closing the target as `Closed` reason `invalidated` (Spec 3.3).

## 6. Live Measures (Post-Build)

Per Spec 3.9, evaluated after V1 is deployed:
1. Capture quality on prompt v3 extraction yield.
2. Human approval prompt fatigue rate.
3. Dense vector candidate recall scale test (500-5000 items).
4. Author ground-truth data for initial 20 benchmark items. Benchmark set runs periodically post-build to measure drift.

## 7. Test Strategy

Test pyramid (Rule T4):
- Unit tests on pure core logic per engine.
- Integration tests on real SQLite temp DB (one per engine).
- Architecture tests asserting engine core never imports adapters (Rule T9, run in CI).
- 1-2 E2E tests per engine with fake outside tools.

Approach: Test-Driven Development (TDD). For each L3 step plan: write failing test first, run it (red), write minimal code to pass (green), refactor. Each step ends with passing tests + green CLI check before moving on.

Test targets (Rule T6): contract promises, edge cases, expected error codes, regression bugs. Skip internal implementation details.

AI testing (Rule T7): test parser, validation, retries with saved fixtures. Assert output schema and types. Never assert exact prose words.

## 8. Next Step

Human approves L1. Then 4 L2 engine master plans: `capture`, `relate`, `maintain`, `query`. Each L2 defines internal pipeline phases for its engine.

## 9. Deferred to L2 (Reminder)

- Embedding table name and metadata table name.
- `Signals` object wrapper for candidate builder (deferred until signal count grows beyond 3).
- **Embedder model revalidate at Engine B L2 planning start.** Current default `bge-base-en-v1.5` per V1 spec 3.4. Owner: Engine B author. May swap to a different model (e.g. larger or different family) based on V1 spec 3.9 #3 candidate-recall scale test.
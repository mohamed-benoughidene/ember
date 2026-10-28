# L3 Query Step 2: Topic Search + Why (Phases 2+3+4 for modes 2 and 3)

Implements L2 Query plan §4 Phase 2 (the BM25 scorer and the `why` traversal), §4 Phase 3 renderers for both modes, §4.7 (orchestration + gate), §5 (CLI) for `topic_search` and `why`. Builds entirely on step 01's seam — no port or model changes, no L2 amendments.

## 0. Constitution rules this step enforces

- **B1** — scorer, traversal, renderers, orchestrator are separate modules from step 01's.
- **B2 / B3 / P4** — both cores read only through `QueryLookupPort`; SQLite stays behind the adapter.
- **D2** — the BM25 score is derived data, recomputed on every run; nothing is cached.
- **I1** — named by job: `topic_search`, `why`, `run_topic_search`, `run_why`.
- **I4** — returns are named models (`SearchHit`, `WhyReason`, `WhyResult`) or lists of them.
- **D4 / I9** — outside data (`--query`, `--item`) is validated at the gate (D4's mechanism) and the gatekeeper owns QUERY-001/002; the cores assume valid input (no re-checks, no duplicate gate tests in the core unit tests).
- **I17 / I21** — no new codes; the step reuses QUERY-001, QUERY-002, QUERY-005 only.
- **P3** — Load → Derive (pure; per-mode ordering exactly where L2 §4 Phase 3 puts it) → Render → CLI.
- **T1** — both cores are pure: no I/O, no clock, no randomness (`random`-free determinism matters for golden scores).
- **T3** — cores are tested against `FakeQueryLookup`; the golden BM25 scores live in a **named fixture file** under `tests/fixtures/` so every expected number can be re-derived and reviewed, not inline strings.

## 1. Job

Two more read modes on the same seam:

- `ember topic-search --query TEXT`: BM25 over every item's statement (closed items included, each hit carrying its `status`), ranked, token- and formula-fixed by the L2.
- `ember why --item ID`: the reasons behind an item — walk `depends_on` forward-to-target (the premise) and `supports` backward-to-source (the evidence), Confirmed links only, transitive, cycle-safe, unlimited depth.

## 2. Inputs

- `topic-search`: `--query TEXT` (required), `--db PATH`. `validate_query_text` raises QUERY-002 before the core runs (I9).
- `why`: `--item ID` (required, `type=int`), `--db PATH`. `validate_query_item` raises QUERY-001 before the core runs.
- Reads (unchanged port, L2 §4.5): `topic_search` uses `list_items()`; `why` uses `list_items()` + `list_links()`.

## 3. Outputs

Row models (added to `ember/query/rows.py`, L2 §4.5):
- `SearchHit(item_id, score, type, statement, status)` — `status` so a superseded decision is visible next to a live one (L2 §2.2).
- `WhyReason(item_id, type, statement, status, rationale, depth, via_link_type, via_link_id)` — `rationale` is NULL everywhere in V1 (nothing writes the column, L2 §2.4) and that is correct, not a bug.
- `WhyResult(item: QueryItem, reasons: list[WhyReason])`.

Envelopes (L2 §4 Phase 3):
- `{"mode": "topic_search", "query": "<text>", "count": N, "results": [SearchHit, …]}`
- `{"mode": "why", "item": {QueryItem}, "count": N, "reasons": [WhyReason, …]}`

Signatures (L2 §4 Phase 2): `topic_search(items, query) -> list[SearchHit]`; `why(items, links, item_id) -> WhyResult`.

## 4. Steps

1. BM25 scorer (`ember/query/topic_search.py`, pure), formula fixed by L2 §4 Phase 2:
   - `idf(q) = ln(1 + (N - df(q) + 0.5) / (df(q) + 0.5))`, `k1 = 1.2`, `b = 0.75` (see §10 — kept, not tuned).
   - Corpus = every item's statement; a result needs `score > 0`.
   - Tie-break: score descending, then `item_id` ascending (Phase 3 does not re-sort).
   - Guard before scoring: `avgdl == 0` → return `[]` (no `ZeroDivisionError`).
2. `why` traversal (`ember/query/why.py`, pure), rules per L2 §4 Phase 2 + §2.3:
   - From node: `depends_on` with node as **source** → target is a reason; `supports` with node as **target** → source is a reason. Only `Confirmed` links.
   - Transitive, no depth cap, **visited set** across the walk (a `depends_on` cycle is legal in the DB and must terminate).
   - `depth` 0 at the start item, 1 for a direct reason, and so on; output ordered `(depth, item_id)`. The start item is **not** one of the reasons — it travels separately as `WhyResult.item` (L2 §4 Phase 3 envelope), so "no links to walk" is an empty reasons list, not an error.
   - Works for any item type. An item with no qualifying links yields an empty list, which is correct, not an error (its existence was already gated).
3. Renderers in `ember/query/render.py`: envelopes above; neither mode re-sorts (L2 §4 Phase 3).
4. `ember/query/run_query.py`: `run_topic_search(lookup, query) -> str`, `run_why(lookup, item_id) -> str` — validate (§4.7) → load → derive → render.
5. `ember/cli.py`: `ember topic-search --query TEXT [--db PATH]` and `ember why --item ID [--db PATH]`, flat on the root group; exit codes and stderr format as step 01.
6. Golden fixture: `tests/fixtures/query/bm25_golden.json` — corpus (3 documents with known token counts), the query, `k1`, `b`, and the expected scores to 6 decimal places. Committed with the computation inputs so a future reader can re-derive every number.
7. Tests per §6.

## 5. Errors (codes only, per L2 §6)

- `QUERY-001` `QueryItemNotFound` — `why --item <unknown>`; context `item_id`; raised by `validate_query_item`. **L2 §4.7 — first CLI exposure.**
- `QUERY-002` `QueryTextEmpty` — `topic-search` with a token-free query; raised by `validate_query_text`; carries `query_length`, never the text (a newline in user text must not break the one-line log, and the text may hold a pasted secret). **L2 §6 / §4.7 — first CLI exposure.**
- `QUERY-005` `ItemsReadFailed` — any `list_items` / `list_links` failure. **L2 §4.5.**

No new codes are created by this step.

## 6. Test Targets

Unit (pure cores + fakes, no DB):
- BM25 vs the golden fixture, 6 decimal places (named fixture file, T3).
- `ln(1 + …)` property: a term in every document still scores above zero; scores stay positive.
- Zero-token corpus → `[]`; empty corpus → `[]`; an item with no query token is not a result.
- Tokenizer: mixed case folds; punctuation splits; a unicode letter is a token character; digits are tokens.
- Tie-break: equal scores come out in `item_id` order.
- Gatekeeper on these modes (moved here from the L2 §7.1 bullets): a valid `--query` / `--item` passes the gate and the core is reached through the port only — the gate returns without touching the core; `why`'s item check runs, `topic-search`'s text check runs.
- Renderers: both envelopes (`topic_search`, `why`) round-trip through `json.loads` and every row's keys match its model (the step-01 renderer contract, extended).
- `why`: one test per link type with the yielded **direction** asserted; a Rejected link yields nothing; a `depends_on` cycle terminates with every node exactly once; transitivity returns `depth` 2 reasons; a reason-Decision carries its `rationale`; `rationale` null when the column is NULL.

Integration (real temp DB, migrations 001–010, compat-legal fixtures — the L2 §7.2 rule inherited from Maintain):
- `topic_search` over a DB with a known statement returns the expected item and score.
- `why` over a DB with a real `depends_on` link returns the premise.

CLI (smoke, L2 §7.4):
- `ember topic-search --query sqlite --db <fixture>` → exit 0, `results` present in parsed JSON.
- `ember why --item 99 --db <fixture>` → exit 1, `error: QUERY-001 …` on stderr.
- `ember topic-search --query "!!!" --db <fixture>` → exit 1, `error: QUERY-002 …` on stderr.
- stdout carries nothing but the JSON document on both success paths.

## 7. CLI check (Rule S1)

- `ember topic-search --query <term> --db tests/fixtures/query/current_state.db` → `{"mode": "topic_search", "query": …, "count": ≥1, "results": […]}`, exit 0.
- `ember why --item 1 --db tests/fixtures/query/current_state.db` → `{"mode": "why", …}`, exit 0; `ember why --item 99 --db …` → `error: QUERY-001 …`, exit 1.

## 8. Out of Scope (this step)

- The change_log classifier and `history` (step 03); README/PROJECT_MAP and issue closures (step 03).
- Semantic/vector search, FTS5, `rank_bm25` (rejected, L2 §4 Phase 2 + §8).
- A result cap and status/type filters — resolved to "not in V1" (§10), not code.

## 9. Next

Step 03 adds `history` (classifier + union derivation + command) and the closeout (README, PROJECT_MAP, cross-plan amendments, issue closures).

## 10. Deferred Settings (from L2 §9) — resolved by this step

1. **#1 BM25 `k1` / `b`: kept at L2's 1.2 / 0.75.** Standard textbook values; tuning would invalidate every golden score for no measured need. Revisit only if search quality is reported poor, with a new golden fixture in the same commit.
2. **#2 result cap: no `--limit` in V1.** The corpus is the founder's own project notes, not 5 000+ rows; an unbounded hit list is honest output, and a cap silently hides the tail. Recorded as a `deferred` GitHub issue at step 03 closeout ("topic-search cap for large corpora").
3. **#3 status / type filters: not in V1.** §2.2's Closed decision already covers the only filter real use asks for (search scope). Same closeout issue as #2 records the deferral.

## 11. Rollback

No rollback — Engine D writes no rows and ships no migration (L2 §2.6). Undo of the code itself: drop the commits.

## 12. Build Notes (post-implementation)

To be added after the code lands.

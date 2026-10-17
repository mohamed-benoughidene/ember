# L3 Relate Step 2: Candidate Pool (Phase 2: 3 signals + merge)

Implements Phase 2 of L2 Relate plan. Build a ranked candidate pool from 3 signals (content/dense, graph, metadata) and merge them with cosine-or-0.5 scoring.

## 0. Constitution rules this step enforces

- **B1** — `candidate_pool.py` is one module, one purpose.
- **B2** — engine core reads only through ports (`LinkLookupPort`, `EmbeddingStorePort`); no `sqlite3` import.
- **B3** — `sentence-transformers` is hidden behind `EmbedderPort`; engine core does not know the model.
- **B4** — `EmbeddingStorePort` hides the "do we cache or recompute" decision.
- **B5** — one public function `build_candidate_pool` runs all 3 signals + merge.
- **D2** — embeddings are a regenerable derived cache (per L1 §3 "raw input immutable; history immutable; derived data rebuildable").
- **I4** — `Pool(ranked, counts)`, `RankedCandidate(item, cosine, source)`, `SignalKind` are Pydantic models (L2 §5.5). `source: SignalKind` (single value, the strongest signal — content wins if present).
- **I6** — RELATE-017 through RELATE-023 subclass `EmberError` per L2 §6.
- **I10 / T6** — cosine math in `ember/relate/candidate_pool.py` is a private helper `_cosine`; public surface is `build_candidate_pool`.
- **I15** — embedder adapter carries `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS=120` per L2 §5.2; engine core inherits.
- **I21** — error codes from §5 below name themselves; tests assert codes, not message prose.
- **P3 / P4** — Phase 2 of the L2 §4 pipeline; all DB/cache I/O goes through ports.
- **S1 / S3** — CLI check in §7; input/output shapes in §2 and §3.
- **T1 / T2** — the merge step is pure; side effects (cache writes, wipe) are behind `EmbeddingStorePort`.
- **T9** — `candidate_pool.py` and `embedding_store.py` import nothing from `ember.adapters.*`; `numpy` is forbidden (stdlib `math` only).

## 1. Job

Take the `(NewItem, CandidateUniverse)` from Step 1 and produce a ranked `list[RankedCandidate]` for Phase 3. Three signals run independently and are merged by union (with cosine score if present, else 0.5).

## 2. Inputs

From Step 1: `NewItem` and `CandidateUniverse`.
From ports (L2 §4.5):
- `LinkLookupPort.neighbors_of(item_id) -> list[int]`
- `EmbeddingStorePort.get(item_id) -> list[float] | None`
- `EmbeddingStorePort.upsert(item_id, vector, model_name) -> None`
- `EmbeddingStorePort.model_name_of(item_id) -> str | None`
- `EmbeddingStorePort.wipe() -> None`
- `EmbedderPort.embed(texts) -> list[list[float]]`
- `EmbedderPort.dim() -> int`
- `EmbedderPort.model_name() -> str`

## 3. Outputs

- `list[RankedCandidate]` — the merged, ranked candidate list. Rank order is descending cosine, then by id ASC as the stable tie-breaker.
- A side-effect: `item_embeddings` may gain new rows for the new item or any universe member that lacked a cached vector.
- A side-effect: if the cached `model_name` on the first read row mismatches the active embedder, `wipe()` runs and the loop re-encodes (L2 §4.6 RELATE-020 behavior; STDERR warning only, no code).

`RankedCandidate(item: NewItem, cosine: float | None, source: SignalKind)` — `SignalKind` is a single value (per M5: the strongest signal wins; per L2 §5.5). `Pool(ranked, counts)` is **dropped** (per M4): Step 3 only needs `ranked`; `counts` is for the CLI's debug print (§7) and lives inside the function.

## 4. Steps

1. **Pre-flight model name check.** Read the first existing row from `item_embeddings` (any row). If `model_name_of` returns a name and it differs from `embedder.model_name()`, print to STDERR `"embedding model changed: wiping cache (this is a one-time minutes-long cost on large DBs)"` and call `embedding_store.wipe()`. The "minutes-long cost" line is per the §3 #12 reviewer note (L2 §3.2 last paragraph acknowledges this; L3 surfaces it to the user). This is the L2 §4.6 RELATE-020 behavior (no error code; wipe + warning).
2. **Resolve the new item's vector.** Call `embedding_store.get(new_item.id)`. If non-None and `model_name` matches, use it. Else call `embedder.embed([new_item.statement])` and `embedding_store.upsert(new_item.id, vector, embedder.model_name())`. Wrap any raise in `RELATE-018` (encode fail) or `RELATE-017` (load fail; the load happens at factory time, so by Step 2 it's already loaded — RELATE-017 surfaces at CLI startup, not here).
3. **Content signal.** For each `X` in `universe.items`:
   - Try `embedding_store.get(X.id)`. If None, call `embedder.embed([X.statement])` and `embedding_store.upsert(X.id, vector, model_name)`. Wrap upsert failures in `RELATE-019`.
   - Compute cosine(new_vec, X_vec). Helper `_cosine(a, b) -> float` (per §0 T9: stdlib `math` only, no `numpy`); raises `RELATE-022` only on **zero vector** (denominator = 0, from a corrupted cache row). NaN/Inf branches are dropped (per M6): `sentence-transformers` bge-base-en-v1.5 produces float32 vectors bounded in `[-1, 1]`, so NaN/Inf cannot occur.
   - Top 10 by cosine become the content signal candidates. Each carries its cosine.
4. **Graph signal.** Call `link_lookup.neighbors_of(new_item.id)`. Returned ids are intersected with `universe.items` (a neighbor that did not survive the Phase 1 filter is dropped). Each surviving id gets `cosine = 0.5`, `source = graph`. BFS depth = 1 (L2 §4 Phase 2 default; Step 2 does not deepen).
5. **Metadata signal (temporal proximity only).** For each `X` in `universe.items`, parse `X.created_at` (ISO TEXT) and `new_item.created_at`. Keep `X` if `|X.created_at - new_item.created_at| <= 30 days`. The subtraction is done via `datetime.fromisoformat` + `timedelta(days=30)`. Wrap parse failures in `RELATE-023`. Each surviving id gets `cosine = 0.5`, `source = metadata`. No status filter (per M7: L2 §4 Phase 1 keeps Closed items; Step 2 does not re-filter).
6. **Merge.** Union of content, graph, metadata. When the same id appears from multiple signals, keep the highest cosine and set `source` to the strongest single signal: `dense` if content matched, else `graph` if it matched, else `metadata`. `source` is a single `SignalKind` (per M5; L2 §5.5's spec).
7. **Rank.** Sort by cosine DESC, then by id ASC as the stable tie-breaker. Return `list[RankedCandidate]`.

## 5. Errors (codes only, per L2 §6 + §4.6)

- `RELATE-017` — embedder load fail (raised at factory / CLI startup; Step 2 surfaces it on the first `embed()` if the load failed late).
- `RELATE-018` — embedder encode fail (any `embedder.embed(...)` raises).
- `RELATE-019` — `embedding_store.upsert(...)` raises.
- `RELATE-021` — `link_lookup.neighbors_of(...)` raises.
- `RELATE-022` — cosine math hits a zero vector (denominator = 0).
- `RELATE-023` — `datetime.fromisoformat` raises on a malformed `created_at` (defensive; schema enforces ISO TEXT but the helper double-checks).

## 6. Test Targets

Unit (fake ports per T3; in-memory `LinkLookupPort`, in-memory `EmbeddingStorePort`, fake `EmbedderPort`):
- Empty universe -> empty list, no signals fire.
- Content-only: embedder returns 5 distinct vectors; one cached, four not; top-10 are the 5 with cosine computed.
- Graph-only: 3 neighbors, all in universe, none in content; pool has 3 entries with `cosine=0.5`, `source=graph`.
- Metadata-only: 2 items within ±30 days, 3 outside; pool has 2 with `cosine=0.5`, `source=metadata`.
- Union: same id from content + graph; pool has one entry with `cosine` from content, `source=dense` (content wins per merge rule).
- Pre-flight: cached `model_name` mismatches active -> `wipe()` called, STDERR line printed, loop re-encodes.
- Cosine helper: zero vector -> `RELATE-022`. Normal vectors -> float in `[-1.0, 1.0]`.
- `--item` whose `universe.items` is empty -> empty list, Phase 3 will exit 0 with `accepted: 0` (Step 3 owns that exit).

Integration (real SQLite temp DB, migrations 001-009 applied, fake embedder returning fixed 384-dim vectors):
- 10 items seeded; 3 linked to the new item, 2 within ±10 days, 2 far away. Run Phase 2; assert pool size and ranking.
- Embedder pre-warmed: all 10 items have cached vectors. Run twice; the second run must not call `embedder.embed` (assert via call counter on the fake adapter).
- Pre-flight mismatch: insert one row with `model_name='old-model'` -> wipe, STDERR line, re-encode.

## 7. CLI check (Rule S1)

Step 1 + Step 2 alone, with Phase 3 stubbed: `ember relate --item <id>` prints `{"phase": 2, "pool_size": <int>, "signals": {"dense": <int>, "graph": <int>, "metadata": <int>}}` and exits 0. Step 3 replaces the stub.

## 8. Out of Scope (this step)

- AI propose (Phase 3).
- User confirm + write (Phase 4).
- BM25 / Engine D territory.
- `--item` status filter (Step 1 accepts any status; Step 2 does not re-filter because Phase 1 already passed it).
- Multi-item batch runs (L2 §8 #5: one item per run).
- Post-union candidate cap (L2 §9 #7: not picked; L3 default is no cap).

## 9. Next

Step 3 runs Phase 3 (AI propose via `LinkProposerPort` + Phase 3.5 raw-response save via `AiResponseStorePort`) and Phase 4 (gatekeeper + user confirm + atomic write via `LinkStorePort`).

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #2) Graph BFS depth — Step 2 picks **1-hop**. Implementation: single `neighbors_of` call, no recursion. Recorded in §6 (no depth-2 test).
- (L2 §9 #3) Metadata temporal window — Step 2 picks **±30 days** as the literal L2 default. No widening for older items.
- (L2 §9 #4) Tie-breaker for `cosine=None` rows — Step 2 picks **id ASC** as the stable tie-breaker. No recency or statement-length tie-breaker.
- (L2 §9 #7) Post-union cap — Step 2 picks **no cap**. If the user reports cost problems on hub items later, this step grows a `top_k` parameter at L3 next time.

## 11. Rollback

No rollback — embeddings are cached rows, but they are a derived cache, not an immutable history. Per L1 §4 rule 7, the source-of-truth items are immutable; the cache is regenerable. L3 documents the wipe procedure: `DELETE FROM item_embeddings;` (no `change_log` entry needed; not a user-visible change).

## 12. Build Notes (post-implementation)

TBD after code lands.

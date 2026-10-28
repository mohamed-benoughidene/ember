# L3 Relate Step 2: Candidate Pool (Phase 2: 3 signals + merge)

Implements Phase 2 of L2 Relate plan. Build a ranked candidate pool from 3 signals (content/dense, graph, metadata) and merge them with cosine-or-0.5 scoring.

## 0. Constitution rules this step enforces

- **B1** — `candidate_pool.py` is one module, one purpose.
- **B2** — engine core reads only through ports (`LinkLookupPort`, `EmbeddingStorePort`); no `sqlite3` import.
- **B3** — `sentence-transformers` is hidden behind `EmbedderPort`; engine core does not know the model.
- **B4** — `EmbeddingStorePort` hides the "do we cache or recompute" decision.
- **B5** — one public function `build_candidate_pool` runs all 3 signals + merge.
- **D2** — embeddings are a regenerable derived cache (per L1 §3 "raw input immutable; history immutable; derived data rebuildable").
- **I3** — `build_candidate_pool` takes at most 4 inputs: `loaded` plus the 3 ports. No out-parameters.
- **I4** — `Pool(ranked, counts, warning)`, `RankedCandidate(item, cosine, source)`, `SignalKind` are Pydantic models (L2 §5.5). `source: SignalKind` (single value, the strongest signal — content wins if present). `Pool` is the named return object.
- **I5** — the adapters map expected external failures to named errors; the core re-raises them. Code bugs crash loudly; the core has no broad `except`.
- **I6** — RELATE-017 through RELATE-023 and RELATE-037 subclass `EmberError` per L2 §6.
- **I10 / T6** — cosine math in `ember/relate/candidate_pool.py` is a private helper `_cosine`; public surface is `build_candidate_pool`. Tests exercise cosine behavior through the public function, not the private helper.
- **I11 / I21** — the public function contract lists inputs, output, raised codes, and side effects; tests assert codes, not message prose.
- **I13** — `validate_embedder_config` runs at CLI boot, before DB work, and fails fast on missing packages or a bad timeout.
- **I15** — embedder adapter carries `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS=120` per L2 §5.2; engine core inherits.
- **I17** — cache reads get their own stable code, `RELATE-037 EmbeddingReadFailed`; `RELATE-016` stays for Phase 1 item/link reads.
- **P3 / P4** — Phase 2 of the L2 §4 pipeline; all DB/cache I/O goes through ports.
- **S1 / S3** — CLI check in §7; input/output shapes in §2 and §3.
- **T1 / T2** — the merge step is pure. Side effects (cache writes, wipe) are behind `EmbeddingStorePort`; the model-change warning is returned in `Pool.warning`, not printed by the core.
- **T9** — `candidate_pool.py` and `embedding_store.py` import nothing from `ember.adapters.*`; `numpy` is forbidden (stdlib `math` only).

## 1. Job

Take the `LoadedCandidates` from Step 1 and produce a `Pool` for Phase 3. `Pool.ranked` is the ranked `list[RankedCandidate]`. Three signals run independently and are merged by union (with cosine score if present, else 0.5).

## 2. Inputs

From Step 1: `LoadedCandidates(new_item: NewItem, universe: CandidateUniverse)` (the named wrapper from `ember/relate/load_filter.py:load_item_candidates` and `load_latest_candidates`; Step 2 destructures into `new_item` and `universe` internally).
From ports (L2 §4.5 + Step 1 protocol amendments):
- `LinkLookupPort.neighbors_of(item_id) -> list[int]`
- `EmbeddingStorePort.get(item_id) -> list[float] | None`
- `EmbeddingStorePort.upsert(item_id, vector, model_name) -> None`
- `EmbeddingStorePort.model_name_of(item_id) -> str | None`
- `EmbeddingStorePort.first_model_name() -> str | None`
- `EmbeddingStorePort.wipe() -> None`
- `EmbedderPort.embed(texts) -> list[list[float]]`
- `EmbedderPort.dim() -> int`
- `EmbedderPort.model_name() -> str`

## 3. Outputs

- `Pool(ranked, counts, warning)` — the named return object:
  - `ranked: list[RankedCandidate]` — the merged, ranked candidate list. Rank order is descending cosine, then by id ASC as the stable tie-breaker.
  - `counts: dict[str, int]` — pre-merge signal sizes under `dense`, `graph`, and `metadata`. `dense` is the size after the top-10 cut.
  - `warning: str | None` — the model-change text when a wipe happened, else None.
- A side-effect: `item_embeddings` may gain new rows for the new item or any universe member that lacked a cached vector.
- A side-effect: if the cached `model_name` on the first read row mismatches the active embedder, `wipe()` runs and the loop re-encodes (L2 §4.6 RELATE-020 behavior; the warning is returned, no code).

`RankedCandidate(item: NewItem, cosine: float | None, source: SignalKind)` — `SignalKind` is a single value (per M5: the strongest signal wins; per L2 §5.5). `Pool` is **returned**, reversing the earlier M4 "dropped" decision: I3 and I4 require at most 4 inputs and a named return object, and T1 forbids the core printing the warning. Step 3 only needs `Pool.ranked`.

## 4. Steps

1. **Pre-flight model name check.** Read the first existing row from `item_embeddings` (any row). If the cached name is not None and differs from `embedder.model_name()`, call `embedding_store.wipe()` and set `warning` to `"embedding model changed: wiping cache (this is a one-time minutes-long cost on large DBs)"`. The core does not print; the CLI prints `Pool.warning` to STDERR. The "minutes-long cost" line is per the §3 #12 reviewer note (L2 §3.2 last paragraph acknowledges this; L3 surfaces it to the user). This is the L2 §4.6 RELATE-020 behavior (no error code; wipe + warning).
2. **Resolve the new item's vector.** Call `embedding_store.get(new_item.id)`. If non-None and `model_name` matches, use it. Else call `embedder.embed([new_item.statement])` and `embedding_store.upsert(new_item.id, vector, embedder.model_name())`. The adapter maps encode/load failures to `RELATE-018` / `RELATE-017`; the core re-raises. `RELATE-017` also surfaces at CLI boot from `validate_embedder_config`.
3. **Content signal.** For each `X` in `universe.items`:
   - Try `embedding_store.get(X.id)`. If None, call `embedder.embed([X.statement])` and `embedding_store.upsert(X.id, vector, model_name)`. The adapter maps upsert failures to `RELATE-019`; the core re-raises.
   - Compute cosine(new_vec, X_vec). Helper `_cosine(a, b) -> float` (per §0 T9: stdlib `math` only, no `numpy`); raises `RELATE-022` on a **zero vector** (denominator = 0) or **unequal lengths**. NaN/Inf branches are dropped (per M6): `sentence-transformers` bge-base-en-v1.5 produces float32 vectors bounded in `[-1, 1]`, so NaN/Inf cannot occur.
   - Top 10 by cosine become the content signal candidates. Each carries its cosine.
4. **Graph signal.** Call `link_lookup.neighbors_of(new_item.id)`. Returned ids are intersected with `universe.items` (a neighbor that did not survive the Phase 1 filter is dropped). Each surviving id gets `cosine = 0.5`, `source = graph`. BFS depth = 1 (L2 §4 Phase 2 default; Step 2 does not deepen). The adapter maps read failures to `RELATE-021`; the core re-raises.
5. **Metadata signal (temporal proximity only).** For each `X` in `universe.items`, parse `X.created_at` (ISO TEXT) and `new_item.created_at`. Keep `X` if `|X.created_at - new_item.created_at| <= 30 days`. The subtraction is done via `datetime.fromisoformat` + `timedelta(days=30)`. Parse failures raise `RELATE-023`. Each surviving id gets `cosine = 0.5`, `source = metadata`. No status filter (per M7: L2 §4 Phase 1 keeps Closed items; Step 2 does not re-filter).
6. **Merge.** Union of content, graph, metadata. When the same id appears from multiple signals, keep the highest cosine and set `source` to the strongest single signal: `dense` if content matched, else `graph` if it matched, else `metadata`. `source` is a single `SignalKind` (per M5; L2 §5.5's spec).
7. **Rank and return.** Sort by cosine DESC, then by id ASC as the stable tie-breaker. Return `Pool(ranked, counts, warning)`.

## 5. Errors (codes only, per L2 §6 + §4.6)

- `RELATE-017` — embedder load fail. Raised by `validate_embedder_config` at CLI boot when a package is missing, or by the embedder adapter when the model cannot load.
- `RELATE-018` — embedder encode fail. Raised by the embedder adapter for any encode failure or a wrong vector count.
- `RELATE-019` — `embedding_store.upsert(...)` / `wipe(...)` fails. Raised by the store adapter.
- `RELATE-021` — `link_lookup.neighbors_of(...)` fails. Raised by the link adapter.
- `RELATE-022` — cosine math hits a zero vector (denominator = 0) or vectors of unequal length.
- `RELATE-023` — `datetime.fromisoformat` raises on a malformed or mixed-zone `created_at` (defensive; schema enforces ISO TEXT but the helper double-checks).
- `RELATE-037` — `embedding_store.get(...)` / `model_name_of(...)` / `first_model_name(...)` read fails. Raised by the store adapter.

The core re-raises named errors unchanged and does not catch generic exceptions (I5). A code bug crashes loudly.

## 6. Test Targets

Unit (fake ports per T3; in-memory `LinkLookupPort`, in-memory `EmbeddingStorePort`, fake `EmbedderPort`):
- Empty universe -> `Pool(ranked=[], counts={dense:0, graph:0, metadata:0})`, no signals fire.
- Content-only: embedder returns 5 distinct vectors; one cached, four not; top-10 are the 5 with cosine computed. Assert the cache rows, not call counts.
- Graph-only: 3 neighbors, all in universe, none in content; pool has 3 entries with `cosine=0.5`, `source=graph`.
- Metadata-only: 2 items within ±30 days, 3 outside; pool has 2 with `cosine=0.5`, `source=metadata`.
- Union: same id from content + graph; pool has one entry with `cosine` from content, `source=dense` (content wins per merge rule).
- Pre-flight: cached `model_name` mismatches active -> `wipe()` happened, `pool.warning` is the exact line, the loop re-encodes (assert the cache rows).
- Cosine behavior through `build_candidate_pool`: a cached zero vector -> `RELATE-022`; a cached short vector -> `RELATE-022`; normal results in `[-1.0, 1.0]`. No direct `_cosine` calls (T6).
- Generic exceptions from a port propagate unchanged (I5); the core does not wrap them.
- `--item` whose `universe.items` is empty -> `Pool(ranked=[])`, Phase 3 will exit 0 with `accepted: 0` (Step 3 owns that exit).

Integration (real SQLite temp DB, migrations 001-009 applied, fake embedder returning fixed 384-dim vectors):
- 10 items seeded; 3 linked to the new item, 2 within ±10 days, 2 far away. Run Phase 2; assert `pool.ranked` size, order, and `pool.counts`.
- Embedder pre-warmed: all 10 items have cached vectors. Run twice; the second run must not rewrite any row. Assert every `embedded_at` and every stored vector blob is unchanged (T6: no call counter).
- Pre-flight mismatch: insert one row with `model_name='old-model'` -> wipe, `pool.warning` is the exact line, re-encode (assert every row now carries the active model name and the old row for a dropped item is gone).

## 7. CLI check (Rule S1)

Step 1 + Step 2 alone, with Phase 3 stubbed: `ember relate --item <id>` prints `{"phase": 2, "pool_size": <int>, "signals": {"dense": <int>, "graph": <int>, "metadata": <int>}}` and exits 0. If `Pool.warning` is set, it is printed to STDERR. Step 3 replaces the stub.

At the start of the command, `validate_embedder_config()` runs before the DB is opened, so a missing optional package (`RELATE-017`) or a bad timeout (`RELATE-035`) fails fast (I13). The model is built only when the universe is non-empty; an empty universe prints zero counts without loading the model.

## 8. Out of Scope (this step)

- AI propose (Phase 3).
- User confirm + write (Phase 4).
- BM25 / Engine D territory.
- `--item` status filter (Step 1 accepts any status; Step 2 does not re-filter because Phase 1 already passed it).
- Multi-item batch runs (L2 §8 #5: one item per run).
- Post-union candidate cap (L2 §9 #7: not picked; L3 default is no cap).

## 9. Next

Step 3 runs Phase 3 (AI propose via `LinkProposerPort` + Phase 3.5 raw-response save via `AiResponseStorePort`) and Phase 4 (gatekeeper + user confirm + atomic write via `LinkStorePort`). It consumes `Pool.ranked` from Step 2.

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #2) Graph BFS depth — Step 2 picks **1-hop**. Implementation: single `neighbors_of` call, no recursion. Recorded in §6 (no depth-2 test).
- (L2 §9 #3) Metadata temporal window — Step 2 picks **±30 days** as the literal L2 default. No widening for older items.
- (L2 §9 #4) Tie-breaker for `cosine=None` rows — Step 2 picks **id ASC** as the stable tie-breaker. No recency or statement-length tie-breaker.
- (L2 §9 #7) Post-union cap — Step 2 picks **no cap**. If the user reports cost problems on hub items later, this step grows a `top_k` parameter at L3 next time.
- **L2 amendment log entries recorded by this step** (folded into `plans/engine-relate-plan.md` on 2026-10-17):
  - L2 §6 gains `RELATE-037 EmbeddingReadFailed` for `item_embeddings` cache reads; `RELATE-016` stays for Phase 1 `items` / `links` reads (folded at L2 §6 line 388).
  - L2 §4.5 `EmbeddingStorePort` gains `first_model_name() -> str | None` — the pre-flight "any row" read, because `model_name_of(item_id)` cannot read an arbitrary first row.
  - **Added at review 2026-10-28:** `_resolve_vector` in the engine core raises `RELATE-022` when a cached or freshly encoded vector's length ≠ `embedder.dim()`, *before* cosine runs. This is a defensive duplicate of the embedder adapter's `RELATE-018` wrong-count check; neither §4 steps 2-3 nor §5 spelled it out, so it is recorded here.

## 11. Rollback

No rollback — embeddings are cached rows, but they are a derived cache, not an immutable history. Per L1 §4 rule 7, the source-of-truth items are immutable; the cache is regenerable. L3 documents the wipe procedure: `DELETE FROM item_embeddings;` (no `change_log` entry needed; not a user-visible change).

## 12. Build Notes (post-implementation)

### 12.1 Embedder package decision (approved 2026-10-17)

The `sentence-transformers` package is **left for later**: it is declared as an optional extra (`[project.optional-dependencies] relate = ["sentence-transformers>=3"]`), not as a main dependency. A plain `pip install -e .` stays small and does not install the model library.

- Install path for a developer who wants real embeddings: install CPU-only `torch` first from `https://download.pytorch.org/whl/cpu`, then install the extra. This avoids the CUDA packages (a normal Linux install pulled 47 packages, including `nvidia-*`).
- `validate_embedder_config()` checks package presence with `importlib.util.find_spec` at CLI boot. If `sentence_transformers` or `torch` is missing, `ember relate` fails fast with `RELATE-017 EmbedderLoadFailed`; the error names the missing optional extra. The real adapter still imports the library lazily and loads the model only when needed.
- Unit and integration tests use fakes. The CLI tests stub the boot check, so the suite passes without the optional extra. The real model is only used by the live terminal check.
- Undo: remove the `relate` extra and uninstall `sentence-transformers` / `torch`. No `items`, `sources`, `links`, or `change_log` rows are touched.

### 12.2 Implementation decisions made while building Step 2

These are deviations or clarifications from the text above. They are recorded here so the reviewer can see them in one place.

- **`Pool` is returned (M4 reversed).** The earlier plan dropped `Pool` because Step 3 only needs `ranked`. That conflicts with I3 (4-input maximum: `loaded` plus 3 ports), I4 (named return object, no out-parameter), and T1 (the core must not print). `build_candidate_pool` now returns `Pool(ranked, counts, warning)` and takes exactly 4 inputs. Step 3 uses `pool.ranked`.
- **No STDOUT/STDERR in core.** The model-change warning is returned in `Pool.warning`; the CLI prints it to STDERR. The core has no `print` and no stream parameter (T1).
- **Adapters map; core re-raises (I5).** `SentenceTransformerEmbedder.embed` raises `RELATE-018`; `SqliteEmbedderStore` raises `RELATE-019` / `RELATE-037`; `SqliteLinkContext.neighbors_of` raises `RELATE-021`. The core does not catch `Exception` and does not wrap code bugs. The vector-count check lives in the embedder adapter.
- **Cache reads get `RELATE-037 EmbeddingReadFailed` (I17).** `RELATE-016 ItemsReadFailed` stays for Phase 1 `items` / `links` reads; it is no longer used for `item_embeddings`. The L2 error table gains 037.
- **CLI boot validation (I13).** `validate_embedder_config()` runs at the start of `relate`, before the DB opens. It parses the timeout and checks the optional packages without importing them or loading the model. The model itself is built after Phase 1 only when the universe is non-empty.
- **Public contracts list codes (I11 / I21).** `build_candidate_pool`, the three ports, `build_embedding_store`, `build_embedder`, and `validate_embedder_config` document their inputs, output, raised codes, and side effects.
- **Tests use public behavior (T6).** The unit tests no longer import `_cosine`; cosine behavior is exercised through `build_candidate_pool`. Cache reuse is proven with `embedded_at` and stored vector blobs, not call counters.
- **`EmbedderPort` location:** `ember/relate/embedder.py` (engine core). The spec named the adapter location but not the protocol file. Keeping it separate from `embedding_store.py` preserves B1 (one module, one purpose).
- **Pre-flight "any row" read:** `EmbeddingStorePort` gains `first_model_name() -> str | None`. `model_name_of(item_id)` cannot read an arbitrary first row. This is the only added method on the port.
- **Real model dimension:** `bge-base-en-v1.5` returns 768 floats; the L2 text says 384 (that is `bge-small`). The engine is dimension-agnostic: `_cosine` rejects unequal lengths with `RELATE-022`. Tests use the 384-dim fake from the plan.
- **Model id mapping:** `SentenceTransformerEmbedder` maps a short `bge-*` name to its Hugging Face org id (`BAAI/...`) for loading, while `model_name()` returns the configured short name so the cache key stays stable.
- **`upsert` replaces an existing row unconditionally.** The L2 text says "replace if `model_name` matches"; replacing a stale vector is safer than leaving a wrong-dimension row behind.
- **Cosine clamp:** `_cosine` clamps tiny float overshoot to `[-1.0, 1.0]`; the plan's test target asserts that range through the public function.
- **Wipe ownership:** the wipe runs in engine core (`candidate_pool.py`) through `EmbeddingStorePort.wipe()`, not in the embedder adapter as L2 §3.2/§4.6 word it. This keeps the "do we recompute" decision behind the port (B4).
- **Warning text:** the full line "embedding model changed: wiping cache (this is a one-time minutes-long cost on large DBs)" is the §4 step 1 text. L2 §6 only shows the shorter prefix; the §4 text is authoritative for Step 2.
- **Pre-flight ordering:** pre-flight runs before the empty-universe early return, as §4 orders it. An empty-universe run with an old-model cache returns the warning (the CLI short-circuits empty universes before calling the function, so the CLI does not wipe). Per-item model checks still re-encode any stale row on the next non-empty run.
- **`first_model_name()` order:** the adapter uses `ORDER BY item_id LIMIT 1` so the pre-flight choice is deterministic. A mixed-model cache is still possible in theory; the per-item `model_name_of` check in the content loop re-encodes any straggler.
- **Counts semantics:** `Pool.counts["dense"]` is the size after the top-10 cut, matching the candidates that enter the merge. `graph` and `metadata` are raw signal sizes. All three are pre-merge.
- **`RankedCandidate.item` type:** `NewItem` (per this step's §3), not the L2 §5.5 `Item` name; Step 1 renamed the row model.
- **Integration tests landed:** `tests/relate/test_candidate_pool_integration.py` covers the three §6 real-DB targets (seeded ranking + counts, pre-warmed second run with unchanged `embedded_at` and blobs, pre-flight wipe + re-encode) plus a real `RELATE-021` path.

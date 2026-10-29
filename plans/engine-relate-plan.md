# L2 Relate Engine Master Plan

Terse caveman style. Source: L1 (`plans/master-plan.md`) + V1 spec 3.3 + 3.4. No invention.

**Stack:** see L1 §0. Relate-specific deviation: none. Relate does not call the LLM adapter directly; uses the same OpenAI-SDK-→-OpenRouter pattern as Capture for `LinkProposerPort`. Relate adds the `sentence-transformers` dependency to `pyproject.toml` (Engine B owns the embedder; Capture does not import it).

## 1. Engine Job

Given one new item id, find candidate typed links to other items. User confirms or rejects each. Confirmed or rejected links go to DB. Rejected links persist (negative memory — never asked again).

## 2. Engine-Specific Deferrals from L1 (Resolved at L2 Start)

L1 §9 deferred 3 items to "Engine B L2 planning start". Decisions made here:

- **Embedder model:** keep `bge-base-en-v1.5` (384d) per L1 §0 + V1 spec 3.4. Reevaluate after V1 spec 3.9 #3 candidate-recall scale test (deferred to GitHub issue #12, labeled `deferred`).
- **Embedding table name:** `item_embeddings`. See §3 schema.
- **Metadata table name:** not needed in V1. The 3 signals (dense, graph, metadata) are flat phases that produce a single candidate list; no wrapper table required. L1 §9 deferred the `Signals` object wrapper until signal count grows beyond 3 — V1 has exactly 3, so no wrapper. Re-open trigger: if a 4th signal is added in a future V1.x, introduce a `Signals` wrapper class.

## 3. New Tables (Migrations 006 + 007 + 008 + 009)

Migrations must run in numerical order. Migration 008 depends on 006 (`links(id)` must exist before `change_log.link_id` can reference it). Migration 009 depends on 002 (`items(id)` for the new `item_id` FK) and 005 (`ai_responses` table itself). `_apply_migrations` orders scripts numerically and applies each script plus its `schema_version` bump in one transaction. Relate adds 006/007/008/009 to the migrations directory; the 008/009 scripts carry no transaction control of their own because the runner owns it.

**Schema version:** the source-of-truth schema version is the `schema_version` **table** (row `version`), read by `_apply_migrations` in `ember/adapters/sqlite.py`. Migrations 006-009 must run before any Relate operation; after 009 the stored version is 9. `RELATE-014 SchemaOutdated` is raised by Phase 1 when `SELECT version FROM schema_version` < 9. `PRAGMA user_version` is not used. Capture's `_apply_migrations` is responsible for applying the scripts and bumping the row; Relate only reads it.

### 3.1 `links` table (migration `006_create_links.sql`)

Typed directional edges. Status values `Confirmed` or `Rejected` (both stored permanently; rejection is negative memory).

Columns:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `source_item_id INTEGER NOT NULL REFERENCES items(id)`
- `target_item_id INTEGER NOT NULL REFERENCES items(id)`
- `link_type TEXT NOT NULL CHECK (link_type IN ('supports', 'contradicts', 'depends_on', 'supersedes', 'answers'))`
- `status TEXT NOT NULL CHECK (status IN ('Confirmed', 'Rejected'))`
- `created_at TEXT NOT NULL`
- `UNIQUE (source_item_id, target_item_id, link_type)` — no duplicate links
- `CHECK (source_item_id != target_item_id)` — no self-links

No `updated_at` column: links are immutable (V1 spec 3.3). Reversal of `supersedes` is an **item-status** event owned by Engine C; it writes **no `links` row** and does not change `links.status`. It is recorded as a `change_log` row with `field_changed='link_reversed'`. See `plans/engine-maintain-plan.md` §2 Gap C.

### 3.2 `item_embeddings` table (migration `007_create_item_embeddings.sql`)

Cached dense vectors for items. Computed once per item, reused on every Relate run.

Columns:
- `item_id INTEGER PRIMARY KEY REFERENCES items(id)`
- `vector BLOB NOT NULL` — packed float32 array, little-endian, length = model_dim * 4 bytes. L3 should add `CHECK (length(vector) = model_dim * 4)` once the embedder dim is fixed; for now a runtime assertion in the adapter catches size mismatches.
- `model_name TEXT NOT NULL` — embedder model identifier (e.g. `bge-base-en-v1.5`)
- `embedded_at TEXT NOT NULL`

Why `model_name` stored: V1 spec 3.9 #3 may force a model swap. If the new model is different dim, the cached vectors have wrong shape and silently corrupt cosine math. Pre-flight at Phase 2 start: if any `item_embeddings.model_name` row ≠ the active model name (from `EMBER_EMBEDDER_MODEL` env), the embedder adapter wipes `item_embeddings` (transactional) before Phase 2 starts. This is the L2 decision for the cache-invalidation rule (was in §9 #1; promoted to L2 here). First run after a model swap: cache is wiped; Phase 2 then re-encodes all of `candidate_universe` plus the new item. On a 5000-item DB this is a one-time minutes-long cost. After that, only deltas need encoding.

### 3.3 `change_log.link_id` FK (migration `008_add_change_log_link_fk.sql`)

Closes the deferred GitHub issue: add `REFERENCES links(id)` to `change_log.link_id`. SQLite needs a table rebuild for this — write as a numbered migration, not an edit to 003.

Standard SQLite rebuild recipe (must be followed exactly; L3 author pastes this into the migration file):

```sql
PRAGMA foreign_keys=OFF;
BEGIN;
ALTER TABLE change_log RENAME TO change_log_old;
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES items(id),
    link_id INTEGER REFERENCES links(id),
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    timestamp TEXT NOT NULL,
    trigger_cause TEXT NOT NULL
);
INSERT INTO change_log (id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause)
    SELECT id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause
    FROM change_log_old;
DROP TABLE change_log_old;
COMMIT;
PRAGMA foreign_keys=ON;
```

Today every `change_log.link_id` row is `NULL` (Capture never writes `link_id` non-null), so the rebuild is safe.

### 3.4 `ai_responses` extension (migration `009_drop_source_id_not_null_and_add_item_id.sql`)

Closes the Constitution D8 + I16 gap: Relate's `LinkProposerPort` calls must save the raw AI response verbatim, same as Capture does for `ItemProposerPort`. Relate's call has no source — only an item. Today's `ai_responses.source_id` is `NOT NULL REFERENCES sources(id)`, which blocks Relate from inserting with `source_id = NULL`. **Migration 009 must drop the NOT NULL on `source_id` (using the same rebuild recipe as 008) AND add the nullable `item_id` column.** A bare `ALTER TABLE ... ADD COLUMN` is not enough.

Full migration SQL (L3 author pastes verbatim):

```sql
PRAGMA foreign_keys=OFF;
BEGIN;
ALTER TABLE ai_responses RENAME TO ai_responses_old;
CREATE TABLE ai_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),  -- was NOT NULL; now nullable
    item_id INTEGER REFERENCES items(id),     -- new; nullable
    response_text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
INSERT INTO ai_responses (id, source_id, item_id, response_text, timestamp)
    SELECT id, source_id, NULL, response_text, timestamp
    FROM ai_responses_old;
DROP TABLE ai_responses_old;
COMMIT;
PRAGMA foreign_keys=ON;
```

Invariants after migration 009:
- Capture's writer sets `source_id = <source>` and `item_id = NULL`. Capture's call site is unchanged (its existing `save(*, source_id, raw_response)` still works).
- Relate's writer sets `source_id = NULL` and `item_id = <item.id>`. The `save` method must be extended to accept an optional `item_id: int | None = None` keyword arg (see §5.4).

Writer extension (L3 implements, L2 spec):

```python
class SqliteAiResponseStore:
    def save(self, *, source_id: int | None = None, item_id: int | None = None, raw_response: str) -> None:
        # exactly one of source_id, item_id must be set
        if (source_id is None) == (item_id is None):
            raise ValueError("save requires exactly one of source_id, item_id")
        self._conn.execute(
            "INSERT INTO ai_responses (source_id, item_id, response_text, timestamp) VALUES (?, ?, ?, ?)",
            (source_id, item_id, raw_response, self._utc_now()),
        )
        self._conn.commit()
```

Capture's call site `save(source_id=X, raw_response=Y)` still works (item_id defaults to None). Relate calls `save(item_id=X, raw_response=Y)`.

## 4. Pipeline (4 Phases)

```
[Human picks item id OR --item flag]
   |
   v
Phase 1: Load + filter
   |
   v
Phase 2: Build candidate pool
   |
   v
Phase 3: AI proposes link types
   |
   v
Phase 4: User confirm + validate_add_link + change_log
   |
   v
[Human picks next item or quits]
```

### Phase 1: Load new item + filter

- Input: `--item ID` flag, or `--latest` (pick the most recent `Active` item the user has not yet related).
- **`--latest` algorithm:** one query: `WHERE status='Active' AND id NOT IN (SELECT source_item_id FROM links) ORDER BY id DESC LIMIT 1`. If the result is empty, print "no unrelated items" to STDOUT and exit 0 (not an error). The `NOT IN` subquery has no status filter, so a row of any status (`Confirmed` or `Rejected`) disqualifies the item. A single rejected proposal disqualifies the item from `--latest` forever, by design: the user has already engaged with it.
- If `--item ID` is given, fail fast at the DB lookup: if the item is not in the DB, exit with `RELATE-001` and a message naming `--item ID` and the DB path (so the user knows if they pointed at the wrong DB).
- Read the item from `items`. L3 reads `id`, `type`, `statement`, and `created_at` into `NewItem`; `status` and `source_id` are not needed by Phases 2-4 and are trimmed from the model (M13).
- **Build the candidate universe** with two filters, in order:
  - **Filter #1 (batch read):** call `existing_link_types(new_item.id)` once. It returns, per target id, the set of link types already present from the new item (any status: `Confirmed` or `Rejected`). Subtract those used types in memory; for each candidate `X`, drop the `(new_item.id, X.id, T)` triple from consideration but keep `X` itself if at least one other `link_type` remains viable. (No duplicate links, no repeated suggestions for the same type. Different `link_type` for the same target is still suggested.) Step 1 makes no per-candidate `find_existing` calls; `find_existing` stays for Phase 4's gatekeeper.
  - **Filter #2:** drop items where no remaining `link_type` yields a valid `(source_type=new_item.type, target_type=X.type)` pair per the V1 spec 3.3 compatibility table. The table (inlined here so L3 does not re-read the spec):

    | source_type \ link_type | supports | contradicts | depends_on | supersedes | answers |
    |---|---|---|---|---|---|
    | Decision | — | — | Assumption, Finding, Decision | Decision | Question |
    | Assumption | — | — | Finding, Assumption | Assumption | — |
    | Finding | Assumption, Decision | Assumption, Decision, Finding | — | Finding | Question |
    | Question | — | — | — | Question | — |

    For example, a `Question` new_item can only be a `supersedes` source (target same type), reducing its universe to other `Question` items. A `Finding` cannot be a `depends_on` source but can answer `Question`. This filter is an optimization — it shrinks the candidate universe passed to Phase 2's signals. The gatekeeper (Phase 4 rule #5) is the correctness check on the AI's specific proposal. Both can coexist.
  - Closed items are kept in the candidate universe (they remain valid targets for 4 of 5 link types). The gatekeeper's check #6 below rejects `supersedes` to a Closed target. This matches V1 spec 3.3 exactly.
- Output: `LoadedCandidates(new_item: NewItem, universe: CandidateUniverse)` — the named wrapper from `ember/relate/load_filter.py` (per Constitution I4; a 2-tuple is acceptable but the named object documents the contract). `load_item_candidates` and `load_latest_candidates` are the two entry points (no boolean behavior flag; I2 compliance).

### Phase 2: Build candidate pool (3 signals, merged)

Inputs: `LoadedCandidates` (new item + filtered candidate universe). Output: `Pool(ranked, counts, warning)`. `ranked: list[RankedCandidate]` is ranked and deduplicated; `counts` holds the pre-merge signal sizes; `warning` carries the model-change text for the CLI. `RankedCandidate(item, cosine: float | None, source: enum)` is a transient Pydantic model for the merge step; not persisted. `Pool` is the named return object per Constitution I3/I4 (4 inputs, no out-parameter).

3 signals, in order:

1. **Content signal (dense vector):** embedding input is `items.statement` text only. Source `full_text` is Engine D (`topic_search`) territory, not Relate. If the new item is already in `item_embeddings` (and `model_name` matches the active model), read the cached vector — do not re-encode. Otherwise compute the embedding, INSERT into `item_embeddings`, then cosine-similarity top-10 against cached embeddings of `candidate_universe`. (For `candidate_universe` items, same rule: if cached, read; else encode + INSERT.) Result: top-10 by cosine, each carrying its cosine score.
2. **Graph signal:** walk **1-hop** (direct neighbors only) from the new item through existing `Confirmed` links. Direction: include any link where `source_item_id = new_item.id OR target_item_id = new_item.id`. Result: items reachable from the new item via 1-step graph expansion, each carrying cosine = 0.5. (L3 may pick a different BFS depth per §9 #2.)
3. **Metadata signal:** spec 3.4 lists 3 sub-signals: project area, temporal proximity, type compatibility. Type compatibility is already done in Phase 1 filter #2. Project area is V1-deferred (no `items.metadata` column per L1 §3 + §5). This signal only does **temporal proximity**: items created within ±30 days of the new item's `created_at`. ISO TEXT comparison is correct for ordering; the ±30-days subtraction needs `datetime` parsing at L3 step 2. Result: temporally close items, each carrying cosine = 0.5.

Merge: union of the 3 sets, deduplicated by `item_id`, ranked by (cosine score if present, else 0.5; tie-breaker is L3's call per §9 #4). **No cap on post-union set** (only the dense top-10 is capped, per V1 spec 3.4 line 94 "Top 10 by cosine similarity form initial candidate pool" — interpreted as the dense-signal top-10, not the final union). Note: a heavy graph expansion (hub item) could produce 100+ candidates and inflate `LinkProposerPort` cost; L3 may add a post-union cap per §9 #7.

If the union is empty: `Pool.ranked` is empty. The CLI prints the Phase 2 JSON with `pool_size: 0` and exits 0. No AI call.

If the union has 1+ items: pass to Phase 3.

### Phase 3: AI proposes link types via `LinkProposerPort`

- **Port name:** `LinkProposerPort` (per L1 §2). Signature: `propose_links(new_item, candidates) -> LinkProposalResponse` where `LinkProposalResponse(raw_response: str, proposals: list[LinkProposal])`. Mirrors Capture's `ProposalResponse` shape so Phase 3.5 has access to the raw response.
- **Adapter:** extend `ember/adapters/llm.py` (L2 picks: same file as Capture, no new module). Default model: `anthropic/claude-haiku-5.5` (same as Capture; cost). Override at runtime via `EMBER_AI_MODEL` env.
- **System prompt instructs AI:** "For each candidate, pick the most fitting link type from {supports, contradicts, depends_on, supersedes, answers}, or drop the candidate if no type fits. Never invent types. Never reverse a direction the spec forbids (e.g. `supports` from `Assumption` is rejected — use `depends_on` instead)."
- **Per-proposal shape:** `{target_item_id: int, link_type: str, rationale: str (optional)}`. `link_type` must be in the closed set; gatekeeper validates.
- **Retry policy:** 1 retry on transient AI error (network, auth, rate limit, timeout — lumped per Capture convention), 0s backoff. Same as Capture.
- **Phase 3.5: save raw AI response (Constitution D8 + I16).** After `LinkProposerPort.propose_links` returns successfully and **before** the engine-core returns to Phase 4, the engine-core calls `AiResponseStorePort.save(item_id=new_item.id, raw_response=raw_response)` (see §4.5 for the new port). The CLI wires `SqliteAiResponseStore` as the adapter implementation. Phase 3.5 lives in the engine core because the raw-response-save is an invariant; the adapter just performs the SQL. If the save raises (disk full, FK violation), the engine core catches it and re-raises as `RELATE-036 AiResponseWriteFailed` (per §6). The `ValueError` from the `save` defensive check (both/neither of `source_id`/`item_id` set) propagates and is mapped to `RELATE-030 SchemaValidationFailed`. Mirrors Capture's CLI-edge save pattern (see `ember/cli.py:215-221`); Relate puts the call in engine core to keep the wiring close to the data.
- If `LinkProposerPort` returns `proposals=[]`: exit 0 with summary `accepted: 0, rejected: 0, skipped: 0, aborted: false`. (Empty proposals is not an error.)
- Output: `LinkProposalResponse(raw_response, proposals)`.

### Phase 4: User confirm + write

Engine-core split: **`validate_add_link` is pure (no I/O); `SqliteLinkStore` is the edge adapter that does the writes.** The architecture test forbids `sqlite3` in `ember.relate.*`, so the gatekeeper must not import it. Core = `ember/relate/link_gatekeeper.py` (pure) + `ember/relate/link_proposal.py` (Phase 3.5 wrapper) + `ember/relate/confirm_write.py` (the user loop). Edge = `ember/adapters/sqlite.py` (new `SqliteLinkStore` + `SqliteLinkContext` classes — see §5.4 for the split).

**Wiring:** the CLI builds `lookup = SqliteLinkContext(conn)` and `store = SqliteLinkStore(conn)` once at Relate invocation (not per proposal). The orchestrator (`run_confirm_loop`) takes `lookup` and `store` as 2 separate args (per M8; the `LinkRun` bundle was dropped from §5.5). The orchestrator calls `validate_add_link(draft, lookup)` (pure, no I/O) for each proposal; if the gatekeeper returns `ValidatedLink`, the orchestrator calls `store.insert_link_with_log(link_row, change_log_row)` to commit. The gatekeeper never sees the store.

Loop over `LinkProposal`s.

- For each: print the new item's statement + the candidate's statement + the proposed link type + rationale. Prompt `[y]es / [n]o / [s]kip / [q]uit`. Garbage input re-prompts silently (no code raised; `RELATE-034` removed in v3).
- **Edge case: `contradicts` direction.** Spec 3.3 line 67: source must be `Finding`, target ∈ {Assumption, Decision, Finding}. Only Finding↔Finding pairs are orientation-ambiguous. For those, the CLI shows the proposed orientation and lets the user flip. For Finding→non-Finding pairs, the direction is fixed (Finding as source) — do not offer a flip. L1 §2 line 50's "Link direction chosen by user at accept time" is interpreted as the Finding↔Finding flip only, because spec 3.3 line 67 constrains the source side to `Finding` — non-Finding sources are invalid regardless of user preference. (L1's wording is loose; L2 narrows to the spec-strict reading.)
- For each `y`:
  1. Call `validate_add_link(draft, run)` (pure, returns `ValidatedLink | RejectedLink`).
  2. If `RejectedLink`: print the reason, increment the rejected counter, continue to next proposal. Do not prompt again.
  3. If `ValidatedLink`: in one SQLite transaction (single `conn.execute('BEGIN')` before the link INSERT, single `conn.commit()` after the change_log INSERT), call `SqliteLinkStore.insert_link_with_log(link_row, change_log_row)`. This single method does both INSERTs and one COMMIT atomically. Order inside the method: INSERT the `Confirmed` link row FIRST, capture `cursor.lastrowid`, then INSERT the `change_log` row with `link_id = lastrowid`. (Order matters: `change_log.link_id` has the FK to `links(id)` after migration 008, so the link row must exist before the change_log row references it.) If the link INSERT fails, raise `RELATE-029 LinkWriteFailed`. If the change_log INSERT fails, the transaction rolls back the link INSERT; raise `RELATE-011 ChangeLogWriteFailed`. **This is a new pattern for Relate** (Capture uses per-method autocommit at `ember/adapters/sqlite.py:240`); the L2 plan explicitly requires atomicity here.
  4. Print one-line summary.
  5. `change_log` row template (link_confirmed):
     - `item_id = new_item.id`
     - `link_id = <new link id>`
     - `field_changed = 'link_confirmed'`
     - `old_value = NULL`
     - `new_value = '<link_type>:<target_item_id>'` (e.g. `supports:42`; gives the auditor both type and target without parsing JSON)
     - `timestamp = <clock>`
     - `trigger_cause = 'user_confirmed'` (matches Capture's accept-path vocabulary)
- For each `n`: in one transaction (via `SqliteLinkStore.insert_link_with_log`), INSERT a `Rejected` link row + a `change_log` row.
  - `Rejected` link row: same shape as Confirmed, with `status = 'Rejected'`.
  - `change_log` row template (link_rejected):
    - `item_id = new_item.id` (the source item still exists; mirroring link_confirmed's pattern for consistency)
    - `link_id = <new rejected link id>`
    - `field_changed = 'link_rejected'`
    - `old_value = NULL`
    - `new_value = '<link_type>:<target_item_id>'`
    - `timestamp = <clock>`
    - `trigger_cause = 'rejected'` (matches Capture's reject-path vocabulary; `rejection_persisted` was inconsistent)
- For each `s`: leave the candidate without a link row. Print "skipped". (Re-running Relate on the same item may re-suggest it. Skipped ≠ rejected; rejected persists as negative memory, skipped does not.)
- For `q` or EOF (Ctrl-D): exit loop, exit code 2, raise `UserAbort` (RELATE-031), `aborted=true` in summary. Mirrors Capture's `UserAbort` (CAPTURE-014) — same name, no `Relate` prefix. Pending proposals on `q` are neither confirmed nor rejected nor skipped — they are simply ignored. Relate's negative-memory rule (spec 3.3 line 85) applies only to explicit `n`.
- **Gatekeeper `validate_add_link` checks** (9 rules; pure function, no DB I/O; takes injected `LinkLookupPort` for existence/uniqueness/cycle checks; each rule raises a specific `RelateError` subclass with the code from §6):
  1. `source_item_id` exists in `items` (via `LinkLookupPort.item_exists(id) -> bool`) — raises `RELATE-026 SourceItemNotFound`.
  2. `target_item_id` exists in `items` (via `LinkLookupPort.item_exists`) — raises `RELATE-027 TargetItemNotFound`.
  3. `source_item_id != target_item_id` — raises `RELATE-010 SelfLink`.
  4. `link_type` ∈ closed set of 5 — raises `RELATE-005 LinkTypeNotInClosedSet`.
  5. Pair is allowed by the V1 spec 3.3 compatibility table (table inlined in Phase 1 above) — raises `RELATE-006 SourceTargetTypeIncompatible`.
  6. `supersedes` target's status ≠ `Closed` (via `LinkLookupPort.item_status(id) -> str`) — raises `RELATE-007 SupersedesTargetClosed`.
  7. Premise rule: if `source.type == 'Assumption'` and `link_type == 'supports'`, reject (use `depends_on`) — raises `RELATE-008 PremiseRuleViolated`. Note: `Decision → supports` is **forbidden** per V1 spec 3.3 line 66 (supports source must be `Finding`); already blocked by rule 5 (compat table) before rule 7 runs.
  8. **Supersedes cycle:** reject when the source's `supersedes` ancestors include the target (or vice versa). Compute via BFS through existing `Confirmed` `supersedes` links via `LinkLookupPort.supersedes_ancestors(id) -> set[int]`; reject if source in target's ancestors OR target in source's ancestors. Raises `RELATE-028 SupersedesCycle`. Mandated by V1 spec 3.3 line 71 ("Loops forbidden").
  9. No existing `Confirmed` or `Rejected` link of the same `(source, target, link_type)` (uniqueness, via `LinkLookupPort.find_existing(source, target, link_type) -> Link | None`) — raises `RELATE-009 DuplicateLink`.
- Output: `ConfirmResult(accepted: list[link_id], rejected: int, skipped: int, aborted: bool)`.

### 4.5 New Ports to Implement

- `LinkProposerPort` — defined above (Phase 3). Adapter: `OpenAiLinkProposer` in `ember/adapters/llm.py`.
- `EmbedderPort` — `embed(texts: list[str]) -> list[list[float]]` + `dim() -> int` + `model_name() -> str`. Adapter: `SentenceTransformerEmbedder` in `ember/adapters/embedder.py`.
- **`LinkLookupPort`** — used by Phase 1 (load/filter), Phase 2 (graph), and Phase 4 (gatekeeper). Engine core must not import `sqlite3`.
  - `item_exists(item_id: int) -> bool` — Phase 1/4.
  - `item_status(item_id: int) -> str | None` — Phase 4 (supersedes-Closed rule). Returns `'Active'`, `'Challenged'`, `'Closed'`, or `None` if missing.
  - `item_type(item_id: int) -> str | None` — Phase 1/4. Returns `'Decision'`, `'Assumption'`, `'Finding'`, `'Question'`, or `None`.
  - `item_statement(item_id: int) -> str | None` — Phase 1/4.
  - `item_created_at(item_id: int) -> str | None` — Phase 1 (the metadata signal needs the timestamp). Returns ISO TEXT or `None`.
  - `list_other_items(new_item_id: int) -> list[NewItem]` — Phase 1. Returns every item except `new_item_id`, ordered by id.
  - `find_latest_unlinked_active() -> NewItem | None` — Phase 1 (`--latest`). Newest `Active` item with no outgoing link (any status).
  - `find_existing(source_id: int, target_id: int, link_type: str) -> Link | None` — Phase 1/4. Returns the existing link row if any (any status: `Confirmed` or `Rejected`).
  - `existing_link_types(source_item_id: int) -> dict[int, set[str]]` — Phase 1. One read of every outgoing link type (any status), keyed by target id. Replaces the per-candidate `find_existing` loop in Phase 1; `find_existing` stays for Phase 4's gatekeeper.
  - `supersedes_ancestors(item_id: int) -> set[int]` — Phase 4. BFS through `Confirmed` `supersedes` links, returns the set of all items reachable upstream.
  - `neighbors_of(item_id: int) -> list[int]` — Phase 2. 1-hop neighbors via `Confirmed` links (either side).
  - Adapter: `SqliteLinkContext` in `ember/adapters/sqlite.py`. Protocol defined in `ember/relate/link_lookup.py` (engine core; can be co-located with `link_gatekeeper.py`). Step 1 implements the 8 Phase 1 methods; `neighbors_of` lands with Step 2 and `item_status` / `supersedes_ancestors` with Step 3.
- **`LinkStorePort`** — used by Phase 4 for the atomic link+log write:
  - `insert_link_with_log(link_row: Link, change_log_row: ChangeLogEntry) -> int` — one transaction, returns the new `link.id`. Raises `RELATE-029` on link-insert failure, `RELATE-011` on change_log-insert failure.
  - Adapter: `SqliteLinkStore` in `ember/adapters/sqlite.py`. Protocol in `ember/relate/link_store.py`.
- **`AiResponseStorePort`** — used by Phase 3.5 to save the raw AI response (Constitution D8 + I16). Engine core never imports the adapter directly.
  - `save(item_id: int, raw_response: str) -> None` — persists the raw response. Adapter enforces "exactly one of `source_id`/`item_id`" internally.
  - Adapter: `SqliteAiResponseStore` in `ember/adapters/sqlite.py` (extended per §3.4). Protocol in `ember/relate/ai_response_store.py`.
- **`EmbeddingStorePort`** — used by Phase 2 to read/write the `item_embeddings` cache. Separated from `LinkLookupPort` (which is read-only for gatekeeper queries) to avoid the read-port-does-writes smell.
  - `get(item_id: int) -> list[float] | None` — returns the cached vector or `None`. Read failure → `RELATE-037`.
  - `upsert(item_id: int, vector: list[float], model_name: str) -> None` — insert or replace the row. Write failure → `RELATE-019`.
  - `model_name_of(item_id: int) -> str | None` — returns the cached model name. Read failure → `RELATE-037`.
  - `first_model_name() -> str | None` — returns the model name from any one cached row (deterministic `ORDER BY item_id LIMIT 1`), or `None`. Read failure → `RELATE-037`.
  - `wipe() -> None` — empties the table (used when `model_name` mismatch detected). Write failure → `RELATE-019`.
  - Adapter: `SqliteEmbedderStore` in `ember/adapters/sqlite.py`. Protocol in `ember/relate/embedding_store.py`.

### 4.6 Phase 2 Signal Error Sources (which module raises which code)

- `RELATE-017 EmbedderLoadFailed` — raised by `validate_embedder_config` at CLI boot when `sentence_transformers` / `torch` is missing, or by `SentenceTransformerEmbedder` when the model cannot load. The engine core re-raises it unchanged (no wrapping).
- `RELATE-018 EmbedderEncodeFailed` — raised by `SentenceTransformerEmbedder.embed` (adapter) for an encode failure or a wrong vector count. The engine core re-raises it unchanged.
- `RELATE-019 EmbeddingWriteFailed` — raised by `SqliteEmbedderStore.upsert` / `wipe` (adapter). The engine core re-raises it unchanged.
- `RELATE-020 EmbeddingModelMismatch` — **not raised**; the pre-flight check wipes the cache and returns the warning in `Pool.warning` (`embedding model changed: wiping cache`). The CLI prints it to STDERR. Removed from the error table in v3.
- `RELATE-021 GraphReadFailed` — raised by `SqliteLinkContext.neighbors_of` (adapter). The engine core re-raises it unchanged.
- `RELATE-022 CosineComputeFailed` — raised by the cosine-math helper in `ember/relate/candidate_pool.py` (engine core) on a zero-vector (denominator = 0) or unequal-length vectors. NaN/Inf branches are dropped per M6. Cosine math uses **stdlib `math` only** — `numpy` is forbidden in engine core (architecture test §7.3).
- `RELATE-023 MetadataReadFailed` — raised by the temporal-window helper (engine core) on a malformed or mixed-zone `datetime` parse.
- `RELATE-037 EmbeddingReadFailed` — raised by `SqliteEmbedderStore.get` / `model_name_of` / `first_model_name` (adapter) on a cache read failure. The engine core re-raises it unchanged. `RELATE-016` stays for Phase 1 `items` / `links` reads.

## 5. CLI + Configuration

### 5.1 CLI

```
ember relate --item <id> [--db <path>]
ember relate --latest          # pick newest Active item the user has not yet related
```

`--item` and `--latest` are mutually exclusive; one is required. `--db` defaults to `ember.db` (Relate CLI imports `DEFAULT_DB_PATH` from `ember.cli` to avoid string-literal drift). `--item ID` accepts any status; status filtering is `--latest`-only.

Output: a YAML block per accepted link (mirrors Capture's per-candidate confirm output at `ember/capture/confirm_write.py:96-106` via `format_block`; same data shape, same YAML emitter). Capture's `capture-source` is JSON, but the confirm path is YAML — Relate follows the confirm path. One-line summary `accepted: N, rejected: N, skipped: N, aborted: true|false`. Exit codes: 0 success, 1 phase error, 2 user abort.

### 5.2 Environment Variables (Constitution I13: load once, fail fast)

Loaded once at CLI startup via factory functions:

- `EMBER_AI_MODEL` — LLM model name. Default: `anthropic/claude-haiku-5.5` (matches Capture).
- `EMBER_AI_API_KEY` / `OPENROUTER_API_KEY` — LLM auth. `EMBER_AI_API_KEY` is the canonical L1 §0 var; `OPENROUTER_API_KEY` is accepted as a fallback because the LLM base URL defaults to OpenRouter (see §5.2 note). Required, else `RELATE-035 ConfigMissing` at boot.
- `EMBER_AI_BASE_URL` — LLM base URL. Default: `https://openrouter.ai/api/v1`.
- `EMBER_EMBEDDER_MODEL` — embedder model name. Default: `bge-base-en-v1.5`.
- `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS` — model load timeout. Default: 120. Enforced by the embedder adapter.

At the start of `ember relate`, `validate_embedder_config()` parses the timeout and checks that `sentence_transformers` and `torch` are installed via `importlib.util.find_spec`. It imports nothing and loads no model. A missing package raises `RELATE-017` and a bad timeout raises `RELATE-035` before the DB is opened (I13).

### 5.3 Factories

- `build_link_proposer(env=None) -> LinkProposerPort` — same pattern as `build_item_proposer` in Capture.
- `build_embedder(env=None) -> EmbedderPort` — reads `EMBER_EMBEDDER_MODEL` + `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS`, instantiates the embedder adapter.
- `validate_embedder_config(env=None) -> float` — boot check; parses the timeout, checks the two optional packages, returns the timeout. Raises `RELATE-035` / `RELATE-017`; no model load.
- **`build_link_lookup(conn) -> LinkLookupPort`** — wraps a `SqliteLinkContext(conn)` for injection into `validate_add_link`. Built once per Relate invocation (not per proposal).
- **`build_link_store(conn) -> LinkStorePort`** — wraps a `SqliteLinkStore(conn)` for the Phase 4 atomic write.
- **`build_ai_response_store(conn) -> AiResponseStorePort`** — wraps `SqliteAiResponseStore(conn)` for Phase 3.5.
- **`build_embedding_store(conn) -> EmbeddingStorePort`** — wraps `SqliteEmbedderStore(conn)` for Phase 2.

### 5.4 Adapter Locations

- `ember/adapters/llm.py` — extended with `OpenAiLinkProposer` (L2 pick: same file as Capture, no new module). Returns `LinkProposalResponse(raw_response, proposals)`.
- `ember/adapters/embedder.py` — new file. `SentenceTransformerEmbedder(model_name, load_timeout)` implements `EmbedderPort`; `build_embedder` and `validate_embedder_config` are the env-driven factories. This is where `sentence-transformers` is imported; engine core never sees it.
- `ember/adapters/sqlite.py` — extended with:
  - `SqliteLinkContext(conn)` — implements `LinkLookupPort`. Step 1 ships 8 Phase 1 methods (`item_exists`, `item_type`, `item_statement`, `item_created_at`, `find_existing`, `existing_link_types`, `list_other_items`, `find_latest_unlinked_active`); `neighbors_of` lands with Step 2 and `item_status` + `supersedes_ancestors` with Step 3. After Step 3 lands, the full 11-method protocol is in place.
  - `SqliteLinkStore(conn)` — implements `LinkStorePort` (1 write method: `insert_link_with_log(link_row, change_log_row) -> int` — single `BEGIN` / `INSERT link` / capture `lastrowid` / `INSERT change_log` / `COMMIT`, atomic).
  - `SqliteEmbedderStore(conn)` — implements `EmbeddingStorePort` (5 methods: `get`, `upsert`, `model_name_of`, `first_model_name`, `wipe`). Reads raise `RELATE-037`; writes raise `RELATE-019`.
  - `SqliteAiResponseStore.save` is extended per §3.4 to accept optional `item_id`. L3 must widen `source_id` from `int` to `int | None` in the type hint. The INSERT body SQL is also widened from `(source_id, response_text, timestamp)` to `(source_id, item_id, response_text, timestamp)`. The `save` call from Phase 3.5 goes through `build_ai_response_store` (engine core never imports the adapter directly).

### 5.5 Data Models (Pydantic per L1 §0 + Constitution I9 + D4)

Pydantic models. **Location:** defined in `ember/relate/` (engine core, since they are type contracts, not I/O). The adapter instantiates them from the raw AI response; the gatekeeper validates them again at the edge. Pydantic is OK in engine core (I9/D4 mandate validating at the edge; Pydantic models in core are the type contract, only instantiating from untrusted data is the edge act). Mirrors Capture's pattern (`ContextItem`, `ItemProposal`, `ProposalBatch` in `ember/capture/`).

Models:
- `LinkProposal(target_item_id: int, link_type: str, rationale: str | None)` — Phase 3 AI output shape.
- `LinkProposalResponse(raw_response: str, proposals: list[LinkProposal])` — Phase 3 port return shape.
- `LinkDraft(source_item_id: int, target_item_id: int, link_type: str, rationale: str | None)` — Phase 4 gatekeeper input.
- `ValidatedLink(link_row: Link, change_log_row: ChangeLogEntry)` — gatekeeper success.
- `RejectedLink(code: str)` — gatekeeper failure (e.g. premise rule). The CLI maps the `code` (RELATE-NNN string) to user-facing prose at print time; the engine core does not carry a `reason` field.
- `ConfirmResult(accepted: list[link_id: int], rejected: int, skipped: int, aborted: bool)` — Phase 4 output.
- `Pool(ranked: list[RankedCandidate], counts: dict[str, int], warning: str | None)` — Phase 2 return object; the CLI prints `warning` and the counts.
- `RankedCandidate(item: NewItem, cosine: float | None, source: SignalKind)` — transient Pydantic model for Phase 2 merge. `SignalKind` is a Pydantic `Enum` with values `dense`, `graph`, `metadata`.
- ~~`LinkRun(lookup: LinkLookupPort, store: LinkStorePort)`~~ — **dropped.** The orchestrator takes `lookup` and `store` as 2 separate args (a bundle was over-engineered per M8; the read/write asymmetry is clearer with explicit names). Per Step 3 v3 §10 amendment log.
- `RelatePorts(link_lookup, link_store, link_proposer, ai_response_store)` and `RelateRequest(new_item, ranked, env)` — Step 3 input objects, so `run_relate(ports, request)` has 2 inputs (Constitution I3). This is not the `LinkRun` read/write pair; that stays dropped.

`Item`, `Link`, `ChangeLogEntry` are Pydantic models representing DB rows. Defined in `ember/relate/rows.py` (engine core) so the gatekeeper and adapter share a single source of truth.

## 6. Errors (Stable Codes)

All errors inherit from `ember.relate.errors.RelateError(EmberError)` (Constitution I6: one base error per project). Each subclass has `code: str` and `name: str` class attributes (I17). All raise → exit 1 except `RELATE-031` (UserAbort) → exit 2.

Codes in `ember/relate/errors.py` (31 codes total: 001 + 005-014 + 016-019 + 021-033 + 035-037. Gaps 002/003/004 + removed 015/020/034 = 6 slots, 31 raised):

| Code | Name | Phase | Trigger | Exit |
|---|---|---|---|---|
| `RELATE-001` | `ItemIdNotFound` | 1 | `--item ID` not in this DB. | 1 |
| `RELATE-005` | `LinkTypeNotInClosedSet` | 3, 4 | AI proposed or user picked a `link_type` not in the 5. | 1 |
| `RELATE-006` | `SourceTargetTypeIncompatible` | 4 | `(source_type, target_type, link_type)` violates V1 spec 3.3 table. | 1 |
| `RELATE-007` | `SupersedesTargetClosed` | 4 | `supersedes` target's status is `Closed`. | 1 |
| `RELATE-008` | `PremiseRuleViolated` | 4 | `source.type == 'Assumption'` and `link_type == 'supports'`. | 1 |
| `RELATE-009` | `DuplicateLink` | 4 | Existing `Confirmed` or `Rejected` link of same `(source, target, link_type)`. | 1 |
| `RELATE-010` | `SelfLink` | 4 | `source_item_id == target_item_id`. | 1 |
| `RELATE-011` | `ChangeLogWriteFailed` | 4 | `change_log` row insert failed (after link row insert succeeded). | 1 |
| `RELATE-012` | `DbOpenFailed` | 1 | DB file missing, corrupt, permission denied, or otherwise unopenable. | 1 |
| `RELATE-013` | `DbMigrationFailed` | 1 | Migration 006/007/008/009 crashed during apply. | 1 |
| `RELATE-014` | `SchemaOutdated` | 1 | `schema_version` version < 9 (migrations 006-009 not applied). Migration 010 makes the DB version 10; Relate's floor stays 9. | 1 |
| `RELATE-016` | `ItemsReadFailed` | 1 | Phase 1 read failed (items or links table: disk mid-read, lock). | 1 |
| `RELATE-017` | `EmbedderLoadFailed` | 2 | Optional package missing at CLI boot, or the model load timed out / network / DNS failed. | 1 |
| `RELATE-018` | `EmbedderEncodeFailed` | 2 | `EmbedderPort.embed(texts)` raised or returned the wrong vector count. | 1 |
| `RELATE-019` | `EmbeddingWriteFailed` | 2 | `item_embeddings` insert, replace, or wipe failed. | 1 |
| `RELATE-021` | `GraphReadFailed` | 2 | Graph signal DB read failed. | 1 |
| `RELATE-022` | `CosineComputeFailed` | 2 | Zero vector (denominator = 0) or unequal-length vectors in cosine math. | 1 |
| `RELATE-023` | `MetadataReadFailed` | 2 | Metadata `datetime` parse failed in the core temporal-window helper. | 1 |
| `RELATE-024` | `TargetNotInCandidates` | 3 | AI returned `target_item_id` that was not in the `candidates` list. | 1 |
| `RELATE-025` | `ProposalSourceMismatch` | 3 | AI returned a proposal whose `source_item_id` ≠ the new item id. | 1 |
| `RELATE-026` | `SourceItemNotFound` | 4 | Gatekeeper pre-check: `source_item_id` not in `items`. | 1 |
| `RELATE-027` | `TargetItemNotFound` | 4 | Gatekeeper pre-check: `target_item_id` not in `items`. | 1 |
| `RELATE-028` | `SupersedesCycle` | 4 | Cycle detected in `supersedes` ancestors (V1 spec 3.3 line 71). | 1 |
| `RELATE-029` | `LinkWriteFailed` | 4 | `links` row insert failed (FK violation, constraint fail, disk full). Distinct from `RELATE-011` (change_log) per Capture convention. | 1 |
| `RELATE-030` | `SchemaValidationFailed` | cross | Pydantic validation failed (bad data shape from any source). | 1 |
| `RELATE-031` | `UserAbort` | 4 | `q` pressed or EOF (Ctrl-D) on a confirm prompt. Mirrors `CAPTURE-014`. | 2 |
| `RELATE-032` | `AiCallFailed` | 3 | LLM call failed after retry (network, auth, rate limit, timeout — lumped per Capture convention). | 1 |
| `RELATE-033` | `AiResponseSchemaInvalid` | 3 | LLM response not JSON, or JSON not a list, or list missing `target_item_id` key per proposal shape. | 1 |
| `RELATE-035` | `ConfigMissing` | boot | Required env var missing (e.g. no API key). Per Constitution I13. | 1 |
| `RELATE-036` | `AiResponseWriteFailed` | 3 | Phase 3.5 raw-AI-response save to `ai_responses` failed (disk full, FK violation). | 1 |
| `RELATE-037` | `EmbeddingReadFailed` | 2 | `item_embeddings` read failed (disk mid-read, lock, corrupt vector blob). `RELATE-016` stays for Phase 1 `items` / `links` reads. | 1 |

Removed codes (v3 cleanup; were "soft" / "reserved" / unused per I17):
- `RELATE-002` (was: "candidate universe empty"; v2 plan removed from the table; here for traceability).
- `RELATE-015` (was: "no unrelated active item" — soft exit 0; not raised; would be dead code).
- `RELATE-020` (was: "embedding model mismatch" — pre-flight wipes cache; not raised; would be dead code. Replaced with the warning returned in `Pool.warning`: `embedding model changed: wiping cache`; the CLI prints it to STDERR).
- `RELATE-034` (was: "invalid confirm input" — current behavior is silent re-prompt; reserved = dead code per I17).

**RELATE-014 is defensive:** `open_relate_database` applies migrations before it checks the version, so a normal run reaches version 9 first. The code fires only when migrations are skipped or the schema is otherwise stale. Step 1 tests the mapping directly and through a simulated old DB.

Empty candidate universe and empty `LinkProposerPort` return are soft exits 0 — no code, no row.

## 7. Test Targets

Test pyramid per L1 §7 + Constitution T1-T4 + T7 + T9.

### 7.1 Unit (pure core, no DB)

- **Phase 1 (load + filter):** candidate universe construction; inlined compat table filter; "not yet related" check; `--item ID` fail-fast path.
- **Phase 2 (candidate pool):** rank-by-cosine-or-0.5 merge; union dedup; empty union returns `Pool(ranked=[])` (no raise); embedding input = `items.statement` only; new-item embedding upsert; cosine behavior exercised through `build_candidate_pool` (no private `_cosine` tests); cache reuse asserted with `embedded_at`/stored vectors, not call counters.
- **Phase 3 (AI propose):** `LinkProposerPort` parser (bad types, empty list, Markdown fences same as Capture); retry on `AiCallFailed` (1 retry, 0s backoff, raises after 2nd failure); raw response save shape (returns `LinkProposalResponse(raw_response, proposals)`).
- **Phase 4 (confirm + write):** `y`/`n`/`s`/`q` paths; garbage input re-prompts silently; `contradicts` orientation flip (Finding↔Finding only; Finding→non-Finding fixed); EOF raises `UserAbort`; pending proposals on `q` are ignored.
- **Gatekeeper (9 rules):** every check from §4 Phase 4 — items exist, no self, link_type in closed set, compat table, supersedes-Closed, premise rule, supersedes cycle, uniqueness. Each check tested in isolation. The `validate_add_link` rejection branch prints the reason and increments the rejected counter (no re-prompt).
- **Error code stability:** every code in §6 that is raised (i.e. 001, 005-014, 016-019, 021-033, 035-037 — 31 codes; the removed 002/003/004/015/020/034 are untestable) has a test that asserts the raised `code` (not message prose). Per Constitution E2 + I21.

### 7.2 Integration (real temp DB, migrations 001-009 applied)

- **Happy path:** new item, 5 candidates, 3 accepted + 2 rejected → 5 link rows (3 Confirmed + 2 Rejected) + 5 `change_log` rows. Each `change_log` row uses the templates from §4 Phase 4 (link_confirmed / link_rejected). Both rows have `item_id = new_item.id`. `new_value` follows the `<link_type>:<target_item_id>` convention.
- **Re-run with same new item:** candidates with already-used `(source, target, link_type)` are dropped; different `link_type` for the same target is still suggested. (Plan v1 had this wrong — fixed.)
- **Embedding cache hit:** re-running with same item does NOT re-compute (assert `embedded_at` unchanged). Phase 3 only runs when there are candidates — if the candidate universe is empty, no `ai_responses` row is written (D8 save is gated on Phase 3 firing).
- **Embedding model swap:** pre-flight wipes cache when `item_embeddings.model_name` ≠ `EMBER_EMBEDDER_MODEL`. Assert the old rows are gone and re-encoded under the active model; `Pool.warning` carries the warning and the CLI prints it to STDERR.
- **Raw AI save:** assert `ai_responses` row exists for the new item after every Phase 3 call (Constitution D8). Both `source_id` and `item_id` nullable post-009; Capture's writer sets `source_id`, Relate's sets `item_id`.
- **Phase 4 atomic transaction:** link row inserted FIRST (lastrowid captured), then `change_log` row with `link_id = lastrowid`. Assert no FK violation. Assert both rows commit or both rollback (use a fault-injection test that raises mid-transaction and verifies zero rows).
- **Closed-item handling:** `supersedes` to a `Closed` target → RELATE-007. `depends_on` to a `Closed` target → allowed.
- **Premise rule:** Assumption + supports → RELATE-008. Decision + supports → RELATE-006 (compat table, not premise).
- **Supersedes cycle:** A→supersedes→B, B→supersedes→A → RELATE-028.
- **`--latest` with no eligible items:** all `Active` items already have a `links` row → exit 0, print "no unrelated items".
- **`--item ID` fail-fast:** non-existent id → RELATE-001 with message naming the id and DB path.

### 7.3 Architecture test (Rule T9)

- L3 Step 1 extends `tests/test_architecture.py` with a **second function** `test_relate_core_does_not_import_adapters` that imports each `ember.relate.*` module and asserts none of `forbidden_relate = ("sentence_transformers", "numpy", "sqlite3", "openai", "anthropic", "ember.adapters")` appear in its source. The existing `test_capture_core_does_not_import_adapters` function is left untouched. Both functions run in CI.
- **Timing:** the extended test ships with L3 Step 1 (the first step that creates `ember/relate/*.py` modules). Until then, the test is not added. The L2 plan §10 "Next Step" rule is reframed: the architecture test extension is part of L3 Step 1's deliverable, not a precondition.
- Test files under `tests/relate/` are exempt from the forbidden set (they may import `sentence_transformers` to fake the model). The architecture test does not iterate over test files; the exemption is a non-issue but documented for clarity.

### 7.4 CLI tests (smoke)

- `ember relate --item 1 --db tmp.db` exits 0 on a fixture DB with an eligible item.
- `ember relate --latest` exits 0 on a fixture DB.
- `ember relate --item 9999 --db tmp.db` exits 1, code RELATE-001.
- `q` mid-prompt exits 2, summary `aborted: true`.

### 7.5 Retry behavior

- First AI call raises → second succeeds → assert both calls fired, no third.
- Both calls fail → RELATE-032 raised. Replayable from saved fixture.

### 7.6 E2E (fake outside tools, per L1 §7)

- 1 test that runs the full pipeline end-to-end with a fake `LinkProposerPort` returning a fixture response + a fake embedder returning a fixed vector. Asserts: items + embeddings + links + change_log + ai_responses all written correctly.

### 7.7 Live (opt-in via `@pytest.mark.live`)

- **Test A — full pipeline with real deps:** calls real OpenRouter + real `bge-base-en-v1.5` end-to-end. Asserts ≥ 1 link row + ≥ 1 change_log row + ≥ 1 ai_responses row.
- **Test B — parser only with mocked embedder:** calls real OpenRouter with a mocked embedder. Asserts the parser handles the real response shape and writes the correct link rows. Faster than Test A (no model load).

## 8. Out of Scope (this L2 plan)

- Engine C (Maintain) cascade rules — out of scope. Reversal of `supersedes` is Engine C's job. **Resolved (2026-10-25):** Maintain does **not** listen for events — it **sweeps** the `links` table (`status='Confirmed'`) to know what is live; there is no dispatch table because there is no event bus (L1:70). The vocabulary Maintain writes is fixed in `plans/engine-maintain-plan.md` §4.6. Relate does not own the cascade writes; it only emits the source-of-truth link row + the user-confirm log row.
- Engine D (Query) BM25 — out of scope. BM25 is Engine D's `topic_search` only (`plans/engine-query-plan.md` §4 Phase 2).
- `items.metadata` field — V1 spec 3.x deferred. Relate uses `created_at` proximity as a proxy.
- A `Signals` object wrapper — L1 §9 deferred until signal count > 3.
- Embedder model swap — kept `bge-base-en-v1.5` per L1 §0. Scale test is GitHub issue #12 (note: consider External vector DB at scale, tracked as GitHub issue #4, `note`).
- Multi-item batch runs — one item per run (L2 decision for testability, not Rule S1 which is about standalone CLI).
- Status cascade propagation — Engine C territory.

## 9. Deferred to L3 (Reminder)

L3 step plans (in `plans/steps/relate/`) will resolve these. They are recorded here so the L3 author does not forget:

1. **Phase 3 + Phase 4 fold decision.** L2 Capture defers this to L3 ("folded or separate — L3 author decides per testability"). L2 Relate defers the same way. L3 may keep Phases 3 and 4 separate (better unit testability) or fold them (one round-trip). Either is acceptable; match whatever Capture's L3 step 3 picks.
2. **Graph signal BFS depth.** L2 picks 1-hop (direct neighbors). L3 may pick depth-2, depth-3, or BFS to a fixed cost.
3. **Metadata signal temporal window.** L2 says ±30 days. L3 picks the exact window and whether to widen for older items with no candidates.
4. **Candidate rank formula when cosine is missing.** L2 says "cosine if present, else 0.5". L3 picks the exact tie-breaker (e.g. recency, statement length).
5. **Live AI prompt format for `LinkProposerPort`.** System prompt contents, few-shot examples, temperature.
6. **CLI confirm prompt format.** Exact wording, color output, paging for many candidates.
7. **Post-union candidate cap.** L2 has no cap. L3 may add a cap (e.g. top 30 by cosine) if `LinkProposerPort` cost becomes a problem on hub items.
8. **Engine C dispatch vocabulary** — **resolved** by `plans/engine-maintain-plan.md` §4.6.

## 10. Next Step

Human approves this L2 plan. Then 3 L3 step plans in `plans/steps/relate/`:
- `01-load-and-filter.md` (Phase 1) — landed
- `02-candidate-pool.md` (Phase 2: 3 signals + merge)
- `03-ai-propose-and-confirm-write.md` (Phases 3 + 4, fold decision per §9 #1)

L3 deliverable checklists:

**Step 1 (landed on `feat/relate-engine`):**
- (a) `ember/relate/*.py` modules: `compat.py`, `errors.py`, `link_lookup.py`, `load_filter.py`, `rows.py`. (`__init__.py` package marker.)
- (b) `SqliteLinkContext` Phase 1 methods: `item_exists`, `item_type`, `item_statement`, `item_created_at`, `find_existing`, `existing_link_types`, `list_other_items`, `find_latest_unlinked_active` (8 methods in `ember/adapters/sqlite.py`).
- (c) `compat.py` — V1 spec 3.3 type-compatibility table.
- (d) Migrations 006 (`links`), 007 (`item_embeddings`), 008 (`change_log.link_id` FK), 009 (`ai_responses` widening) in `ember/adapters/migrations/`.
- (e) `open_relate_database` + `ensure_relate_schema` boot checks in `ember/adapters/sqlite.py:48-91` (migrate-then-validate `schema_version >= 9`).
- (f) Architecture test extension: `test_relate_core_does_not_import_adapters` added to `tests/test_architecture.py` (per §7.3).
- (g) `tests/relate/` directory with fakes: `FakeLinkContext` + the per-method test suites (`test_load_filter_unit.py`, `test_load_filter_integration.py`, `test_relate_cli.py`).

**Step 2 (landed on `feat/relate-engine`):**
- (a) `ember/relate/embedding_store.py` — `EmbeddingStorePort` protocol; methods `get`, `upsert`, `model_name_of`, `first_model_name`, `wipe`; reads raise `RELATE-037`.
- (b) `ember/relate/candidate_pool.py` — public `build_candidate_pool(LoadedCandidates, *, link_lookup, embedding_store, embedder) -> Pool` + private `_cosine` helper.
- (c) `SqliteEmbedderStore` in `ember/adapters/sqlite.py`.
- (d) `LinkLookupPort.neighbors_of` implementation in `SqliteLinkContext` (1-hop BFS via `Confirmed` links).
- (e) `SentenceTransformerEmbedder` + `build_embedder` + `validate_embedder_config` in new `ember/adapters/embedder.py` (where `sentence-transformers` is imported).
- (f) Step 2 fakes + tests.

**Step 3 (planned):**
- (a) `ember/relate/link_proposal.py` — Phase 3 AI orchestration.
- (b) `ember/relate/link_gatekeeper.py` — pure `validate_add_link` with 9 rules.
- (c) `ember/relate/confirm_write.py` — user loop (y/n/s/q) + `format_link_block` YAML emitter.
- (d) `ember/relate/ai_response_store.py` — `AiResponseStorePort` protocol.
- (e) `SqliteLinkStore` in `ember/adapters/sqlite.py` — atomic `insert_link_with_log` (BEGIN / INSERT link / capture lastrowid / INSERT change_log / COMMIT).
- (f) `OpenAiLinkProposer` in `ember/adapters/llm.py` (extending Capture's adapter).
- (g) `LinkLookupPort.item_status` + `LinkLookupPort.supersedes_ancestors` implementations in `SqliteLinkContext`.
- (h) The `ember relate` Click command in `ember/cli.py`.
- (i) Step 3 fakes + tests.

(Five new ports across Step 2 + Step 3: `LinkProposerPort`, `EmbedderPort`, `LinkLookupPort` extended with `neighbors_of` / `item_status` / `supersedes_ancestors`, `LinkStorePort`, `EmbeddingStorePort`, `AiResponseStorePort`. The `AiResponseStorePort` is rarely faked — Capture's fakes pattern applies.)

## 11. V1.x Amendment (hardening phase): links immutability narrowed

Amended 2026-10-28, implementation pending. Source: `plans/hardening-schema-plan.md` (Cluster 1, issues #15 #17 #20 #21 #23).

- **§3.1 immutability clause narrowed.** Migration 011 adds `links.reversed_at TEXT NULL` (NULL = live, non-NULL = reversal timestamp). `links` stays insert-only otherwise — `status`, `link_type`, endpoints never change. The column is derived from `change_log` (`link_reversed` markers) and rebuildable; the ledger stays the source (master plan rule 7 unchanged).
- **Gatekeeper rules 8 and 9 will see the reversal column.** Rule 8: `supersedes_ancestors` walks only `Confirmed` links with `reversed_at IS NULL` — a corrective inverse after reversal no longer false-fires. Rule 9: `find_existing` still rejects the duplicate triple but reports the existing row's reversal state (the UNIQUE triple itself stands pending #15).
- **RELATE-028 message improves.** The rejection gains a detail naming the blocking link (id, source -> target); the cycle decision logic is unchanged.
- **UNIQUE-triple ruling (#15) pending.** Keep-block = spec 3.3 compliant, no schema work. Relax = partial unique index on live rows = `links` table rebuild + recorded spec 3.3 deviation. Decision is the maintainer's; it gates any rebuild — mechanics pinned in `plans/hardening-schema-plan.md` §10.
- Boot floor: relate 9 → 11 (RELATE-014 required moves; the six `version == 10` test sites are declared churn points).
- Maintain's floor moves 10 → 11 in the same migration (`MAINTAIN-009`); recorded here because both floors ship in one step.
- The pairing UPDATE widens "Maintain never writes links" by one column; this L2 records that widening now (mirrored in `plans/hardening-schema-plan.md` §6) — it is not deferred to the cluster-2 amendment.
- `RejectedLink` gains an optional `detail` field (the frozen "no reason field" clause, §5.5, is amended).
- `LinkLookupPort` grows a 12th method, `supersedes_blocking_link` (the frozen 11-method protocol, §5.4, is amended).
- Boot floors move with the immutability migration — see the two floor bullets above; both ship in one step.

## 12. V1.x Amendment: Signals wrapper (ticket 10, #8 ruling)

Added 2026-10-29. Source: `plans/hardening-decisions.md` #8 ("Decision: build", maintainer, 2026-10-29, against the defer recommendation — the recorded warning stands: structure without behavior change) and `.scratch/hardening/issues/10-signals-wrapper.md`. Implementer: `plans/steps/hardening/04-signals-wrapper.md`. Supersedes two lines of this plan: §2's "V1 has exactly 3, so no wrapper" bullet and §8's "A `Signals` object wrapper" out-of-scope bullet. §5.5 unchanged: `Signals` is not a shared row model and does not enter `rows.py`.

**The pin (frozen by this amendment):**

- Type name `Signals`, one Pydantic `BaseModel` (same base as `Pool`, §5.5), defined in `ember/relate/candidate_pool.py` — the module that builds it and its single consumer. Not `rows.py` (`rows.py` holds shapes shared across modules; `Signals` crosses no module line). No re-export, no `__init__` entry.
- Exactly three fields, matching today's local signal results verbatim (`candidate_pool.py:71-89` composition block):
  - `content: dict[int, float]` — the top-`CONTENT_TOP_K`(10) cosine scores from `_content_signal`
  - `graph: set[int]` — universe-surviving 1-hop neighbor ids from `_graph_signal`
  - `metadata: set[int]` — in-window item ids from `_metadata_signal`
- Boundary: built inside `build_candidate_pool` after the three signal calls return; consumed in the same function by `_merge` and the `counts` construction. No other module imports or names it (architecture test enforces). The empty-universe path still returns `Pool.empty(warning=warning)` before any signal runs — no `Signals` is built there.
- Naming trap, do not "fix" either side: `counts` keys stay `dense`/`graph`/`metadata` (frozen in the CLI JSON and the tests) while the content-signal field stays `content` (today's local variable name).

**Guarantees (zero output change):**

- `Pool(ranked, counts, warning)` unchanged: `rows.py::Pool` gains no field, `Pool.empty` untouched, `ranked` order and tie-break unchanged.
- CLI unchanged: the empty-pool JSON `{"phase": 2, "pool_size": 0, "signals": pool.counts}` (`ember/cli.py:306-310`) byte-identical; the model-change warning to STDERR unchanged; the `relate rejected: CODE [| detail]` lines and the `accepted: N, rejected: N, skipped: N, aborted: <bool>` summary unchanged; exit codes 0/1/2 unchanged.
- `build_candidate_pool` keeps its 4-input signature (I3) and raises exactly today's codes: RELATE-017, 018, 019, 021, 022, 023, 037. **Zero new error codes.**

**Test accept list:**

- Must pass unmodified: every test in `tests/relate/test_candidate_pool_unit.py` (34 test functions, two parametrized) and all four in `tests/relate/test_candidate_pool_integration.py` (`test_seeded_pool_ranks_by_cosine_then_id_and_counts_all_three_signals`, `test_prewarmed_cache_is_reused_on_the_second_run`, `test_preflight_model_mismatch_wipes_and_reencodes_every_item`, `test_graph_read_failure_surfaces_as_relate_021`). Reason: both files drive only `build_candidate_pool` and read the returned `Pool`; no test imports a private helper (the unit docstring pins this).
- Pure-restructure churn: **none expected.** The ticket's "except pure-restructure churn" clause should stay unused. If a test must be edited, that is a bug in the restructure, not churn — stop and record why in Build Notes.
- Adjacent, must stay green untouched: `tests/relate/test_relate_cli.py` (it patches `ember.cli.build_candidate_pool` at `:238-245` and constructs `Pool` directly — the wrapper changes nothing it sees) and `tests/test_architecture.py::test_relate_core_does_not_import_adapters`.

**Out of scope (this amendment):** no 4th signal; no BM25 into the pool (master-plan §2 exclusion stands; an L1 amendment is still required before that); no `ember.query` import anywhere under `ember/relate/` (architecture test stays green); no `Pool`/`RankedCandidate`/`RelateRequest` field change; no `rows.py` entry; no module move; no behavior, output, ranking, or cache-write change of any kind.

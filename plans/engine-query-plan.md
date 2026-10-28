# L2 Query Engine Master Plan

Engine D. Read-only. Returns context views.

## 0. Deferred Issues This Engine Owns

| Issue | Subject | Owner | Action |
|---|---|---|---|
| **#7** | BM25 `topic_search` | **Engine D** | **this engine's job.** §2.2, §4 Phase 2. Close when the L2 lands — the mode and its BM25 formula are specified below. |
| **#22** | `close_reason` / `status_origin` history rendering | **Engine D** | **this engine's job.** §4.6. Close when the L2 lands — the `change_log` vocabulary contract is written there. |
| **#24** | write the Engine D (Query) L2 | **Engine D** | **this file.** The ordering constraint it names is satisfied (`plans/master-plan.md` §8). Close when the L2 lands. |
| #1 | `items.rationale` / `items.source` | Capture | not ours — but `why` reads `rationale` and **nothing writes it**, so the field is NULL today (§2.4). |
| #16 | AI-proposed `close_item` | Maintain | not ours — L1 §5 defers it to V1.x. |
| #17 | DB-level compat-table enforcement | — | not ours — needs a `links` rebuild or triggers. No step plan owns it yet. |
| #18 | plain-text export | — | not ours — a separate utility plan (approved in a prior planning session, **not yet written to `plans/`**). See §8. |
| #19 | `edit_item` + `remove_link` | — | not ours — human-only writes. No plan owns them. |
| #20 | `links` rows have no lifecycle | note | not ours — but `history` is where a reversal becomes visible (§4.6). |
| #23 | `Closed ⇒ close_reason` not enforced in schema | note | not ours — but `history` must tolerate a NULL `close_reason` (§4.6). |

Closed by this plan's landing: **#7, #22, #24**.

## 1. Engine Job

Return context views. One job: read the DB, return structured lists.

- **Input:** the `items` + `links` + `change_log` tables. Read-only. No writes, no AI, no embedder, no network.
- **Output:** structured lists. Zero AI prose (L1 §2 line 65).
- **Four modes:** `current_state`, `topic_search`, `why`, `history`.
- **Status:** `Active`.

This engine never mutates. It has no write path, so it has no write port.

## 2. Engine-Specific Deferrals from L1 (Resolved at L2 Start)

### 2.1 The four modes are L1's four modes

L1 §2 lines 57–66 already names them, with the same names. No L1 amendment needed for the modes.

Spec §2's one-liner "traverse graph, filter by state" is superseded for V1 by spec §3.8's four modes (spec line 42: "Section 3 supersedes Section 2"). Status and type filters are deferred to L3 (§9).

### 2.2 `topic_search` searches every item, `Closed` included

L1 line 61: "`topic_search`: BM25 keyword search over item statements. Returns ranked item IDs."
L1 line 60: "`current_state`: `Active` + `Challenged`. `Closed` omitted."

Mode 1 states the Closed omission; mode 2 does not. That contrast is deliberate — mode 1 answers "what is true now" and mode 2 answers "what do I know about X". A closed item is still knowledge, and the spec keeps closed items forever (AI spec 3.2:62 "Deletion forbidden. Historical items immutable.").

**Decision:** `topic_search` scores every item, closed ones included, and each result carries its `status` so the reader can tell a superseded decision from a live one.

**If wrong:** the fix is one filter in `topic_search` (§4 Phase 2). Cheap to flip, so it is not worth an L1 amendment.

### 2.3 `why` walks two link types in two opposite directions

L1 line 62: "`why`: backward traversal of `depends_on` and `supports` links, plus read of `Decision.rationale` text field."

"Backward" = toward the reasons. The two link types point their reasons in opposite directions, so the rule is per link type, not per graph direction:

| Link | Stored direction | Means | "Why" direction | Yields |
|---|---|---|---|---|
| `depends_on` | source → target | source rests on target | source → target | the premise |
| `supports` | source → target | source backs target | target → source | the evidence |

Checked against `ember/relate/compat.py:13-25`: `depends_on` only ever runs Decision/Assumption → Assumption/Finding/Decision, so the target is always the premise. `supports` only ever runs Finding → Assumption/Decision, so the source is always the evidence. One rule per link type fits the table with no exceptions.

Two readings this explicitly is **not**:

- **not the incoming-edge reading** — that returns *dependents* for `depends_on` (the Maintain direction, i.e. consequences, not reasons);
- **not undirected** — that would also surface the Decisions which *rest on* an Assumption when you ask `why` about that Assumption.

Only `Confirmed` links count; a `Rejected` link is a link the human said no to (AI spec 3.3:80–81).

### 2.4 `Decision.rationale` is written by nobody — today

Migration 004 added `items.rationale` and `items.source`. **Nothing writes either column** (issue #1): Capture's AI returns only `type`, `statement`, `source_quote`, `confidence` (`ember/capture/item_proposal.py:65-68`), and Relate's `rationale` belongs to the *link*, not the item (`ember/relate/link_gatekeeper.py:47,54`; `links` has no `rationale` column).

So `why` reads a column that is NULL on every row it will ever see in V1.

**Decision:** `why` reads and returns `rationale` as L1 line 62 requires, on the item being explained **and** on every Decision it reaches as a reason. The field is NULL until issue #1 lands. **The L2 must not describe rationale as populated.** A `why` result with `"rationale": null` is correct today, not a bug.

`items.source` (Finding evidence text) is **not** read by this engine. L1 line 62 names `Decision.rationale` only, and L1 line 127 places `Evidence` text on the `Finding` row.

### 2.5 No AI, no embedder, no network

Engine D reads a local SQLite file. Spec 3.8's output rule ("Zero AI-written prose summaries in V1") is satisfied by construction: there is no model in this engine. So `D8`, `I16`, `T7`, `T8` are N/A in §Z, same as Maintain.

**"Raw data only" (L1 line 118) is read as "no AI prose and no writes."** Spec 3.8 governs what each mode returns. Every returned field is a stored value or a deterministic function of stored values — a BM25 score, a traversal depth — never model output. If the founder wants L1 line 118 spelled out that way, it rides with step 03's commit (A2: L1 never describes behaviour that is not built).

### 2.6 The engine never writes — not even at boot

Every other engine's boot path applies pending migrations (`open_relate_database` at `ember/adapters/sqlite.py:65-92`, `open_maintain_database` at `:110-138`). Engine D does not, and this is deliberate.

Migrations are not always additive. `008_add_change_log_link_fk.sql` does `ALTER TABLE … RENAME`, `CREATE`, `INSERT…SELECT`, `DROP`; `009_drop_source_id_not_null_and_add_item_id.sql` does the same to `ai_responses`. Those **rewrite and drop rows**. L1 rule 1 (line 115) says "AI direct DB write: PROHIBITED", and L1 line 118 makes `query` the one command an AI may run against the user's database. A read command that rewrites the ledger on the way in is not a read.

**Decision:** Engine D opens the database **read-only** and never calls `_apply_migrations`.

Consequence, stated plainly: a database behind version 10 is **refused** (`QUERY-004`), not upgraded. Another engine must upgrade it. That is the price of a read command that provably cannot write, and §7.2 tests it by hashing the database file before and after a query.

## 3. Boot (read-only)

**Engine D ships no migration** and applies none. It reads columns that already exist. `schema_version` stays at 10 until another engine adds a migration.

**`open_query_database(db_path)`** in `ember/adapters/sqlite.py`:

1. `if not os.path.exists(db_path)` → raise `DbOpenFailed` (**QUERY-003**), message `db file missing`, context `db_path`.
   The generic `open_database` is **not** used — it creates a missing file *and* writes migrations. A read engine must do neither.
2. Open **read-only**:
   `sqlite3.connect(f"file:{urllib.parse.quote(str(db_path))}?mode=ro", uri=True)`.
   **`uri=True` is part of the contract.** Without it `sqlite3.connect` treats the whole string as a literal filename and the open fails on a perfectly good database. The path is quoted because SQLite parses `?`, `#` and `%` as URI syntax.
   Verified behaviour of this open: a missing file raises `OperationalError` **and is not created**; a write attempt raises `OperationalError: attempt to write a readonly database`; a non-SQLite file raises `DatabaseError: file is not a database`.
3. Probe `SELECT COUNT(*) FROM sqlite_master` **inside the try** — this is what makes "file is not a database" land on `QUERY-003`.
4. `ensure_query_schema(conn)` → `SELECT version FROM schema_version`; if the read fails → `DbOpenFailed` (**QUERY-003**), message `schema version read fail`; if `version < 10` → `SchemaOutdated` (**QUERY-004**), message `schema version too old`, context `version`, `required=10`.
   **Required version is 10.** Engine D reads `items.close_reason` / `items.status_origin` (migration 010) and `change_log.link_id` (migration 008).
5. `PRAGMA foreign_keys = ON`.

**`ensure_query_schema` is a separate function**, like `ensure_relate_schema` and `ensure_maintain_schema`.

**Known limitation, recorded:** a read-only connection cannot roll back a hot journal, so a database left with an unclean shutdown fails to open (`QUERY-003`). The error message names the fix: run another `ember` command once to recover it. This is inherent to reading without writing.

**Unlike the other engines, this boot path never migrates** (§2.6).

## 4. Pipeline (4 Phases)

```
[ember current-state | topic-search | why | history]
   |
   v
Phase 1: Load    (read the tables this mode needs -> pure input)
   |
   v
Phase 2: Derive  (PURE - the core. One function per mode.)
   |
   v
Phase 3: Render  (the display layer - sort + format)
   |
   v
Phase 4: CLI     (one command per mode)
```

**Phase 2 is "the core"** in L1 line 64's sense — it returns unsorted, and never touches stdout. **Phase 3 is "the display layer"** — it sorts and formats, and is where L1 line 64 puts the `Challenged`-first ordering. Both are pure and live in `ember/query/`; they are separate layers, and no core module prints anything.

### Phase 1: Load

Read through `QueryLookupPort` (§4.5). Each mode reads only what it needs:

| Mode | Reads |
|---|---|
| `current_state` | `list_items()` |
| `topic_search` | `list_items()` |
| `why` | `list_items()`, `list_links()` |
| `history` | `list_change_log()`, `list_links()` |

The load returns raw rows. Filtering, scoring, traversal and classification are Phase 2, and they are pure.

### Phase 2: Derive (pure, the core)

One function per mode. No I/O, no clock, no DB, no randomness, no printing (Rule T1).

- **`current_state(items) -> list[CurrentStateRow]`** — keep `status in ("Active", "Challenged")`, drop `Closed`. **No sorting here** — Phase 3 owns that.
- **`topic_search(items, query) -> list[SearchHit]`** — BM25 over `items.statement`. Formula, tokenizer and tie-break below.
- **`why(items, links, item_id) -> WhyResult`** — backward traversal, cycle-safe.
- **`history(rows, links, item_id) -> list[HistoryEvent]`** — classify each `change_log` row and keep the rows that belong to `item_id`.

#### BM25 formula (fixed, so the implementer does not choose)

Corpus = the `statement` of **every** item. Document = one item.

```
idf(q)      = ln(1 + (N - df(q) + 0.5) / (df(q) + 0.5))
score(D, Q) = SUM over q in Q of
               idf(q) * ( f(q,D) * (k1 + 1) )
               / ( f(q,D) + k1 * (1 - b + b * len(D) / avgdl) )
k1 = 1.2    b = 0.75
```

- `N` = number of documents, `df(q)` = number of documents containing `q`, `f(q,D)` = count of `q` in `D`, `len(D)` = token count of `D`, `avgdl` = mean token count over the corpus.
- The `ln(1 + ...)` form keeps `idf` positive when a term appears in more than half the corpus. The plain `ln(...)` form goes negative and would rank a common term below a rare one.
- **Tokenizer** (`ember/query/tokenize.py`, shared with the gatekeeper): lowercase, then split on runs of characters that are not letters or digits (unicode letters and digits are kept). No stemming, no stopword list, no phrase matching. A term is one token.
- **Zero-token corpus:** if `avgdl == 0` (every statement tokenizes to nothing) → return `[]`. The formula divides by `avgdl`, so this must be guarded before scoring.
- An item is a result only if `score > 0` (it contains at least one query token).
- **Tie-break:** score descending, then `item_id` ascending. Two items with equal scores always come out in the same order.
- A query that contains no tokens at all (empty, or only punctuation) → **QUERY-002**, raised by the gatekeeper (§4.7).
- `k1` and `b` are fixed here. L3 may tune them (§9), but a change to either changes every expected score in §7.1.

**Why hand-rolled and not SQLite FTS5?** FTS5 is available in this repo's SQLite (3.46.1 at review time) and is the obvious alternative. It is the wrong tool here for one structural reason: FTS5 needs a virtual table plus sync triggers, which means a migration and writes, contradicting §3's no-migration read-only boot. That is the whole argument, and it does not rest on a claim about FTS5's ranking. (FTS5 does **not** return `idf = 0` for a common term — it clamps a non-positive `idf` to `1e-6`, verified live at review — so the `ln(1 + …)` form above is *this plan's* fixed, transparent formula, not a repair of an FTS5 defect.) `rank_bm25` is rejected by L1 §0 ("Engine core imports only stdlib + Pydantic + Click + pytest").

#### `why` traversal rules

- Start at `item_id`. The item must exist — the gatekeeper checked (§4.7).
- From the current node, follow:
  - `depends_on` links where the node is the **source** → the **target** is a reason.
  - `supports` links where the node is the **target** → the **source** is a reason.
- Only `Confirmed` links.
- **No depth limit.** The traversal is the transitive closure of those two edge rules. L1 line 62 says "traversal" and names no depth; a depth cap would narrow it without a spec basis.
- **Cycle-safe:** keep a visited set of item ids across the whole walk. A `depends_on` cycle between two Decisions is legal in the DB (the compatibility table allows `Decision → Decision`) and only `supersedes` is cycle-checked (`RELATE-028`). Without a visited set the walk does not terminate.
- Each reason carries its `depth` (0 for the start item, 1 for a direct reason, and so on).
- Results are ordered by `depth` ascending, then `item_id` ascending.
- `why` works for **any** item id, not only Decisions (AI spec 3.8:139 says "from item ID"). A Finding can be the target of a `depends_on` link and so has reasons; an item with no such links yields an empty list, which is correct, not an error.

#### `history` rules

The `change_log` vocabulary is Engine C's handoff to this engine. §4.6 is the contract; the rules are:

- A row belongs to item `N` if **either**:
  - `row.item_id == N` — the row's subject is the item (Engine C's convention, and Capture's `created` / `validated` rows), **or**
  - `row.link_id` names a link where `N` is the source **or** the target — the row is about a link that touches `N` (Engine B's `link_confirmed` / `link_rejected` rows, whose `item_id` is the link's **source**).
- The `link_id` join is what makes the second rule possible, and it is why the answer is a union rather than a filter on `item_id`. (`link_id` is L1 line 75's nullable column for link-driven mutations; migration 008 adds its FK.)
- **A row matching both conditions appears once.**
- Order: `timestamp` ascending, then `id` ascending. Timestamps are compared as opaque ISO text; they are written by one clock and never reformatted. Note the house-wide edge case: `datetime.isoformat()` omits microseconds when they are zero, so within one second two rows can compare with the later one first. `id` is the tiebreak, and `id` is the append order.
- A row with `item_id IS NULL` (Capture's `proposed` rejection rows) has no subject and no link, so it belongs to **no** item. It appears in the **global** history (§5) and in no item-scoped one.

### Phase 3: Render (the display layer)

One rule comes straight from L1 line 64: **"Sorting by `Challenged` first happens at the display layer. Core returns unsorted."**

- `current_state`: Phase 2 returns items in the order `list_items()` gave them. Phase 3 sorts **`Challenged` first**, then `Active`, and within each group `item_id` ascending. The sort is by `(status_rank, id)` with `Challenged` → 0 and `Active` → 1, so it does not depend on the adapter's row order.
- `topic_search`: Phase 2 already returns hits in score order (the score *is* the ranking, and L1 line 61 says "ranked item IDs"). Phase 3 does not re-sort.
- `why`: Phase 2 already returns reasons in `(depth, item_id)` order. Phase 3 does not re-sort.
- `history`: Phase 2 already returns events in `(timestamp, id)` order. Phase 3 does not re-sort.

**The renderer lives in `ember/query/render.py`** and returns a **string**. It is pure: `json.dumps` only, no `click`, no `print`. The CLI echoes it. This is the house display-layer shape (`ember/maintain/report.py:8` returns `list[str]`; `ember/relate/confirm_write.py:90` returns `str`), and it keeps stdout out of the engine package.

**The output contract has one source: the row models in §4.5.** Each row object in the JSON is exactly its model's fields, in the model's field order. The envelope is:

| Mode | Envelope |
|---|---|
| `current_state` | `{"mode": "current_state", "count": N, "items": [CurrentStateRow, …]}` |
| `topic_search` | `{"mode": "topic_search", "query": "<text>", "count": N, "results": [SearchHit, …]}` |
| `why` | `{"mode": "why", "item": {QueryItem}, "count": N, "reasons": [WhyReason, …]}` |
| `history` | `{"mode": "history", "item_id": N or null, "count": N, "events": [HistoryEvent, …]}` |

`count` is the length of the list field. `history`'s `item_id` is `null` for the global view (§5).

### Phase 4: CLI

One Click command per mode (§5). Each command calls exactly one `run_*` function (§4.7). No command has a `--mode` flag and no function takes a mode argument — the mode is the entry point, not a runtime switch (Rule I2).

The four commands are **flat on the root group**, like all nine existing commands (`ember/cli.py:103-545`). The house never names a CLI command after an L1 action — `add_item` ships as `ember capture`, `add_link` as `ember relate` — so L1 line 118's `query` action maps to a family of four read commands the same way.

### 4.5 Ports + Data Models

**`QueryLookupPort`** — engine core, `ember/query/lookup.py`. The engine core must not import `sqlite3` (Rule T9).

- `list_items() -> list[QueryItem]` — every item, `ORDER BY id` ascending: `id`, `type`, `statement`, `status`, `close_reason`, `status_origin`, `rationale`, `created_at`, `source_id`. Raises **QUERY-005** on a read failure.
- `list_links() -> list[Link]` — every link, `ORDER BY id` ascending. Raises **QUERY-005** on a read failure.
- `list_change_log() -> list[ChangeRow]` — every row, `ORDER BY id` ascending: `id`, `item_id`, `link_id`, `field_changed`, `old_value`, `new_value`, `timestamp`, `trigger_cause`. Raises **QUERY-005** on a read failure.
- `item_exists(item_id: int) -> bool` — used by the gatekeeper. Raises **QUERY-005** on a read failure. House precedent: `LinkLookupPort.item_exists` (`ember/relate/link_lookup.py`).

**Adapter:** `SqliteQueryContext(conn)` in `ember/adapters/sqlite.py`. All `sqlite3` lives there.

**Data models** (Pydantic, `ember/query/rows.py`):

- `QueryItem(id: int, type: str, statement: str, status: str, close_reason: str | None, status_origin: str, rationale: str | None, created_at: str, source_id: int)` — the **input** row.
- `CurrentStateRow(id: int, type: str, statement: str, status: str, created_at: str, source_id: int, status_origin: str, challenged: bool)` — the **output** view, a projection of `QueryItem`. `challenged` is the explicit warning flag the spec asks for (AI spec 3.8:137 "explicit warning flags"; human spec 3.8:137 "warning badges").
- `SearchHit(item_id: int, score: float, type: str, statement: str, status: str)`
- `WhyReason(item_id: int, type: str, statement: str, status: str, rationale: str | None, depth: int, via_link_type: str, via_link_id: int)`
- `WhyResult(item: QueryItem, reasons: list[WhyReason])`
- `HistoryEvent(timestamp: str, kind: str, cause: str, field_changed: str, item_id: int | None, link_id: int | None, link_source_item_id: int | None, link_target_item_id: int | None, link_type: str | None, old_value: str | None, new_value: str | None, close_reason: str | None)`
- **`Link` is IMPORTED from `ember.relate.rows`, not duplicated** (D3 — one table, one shape; `ember/maintain/rows.py:1-11` does the same for the same reason).
- **`ChangeRow` is a separate read model on purpose:** `ChangeLogEntry.item_id` is `int` and non-nullable (it is a *write* model), but Capture writes `proposed` rows with a NULL `item_id` (`ember/adapters/sqlite.py:860-875`). The read side needs the nullable shape. Recorded in §Z(c) D3.

**No write port.** Engine D has no write path. A `QueryStorePort` would be dead code.

### 4.6 The `change_log` vocabulary (Engine C's handoff)

This is the contract issue #22 asks for. It is what Engine D must know about the ledger.

**Who writes what** is `plans/engine-maintain-plan.md` §4.6 (and Relate's and Capture's plans). **Not restated here** — that table is the writers' contract and this one is the readers'. What follows is the mapping Engine D renders.

| `field_changed` | `trigger_cause` | `kind` | `item_id` means |
|---|---|---|---|
| `created` | `user_confirmed` | `created` | the new item |
| `proposed` | `rejected` | `proposed_rejected` | **NULL** — a rejected proposal has no item |
| `validated` | `user_set_validated` | `validated` | the item |
| `link_confirmed` | `user_confirmed` | `link_confirmed` | the link's **source** |
| `link_rejected` | `rejected` | `link_rejected` | the link's **source** |
| `status` | `supersedes_confirmed` | `status_changed` | the link's **target** (the closed item) |
| `status` | `answers_confirmed` | `status_changed` | the link's **target** |
| `status` | `dependency_closed` | `status_changed` | the link's **source** (the dependent) |
| `status` | `contradicts_confirmed` | `status_changed` | the link's **target** |
| `status` | `user_closed` | `status_changed` | the item |
| `status` | `user_set_status` | `status_changed` | the item |
| `status` | `reversal` | `status_changed` | the restored item |
| `status_origin` | `user_set_status` | `status_origin_changed` | the item whose `status_origin` changed |
| `link_reversed` | `reversal` | `link_reversed` | the restored item (the marker) |

**`kind` is derived from the PAIR `(field_changed, trigger_cause)`, and the pair is the only reliable discriminator.** Neither half works alone:

- `field_changed == "status"` covers **seven** causes — two machine closes (`supersedes_confirmed`, `answers_confirmed`), two machine challenges (`dependency_closed`, `contradicts_confirmed`), a human close (`user_closed`), a human status set (`user_set_status`), and a machine restore (`reversal`). `trigger_cause` says which.
- `trigger_cause == "user_set_status"` covers **both** a `status` row and a `status_origin` row. `trigger_cause == "reversal"` covers **both** the `status` restore and the `link_reversed` marker. `field_changed` says which.

**The nine `kind` values are: `created`, `proposed_rejected`, `validated`, `link_confirmed`, `link_rejected`, `status_changed`, `status_origin_changed`, `link_reversed`, and `unknown`.** `unknown` is the fallback for a `field_changed` this build does not recognise — a row written by a future engine, or a hand edit. It renders with the raw `field_changed` and `trigger_cause` visible, so nothing is lost and nothing crashes. The ledger is append-only; dropping a row would hide history.

**`status_origin` and `link_reversed` are not status changes.** A renderer that assumes every row's `new_value` is a status prints "status changed to Reversed" for an item that never held a status `Reversed`. `status_origin` moves `derived` ↔ `manual`; `link_reversed` moves a link `Confirmed` → `Reversed`. Both get their own `kind`, and for both `close_reason` is `null`.

**`item_id` means two different things, and this engine must not guess.** Engine C writes `item_id` = *the item whose status changed* — for rules 1, 3 and 4 that is the link's **target**, but for rule 2 (`dependency_closed`) it is the link's **source**. Engine B writes `item_id` = *the link's source*. Same column, opposite subject. That is why `history` joins on `link_id` (§4 Phase 2) and why the rendered event carries `link_source_item_id` / `link_target_item_id` next to `item_id`.

**`old_value` / `new_value` encoding for a status row:** `<status>`, or `<status>:<close_reason>` when the status is `Closed` (e.g. `"Closed:superseded"`). `old_value` is the **observed** prior status, not a constant — a `Challenged` target closed by rule 1 records `old_value = "Challenged"`. Split on the **first** `:` to get the status and the reason. A value with no `:` has a null reason. **A reason segment of the literal `"None"` means no reason** — the writer formats a null reason as `f"{status}:{reason}"`, which produces `"Closed:None"` when the reason is null. The splitter maps that to `null`.

**`close_reason` may be NULL on a Closed item.** Issue #23: nothing in the schema ties `status = 'Closed'` to `close_reason IS NOT NULL`. The invariant holds in the write path, not in the storage. So `history` renders `close_reason: null` for such a row instead of failing, and never assumes a Closed item has a reason.

**`old_value` and `new_value` are rendered verbatim.** They are the ledger's own record and are never re-encoded. `close_reason` is the one derived field, computed by the same splitter that documents the encoding, so the two cannot disagree.

**A reversed link still reads `Confirmed`.** Issue #20: `reverse-supersedes` writes no `links` row. The `links` table still says `status = 'Confirmed'` for a reversed `supersedes` link, and the `link_reversed` marker row is the only record. This engine does not traverse `supersedes` (§2.3), so the stale `Confirmed` row does not corrupt a `why` walk — but `history` is where the reversal becomes visible, and the `link_reversed` event is what makes it visible.

**`item_id` is nullable.** Only Capture's `proposed` rows use NULL. They have no subject and no link, so they belong to no item and never appear in an item-scoped `history` (§5).

### 4.7 Orchestration

`ember/query/run_query.py` mirrors `ember/maintain/run_maintain.py`: one function per entry point, no mode argument, no boolean flag.

- `run_current_state(lookup: QueryLookupPort) -> str`
- `run_topic_search(lookup: QueryLookupPort, query: str) -> str`
- `run_why(lookup: QueryLookupPort, item_id: int) -> str`
- `run_history(lookup: QueryLookupPort, item_id: int | None) -> str`

Each one: validate (§4.7 gatekeeper) → load (Phase 1) → derive (Phase 2) → render (Phase 3). Each returns the rendered string; the CLI echoes it.

**The gatekeeper** is `ember/query/query_gatekeeper.py` — the read-side gate L1 line 82 names (`validate_query`). It exposes two functions, like Relate's `link_gatekeeper.py` exposes its rules:

- `validate_query_text(text: str) -> str` — pure. Normalises the text and raises **QUERY-002** if it has no tokens. Uses the shared tokenizer (`ember/query/tokenize.py`), so the gate and the scorer agree on what a token is.
- `validate_query_item(lookup: QueryLookupPort, item_id: int) -> None` — raises **QUERY-001** if the item does not exist.

**When the item check runs:** `run_why` always calls `validate_query_item`. `run_history` calls it **only when an explicit `--item` is given** — `history --item <unknown-id>` is **QUERY-001**, because the user named a specific item, exactly as `why` does. The **global** view (`history` with no `--item`, i.e. `item_id = None`) validates nothing and never raises QUERY-001. (Decided at review, 2026-10-28: the alternative — return `"count": 0` for an unknown id — was rejected, because it would make `history` disagree with `why` about what a named-but-missing item means. I8's "design error away" applies to *unfiltered* reads, where there is nothing to name.)

**Each error code has exactly one owner.** The gatekeeper owns QUERY-001 and QUERY-002; the pure core assumes valid input and never re-raises them (I9: validate at the edge, trust inside). A bad request therefore never reaches the core — and the pure core's unit tests do not duplicate the gate's checks.

**The gatekeeper also fixes what a read may touch:** Engine D reads `items`, `links` and `change_log` **only**. It never reads `sources` (raw source text) or `ai_responses` (raw model output). `query` is the one command an AI may run against the user's database, and those two tables hold the most sensitive bytes in it.

## 5. CLI + Configuration

```
ember current-state [--db PATH]
ember topic-search --query TEXT [--db PATH]
ember why --item <id> [--db PATH]
ember history [--item <id>] [--db PATH]
```

- `--db` defaults to `ember.db` — the module-level `DEFAULT_DB_PATH` in `ember/cli.py:64`. The commands live in `ember/cli.py` and use that constant directly; **no module imports it from `ember.cli`** (that would be a circular import, Constitution B6's first warning sign).
- `--item` is `type=int`. **Required** for `why`. **Optional** for `history`: with no `--item` the mode returns the **global** ledger, every row in `(timestamp, id)` order — which is the literal spec reading ("Reads the change log", AI spec 3.8:140) and the only way Capture's NULL-subject `proposed` rows are reachable at all. With `--item <id>` it returns that item's rows by the union rule (§4 Phase 2). **A `--item` id that is not in `items` raises QUERY-001** (see §4.7), the same as `why`; the global view never raises it.
- `--query` is **required** for `topic-search`.
- **Exit codes:** 0 success (including an empty result), 1 on any `QUERY-*` error, 2 on a Click usage error. No exit 2 for abort — this engine has no prompt, so there is no `UserAbort`.
- **Output:** one JSON document on stdout (§4 Phase 3). Nothing else goes to stdout. Errors go to stderr as `error: {exc.log_line()}` (house format, `ember/cli.py:131`).
- **Config:** none. No env vars, no API key, no model name. This engine reads a local file.

## 6. Errors (Stable Codes)

`ember/query/errors.py`, base `QueryError(EmberError)` with `code = "QUERY-000"`, `name = "QueryError"`. Each subclass has `code` + `name` class attributes (I17). **No subclass defines `__init__`**, so `EmberError._caller_location()` (`ember/errors.py:29-32`) injects the raising module and function for free (I18).

| Code | Name | Trigger | Context (I19) |
|---|---|---|---|
| `QUERY-000` | `QueryError` | base; never raised directly | — |
| `QUERY-001` | `QueryItemNotFound` | the `--item` id does not exist in `items`. | `item_id` |
| `QUERY-002` | `QueryTextEmpty` | the `--query` text has no tokens. | `query_length` |
| `QUERY-003` | `DbOpenFailed` | the DB file is missing, is not a readable SQLite database, the `schema_version` read failed, or the database has a hot journal. | `db_path` |
| `QUERY-004` | `SchemaOutdated` | `schema_version` is below the required 10. | `version`, `required` |
| `QUERY-005` | `ItemsReadFailed` | an `items`, `links` or `change_log` read failed (disk error, lock, corrupt page). | `table` |

**Codes are contiguous, 000–005, with no gaps and no removals** (I17) — the same shape as Maintain's 000–012. Six raisable codes is the right size for a read-only engine with one read port: Maintain has 12 raised codes (plus the `MAINTAIN-000` base), Relate 31, Capture 16.

**Name collisions are house style.** `DbOpenFailed` is also RELATE-012 and MAINTAIN-007; `SchemaOutdated` is RELATE-014 and MAINTAIN-009; `ItemsReadFailed` is RELATE-016 and MAINTAIN-010. The house resolves this with an import alias (`from ember.relate.errors import DbOpenFailed as MaintainDbOpenFailed`, `ember/adapters/sqlite.py:24-31`). Engine D follows it: `from ember.query.errors import DbOpenFailed as QueryDbOpenFailed` in the adapter. The `QUERY-` prefix makes the **code** unique (I17); the shared name makes it readable, and `name` is the bare class name, exactly as Maintain does it (`name = "DbOpenFailed"`).

`QueryItemNotFound` **is** prefixed, because `ItemNotFound` is already CAPTURE-015's class name. The house sets the precedent for exactly this case: Maintain's `MaintainItemNotFound` is prefixed because `ItemIdNotFound` is Relate's RELATE-001 class name.

**QUERY-002 carries `query_length`, not the query text.** The text is user input; it can contain a newline, which would break the one-line log format (I20), and it can contain a pasted secret. The length is enough to diagnose it.

**No code is reused from another namespace.** A `QUERY-*` code is raised by this engine only.

**An empty result is not an error.** No `items` matching a search, no reasons for an item, no history rows — all exit 0 with `"count": 0` and an empty list. I4: empty list, not `None`.

**Each code has one raising site:**

| Code | Raised in |
|---|---|
| 001 | `ember.query.query_gatekeeper.validate_query_item` |
| 002 | `ember.query.query_gatekeeper.validate_query_text` |
| 003 | `ember.adapters.sqlite.open_query_database` (missing file, open fail, probe fail) and `ensure_query_schema` (version read fail) |
| 004 | `ember.adapters.sqlite.ensure_query_schema` |
| 005 | `ember.adapters.sqlite.SqliteQueryContext.list_items` / `list_links` / `list_change_log` / `item_exists` |

## 7. Test Targets

Test pyramid per L1 §7 + Constitution T1–T6, T9, T10. No T7 / T8 — no AI in this engine.

### 7.1 Unit (pure core, no DB)

- **`current_state`:**
  - `Active` and `Challenged` kept, `Closed` dropped.
  - `challenged` is `true` for a `Challenged` row and `false` for an `Active` one.
  - `close_reason` and `rationale` do not leak into the row.
  - **the core returns the input order**: feed a deliberately scrambled list and assert the output order **equals the input order**. (This is the real "core returns unsorted" contract. Asserting "not sorted by status" passes for any order and cannot fail.)
- **`topic_search` (BM25):**
  - the formula against a hand-computed fixture: a corpus of 3 documents with known token counts, `k1 = 1.2`, `b = 0.75`, checked to 6 decimal places.
  - the `ln(1 + ...)` IDF form: a term present in every document still scores above zero, and scores stay positive.
  - tokenizer: mixed case folds; punctuation splits; a unicode letter is a token character; digits are tokens.
  - **a corpus whose statements all tokenize to nothing returns `[]`** — no `ZeroDivisionError`.
  - an item with no query token is not a result.
  - tie-break: equal scores come out in `item_id` order.
  - an empty corpus returns an empty list, not an error.
- **`why`:**
  - `depends_on` yields the **target**; `supports` yields the **source** (§2.3) — one test per link type, with the pair direction asserted.
  - a `Rejected` link yields nothing.
  - **a `depends_on` cycle terminates** and every item appears once.
  - the traversal is transitive: a reason-of-a-reason is returned, with its `depth`.
  - a reason that is a Decision carries its own `rationale`.
  - `rationale` is `null` when the column is NULL.
- **`history`:**
  - a row whose `item_id` matches is included.
  - a row whose `link_id` names a link where the item is the **target** is included even though `item_id` points at the link's source.
  - a row about an unrelated item and an unrelated link is excluded.
  - **a row matching both conditions appears once.**
  - each of the nine `kind` values renders; `status_origin` and `link_reversed` get their own `kind`, and their `close_reason` is `null`.
  - a `Closed:superseded` value splits into status `Closed` + reason `superseded`; a bare `Closed` splits into status `Closed` + null reason; **`Closed:None` splits into status `Closed` + null reason** (issue #23).
  - a `Closed` item with a NULL `close_reason` renders without failing.
  - an unrecognised `field_changed` renders as `kind: "unknown"` with the raw values visible, and does not crash.
  - order is `(timestamp, id)`.
- **the gatekeeper** (L1 line 82 names it, so it gets its own tests):
  - an empty or punctuation-only query raises QUERY-002; a query with tokens passes.
  - a missing item id raises QUERY-001; an existing one passes.
  - the item check runs for `why` and for `history --item`; the global `history` (no `--item`) makes **no** lookup call and never raises QUERY-001.
  - a valid request returns without touching the core.
- **the renderer** (the display layer):
  - `current_state` puts `Challenged` first and `Active` second, each group in `item_id` order — from a scrambled input list.
  - the JSON round-trips through `json.loads` and every row's keys match its model.
- **Error codes:** each code has a stable value and a name equal to its class name.

### 7.2 Integration (real temp DB, migrations 001–010 applied)

- `open_query_database` on a **missing** file raises QUERY-003 and **does not create the file**.
- `open_query_database` on a non-SQLite file raises QUERY-003.
- `open_query_database` on a **v9** database raises QUERY-004 with `version=9`, `required=10`. **This needs no monkeypatch** — a read-only open never migrates, so the version stays 9 and the check fires for real. (Every other engine's floor check is unreachable on the real path, because the runner upgrades first; this one is not.)
- **the database file is byte-identical before and after a query** — hash it. This is the strongest possible proof of the read-only claim (§2.6) and the guarantee L1 rule 1 needs.
- a write attempt on the export connection raises `sqlite3.OperationalError` — the read-only handle really is read-only.
- `current_state` on a DB holding one item in each status returns two rows, `Closed` omitted, `Challenged` first.
- `topic_search` over a DB with a known statement returns the expected item and score.
- `why` over a DB with a real `depends_on` link returns the premise.
- `history --item 1` over a DB with a real `change_log` row returns the event; `history` with no `--item` returns every row.
- a read failure raises QUERY-005 (the house pattern: a closed connection or a dropped table).
- **fixtures must be compat-legal.** The DB does not enforce the compatibility table (issue #17), so a hand-seeded `Assumption --supports--> X` would produce a nonsense `why` walk. The Maintain plan makes this an explicit rule (`plans/engine-maintain-plan.md:366`); this plan inherits it.

### 7.3 Architecture test (Rule T9)

Extend `tests/test_architecture.py` with `test_query_core_does_not_import_adapters`: glob `ember/query/*.py` and assert none of them contains `sqlite3`, `openai`, `anthropic`, `sentence_transformers`, `numpy`, or `ember.adapters` — the house's `FORBIDDEN_RELATE` constant, the same one Maintain uses.

**The scan is a raw substring match.** So an engine-core docstring that says "implemented in `ember/adapters/sqlite.py`" **fails the test.** Engine-core docstrings say *the storage adapter*, never the module path. The house already writes it this way — `grep -rn "ember.adapters\|sqlite3" ember/maintain ember/relate` returns nothing.

### 7.4 CLI tests (smoke)

- `ember current-state --db <fixture>` exits 0 and prints one JSON document whose `items` array lists the `Challenged` item **first**.
- `ember topic-search --query sqlite --db <fixture>` exits 0 and prints a JSON document with `results`.
- `ember why --item 99 --db <fixture>` exits 1 and prints `error: QUERY-001 ...` to stderr.
- `ember history --item 99 --db <fixture>` exits 1 and prints `error: QUERY-001 ...` to stderr.
- `ember history --db <fixture>` **with no `--item`** exits 0 (the global view; item 99 exists or not, it does not matter).
- `ember history --db <fixture>` exits 0 and prints the global ledger.
- `ember current-state --item abc` exits 2 (a Click usage error).
- stdout is valid JSON on every success path — parse it with `json.loads` in the test, do not match strings.

### 7.5 Error-code coverage (I21)

| Code | Test target |
|---|---|
| 001 `QueryItemNotFound` | §7.1 (gatekeeper) + §7.4 (`why --item 99`, `history --item 99`) |
| 002 `QueryTextEmpty` | §7.1 (gatekeeper, empty and punctuation-only) |
| 003 `DbOpenFailed` | §7.2 (missing file, non-SQLite file) |
| 004 `SchemaOutdated` | §7.2 (real v9 database) |
| 005 `ItemsReadFailed` | §7.2 (read failure) |

### 7.6 E2E (fake outside tools)

**One** test. It runs the house chain `capture → relate → maintain → query` against a temp DB using the existing fakes (`tests/fakes.py`: `FakeItemProposer`, `FakeEmbedder`) so no model is ever loaded, then asserts the JSON from all four query commands against that one DB.

T4 caps E2E at 1–2 per engine; Relate and Maintain each ship one.

### 7.7 Live

**None.** No AI call, no embedder, no network. Second engine with no live tier.

**Pyramid (T4):** ~25 unit, ~10 integration, 8 CLI, 1 E2E, 0 live, 1 architecture.

## 8. Out of Scope (this L2 plan)

- **Plain-text export** (AI spec 3.6:118 / human 3.6:115). Not one of the four modes in L1 line 59, and not a context view. It has its own approved plan (a separate utility L2 with its own `EXPORT-*` codes), which is **not yet written to `plans/`**. **Issue #18 stays with that plan** — Engine D does not own it.
- **Status and type filters on `topic_search`** (§9).
- **A `links` rebuild or DB-side compatibility enforcement** (issue #17). Not this engine's tables.
- **Writing anything.** No `edit_item`, no `remove_link` (issue #19 — still unowned), no `close_item`, no proposal path.
- **Semantic / vector search.** `topic_search` is lexical per L1 line 61. The embedder belongs to Relate's candidate pool.
- **A `query` AI-proposal path.** `query` is already an AI-callable **read** (L1 line 118); it needs no confirmation and no proposal machinery.
- **The `links` lifecycle** (issue #20) and the **schema-level `close_reason` invariant** (issue #23). Both are Engine C's and Relate's tables; §4.6 only makes Engine D tolerant of them.

## 9. Deferred to L3 (Reminder)

L3 step plans (in `plans/steps/query/`) will resolve these. Recorded so the L3 author does not forget:

1. **BM25 `k1` and `b`.** L2 fixes 1.2 / 0.75. L3 may tune them — but a change to either changes every expected score in §7.1, so the golden fixture moves with it.
2. **A result cap for `topic_search`.** L2 has none, so a one-word query over a 5 000-item database returns 5 000 hits. L3 may add a `--limit`.
3. **Status and type filters** on `topic_search` (§2.2's `Closed` decision is about search *scope*, not filters).
4. **Whether `history` needs pagination or a limit** once the ledger is large.
5. **The `unknown` `kind` fallback.** L2 defines it; L3 may decide a future vocabulary deserves its own kind instead.
6. **Plan length (housekeeping).** This L2 runs past the framework's 500-line guidance (§1 L2) even though it has none of the named exceptions (few codes, no migrations, one port). Nothing is wrong today; if the plan grows, split an appendix: §A error codes, §B the `change_log` vocabulary contract (§4.6).

## 10. Next Step (L3 step plans)

Human approves this L2 plan. Then 3 L3 step plans in `plans/steps/query/`:

- **`01-load-and-current-state.md`** — `errors.py`; `rows.py`; `lookup.py` (`QueryLookupPort`); `query_gatekeeper.py` (`validate_query_text`, `validate_query_item`); `tokenize.py`; `SqliteQueryContext`; `open_query_database` (read-only) + `ensure_query_schema`; the pure `current_state` derivation; `render.py` (the display layer, including the `Challenged`-first sort); the `ember current-state` command; the architecture-test extension; `tests/query/fakes.py` (`FakeQueryLookup`). **CLI check:** `ember current-state --db <fixture>` → JSON with the `Challenged` item first, exit 0. (**Ships a runnable CLI** — Rule S1.)
- **`02-topic-search-and-why.md`** — the BM25 scorer (tokenizer, IDF, scoring, tie-break, the zero-token guard); the pure `why` traversal (both link directions, the visited set, the transitive closure); their renderers; the `ember topic-search` and `ember why` commands; the golden BM25 fixture. **CLI check:** each command on a fixture DB.
- **`03-history-and-closeout.md`** — the `change_log` classifier (§4.6, all nine kinds); the pure `history` derivation (the `item_id` ∪ `link_id` union, the global view); the QUERY-001 item check for `history --item` (§4.7); its renderer; the `ember history` command; the E2E test (§7.6 — the engine's one E2E, runnable once all four commands exist); the README + PROJECT_MAP closeout (§11.4–11.5 — §11.1–11.3 are applied by this planning commit); verify issues #7, #22, #24 are closed with evidence; open the §9 `deferred` issues. **CLI check:** `ember history --item 1 --db <fixture>` → JSON, exit 0.

## 11. Amendments to Other Plans

Amendments to the **other plan documents** are applied by **this planning commit** — they are cross-references recording that a plan exists, which is a planning fact, not built behaviour. The amendments to **README.md** and to the code listings in `PROJECT_MAP.md` are applied by **L3 step 03**, alongside the code that makes them true.

### 11.1 `plans/master-plan.md` (L1) — applied by this planning commit

- **Line 157** — from: `Human approves L1. Then 4 L2 engine master plans: \`capture\`, \`relate\`, \`maintain\`, \`query\`. Each L2 defines internal pipeline phases for its engine.`
  to: `Human approves L1. Then 4 L2 engine master plans: \`capture\`, \`relate\`, \`maintain\`, \`query\`. Each L2 defines internal pipeline phases for its engine. All 4 are written (\`plans/engine-capture-plan.md\`, \`plans/engine-relate-plan.md\`, \`plans/engine-maintain-plan.md\`, \`plans/engine-query-plan.md\`).`
- **Line 159** — from: `**Ordering constraint on \`query\`: satisfied.** Engine C's step 03 landed on 2026-10-25, and the L1 amendments it deferred are applied: \`close_item\` has moved from the AI-callable list (rule 3, line 117) to the human-only list, and \`validate_close_item\` + \`validate_reverse_supersedes\` have joined the human-only gatekeepers (lines 81, 83). Engine D's L2 may now be written — line 117 no longer claims an AI-callable \`close_item\` exists.`
  to: `**Ordering constraint on \`query\`: satisfied.** Engine C's step 03 landed on 2026-10-25, and the L1 amendments it deferred are applied: \`close_item\` has moved from the AI-callable list (rule 3, line 117) to the human-only list, and \`validate_close_item\` + \`validate_reverse_supersedes\` have joined the human-only gatekeepers (lines 81, 83). Engine D's L2 may now be written — line 117 no longer claims an AI-callable \`close_item\` exists. The Engine D L2 is now written (\`plans/engine-query-plan.md\`); its four modes are \`current_state\`, \`topic_search\`, \`why\`, \`history\`.`

**Nothing else in L1 changes.** Engine D adds no global invariant, no stack decision, and no table. L1 §2 lines 57–66 already describe Engine D exactly as this plan builds it.

### 11.2 `plans/engine-maintain-plan.md` — applied by this planning commit

- **§0 table, row for #7** — from: `| #7 | BM25 \`topic_search\` | Engine D | not ours. |`
  to: `| #7 | BM25 \`topic_search\` | Engine D — plans/engine-query-plan.md | **this engine's job.** The mode and its BM25 formula are specified in that plan (§2.2, §4 Phase 2). Close when the Engine D L2 lands. |`
- **§0 table, row for #1** — from: `| #1 | \`items.rationale\` / \`items.source\` | Capture | not ours (Engine D's \`why\` mode needs it). Its Done-when implies an \`edit_item\` writer — §8. |`
  to: `| #1 | \`items.rationale\` / \`items.source\` | Capture | not ours (Engine D's \`why\` mode needs it — it reads \`rationale\`, and the column is NULL until a writer lands; Engine D L2 §2.4). Its Done-when implies an \`edit_item\` writer — §8. |`
- **§0, line 24 (the whole line; note items (7), (8) and (10) are untouched)** — from: `**New \`note\` issues:** (7) \`links\` rows have no lifecycle — a reversed supersedes stays \`Confirmed\` (§2 Gap C); (8) \`supersedes_ancestors\` false-rejects the corrective inverse after a reversal; (9) \`items.close_reason\` / \`status_origin\` need a matching Engine D \`history\` rendering (Engine D's L2); (10) the cross-column invariant \`Closed ⇒ close_reason IS NOT NULL\` is not enforced in the schema (spec 3.2:60).`
  to: `**New \`note\` issues:** (7) \`links\` rows have no lifecycle — a reversed supersedes stays \`Confirmed\` (§2 Gap C); (8) \`supersedes_ancestors\` false-rejects the corrective inverse after a reversal; (9) \`items.close_reason\` / \`status_origin\` need a matching Engine D \`history\` rendering (\`plans/engine-query-plan.md\` §4.6 — **issue #22**, now resolved); (10) the cross-column invariant \`Closed ⇒ close_reason IS NOT NULL\` is not enforced in the schema (spec 3.2:60).`
- **§8, line 420** — from: `- Engine D (Query) — \`current_state\`, \`topic_search\`, \`why\`, \`history\` are Engine D's.`
  to: `- Engine D (Query) — \`current_state\`, \`topic_search\`, \`why\`, \`history\` are Engine D's (\`plans/engine-query-plan.md\`).`
- **§8, line 425** — from: `- \`items.rationale\` / \`items.source\` (issue #1) — Capture's write path.`
  to: `- \`items.rationale\` / \`items.source\` (issue #1) — Capture's write path. Engine D's \`why\` mode reads \`rationale\` (\`plans/engine-query-plan.md\` §2.4); the column has no writer yet.`

### 11.3 `plans/engine-relate-plan.md` — applied by this planning commit

- **§8, line 457** — from: `- Engine D (Query) BM25 — out of scope. BM25 is Engine D's \`topic_search\` only.`
  to: `- Engine D (Query) BM25 — out of scope. BM25 is Engine D's \`topic_search\` only (\`plans/engine-query-plan.md\` §4 Phase 2).`

### 11.4 `README.md` — applied by L3 step 03

- **Line 43** — from: `- **Engine D (Query):** Planned.`
  to: `- **Engine D (Query):** Built and verified.`
- **After line 129** — add a CLI block for the four query commands, in the same style as the existing blocks:

```
**6. Query the project context (Engine D):**

```bash
ember current-state [--db PATH]
ember topic-search --query TEXT [--db PATH]
ember why --item <id> [--db PATH]
ember history [--item <id>] [--db PATH]
```

All four are read-only and never write to the database. Each prints one JSON document on stdout. `current-state` lists the `Active` and `Challenged` items with the `Challenged` ones first; `topic-search` ranks by BM25 over item statements; `why` walks the `depends_on` and `supports` links behind an item; `history` shows that item's `change_log` rows with the cause of each change, or the whole ledger with no `--item`.
```

- **Line 134** — the test count `468` is stale by then; update it to the real number from the test run.

### 11.5 `PROJECT_MAP.md` — applied by this planning commit (plan file) and by L3 step 03 (the code)

- **This planning commit:** add `plans/engine-query-plan.md` to the Planning Documents section.
- **L3 step 03:** add `ember/query/` (every module), `tests/query/` (every file, including `tests/query/__init__.py` and `tests/query/fakes.py`), the `SqliteQueryContext` adapter and `open_query_database` / `ensure_query_schema` to the `ember/adapters/sqlite.py` entry, the four `ember query` commands to the `ember/cli.py` entry, the fourth architecture test to the `tests/test_architecture.py` entry ("Asserts the capture, relate, maintain, and query engine cores never import an adapter"), and the `link_type_compat` note is **not** added here (that is issue #17, not Engine D).

## Z. Constitution Compliance

**Three tables.** (a) touched & satisfied with a §ref; (b) N/A with a reason; (c) knowingly deviated, with a §ref and a justification. Rows marked `—` are spec/L1 readings, not Constitution rules.

**(a) Touched & satisfied:**

| Rule | §ref |
|---|---|
| B1 one job | §1 — four read modes over one read port. |
| B2 public calls only | §4.5 — the core reads only through `QueryLookupPort`; it never touches another module's tables. The tables it reads are the L1 §3 shared contract, mediated by the single SQLite boundary. |
| B3 depend on stable things | §4.5 — the core depends on the port and on Pydantic row models, not on SQLite. |
| B4 hide volatile decision | §4.5 — the DB is behind the port; the pure core never sees a connection. |
| B5 deep module | §4.5 — four coarse port methods cover the whole world, and BM25 needs the whole corpus anyway, so the interface stays small while the work stays inside. |
| D1 raw data immutable | §1 — this engine writes nothing, not even at boot (§2.6). |
| D2 derived rebuildable | §4 Phase 2 — the BM25 score is derived from raw statements and recomputed on every run; nothing is cached. |
| D3 single source of truth | §4.6 — `change_log` is the ledger of record for status history; `items.status` / `close_reason` / `status_origin` are derived caches owned by Engine C. Engine D reads both and reconciles nothing: a divergence between them is observable in `history` but is not repaired here. |
| D4 outside data untrusted | §4.7, §5 — the `--query` and `--item` flags are validated in the command body and by the gatekeeper before the core sees them. |
| D5 prefer new optional fields | §3 — no schema change at all. |
| D6 numbered migrations | §3 — this engine ships no migration and applies none; it reads the version the runner maintains. |
| P1 pattern solves a concrete problem | §4 Phase 2 — the FTS5 and `rank_bm25` rejections, and the dead-`QueryStorePort` rejection (§4.5), are all "no decorative architecture" calls. |
| P3 pipeline | §4 — four fixed phases in one direction: Load → Derive (pure) → Render → CLI. Data is passed explicitly between phases; there is no hidden shared state. |
| P4 ports & adapters | §4.5 — `QueryLookupPort` is the port; `SqliteQueryContext` fits the volatile tool (SQLite) to it. |
| I1 name by job | §4 Phase 2, §4.7 — `topic_search`, `why`, `history`, `run_why`, `validate_query_item`. |
| I2 no boolean behaviour flags | §4, §5 — one command per mode; no `--mode` flag, no mode argument in any function, no boolean reaches a function. |
| I3 max 4 inputs | §4.7 — `run_current_state(lookup)` takes 1 input; the other three take 2. All are at most 4. |
| I4 named object, no tuples | §4.5 — every return value is a Pydantic model or a list of them; an empty result is an empty list. |
| I6 one base error | §6 — `QueryError(EmberError)`. |
| I7 fail fast, handle at edge | §4.7, §5 — the gatekeeper runs before the core; the CLI is the only catcher. |
| I8 design error away | §5, §6 — an empty result is a success with `count: 0`, not an error (§6, "An empty result is not an error"). Only a *missing item* is an error, because the user asked about a specific id. |
| I9 validate at edge | §4.7, §5 — flags validated in the command body, existence and text validated by the gatekeeper; the core trusts them. |
| I10 stable interface | §4.5 — the row models and the §4 Phase 3 envelope are the contract L3 implements. |
| I11 function contract | §4.5, §4.7 — every port method lists the code it raises; §6 lists the raising site of every code. |
| I12 CLI contract | §5 — explicit flags, 0/1/2 exit codes, JSON on stdout, `error: {log_line()}` on stderr. Exit 2 is Click usage errors only: this engine has no prompt, so no user abort and no `UserAbort` code. I12 needs only a non-zero fail, so this is satisfied, not a deviation. |
| I13 config at boot | §5 — the DB path is the only configuration and it is read once at boot; there is no env var, no API key and no model name. |
| I17 stable codes | §6 — `QUERY-000` … `QUERY-005`, contiguous, no gaps, no reuse. |
| I18 module.function injected | §6 — inherited from `EmberError`; no subclass defines `__init__`, so the location is the raiser. |
| I19 entity IDs in errors | §6 — `item_id` for a missing item, `version` / `required` for an outdated schema, `table` for a read failure, `db_path` for an unopenable file, `query_length` for an empty query. The path is carried only where the raising function has it. |
| I20 one-line logging | §5, §6 — `error: {exc.log_line()}` to stderr. QUERY-002 carries a length, not the user's text (§6), so the line cannot be broken by a newline in the query. |
| I21 codes + tests | §6 + §7.5 — every code has a named raising site and a test target. |
| T1 pure core | §4 Phase 2 — no I/O, no clock, no DB, no printing. |
| T2 push side effects to edges | §4.5 — the DB is the only side effect and it sits behind the port; stdout belongs to the CLI. |
| T3 prefer fakes | §7.1, §7.6, §10 — `FakeQueryLookup` (named in §10, step 01) for the unit tests; the house fakes for the E2E chain. |
| T4 test pyramid | §7 — ~25 unit, ~10 integration, 8 CLI, 1 E2E, 0 live. |
| T5 test boundaries | §7 — asserts on JSON output and raised codes, not on internals. |
| T6 good targets | §7 — contract promises, edge cases, expected codes. |
| T9 architecture test | §7.3 — `ember/query/*.py` must not mention `sqlite3` or `ember.adapters`. |
| T10 painful test setup | §7.2 — the integration tests use the real boot path, so the read-only guarantee is testable by hashing the file rather than mocked. |
| S1 run alone | §5 — each of the four commands runs the whole path on a fixture DB. |
| S2 dedicated suite | §10 — `tests/query/`. |
| S3 document input/output | §4.5 — every row model and the §4 Phase 3 envelope are specified. |
| S4 explicit data transfer | §1, §4.5 — the SQLite file is the transfer mechanism (the input tables in §1, read through the port in §4.5). |

**(b) N/A, with reason:**

| Rule | Reason |
|---|---|
| D7 no manual edits to production data | This engine never writes, so there is no production data for a manual edit to damage. |
| D8 save raw model response | Engine D makes no AI call (§2.5). |
| I14 web API | No web API in V1. |
| I15 external services | No external service — a local SQLite file. |
| I16 AI output schema | No AI call. |
| T7 AI fixture testing | No AI parser. |
| T8 AI evaluation benchmark | No AI. |

**(c) Knowingly deviated, with justification:**

| Rule | Deviation | Justification |
|---|---|---|
| B6 warning signs | `ember/adapters/sqlite.py` grows a 4th context class plus a boot pair; `ember/cli.py` grows 4 commands. | The file is already the house's single SQLite boundary. The warning sign to watch is **splitting** it, not growing it. The `import` list is long, but each name is a stable public error or row model. |
| D3 single source of truth | `ChangeRow` is a second shape for the `change_log` table. | `ChangeLogEntry` is a **write** model whose `item_id` is non-nullable; Capture writes `proposed` rows with a NULL `item_id` (`sqlite.py:860-875`). The read side needs the nullable shape, so the two differ by design, not by accident. `Link` has no such difference and **is** imported, not copied. |
| P2 layered | The CLI → core → adapter layering is kept even though P2 says avoid it for one-way flows. | This is a one-way read flow. The layering stays because **T9's architecture test requires the core/adapter seam** — without it, the engine core would import `sqlite3` and the whole boundary would be unenforceable. |
| I5 split failure modes | `DbOpenFailed` covers several triggers (missing file, not a SQLite file, version read failed, hot journal). | House-consistent: `RELATE-012` and `MAINTAIN-007` do exactly the same. One code per failure *site*, not per prose sub-case. |
| I19 entity IDs | `SchemaOutdated` carries no path, and `DbOpenFailed` carries no version. | The raising function has what it has: `open_query_database` knows the path, `ensure_query_schema` knows the version. This matches the house's `SchemaOutdated` (`sqlite.py:151-155`). |
| — | The boot path never migrates, so a database behind version 10 is refused rather than upgraded. | §2.6 — a read command that rewrites the ledger is not a read, and L1 rule 1 forbids an AI-callable write. The cost is one command for the user to run first. |
| — | `topic_search` returns `Closed` items; `current_state` does not. | L1 line 60 states the Closed omission for `current_state` and line 61 does not state it for `topic_search`. The contrast is read as deliberate (§2.2), and the fix is one filter if that reading is wrong. |

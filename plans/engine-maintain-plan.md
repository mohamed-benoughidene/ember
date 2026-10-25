# L2 Maintain Engine Master Plan

Terse caveman style. Source: L1 (`plans/master-plan.md`) + V1 spec 3.2/3.3/3.5/3.6/3.7. No invention.

**Stack:** see L1 §0. Maintain-specific deviation: none. Maintain adds **no dependency** — no AI, no embedder, no network (first engine with no live tier). It reads `items` / `links` / `change_log` and writes `items` + `change_log`.

## 0. Deferred Issues This Engine Owns

| Issue | Subject | Owner | Action |
|---|---|---|---|
| **#6** | status cascade propagation | **Engine C** | **this engine's core job.** The L2 names the cascade rules (§4). Close **when the Maintain engine merges**, with a comment: the cascade is expressed on `items.status`, not on `links`; link statuses stay `Confirmed`/`Rejected` by design (spec 3.3, migration 006's CHECK forbids a third value). |
| **#9** | `supersedes` reversal | **Engine C** | **the reversal.** The L2 names the dispatch vocabulary (§4.6). Close **when the Maintain engine merges**, with a comment recording: the reversal is an item-status event — it writes **no** `links` row and does not change `links.status`; the marker is `field_changed='link_reversed'`; Engine C **sweeps** `links`, it does not listen for events; dependents stay `Challenged` (spec 3.5:111); the rule-2 vocabulary is `dependency_closed`. |
| #1 | `items.rationale` / `items.source` | Capture | not ours (Engine D's `why` mode needs it). Its Done-when implies an `edit_item` writer — §8. |
| #5 | `items.metadata` | Relate | not ours. |
| #4 | external vector DB | Relate | not ours. |
| #7 | BM25 `topic_search` | Engine D | not ours. |
| #8 | `Signals` wrapper | Relate | not ours. |
| #12 | embedder re-validation at scale | Relate | not ours. |

**Closed when:** the Maintain engine ships — **#6 and #9 closed on 2026-10-25 in <COMMIT_SHA>**, with the comments above. Closing them was **step 03's deliverable** (§10), not a planning task: the issues stayed open until the code that satisfies them was merged.

**New `deferred` issues filed by this plan:** (1) re-challenge an item after a human clears it manually (§2 Gap B/B4); (2) re-supersede the same `(source, target)` pair after a reversal; (3) AI-proposed `close_item`; (4) enforce the link compatibility table at the database level (spec 3.6:115); (5) plain-text export command (spec 3.6:118) — **no engine owns it**; (6) `edit_item` + `remove_link` (spec 3.7:130, :133) — **no plan owns them** (`remove_link` is also the only way to delete a link; `edit_item` is the likely writer for issue #1's `items.rationale`/`source`).

**New `note` issues:** (7) `links` rows have no lifecycle — a reversed supersedes stays `Confirmed` (§2 Gap C); (8) `supersedes_ancestors` false-rejects the corrective inverse after a reversal; (9) `items.close_reason` / `status_origin` need a matching Engine D `history` rendering (Engine D's L2); (10) the cross-column invariant `Closed ⇒ close_reason IS NOT NULL` is not enforced in the schema (spec 3.2:60).

**Also filed:** **#24** (`deferred`) — the Engine D (Query) L2 must not be written until this plan's §11 amendments land. Tracked there so the dependency is enforced by the issue list, not only by a note in this file.

## 1. Engine Job

Keep the graph coherent when items and links change. Read `items` + confirmed `links`, derive the status each item should have, write the difference, log every change. Engine 3 of 4. Four deterministic triggers, zero AI.

Trigger directions — verified against `ember/relate/compat.py:13-25` (all 4 correct; re-verify at implementation time):

| Rule | Direction in `compat.py` | Effect |
|---|---|---|
| 1 `supersedes` | source → target, same type | closes the **target**, reason `superseded` |
| 2 `depends_on` | (`Decision`→`Assumption`/`Finding`/`Decision`), (`Assumption`→`Finding`/`Assumption`). **The dependent is the SOURCE; the thing depended-upon is the TARGET.** | challenges the **source** of a `depends_on` whose **target** is flagging-closed |
| 3 `contradicts` | `Finding` → `Assumption`/`Decision`/`Finding` | challenges the **target** |
| 4 `answers` | (`Decision`/`Finding`) → `Question` | closes the **target** if it is a `Question`, reason `answered` |

- Status model `Active` / `Challenged` / `Closed`. Close reasons `answered`, `invalidated`, `superseded`, `reversed`, `expired`. **Spec 3.2:60: "Closed: … Requires close reason."**
- Flag spread **single-step only**. No cascade. "The user inspects the `Challenged` list to resolve items."
- `Challenged` resolution is **human-only** via `set_status` (`Active` ↔ `Challenged` only).
- Items are never deleted. `change_log` is append-only and never edited.
- Maintain **does not delete or rewrite history**. It moves `items.status` forward and appends `change_log` rows.
- **Links are immutable.** Maintain never writes `links`. A reversal is an **item event plus a `change_log` marker**, not a link mutation (§2 Gap C).
- **Content is immutable; status is the point.** Spec 3.2:62's "Historical items immutable" protects the item's *text*. `items.status` and `items.close_reason` are derived state, and mutating them is mandated by spec 3.2/3.5. Precedent: `set_validated` already mutates a column on an existing item (`sqlite.py:579`).
- L1:53's **self-fix for typos** is named: the user creates a new item with a `supersedes` link to the typo'd one; the old typo gets `Closed` reason `superseded`; the new corrected item is live. **This journey works under this plan** — a reversal does not permanently veto future closes (that was v2's bug).

## 2. Engine-Specific Deferrals from L1 (Resolved at L2 Start)

L1 §9 deferred 3 items, all to Engine B. **Nothing is deferred to Engine C at L1.** This section records that and resolves the **two obligations the L2 Relate plan handed over**:

- **Relate §9 #8** ("Engine C dispatch vocabulary … Engine C L2 author confirms the dispatch table") → **resolved.** Maintain does **not** listen to `change_log` for *events*. It reads the `links` table (`status='Confirmed'`) to know what is live. There is no dispatch table because there is no event bus — L1:70 "Engine-to-engine flow goes through DB rows, not direct function calls." Maintain's dispatch table is the `links` table + `items.status`. The vocabulary Maintain **writes** is fixed in §4.6. The one `change_log` read is a *state lookup* for links this engine itself reversed — not a dispatch.
- **Relate §8** ("Engine C listens for the `trigger_cause='user_confirmed'` + `link_id` FK pattern (post-008) and writes the cascade `change_log` rows") → **superseded** by the above. Amendment to `plans/engine-relate-plan.md` §8 and §9 #8 (§11).

Also recorded: **Maintain calls no AI** (§4.0).

### 2.1 The design gaps, and how they are closed

**Gap A — `close_reason` has nowhere to live.** Migration 010 adds `close_reason TEXT` (nullable, CHECK against the 5 reasons). `status_origin` is a **second** column, added for Gap B. Both ship in 010.

**Gap B — the sweep vs. the human's manual clear.**

- **B1. Escalation-only.** The sweep moves an item **up** the ladder `Active → Challenged → Closed` only. It never writes `Active` over a `Challenged`/`Closed` item. This makes AI spec 3.5:111 ("Dependents flagged Challenged remain Challenged until human clears") true **by construction**.
- **B2. The shield is scoped to the human-clear.** `status_origin='manual'` means exactly one thing: *"the human cleared this item's `Challenged` flag; do not re-derive it."* It is set **only** by `ember set-status --to Active` on a `Challenged` item. **Not** by `close-item` (a human close is a *derived* close, so it must not freeze the item). **Not** by `reverse-supersedes` (see Gap C — v2's mistake was making the shield a permanent veto over rule 1). **Not** by `set-status --to Challenged` (challenging is not a resolution; spec 3.2:70 lists human-`Challenged` as a first-class state).
- **B3. No-op → no write.** `set-status --to <current status>` writes **nothing** and exits 0.
- **B4. Known V1 limitation (deferred issue).** Because of B2, a *new* contradiction confirmed later on a human-cleared item will **not** re-flag it. Fixing that needs per-trigger acknowledgment. Deferred, not invented.
- **B5. `validated` does not shield.** AI spec 3.5:110's "Validated assumption remains `Active`" is read as *the validated flag does not itself change status* — which is how Capture implemented it (`set_validated` never touches `status`, `sqlite.py:579`). A validated Assumption **can** become `Challenged` under rule 2. **Knowingly deviated — §Z(c).**
- **B6. Deleted as a separate rule.** Escalation-only (B1) already guarantees a human's `close_reason` is never overwritten by a machine close — the sweep never re-closes a `Closed` item. B6 was a redundant second filter that could never fire. Its §7.1 test is kept, re-pointed at B1.

**Gap C — reversal vs. the immutable `links` table.** v1 was wrong (it needed a false claim about Relate's gatekeeper, mutated an immutable table, and needed a table rebuild whose safety argument was false since SQLite 3.26). v2 was also wrong (it made the shield a permanent veto, silently swallowing any *future* supersedes onto a restored item — breaking L1:53's self-fix journey). **The reversal needs no link mutation, no migration, and no shield.**

**Key insight:** the reversal is itself **a fact recorded in `change_log`**, and the sweep reads `change_log` for exactly one thing: *has this item's `supersedes`-close been reversed?* That is not an event bus — it is reading the current state of a fact the engine itself wrote.

1. `ember reverse-supersedes --item N --link <id>` requires: item N exists (`MAINTAIN-001`); N is `Closed`; N's `close_reason` is `superseded`; and the Confirmed `supersedes` link `<id>` points **at** N. Otherwise → `MAINTAIN-005`.
2. It restores N to `Active`, clears `close_reason`, and writes **two** `change_log` rows:
   - `field_changed='status'`, `old_value='Closed:superseded'`, `new_value='Active'`, `trigger_cause='reversal'`, `link_id=<id>`, `item_id=N`.
   - `field_changed='link_reversed'`, `old_value='Confirmed'`, `new_value='Reversed'`, `trigger_cause='reversal'`, `link_id=<id>`, `item_id=N`.

   **The second row is the reversal marker.** The sweep reads it: a `supersedes` link with a `link_reversed` row is **not** a live supersedes.
3. **`status_origin` is NOT set.** N is `Active` with `close_reason=NULL`. The sweep's rule 1 will **not** re-close it, because the `supersedes` link is marked reversed and the sweep skips reversed links.

**Why the `links` row stays `Confirmed`:** the link is a **historical fact** — the human *did* confirm that supersedes link at that time. The reversal is a **new event**, appended to the ledger. This satisfies human spec 3.6:113 ("Every change to a note **or link** adds a row to an audit ledger") — the change *is* logged, in the `link_reversed` row. `links.status` keeps its 2-value enum (migration 006's CHECK), so **L1:74 needs no amendment**.

**What the marker costs — a `change_log` read in Phase 1.** The sweep needs to know which links are reversed. One extra read: `SELECT DISTINCT link_id FROM change_log WHERE field_changed='link_reversed'`. One query, one set, folded into the snapshot. Not an event bus (no dispatch, no triggers, no cross-engine coupling) — a lookup of a fact this engine wrote.

| Consumer | With the link left `Confirmed` + a `link_reversed` marker | Loss? |
|---|---|---|
| Sweep rule 1 | the link is marked reversed → **skipped**; N is never re-closed | **none** |
| Sweep rule 2 | dependents stay `Challenged` (escalation-only) | **none** (spec 3.5:111 wants exactly this) |
| Relate `neighbors_of` | the edge is still there → one extra graph candidate | cosmetic |
| Relate `supersedes_ancestors` | the chain stays intact → a corrective `B→supersedes→A` is rejected with `RELATE-028` (rule 8) | **one false reject — the corrective inverse** |
| Relate gatekeeper rule 9 | the triple still exists → **re-superseding the same pair is blocked** | **real, and accepted** |
| Relate `--latest` | the source item stays "linked" → excluded from `--latest` | cosmetic (pre-existing: the query has no status filter) |
| Engine D `why` | traverses `depends_on`/`supports` only → unaffected | none |

**The one accepted regression is the corrective inverse:** reverse `A→supersedes→B`, then try `B→supersedes→A` (fixing the *direction* rather than the fact) → `RELATE-028`, because the retained `A→B` row still feeds `supersedes_ancestors`. Minimum setup: 2 items, 1 link, 1 reversal, 1 proposal. **A gatekeeper message, not corruption** — the user sees "cycle detected" while trying to undo a mistaken supersede. Confusing but safe. Deferred note.

**The re-superseding block:** the pair `(source, target, 'supersedes')` is permanently taken by the `UNIQUE` constraint (migration 006) and by gatekeeper rule 9 — `find_existing` returns a row of *any* status (`sqlite.py:296`), and rule 9 blocks on `is not None` (`link_gatekeeper.py:117`). Reversal restores the *old item* to `Active`; it does not free the pair. **But a *new* supersedes from a different source onto the restored item works normally** — the v2 bug, fixed.

**`supersedes_ancestors` should exclude reversed links** — `sqlite.py:428` reads `links WHERE source_item_id = ? AND link_type='supersedes' AND status='Confirmed'`. To drop reversed edges the query would need the reversal marker, i.e. `SqliteLinkContext` would need to know about `change_log` — that crosses the engine boundary. **Decision: do NOT change it.** The false reject is accepted. **Relate stays untouched — no Relate adapter changes at all.**

## 3. New Table Columns (Migration 010) + Boot

`ember/adapters/migrations/010_add_item_close_reason.sql` — one migration, two columns:

```sql
ALTER TABLE items ADD COLUMN close_reason TEXT
    CHECK (close_reason IS NULL OR close_reason IN
           ('answered','invalidated','superseded','reversed','expired'));
ALTER TABLE items ADD COLUMN status_origin TEXT NOT NULL DEFAULT 'derived'
    CHECK (status_origin IN ('derived','manual'));
```

- **No table rebuild. No `PRAGMA`. No `BEGIN`/`COMMIT`** — the runner owns the transaction: `PRAGMA foreign_keys = OFF` outside the transaction (`sqlite.py:109-115`), each script wrapped in `BEGIN; … UPDATE schema_version …; COMMIT;` (`sqlite.py:118-135`). **Scripts must be plain statements.**
- `ALTER TABLE … ADD COLUMN` with a CHECK is legal in SQLite; only PRIMARY KEY / UNIQUE / NOT-NULL-without-default are refused. **Exact precedent in this repo:** `004_add_item_detail_columns.sql` is already two bare `ALTER TABLE items ADD COLUMN` statements. 010 is the **first** migration here whose `ADD COLUMN` carries a CHECK.
- **SQLite version:** the repo pins `requires-python = ">=3.12"` but **does not pin SQLite**, and CPython 3.12 requires only SQLite ≥ 3.15.1. Since **3.37**, an added CHECK **is** tested against pre-existing rows. Both checks pass on existing rows (`close_reason` is NULL → the `IS NULL` branch is TRUE; `status_origin` takes the default `'derived'`). On < 3.37 the CHECKs are skipped and the data still satisfies them — **010 succeeds either way.** The non-empty-DB test in §7.2 pins the behaviour on whatever SQLite CI has.
- `close_reason` is set to `NULL` again when an item is reopened (reversal). The destroyed reason survives in `change_log.old_value` (`'Closed:superseded'`).
- `status_origin` is `'manual'` **only** after `ember set-status --to Active` on a `Challenged` item. **Not** after `close-item`, **not** after `reverse-supersedes`, **not** after `set-status --to Challenged`.
- **No cross-column CHECK** (`status='Closed' ⇒ close_reason IS NOT NULL`) is added: SQLite's `ADD COLUMN` CHECK restrictions are unclear for cross-column references, and the invariant is enforced in the write path instead (§4 Phase 3). Recorded as a §Z(c) deviation.
- **No new tables.** Maintain reuses `items`, `links`, `change_log`. **`change_log` needs no migration** — `field_changed` and `trigger_cause` have no CHECK constraint (migration 003), so the new vocabulary is schema-legal.
- `items` (migration 002) has `status` but **no `close_reason`**, so rule 2 cannot fire without a reason. **Nothing writes `items.status` today:** the only `items` writes are `INSERT` (`sqlite.py:521`) and `UPDATE items SET validated` (`sqlite.py:579`). Maintain is the first engine to mutate status. Pre-010 rows are all `Active` → **no backfill needed.**
- After 010 the schema version is **10** — the `schema_version` **table** row, not `PRAGMA user_version`.

### 3.1 Boot: `open_maintain_database` + `ensure_maintain_schema`

**`open_maintain_database(db_path) -> sqlite3.Connection`** — new, in `ember/adapters/sqlite.py`, mirroring `open_relate_database` (`sqlite.py:56-83`):

1. `if not os.path.exists(db_path): raise DbOpenFailed("db file missing", db_path=db_path)`
2. `_connect(db_path)` + a `SELECT COUNT(*) FROM sqlite_master` probe; on `sqlite3.Error` → `DbOpenFailed`.
3. `_apply_migrations(conn)`; on `(sqlite3.Error, ValueError)` → `DbMigrationFailed`.
4. `ensure_maintain_schema(conn)` → `version >= 10`; on failure → `SchemaOutdated`.

**`ensure_maintain_schema(conn)`:** `SELECT version FROM schema_version` → on `sqlite3.Error` → `DbOpenFailed`; `version < 10` → `SchemaOutdated`.

**Why not `open_database`:** it **creates** a missing DB (`sqlite.py:49-53`) and wraps nothing, so a corrupt file leaks a raw `sqlite3.Error` past the CLI's `except EmberError` (violating I20), and `MAINTAIN-007` would be unreachable. Maintain's DB always exists (Capture or Relate created it), so refusing a missing file is the right behaviour. `MAINTAIN-009 SchemaOutdated` is defensive — `open_maintain_database` migrates before it checks — but it is the house pattern (`ensure_relate_schema`, `sqlite.py:86-98`) and is reachable via a monkeypatched `_apply_migrations`, exactly as `tests/test_relate_db_open.py:42-54` already does.

**Do NOT change `ensure_relate_schema`'s floor of 9.** `tests/test_relate_db_open.py:79` asserts `context["required"] == 9`. Relate must keep accepting a v10 DB. The 5 test edits in §7.2 are exactly: 4 × `version == 9` → `10`, and the `items` column list.

## 4. Pipeline (4 Phases)

```
[ember maintain | ember close-item | ember set-status | ember reverse-supersedes]
   |
   v
Phase 1: Load     (items + confirmed links + reversed-link ids -> MaintainSnapshot)
   |
   v
Phase 2: Derive   (PURE — compute the status changes)
   |
   v
Phase 3: Apply    (atomic write: UPDATE items + INSERT change_log)
   |
   v
Phase 4: Report   (print what changed)
```

**4.0 Maintain calls no AI.** The four triggers are deterministic (AI spec 3.5: "Maintain Rules (Deterministic, Zero AI)"). `close_item` is listed in AI spec 3.7:126 under "AI-callable proposals (Require user confirmation)". **V1 implements it as a human-invoked command** (`ember close-item --item N --reason R`) — the human running the command *is* the confirmation. **Corrected justification:** `close_item` is the **only** path that produces the `invalidated` and `expired` close reasons (no deterministic rule generates them; rules 1/4 produce `superseded`/`answered` only), so it cannot be dropped. The reason to keep it human-invoked is that an AI proposal would add a prompt, a parser, an `ai_responses` row, a retry policy, and a cost to produce a decision a human can make explicitly with one flag. **This needs an L1 amendment** (§11). A deferred issue records "AI-proposed close_item" for V1.x. Spec 3.7:126's "User confirms" is satisfied by the human invoking the command — recorded as a §Z(c) deviation.

### Phase 1 — Load

Three reads:

1. all `items` (id, type, status, close_reason, status_origin)
2. all `links` where `status='Confirmed'`
3. the reversed-link ids: `SELECT DISTINCT link_id FROM change_log WHERE field_changed='link_reversed'`

Output: `MaintainSnapshot(items: list[ItemState], links: list[Link], reversed_link_ids: set[int])`.

Zero `CREATE INDEX` exists in migrations 001-009 besides the implicit UNIQUE and PKs, so the `WHERE status='Confirmed'` scan is a full scan. At the spec's 5000-item ceiling that is fine and cheaper than Relate's cosine pass — stated, not assumed.

### Phase 2 — Derive (pure)

`derive_status_changes(snapshot) -> list[StatusChange]`. No I/O, no clock, no DB. Deterministic. Order:

1. **Closes** — for each Confirmed `supersedes` link **not in `reversed_link_ids`**, the target's desired close reason is `superseded`; for each Confirmed `answers` link whose target is a `Question`, the desired reason is `answered`. **Tie-break:** if the same target is hit by both, `superseded` wins.
2. **Challenges** — every target of a Confirmed `contradicts` link; plus every **source** of a Confirmed `depends_on` link whose target is a *flagging-closed* item. "Flagging-closed" = currently `Closed` with reason `invalidated`/`superseded`/`reversed`, **or** being closed in this same sweep with one of those reasons. (`answered` and `expired` do **not** flag dependents — AI spec 3.5:103.) **Single step only**: no recursion.
3. **`merge_and_filter(candidates, snapshot) -> list[StatusChange]`** — the shared Phase-2 boundary. **All four commands run it.**
   - **ONE CHANGE PER ITEM.** The candidate list may contain several changes for one `item_id` (e.g. a `Decision` that is both superseded and contradicted — `compat.py:16` + `:21`). The merge keeps **exactly one** per item: precedence **`Closed > Challenged`** (a close outranks a challenge; a challenge outranks no-change). Without this, Phase 3 would write two UPDATEs (last wins) and two `change_log` rows, one of which is false.
   - **Escalation-only, stated positively:** a *derived* change is dropped unless it moves the item **strictly up** the ladder `Active < Challenged < Closed`. A change whose `new_status` equals `old_status` is dropped, and a change that moves **down** the ladder is dropped. So an item already `Challenged` is not re-written, and an item already `Closed` is not re-closed. (This is also why a human's `close_reason` is never overwritten by a machine close — v2's B6 is subsumed.)
   - **Scope: escalation-only applies to DERIVED changes.** The three human validators' *primary* `StatusChange` is **authoritative and exempt from the ladder check** — a human may move an item down (`Challenged → Active`, `Closed → Active`) or sideways (`Challenged → Closed`). Escalation-only still governs the rule-2 **fan-out** (a dependent that is already `Challenged` or `Closed` is not re-challenged) and the sweep.
   - An item with `status_origin='manual'` is skipped (the shield, B2).
   - Result: `list[StatusChange]`, ≤1 per `item_id`.

### Phase 3 — Apply

**The transport is specified, because the house pattern will otherwise break atomicity. Copy `insert_link_with_log` (`sqlite.py:655-708`), NOT `save_validated_flag` (`sqlite.py:572-596`).** The latter commits per method; the former is the only writer in the codebase with one commit and a rollback in every `except`. Every other writer commits per method (`sqlite.py:196,534,551,568,594,637,779,821`). The rules:

- **Exactly one `commit()`, at the very end.** Never inside the loop.
- **An explicit `rollback()` in every `except` branch** — even though no commit has happened. sqlite3 leaves the implicit transaction open on exception, and the next `commit()` on that connection (test teardown, the next statement) would commit the partial batch.
- **One `BEGIN` for the whole batch** — do not rely on the implicit transaction and do not let any helper commit.

The batch is: for each `StatusChange`, `UPDATE items SET status=?, close_reason=? WHERE id=?`; then for each `StatusChange`, `INSERT INTO change_log (...)`. Then `COMMIT`. All-or-nothing.

- **No `status_origin` in the UPDATE.** The sweep only writes items whose `status_origin` is `'derived'`, so writing it is a no-op that invites "can the sweep un-manual an item?" (it must not). The shield is written by the **`set-status` command only**, in its own write path, and **logged as its own `change_log` row** (`field_changed='status_origin'`).
- **`change_log.timestamp` is `NOT NULL`** and `StatusChange` does not carry it. **The adapter stamps it from an injected clock:** `SqliteMaintainStore(conn, *, clock: Callable[[], str] | None = None)`, defaulting to `_utc_now`. This is the house pattern (`SqliteItemGatekeeper`, `SqliteSourceStore`, `SqliteEmbedderStore` all take `clock=`). The pure Phase 2 stays clock-free (T1).
- **All four commands use the same Phase 1-3 pipeline.** They differ only in Phase 2: `derive_status_changes(snapshot)` (the sweep), `validate_close_item(snapshot, item_id, reason) -> list[StatusChange]`, `validate_set_status(snapshot, item_id, to) -> list[StatusChange]`, `validate_reverse_supersedes(snapshot, item_id, link_id) -> list[StatusChange]`.
- **The three validators are authoritative.** Their **primary** `StatusChange` is **exempt from the escalation-only ladder check** and from the manual-shield skip — a human may move an item down, and a human command may act on a shielded item. Their output **does** pass through `merge_and_filter`'s one-per-item rule, so `close-item` on an item whose dependent is already `Challenged` does **not** re-challenge it.

### Phase 4 — Report

One line per change (`item 3: Active -> Closed (superseded)`) + a summary. **The buckets must cover every row of §4.6**, including a reopen: `closed: 1, challenged: 2, reopened: 1, unchanged: 38`. (`unchanged` = total items − changed items. A `reopened` bucket exists because `reverse-supersedes` and `set-status --to Active` move `Closed → Active` / `Challenged → Active`, which v2's buckets had no place for.)

**One `format_report(changes, total_items) -> list[str]` is used by BOTH the dry-run and the real run.** Otherwise the dry run and the real run describe the same batch differently, and the flag is worse than useless. It lives in `ember/maintain/report.py` and **ships in step 01**, so step 01 can offer a runnable CLI; step 02 reuses it for the real run.

**Report format** (fixed, so the dry run and the real run agree):
- Line: `item <id>: <old_status> -> <new_status>`, plus ` (<close_reason>)` when the item is closed.
- Ordering: by `item_id` ascending; the summary is always last.
- Summary: `closed: N, challenged: N, reopened: N, unchanged: N` — the four buckets are fixed and not extended. Items skipped because they were `manual` are **not** reported.

### 4.5 Ports + Data Models

**`MaintainLookupPort`** — in `ember/maintain/maintain_lookup.py` (engine core, `typing.Protocol`):

- `list_items() -> list[ItemState]` — every item: id, type, status, close_reason, status_origin. Raises `MAINTAIN-010`.
- `list_confirmed_links() -> list[Link]` — every `links` row with `status='Confirmed'`. Raises `MAINTAIN-010`.
- `list_reversed_link_ids() -> set[int]` — the `link_id`s that have a `link_reversed` row. Raises `MAINTAIN-010`.

**One read code for all three** — Relate's `SqliteLinkContext` lumps items+links reads into `RELATE-016` and splits out only the BFS as `RELATE-021`; Maintain has no BFS, so a split by table would be a distinction no caller acts on.

**`MaintainStorePort`** — in `ember/maintain/apply_status.py`, next to its consumer (the rule is "next to the function that calls it": `LinkStorePort` lives in `confirm_write.py`; `AiResponseStorePort` has its own file — the codebase does both):

- `apply_status_changes(changes: list[StatusChange]) -> int` — one transaction, all-or-nothing; returns the number applied. Raises `MAINTAIN-011` on the items UPDATE, `MAINTAIN-012` on the change_log INSERT (both roll the batch back).
- **The int is `len(changes)` or it raises.** It cannot differ (all-or-nothing). It exists because I4 prefers a value over `None`.
- `apply_status_origin(item_id: int, origin: str) -> None` — the `set-status` command needs one more write, because the shield is its own `change_log` row. Writes `items.status_origin` **and** its `field_changed='status_origin'` row in one transaction. Raises `MAINTAIN-011` / `MAINTAIN-012`.
- `apply_reversal(change: StatusChange, marker: ChangeLogEntry) -> int` — the reversal writes the item restore, the `status` log row, **and** the `link_reversed` marker row in **one transaction**. `apply_status_changes` derives `field_changed='status'` for every row and `StatusChange` has no `field_changed` field, so no other call can produce the marker; and a second port method would mean two commits, breaking the one-transaction guarantee. `ChangeLogEntry` is imported from `ember.relate.rows`. Raises `MAINTAIN-011` / `MAINTAIN-012`.

**Adapters:** `SqliteMaintainContext(conn)` implements `MaintainLookupPort`; `SqliteMaintainStore(conn, *, clock=None)` implements `MaintainStorePort`. Both in `ember/adapters/sqlite.py` — all `sqlite3` lives there (Rule T9).

**Data models** (engine core, `ember/maintain/rows.py`):

- `ItemState(id: int, type: str, status: str, close_reason: str | None, status_origin: str)`
- `Link` — **IMPORTED from `ember.relate.rows`, not duplicated.** `sqlite.py:36` already does `from ember.relate.rows import ChangeLogEntry, Link, NewItem`; duplicating the model would force a second import of the same name into the very file being edited, and would create two shapes for one table (D3). `ember/relate/rows.py` imports only `enum` + `pydantic` — safe to import, and it does not trip the architecture test (which globs `ember/maintain/*.py` for the string `ember.adapters`).
- `MaintainSnapshot(items: list[ItemState], links: list[Link], reversed_link_ids: set[int])`
- `StatusChange(item_id: int, old_status: str, new_status: str, close_reason: str | None, old_close_reason: str | None = None, trigger_cause: str, link_id: int | None)` — **7 fields.** v2's `old_value`/`new_value` duplicated `old_status`/`new_status`/`close_reason` in a second encoding, which could disagree with the first. **The `change_log` encoding is derived in the adapter**, not carried in the model:
  - `old_value` = `old_status` if the item was not closed, else `f"{old_status}:{old_close_reason}"`.
  - `new_value` = `new_status` if not a close, else `f"{new_status}:{close_reason}"`.
  - `old_close_reason` is the *prior* reason, needed only by the reversal path (`'Closed:superseded'`).

### 4.6 Trigger -> change_log Vocabulary

The dispatch table the L2 Relate plan asked for:

| Trigger | `field_changed` | `old_value` | `new_value` | `trigger_cause` | `link_id` | `item_id` |
|---|---|---|---|---|---|---|
| Rule 1 (`supersedes` confirmed) | `status` | `<observed>` | `Closed:superseded` | `supersedes_confirmed` | the `supersedes` link id | the closed item |
| Rule 2 (dependency closed) | `status` | `<observed>` | `Challenged` | `dependency_closed` | the `depends_on` link id | the dependent |
| Rule 3 (`contradicts` confirmed) | `status` | `<observed>` | `Challenged` | `contradicts_confirmed` | the `contradicts` link id | the challenged item |
| Rule 4 (`answers` confirmed) | `status` | `<observed>` | `Closed:answered` | `answers_confirmed` | the `answers` link id | the closed item |
| Human `close-item` | `status` | `<observed>` | `Closed:<reason>` | `user_closed` | NULL | the closed item |
| Human `set-status` (clear) | `status` | `<observed>` | `Active` | `user_set_status` | NULL | the item |
| Human `set-status` (challenge) | `status` | `<observed>` | `Challenged` | `user_set_status` | NULL | the item |
| Human `set-status` (the shield) | **`status_origin`** | `<observed>` | `manual` | `user_set_status` | NULL | the item |
| Reversal (the item) | `status` | `Closed:superseded` | `Active` | `reversal` | the `supersedes` link id | the restored item |
| Reversal (the marker) | **`link_reversed`** | `Confirmed` | `Reversed` | `reversal` | the `supersedes` link id | the restored item |

- **`item_id` = the item whose status changed.** **This diverges from Relate's convention** (Relate: `item_id` = the link's *source*). For rules 1/3/4 the changed item is the link's *target*. **Deliberate and documented:** the row describes a *status field* change on an item, and the item is the subject. `link_id` still points at the triggering link, so Engine D's `history` can join either way. (`item_id` is populated, not NULL as in Capture's `log_rejected` at `sqlite.py:565`, because the restored item is the subject of the marker.) **The `trigger_cause` — not `field_changed` — is the column Engine D should filter on**, because `field_changed='status'` appears in both engines' vocabularies.
- **`old_value` is the OBSERVED prior status**, read from the snapshot — not a constant. A `Challenged` target closed by rule 1 records `old_value='Challenged'`. A reversal records `old_value='Closed:superseded'` (prior status **and** reason).
- **`new_value` encoding is decided:** `<new_status>` alone, or `<new_status>:<close_reason>` for a close.
- **The `link_reversed` row is the reversal marker** (Gap C). It is what makes the reversal visible to readers of `links` and to the sweep's rule 1. It satisfies human spec 3.6:113 ("every change to a note **or link** adds a row to an audit ledger") — the link's change **is** logged.
- **The `status_origin` row** makes the shield change auditable — same spec clause, same reason. `status_origin` is **NOT** written by the sweep — only by `set-status`, and only when the shield is set. Its `old_value` is the **observed** prior `status_origin`, read before the UPDATE (a manual item re-cleared records `old_value='manual'`, not a constant `'derived'`).
- Every `trigger_cause` string is unique; every `field_changed` value is `status`, `status_origin`, or `link_reversed`.

### 4.7 Orchestration

`ember/maintain/run_maintain.py` mirrors `ember/relate/run_relate.py`: a frozen `Ports` dataclass, a frozen `Request` dataclass, one `run_*(ports, request)` function.

```python
@dataclass(frozen=True)
class MaintainPorts:
    lookup: MaintainLookupPort
    store: MaintainStorePort

@dataclass(frozen=True)
class MaintainRequest:
    item_id: int | None = None
    reason: str | None = None
    to_status: str | None = None
    link_id: int | None = None
```

- **No `command` field and no `dry_run` field.** The four commands are separate entry points, so a `command` discriminator would be a mode switch nothing reads. `--dry-run` is a **CLI** concern: the command omits the `apply_*` call entirely, so **no boolean ever crosses into a function** (I2).
- **Entry points** — 4 thin functions, so there is no `if command ==` ladder: `run_sweep(ports, request)`, `run_close_item(ports, request)`, `run_set_status(ports, request)`, `run_reverse_supersedes(ports, request)`, each `-> MaintainResult`.
- All four share a private `_load(ports) -> MaintainSnapshot` and `_apply_and_report(ports, changes) -> MaintainResult`. **The shared pipeline is a helper, not a phase engine** — so I2 holds (no mode switch in a single function) and each command keeps its own named entry point.
- **`MaintainResult(changed: list[StatusChange], applied: int, reopened: int, total_items: int)`** — the named object Phase 4 reports from (I4: named object, not a tuple). `reopened` counts the **applied** changes whose `old_status` is not `'Active'` and whose `new_status` is `'Active'`. `total_items` is the snapshot's item count, so the report's `unchanged` bucket is `total_items − changed items`; the CLI calls `run_sweep` and reads it instead of running Phase 1 a second time to count. **(Amended in step 02 — see `plans/steps/maintain/02-apply-and-cli.md` §10.)**
- **The file lives in step 02**, which owns both ports (the store port arrives with the write path). Step 01 owns the pure core + the lookup port + the adapter + `_load` + `format_report` + the `ember maintain --dry-run` command; step 02 owns the store port + the orchestrator + the real-run branch; step 03 owns the three human entry points.

## 5. CLI + Configuration

The four-command split, `items.close_reason` as a new column, and a representable reversal are **user decisions — not re-litigated here**.

```
ember maintain [--dry-run] [--db <path>]
ember close-item --item <id> --reason <reason> [--dry-run] [--db <path>]
ember set-status --item <id> --to <Active|Challenged> [--db <path>]
ember reverse-supersedes --item <id> --link <id> [--db <path>]
```

- `--db` defaults to `DEFAULT_DB_PATH`, **defined in `ember/cli.py`** (all four commands live there).
- `--reason` and `--to` are **plain `str` options, NOT `click.Choice`**. The domain codes (`MAINTAIN-002`, `MAINTAIN-006`) must fire from the command body; `click.Choice` would reject a bad value with exit 2 before the code could run. Written as `(plain str)` in this synopsis so L3 does not implement a Choice.
- `--item` is `type=int`; a non-integer exits 2 (Click's own error). **Error precedence:** `MAINTAIN-001` (item not found) is checked **before** `MAINTAIN-004`/`005`/`006`. `reverse-supersedes --item 99` → `MAINTAIN-001`, never `005`.
- **No environment variables.** Maintain needs no API key, no embedder, no model.
- **Boot sequence** (I13, fail fast): `open_maintain_database(db_path)` (§3 — refuses a missing file, probes corruption, applies migrations, checks `schema_version >= 10`) → validate the command's flags → Phase 1.
- `ember maintain` is **idempotent** — running it twice changes nothing the second time and exits 0.
- `--dry-run` runs Phase 1 + Phase 2, prints the planned changes, writes **no `items` or `change_log` rows**. **The DB must already exist** — `open_maintain_database` refuses a missing file with `MAINTAIN-007`, so a dry run against a fresh path **fails**; there is no create path. The only writes a dry run can make are the migrations, when the DB is at version 9. The §7.4 test must assert "writes no `items` or `change_log` rows", not "touches no file".
- `--dry-run` **still fails on Phase-2 domain errors** — but only for the commands that take such flags (`close-item`, `set-status`, `reverse-supersedes`). `ember maintain` takes no `--reason` / `--to` / `--link` and raises **no** domain code. The flag check happens **after** the validators, not before.
- **Exit codes:** 0 success (including "nothing to change" and a no-op `set-status`); 1 phase error (a `MAINTAIN-*` code); **2 for Click usage errors** (missing `--item`, non-integer `--item`, unknown option). Maintain has **no user-abort exit 2** — there is no confirm loop, so no `aborted` flag to exit on. (The codebase's exit-2 comes from `aborted`, not from `UserAbort` reaching the CLI: `capture/confirm_write.py:158-159` and `relate/confirm_write.py:151-152` swallow `UserAbort` internally.)
- `close-item --reason`: **human-settable reasons are `invalidated` and `expired`.** `superseded` and `answered` are **machine reasons** (produced by rules 1 and 4), and `reversed` is produced by the spec's reversal semantics, which *restore* an item rather than close it — so no v3 path produces a `Closed/reversed` item. A human passing any of those three → `MAINTAIN-003`.
- **`reversed` has a defined meaning:** "closed because a supersedes link pointing at it was reversed." Under this plan a reversal *restores* the item to `Active` rather than closing it — so `reversed` is **not produced by any path here**. **Decision: a valid enum value (the spec requires it) but not settable by `close-item` in V1** → `MAINTAIN-003`. Settable only by the spec's own reversal semantics, which this plan implements as "restore to `Active`". Recorded in §8.
- `set-status --to` accepts only `Active` or `Challenged` (L1:119). `--to` on a `Closed` item → `MAINTAIN-006`. `--to` equal to the current status → **no-op, exit 0, writes nothing**. **`--to Challenged` on an `Active` item does NOT set the shield** (B2) — only `--to Active` on a `Challenged` item does.
- `reverse-supersedes --item N --link L` requires: N exists (`001`); N is `Closed` (`005`); N's `close_reason` is `superseded` (`005`); the Confirmed `supersedes` link `L` points **at** N (`005`). It restores N to `Active`, clears `close_reason`, and writes the two rows (§4.6). It does **not** un-challenge the dependents (AI spec 3.5:111). **`--link <id>` is REQUIRED, not optional** — two `X→supersedes→B` links can both be Confirmed (gatekeeper rule 8 rejects cycles, not fan-in), so the target alone does not identify the link to reverse.
- `close-item` closes the item **and** flags its direct `depends_on` dependents (rule 2) **in one transaction**. It is the command with the widest fan-out → **it gets a `--dry-run` too**, and the dry-run **shows the dependents it would challenge**.

## 6. Errors (Stable Codes)

`ember/maintain/errors.py`, base `MaintainError(EmberError)` with `code = "MAINTAIN-000"`, `name = "MaintainError"`. Each subclass has `code` + `name` class attrs (I17).

| Code | Name | Trigger |
|---|---|---|
| `MAINTAIN-001` | `MaintainItemNotFound` | the `--item` id does not exist in this DB. |
| `MAINTAIN-002` | `CloseReasonInvalid` | `--reason` is not one of the 5 reasons. |
| `MAINTAIN-003` | `CloseReasonMismatch` | `--reason` is a machine-only reason (`superseded`/`answered`), or a human reason that the engine does not accept (`reversed`). |
| `MAINTAIN-004` | `ItemAlreadyClosed` | `close-item` on an item already `Closed`. |
| `MAINTAIN-005` | `ReversalPreconditionFailed` | `reverse-supersedes`: the item is not `Closed`, or its `close_reason` is not `superseded`, or the named `--link` is not a Confirmed `supersedes` link pointing at it. |
| `MAINTAIN-006` | `StatusTransitionInvalid` | `set-status --to` is not `Active`/`Challenged`, or the item is `Closed` (only reversal reopens). |
| `MAINTAIN-007` | `DbOpenFailed` | DB file missing, corrupt, permission denied. |
| `MAINTAIN-008` | `DbMigrationFailed` | migration 010 crashed during apply. |
| `MAINTAIN-009` | `SchemaOutdated` | `schema_version` version < 10 (defensive — migrations run first). |
| `MAINTAIN-010` | `ItemsReadFailed` | an `items`, `links`, or `change_log` read failed. |
| `MAINTAIN-011` | `StatusWriteFailed` | the `items` UPDATE failed; the whole batch rolled back. |
| `MAINTAIN-012` | `ChangeLogWriteFailed` | the `change_log` INSERT failed; the whole batch rolled back. |

**12 codes, contiguous, no reserved-but-unused numbers** (I17). Every code is raised by a named function (§3.1's `open_maintain_database` / `ensure_maintain_schema`, §4.5's `SqliteMaintainContext` / `SqliteMaintainStore`), and every one has a test (§7.5).

- **`MaintainItemNotFound`, not `ItemIdNotFound`** — `ItemIdNotFound` is Relate's `RELATE-001` class name (`ember/relate/errors.py:13`).
- **4 name collisions with `ember/relate/errors.py` → 4 aliases needed in `ember/adapters/sqlite.py`:** `ChangeLogWriteFailed` (RELATE-011), `DbOpenFailed` (RELATE-012), `DbMigrationFailed` (RELATE-013), `ItemsReadFailed` (RELATE-016). **Alias spelling is specified:** alias the **maintain** side — `from ember.maintain.errors import DbOpenFailed as MaintainDbOpenFailed` — so `sqlite.py:25-35` (which already imports nine Relate error classes) does not start aliasing the incumbent. House pattern: `ember/cli.py:44` does `from ember.relate.errors import UserAbort as RelateUserAbort`. **`ember/cli.py` needs NO maintain aliases** — it catches `EmberError` only and never imports an individual maintain class.

## 7. Test Targets

### 7.1 Unit (pure core, no DB)

Against `FakeMaintainLookup`:

- Rule 1: Confirmed `supersedes` → target gets `Closed:superseded`.
- Rule 2: dependency `Closed` with reason `invalidated`/`superseded`/`reversed` → dependent gets `Challenged`; reason `answered`/`expired` → **not** challenged.
- Rule 2 single-step: a dependent-of-a-dependent is **not** challenged.
- Rule 3: Confirmed `contradicts` → target `Challenged`.
- Rule 4: Confirmed `answers` → target `Question` `Closed:answered`.
- Tie-break: `supersedes` beats `answers` for the same target.
- **One change per item:** a `Decision` that is both superseded and contradicted → **exactly one** `StatusChange` (`Closed:superseded` wins over `Challenged`). **Also test rule-2-vs-rule-3** (both want `Challenged` → one change) and **rule-1-vs-rule-2**.
- **A reversed link is not a live supersedes:** a `supersedes` link in `reversed_link_ids` → no rule-1 close.
- `Rejected` links are ignored by all four rules.
- Escalation-only: a `Challenged` item is not written back to `Active`; a `Closed` item is not re-closed. **This is also the test that a human's `close_reason` survives a later machine close** (B6's test, re-pointed at B1).
- Manual shield: an item with `status_origin='manual'` is skipped by the sweep.
- `old_value` is the **observed** prior status (`Challenged`, not `Active`, for a challenged target closed by rule 1).
- Empty snapshot → empty change list (no raise).
- `validate_close_item`: `--reason superseded` (machine reason) → raises `MAINTAIN-003`; `--reason reversed` → raises `MAINTAIN-003`.
- `validate_close_item`: a dependent that is already `Challenged` is **not** re-challenged.
- `validate_set_status`: no-op (same status) → returns an empty change list.
- `validate_reverse_supersedes`: item not `Closed` / wrong reason / wrong link → raises `MAINTAIN-005`.
- **Ladder regression (the human commands move an item DOWN):** `validate_set_status --to Active` on a `Challenged` item returns a `Challenged → Active` change — it is **not** dropped by the escalation-only rule. Same for `validate_reverse_supersedes` (`Closed → Active`) and `validate_close_item` on a `Challenged` item (`Challenged → Closed`). These are the three cases that break if the ladder check is applied to a human command's primary change.

### 7.2 Integration (real temp DB, migrations 001-010)

**All link fixtures must be `compat.py`-legal.** The DB does not enforce the compatibility table (deferred issue, §8), so an illegal fixture yields a test that verifies a graph state Relate's gatekeeper would never write. A `Decision` target needs a `Decision` source for `supersedes` (`compat.py:16`) and a `Finding` source for `contradicts` (`compat.py:21`) — `Decision --contradicts--> Decision` is **not** a legal pair, so the "one change per item" fixture needs **3 items and 2 types**.

- Full sweep on a seeded DB → exact `items.status` + `close_reason` values, exact `change_log` rows (correct `trigger_cause`/`old_value`/`new_value`/`link_id`/`timestamp`).
- Idempotence: run the sweep twice → the second run writes **zero** rows.
- **Atomicity — with a REAL connection and a REAL constraint violation, not a fake.** Vehicle: give one `StatusChange` a `link_id` with no `links` row → the `change_log.link_id REFERENCES links(id)` FK (migration 008) raises `FOREIGN KEY constraint failed` on the INSERT, because `_connect` sets `PRAGMA foreign_keys = ON` (`sqlite.py:45`). Assert: **zero** `items` rows changed, **zero** `change_log` rows written, and the error is `MAINTAIN-012`. **Trap:** a test that builds its own connection with bare `sqlite3.connect` has FK **off** and the violation silently won't fire — use `open_maintain_database` / `_connect`. **Trap:** a fake store cannot observe the adapter's commit boundaries, so it cannot test this — the test must run against the real `SqliteMaintainStore`.
- `close-item` on an item with dependents → the close + the dependents' `Challenged` in one transaction, both logged.
- `set-status --to Active` on a `Challenged` item → item is `Active`, `status_origin='manual'`, a `status_origin` change_log row exists, and the **next sweep does not re-challenge it**.
- `set-status --to Challenged` on an `Active` item → item is `Challenged`, **`status_origin` stays `'derived'`**, no shield row.
- `set-status` no-op → writes nothing, no `change_log` row.
- `close-item` → the item is `Closed` but `status_origin` stays `'derived'` (it does **not** shield).
- Reversal: Confirmed `supersedes` → sweep closes the old item → reverse → the old item is `Active` with `close_reason=NULL`, **two** `change_log` rows exist (`status` + `link_reversed`), the dependents **stay** `Challenged`, and **the `links` row is unchanged** (`status` still `Confirmed`).
- **The reversal does not veto future closes:** after a reversal, a NEW supersedes from a different source onto the restored item → the next sweep **closes** it. **This is the v2-bug regression test.**
- **The 5 existing tests that migration 010 breaks must be updated:** `tests/test_migration_runner.py:83`, `tests/test_migrations.py:210`, `tests/test_source_storage_integration.py:66`, `tests/test_relate_db_open.py:110` (all assert `version == 9` → `10`), and `tests/test_migrations.py:19` (`test_items_table_has_expected_columns` asserts an exact ordered column list → append `close_reason`, `status_origin`). **Do NOT touch `tests/test_relate_db_open.py:79`** (it asserts Relate's `required == 9` and must keep passing).
- **A migration-010 regression test:** a DB with existing items (not empty) → apply 010 → pre-existing rows intact, their `close_reason` is NULL, `status_origin` is `'derived'`.

### 7.3 Architecture test (Rule T9)

Extend `tests/test_architecture.py` with a **third function** `test_maintain_core_does_not_import_adapters`, scanning `ember/maintain/*.py` for the forbidden set. The two existing functions stay untouched. All three run in CI. **Reuse the existing `FORBIDDEN_RELATE` constant** (`tests/test_architecture.py:14`) rather than declaring a third tuple.

### 7.4 CLI tests (smoke)

`ember maintain` on a fixture DB exits 0 and prints a summary; `ember maintain --dry-run` prints the plan and writes **no rows** (not "no file"); `ember close-item --item 1 --reason invalidated` exits 0; `--reason bogus` exits 1 with `MAINTAIN-002`; `--reason superseded` exits 1 with `MAINTAIN-003`; `--reason reversed` exits 1 with `MAINTAIN-003`; `ember set-status --item 1 --to Closed` exits 1 with `MAINTAIN-006`; `--to Bogus` exits 1 with `MAINTAIN-006`; `--to Active` on an Active item exits 0 and writes nothing; `ember reverse-supersedes --item 99 --link 1` exits 1 with `MAINTAIN-001`; `ember close-item --item 1 --reason invalidated` twice exits 1 with `MAINTAIN-004` on the second.

### 7.5 Error-code coverage (I21)

Every code in §6 has a test asserting the raised `code`, not message prose. Relate's precedent: `plans/engine-relate-plan.md:411`.

| Code | Test target |
|---|---|
| 001 `MaintainItemNotFound` | §7.4 (`--item 99`) |
| 002 `CloseReasonInvalid` | §7.4 (`--reason bogus`) |
| 003 `CloseReasonMismatch` | §7.1 + §7.4 (`--reason superseded`, `--reason reversed`) |
| 004 `ItemAlreadyClosed` | §7.4 (close twice) |
| 005 `ReversalPreconditionFailed` | §7.1 (3 cases) + §7.4 |
| 006 `StatusTransitionInvalid` | §7.4 (`--to Closed`, `--to Bogus`) |
| 007 `DbOpenFailed` | §7.2 (missing file + corrupt file) |
| 008 `DbMigrationFailed` | §7.2 (monkeypatch `_apply_migrations` to raise — the technique `tests/test_relate_db_open.py:42-54` already uses, which works **because `open_maintain_database` has the `except`**) |
| 009 `SchemaOutdated` | §7.2 (a DB with `schema_version` = 9 + monkeypatched `_apply_migrations`, the technique `tests/test_relate_db_open.py:91-102` uses) |
| 010 `ItemsReadFailed` | §7.2 (monkeypatch the connection's `execute` to raise `sqlite3.Error` on the `items`/`links`/`change_log` read) |
| 011 `StatusWriteFailed` | §7.2 (a `StatusChange` whose `new_status` violates the `items.status` CHECK → the UPDATE raises) |
| 012 `ChangeLogWriteFailed` | §7.2 (the atomicity test — the FK violation — **and it must assert the code, not just the rollback**) |

### 7.6 E2E (fake outside tools)

**Must be distinct from §7.2 bullet 1.** A **two-command sequence**: capture an item → relate it → `ember maintain` → assert the DB end-state (`items.status`, `links`, `change_log`). Maintain has **no AI and no embedder**, so there are no outside tools to fake — the "E2E" is a real-DB multi-command run.

### 7.7 Live

**None.** No AI call, no embedder, no network. This is the first engine with no live test tier.

Pyramid (T4): ~18 unit, ~14 integration, 1 E2E, 0 live.

## 8. Out of Scope (this L2 plan)

- Engine D (Query) — `current_state`, `topic_search`, `why`, `history` are Engine D's.
- Multi-step cascade — the one-step flag-spread limit is a spec rule, not a limitation.
- Re-opening a `Closed` item by any path other than reversal.
- `edit_item` (human-only, spec 3.7) — a content edit. **No plan owns it** — deferred issue (§0).
- `remove_link` (human-only, spec 3.7) — deletes a link edge. **No plan owns it** — deferred issue (§0). Note: removing a `supersedes` link does **not** reopen the old item.
- `items.rationale` / `items.source` (issue #1) — Capture's write path.
- AI-proposed `close_item` (V1 uses a human-invoked command).
- Re-challenge after a manual clear (Gap B / B4) — deferred issue.
- **Re-superseding the same `(source, target)` pair after a reversal** — blocked by the UNIQUE constraint + gatekeeper rule 9. Deferred note.
- **The corrective inverse after a reversal** (`B→supersedes→A` when `A→supersedes→B` exists) — rejected with `RELATE-028`. Deferred note.
- **DB-level enforcement of the compat table** (AI spec 3.6:115). The compat table lives only in Python (`ember/relate/compat.py`). Adding it needs a `links` rebuild or triggers. Deferred note.
- **The cross-column invariant `status='Closed' ⇒ close_reason IS NOT NULL`** (spec 3.2:60 "Closed: … Requires close reason"). Enforced in the write path, not by a schema CHECK. Deferred note.
- **`reversed` as a close reason** — a valid enum value that **no path here produces**: the spec's reversal semantics *restore* an item to `Active` rather than close it, so there is never a `Closed/reversed` item. It is **not** settable by `close-item` (`MAINTAIN-003`). The spec requires the value to exist; the plan keeps it in the enum and records that nothing writes it.
- **Plain-text export** (AI spec 3.6:118 / human 3.6:115) — "Read-only CLI export script dumps DB into formatted text file." **No engine owns it.** Deferred issue (§0).
- **The stale window** — between a link confirmation and the next `ember maintain`, the superseded item is still `Active`, so Relate's gatekeeper rule 7 (which blocks `supersedes` to a `Closed` target) would allow a second supersedes onto it. **Nothing schedules a sweep, so the window is unbounded**, not "until the next sweep". Mitigation: the user is expected to run `ember maintain` after `ember relate`; a future step may chain them. Deferred to L3 (§9).

## 9. Deferred to L3 (Reminder)

The substantive open decisions. Do NOT forget these when writing L3 step plans.

1. **Whether `ember relate` chains `ember maintain`** at the end of its confirm loop (closes the stale window, §8). L2 picks "no — separate commands"; L3 confirms the seam.
2. **The report's exact wording and ordering** (the buckets are fixed: `closed`, `challenged`, `reopened`, `unchanged`).
3. **Whether `close-item` should prompt for confirmation** or stay flag-driven (L2 picks flag-driven; if it prompts, the step needs a `UserAbort` + exit 2 + a §Z I12 update).
4. **Whether the sweep reports the items it skipped** because they were `manual` (B2's shield).
5. **The `--dry-run` output shape** (same lines as the real run, via the shared `format_report`).

## 10. Next Step (L3 step plans)

3 steps in `plans/steps/maintain/`, matching both peers:

- **`01-load-and-derive.md`** — migration 010; `errors.py`; `rows.py`; `maintain_lookup.py` (`MaintainLookupPort`); `derive.py` (pure: `derive_status_changes`, `merge_and_filter`); `report.py` (**`format_report`**); `run_maintain.py` (`_load` + the `by_id` index); `SqliteMaintainContext`; `open_maintain_database` + `ensure_maintain_schema`; the architecture-test extension; the `tests/fakes.py` helpers (`insert_item` params, `insert_link`, `insert_link_reversed`); **the 5 existing-test edits**; **the migration-010 non-empty regression test**; unit + integration tests. **CLI check:** `ember maintain --dry-run --db <fixture>` → prints the planned changes, exits 0. (**Ships a runnable CLI** — Rule S1. The dry-run needs only Phases 1 + 2, so it is available at the end of step 01.)
- **`02-apply-and-cli.md`** — `apply_status.py` (`MaintainStorePort`, the atomic batch, the clock); `SqliteMaintainStore`; `run_maintain.py` (`MaintainPorts`, `MaintainRequest`, `MaintainResult`, `run_sweep`, `_apply_and_report`); the real-run branch of the `ember maintain` command; the atomicity test (real FK violation); the error-code tests for 010-012. **CLI check:** `ember maintain --db <fixture>` → prints the summary, exits 0.
- **`03-human-actions.md`** — `ember close-item`, `ember set-status`, `ember reverse-supersedes`; the three pure validators; `run_close_item`, `run_set_status`, `run_reverse_supersedes`; `apply_status_origin`; **`apply_reversal`** (the `link_reversed` marker); the `status_origin` + `link_reversed` change_log rows. **CLI check:** each command on a fixture DB.

## 11. Amendments to Other Plans

### 11.1 `plans/master-plan.md` (L1) — 5 lines + 1 new line

- **Status: applied 2026-10-25 in <COMMIT_SHA>.**
- **Line 45** — from: `- Input: any state change event (link confirmed, item closed, etc.).`
  to: `- Input: the `items` + `links` tables, reconciled on demand. No event bus.`
- **Line 47** — from: `- Four fixed triggers (via `validate_close_item` script):`
  to: `- Four fixed triggers (via the `derive_status_changes` script):`
- **Line 81** — from: `- For AI mutations: `validate_add_item`, `validate_add_link`, `validate_close_item`.`
  to: `- For AI mutations: `validate_add_item`, `validate_add_link`.`
- **Line 83** — from: `- For human-only operations: `validate_edit_item`, `validate_set_status`, `validate_set_validated`, `validate_remove_link`.`
  to: `- For human-only operations: `validate_edit_item`, `validate_set_status`, `validate_set_validated`, `validate_remove_link`, `validate_close_item`, `validate_reverse_supersedes`.`
- **Line 117** — from: `3. AI-callable mutations (each requires user confirm): `add_item`, `add_link`, `close_item`.`
  to: `3. AI-callable mutations (each requires user confirm): `add_item`, `add_link`.`
- **§5 Out of Scope** — add a line: `AI-proposed `close_item` deferred to V1.x (issue #16). V1 ships `ember close-item` human-invoked; the human running the command is the confirmation.`
- **Rationale for amending L1 (not just noting it in L2):** L1 §4 is the **global-invariant list for the whole system**; a false entry poisons every later plan, and Engine D's L2 would read line 117 and assume an AI-callable `close_item` exists. L1 line 7's "Changes to stack = new L1 amendment" covers §0 stack decisions, not §4 invariants — **this is a consistency amendment, not a stack amendment.**
- **Not changed by these amendments:** lines 46, 48-51 (the four rules themselves), 52 (single-step flag spread), 53 (self-fix for typos), 54 (reversal intent), 55, and every other L1 section. Line 54's *intent* is unchanged — the amendment only makes the mechanism explicit elsewhere (§2 Gap C).

### 11.2 `plans/engine-relate-plan.md` — 4 lines

- **§3.1 line 39** — from: "Reversal of `supersedes` writes a new link row, not an update" → to: "Reversal of `supersedes` is an **item-status** event owned by Engine C; it writes **no `links` row** and does not change `links.status`. It is recorded as a `change_log` row with `field_changed='link_reversed'`. See `plans/engine-maintain-plan.md` §2 Gap C." (v2 claimed no amendment was needed — a non-sequitur: the sentence is a *positive* claim about a write that no longer happens.)
- **§8** — the Engine C bullet → the resolved statement (Maintain does not listen for events; it sweeps the `links` table) + the §4.6 vocabulary table.
- **§9 #8** — "Engine C dispatch vocabulary" → **resolved** by `plans/engine-maintain-plan.md` §4.6.
- **§6 line 368** — "version < 9" → note that migration 010 makes the DB version 10 and Relate's floor stays 9.

### 11.3 `README.md` — 2 engine lines + a CLI block

- **Line 41** — "Engine B (Relate): Next up" → "Built and verified".
- **Line 42** — "Engine C (Maintain): Planned." → "Built and verified".
- Add a CLI-usage block for the four new commands (`ember maintain`, `ember close-item`, `ember set-status`, `ember reverse-supersedes`) in the same style as the existing command blocks, and fix the stale "183 tests" count.

### 11.4 `PROJECT_MAP.md` — add files, columns, and commands

- Add `ember/maintain/` (every module), `tests/maintain/` (every file), `plans/engine-maintain-plan.md`, `plans/steps/maintain/*.md`, and `ember/adapters/migrations/010_add_item_close_reason.sql`.
- Add the 2 new `items` columns (`close_reason`, `status_origin`) to the `items` table entry.
- Add the 4 CLI commands to the `ember/cli.py` entry.
- Add the `open_maintain_database` boot path.
- The `links.status` note ("`Confirmed` or `Rejected`") **stays accurate** — Maintain adds no third link status.

**`README.md`** — lines 41 + 42 (both engine status lines), a new CLI-usage block for the 4 commands, and the stale "183 tests" count.

**`PROJECT_MAP.md`** — add `ember/maintain/`, `tests/maintain/`, `plans/engine-maintain-plan.md`, `plans/steps/maintain/*.md`, migration 010, the 2 new `items` columns, the 4 CLI commands, and the `open_maintain_database` boot path. The `links.status` note ("`Confirmed` or `Rejected`") **stays accurate** — no third value is added.

## Z. Constitution Compliance

**Three tables.** (a) touched & satisfied with a §ref; (b) N/A with a reason; (c) knowingly deviated, with a §ref and a justification.

**(a) Touched & satisfied:**

| Rule | §ref |
|---|---|
| B1 one job | §1 |
| B3 depend on stable things | §4.5 (ports) |
| B4 hide volatile decision | §4 (Phase 2) |
| B5 deep module | §4.7 (4 thin entry points over a shared helper) |
| D1 raw data immutable | §1 — `sources.full_text`, `ai_responses.response_text`, `change_log`, and `links` are **untouched**. `items.status`/`close_reason` are **derived state**, and mutating them is mandated by spec 3.2/3.5. The destroyed close reason survives in `change_log.old_value`. |
| D2 derived rebuildable | §4 Phase 2 — derived state is rebuildable by **replaying `change_log` in timestamp order**. It is **idempotent**, but **not** "rebuildable by replaying the sweep" (escalation-only reads *current* status, so a from-scratch replay differs). |
| D3 single source of truth | §4.6 — `change_log` is authoritative for every fact about an item's status history, including `status_origin` (its own `change_log` row) and the reversal marker. `items.status`/`close_reason`/`status_origin` are derived caches. The `links` table is Relate's fact store; Maintain reads it, never writes it. |
| D5 prefer new optional fields | §3 (two `ADD COLUMN`s) |
| D6 numbered migrations | §3 (010 + `schema_version`) |
| P2 layered | §4 (CLI → core → adapter) |
| P3 pipeline | §4 (4 phases, explicit boundaries) |
| P4 ports & adapters | §4.5 |
| I1 name by job | §4.5 |
| I2 no boolean behaviour flags | §4.7 — the four commands are separate entry points; `dry_run` is the only boolean and never crosses into a function. |
| I3 max 4 inputs | §4.7 — `run_*(ports, request)`, 2 inputs each. |
| I4 named object, no tuples | §4.5 (`StatusChange`, `MaintainResult`, `MaintainSnapshot` are models) |
| I5 split failure modes | §6 (each code is one failure) |
| I6 one base error | §6 |
| I7 fail fast, handle at edge | §3 (boot), §4 (no swallowing), §5 (the CLI is the only catcher) |
| I9 validate at edge | §5 (flags validated in the command body) |
| I10 stable interface | §3 (additive columns) |
| I11 function contract | §4.5 (each port method lists its raised codes) |
| I12 CLI contract | §5 (explicit flags, 0/1/2, report → stdout, `error: {exc.log_line()}` → stderr) |
| I13 config at boot | §3 + §5 (`open_maintain_database` does open + migrate + schema-check in one place) |
| I17 stable codes | §6 |
| I18 module.function injected | §6 (inherited from `EmberError`) |
| I19 entity IDs in errors | §6 (each code lists the required context: `item_id`, `db_path`, `link_id`) |
| I20 one-line logging | §5 (`error: {exc.log_line()}` to stderr) |
| I21 codes + tests | §6 + §7.5 |
| T1 pure core | §4 Phase 2 |
| T2 push side effects to edges | §4.5 |
| T3 prefer fakes | §7.1 (`FakeMaintainLookup`) |
| T4 test pyramid | §7 — ~18 unit, ~14 integration, 1 E2E, 0 live |
| T5 test boundaries | §7 (asserts DB state + raised codes, not internals) |
| T6 good targets | §7 |
| T9 architecture test | §7.3 |
| S1 run alone | §5 (`ember maintain` runs the whole pipeline; the other 3 are the human-mutation surface L1 §4 rule 5 requires). **Step 01 ships `ember maintain --dry-run`.** |
| S2 dedicated suite | §10 (`tests/maintain/`) |
| S3 document input/output | §4.5 (data models) + §4.7 (`MaintainRequest`/`MaintainResult`) |
| S4 explicit data transfer | §2 (the DB is the transfer mechanism) |

**(b) N/A, with reason:**

| Rule | Reason |
|---|---|
| D8 save raw model response | Maintain makes no AI call (§4.0). Re-arms if "AI-proposed close_item" ships. |
| I14 web API | No web API in V1. |
| I15 external services | No external service. |
| I16 AI output schema | No AI call. |
| T7 AI fixture testing | No AI parser. |
| T8 AI eval benchmark | No AI. |

**(c) Knowingly deviated, with justification:**

| Rule | Deviation | Justification |
|---|---|---|
| B1 one job | The rules are **not** unconditional: escalation-only makes every rule conditional on the item's prior state (a `Closed` item is never re-closed; a `Challenged` item is never re-written). | Spec 3.5's rules are unconditional, but spec 3.5:111 ("Dependents flagged Challenged remain Challenged until human clears") **requires** a stateful reading. Escalation-only is the cheapest way to make that true by construction. |
| B2 public calls only | `Maintain` imports `Link` from `ember.relate.rows` (a public module, no leading underscore). | That is a **public call**, which B2 permits. The first clause of B2 is permission, not prohibition. The alternative (duplicating the model) would put two shapes for one table in one file — a D3 violation, and `sqlite.py:36` already imports it. |
| B6 warning signs | `ember/adapters/sqlite.py` grows 2 classes; `ember/cli.py` grows 4 commands. | The file is already the house's single SQLite boundary. The warning sign to watch is **splitting** it, not growing it. |
| D4 outside data untrusted | The `--item`/`--reason`/`--to` flags are validated in the **command body** (the CLI edge), not in the pure validators. | Both are edges. The CLI catches Click's type errors; the command body runs the domain check; the pure validators are called **after** the command body has validated. |
| P1 no decorative architecture | 2 ports + 4 thin entry points. | Each has a caller. `merge_and_filter` exists because 4 commands need the same 3 rules. |
| I8 design error away | `MAINTAIN-004 ItemAlreadyClosed` is an error, not a no-op. | A second `close-item` with a *different* reason is a real conflict; the human needs to know it was ignored. |
| I12 exit codes | Exit 2 is used for Click usage errors, not only user abort. | Click's behaviour. **I12 requires only "non-zero fail"; exit 2 satisfies it.** No deviation — recorded for clarity. |
| T10 painful test setup | The atomicity test needs FK enforcement ON, so it must use `open_maintain_database` / `_connect`, not a bare `sqlite3.connect`. | Documented as a trap in §7.2, with the reason. |
| — | The sweep writes `items` + `change_log` with **no gatekeeper script**. | **Phase 2's `merge_and_filter` IS the gatekeeper for machine writes** — it is the deterministic rule set the spec calls "gatekeeper scripts" (L1:81). Stated here because L1:116 ("All mutations pass gatekeeper validation scripts") would otherwise read as violated. |
| — | `close_item` does **not** prompt. Spec 3.7:126 says "User confirms." | The human invoking `ember close-item` **is** the confirmation. An L1 amendment records this (§11). |

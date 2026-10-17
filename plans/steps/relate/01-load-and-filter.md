# L3 Relate Step 1: Load + Filter (Phase 1)

Implements Phase 1 of L2 Relate plan. Read the new item, build the candidate universe by dropping pairs that already have a link (any status), and keep only items where at least one link_type is type-compatible per spec 3.3.

## 0. Constitution rules this step enforces

- **B1** — `ember/relate/compat.py` is a separate module from `ember/relate/load_filter.py` (one purpose per module).
- **B2** — engine core reads `items` and `links` only through `LinkLookupPort`; no direct table access.
- **B3** — the type-compatibility table is a constant in `ember/relate/compat.py`; the engine core depends on the constant, not on the DB.
- **I4** — every function returns a named object (`NewItem`, `CandidateUniverse`), never a tuple.
- **I6** — all RELATE-NNN codes subclass `EmberError` per L2 §6.
- **I10 / T6** — the candidate builder is covered through its public function; no direct internal helpers.
- **I13** — env vars read once at Relate CLI startup; this step does not re-read. (Step 1 itself never reads env; the line is here to keep the framework's §0 baseline even when a step has no direct I13 enforcement.)
- **I17 / I21** — error codes have stable RELATE-NNN codes and named classes; tests assert the code, not the message.
- **P3 / P4** — this step is Phase 1 of the L2 §4 pipeline; the DB access is a port (`LinkLookupPort`).
- **S1 / S3** — CLI check in §7; input/output shapes in §2 and §3.
- **T1 / T2 / T9** — Phase 1 is pure (no file/network/clock); side effects are pushed to the `LinkLookupPort` adapter; `load_filter.py` and `compat.py` import nothing from `ember.adapters.*`.

## 1. Job

Take `--item ID` (or `--latest`) and a port-injected `LinkLookupPort`, and return the new item plus the candidate universe. A candidate is an item where at least one of the 5 link_types is type-compatible with the new item. Existing `(source=new_item, target=X, link_type=T)` triples of any status are dropped, but `X` is kept if at least one other link_type remains viable.

## 2. Inputs

From the CLI:
- `--item ID` (status-agnostic) **or** `--latest` (newest `Active` item that has no link of any status from it). Mutually exclusive; one is required.
- `--db PATH` (default: `DEFAULT_DB_PATH` from `ember.cli`).
- The CLI opens the DB via `open_database(db_path)` from `ember/adapters/sqlite.py:24-30`, which sets `PRAGMA foreign_keys=ON` at line 28. Required for migration 008's `change_log.link_id REFERENCES links(id)` to be enforced at runtime. The conn from `open_database` is what `SqliteLinkContext` wraps.

From the port (`LinkLookupPort`, L2 §4.5 + this step's amendments):
- `item_exists(item_id) -> bool`
- `item_type(item_id) -> str | None`
- `item_statement(item_id) -> str | None`
- `find_existing(source_id, target_id, link_type) -> Link | None`
- `list_other_items(new_item_id) -> list[NewItem]` — returns all items except `new_item_id` (Phase 1 candidate universe). New method for this step; amend L2 §4.5 in the next Relate plan revision.
- `find_latest_unlinked_active() -> NewItem | None` — for `--latest`. Returns the newest `Active` item that has no link of any status from it; `None` if no such item. New method for this step; amend L2 §4.5 in the next Relate plan revision.

(`item_status`, `supersedes_ancestors`, and `neighbors_of` are listed in L2 §4.5 but not used by Phase 1; they belong to Phases 2 and 4.)

## 3. Outputs

- `NewItem(id: int, type: str, statement: str, created_at: str)` — the item to relate. (4 fields; Phase 2 reads `id`, `type`, `statement`, `created_at` only. `status` and `source_id` are in the `items` row but are not used by Phase 2/3/4; per M13, trimmed from the model.)
- `CandidateUniverse(items: list[NewItem])` — surviving candidates only. (Per M3, `dropped_pairs` is dropped: Phase 4 gatekeeper rule 9 uses `find_existing` to re-check uniqueness against the live DB, so no need to thread dropped pairs through. Per M2, `ContextSnapshot` wrapper is dropped: the orchestrator takes `NewItem` and `CandidateUniverse` as 2 separate args.)

## 4. Steps

1. Resolve the new item id:
   - `--item ID`: read the item. If `item_exists` returns false, raise `RELATE-001` and print the `--item ID` and the DB path the user pointed at (so they can spot a wrong `--db`).
   - `--latest`: call `link_lookup.find_latest_unlinked_active()`. The implementation runs `WHERE status='Active' AND id NOT IN (SELECT source_item_id FROM links) ORDER BY id DESC LIMIT 1` (per L2 §4 Phase 1 line 154: any link status disqualifies — B6 fix from a previous draft that narrowed to `status='Confirmed'`). If `None` is returned, **print "no unrelated items" to STDOUT and exit 0** — this is a soft exit per L2 §4 Phase 1 line 153 and L2 §6 line 385. No code is raised; the case is not an error.
2. Read the new item row via `LinkLookupPort` (`item_type`, `item_statement`, plus the existing fields). Build the `NewItem` object.
3. Call `link_lookup.list_other_items(new_item.id)` to get the raw candidate pool. Build the initial universe.
4. **Filter #1 — drop pairs.** For each raw candidate `X`, for each of the 5 link_types, call `find_existing(new_item.id, X.id, T)`. If a `Link` is returned (any status: `Confirmed` or `Rejected`), drop the `(X.id, T)` pair from the universe. If a candidate loses all 5 pairs, also drop `X` itself. The dropped pairs are not tracked separately — Phase 4 will re-check via `find_existing` against the live DB.
5. **Filter #2 — type compatibility.** For each surviving candidate `X`, ask the compat table (L2 §4 spec 3.3 inlined in `ember/relate/compat.py`): is there at least one `link_type` where `(source_type=new_item.type, target_type=X.type)` is allowed? If no, drop `X`. The compat table is a `dict[tuple[str, str], set[str]]` keyed by `(source_type, target_type)`, values = allowed link_types.
6. Build `CandidateUniverse`. Return `(NewItem, CandidateUniverse)` to the orchestrator. (2-tuple is fine here; both are named types.)
7. The orchestrator passes the candidate universe to Phase 2. Phase 1 is done.

## 5. Errors (codes only, per L2 §6)

- `RELATE-001` — `--item ID` not in DB.
- `RELATE-012` — DB open fail (DB file corrupt, permission denied, disk full at open). New in Step 1's §5 (M1).
- `RELATE-013` — migration 006/007/008/009 crashed during apply. New in Step 1's §5 (M1).
- `RELATE-014` — `schema_version.version` < 8 (migrations 006-009 not applied). (B5 fix: source of truth is the `schema_version` **table** per `ember/adapters/sqlite.py:35-43`, not `PRAGMA user_version`. L2 §3 line 23 was wrong; Step 1 reads `SELECT version FROM schema_version`.)
- `RELATE-016` — Phase 1 read failed (covers `items` and `links` table reads: `item_exists`, `list_other_items`, `find_latest_unlinked_active`, `find_existing`). Per L2 amendment log entry recorded by this step, the L2 §6 line 359 trigger text is widened from "Reading items table failed" to "Phase 1 read failed (items or links table)". Replaces the previously-misattributed `RELATE-005` (M1).

**No `RELATE-002`.** L2 §6 line 380 removed it. The `--latest` no-eligible-items case is a soft exit 0 per L2 §4 Phase 1 line 153 (B4 fix). Likewise no `RELATE-020` or `RELATE-034` (L2 §6 lines 382-383 remove both).

## 6. Test Targets

Unit (in-memory `LinkLookupPort`, in-memory compat table):
- `--item ID` happy path: candidate universe contains items where at least one link_type is allowed; drops the rest.
- `--item ID` not in DB: `RELATE-001` raised with both ID and DB path in the message.
- `--latest` no eligible item: **soft exit 0**, prints "no unrelated items" to STDOUT, no code.
- Filter #1: existing `(source, target, T)` triple removed from the universe, but `X` kept if another link_type still viable.
- Filter #1: existing link of any status (`Confirmed` or `Rejected`) counts as a drop.
- Filter #2: type-incompatible candidate dropped; type-compatible kept.

Integration (real SQLite temp DB, migrations 001-009 applied):
- Seed: 5 items, 2 already linked from item #1 (one `Confirmed`, one `Rejected`). Run `--item 1` -> universe = 3 items; no `dropped_pairs` collection.
- `--item 999` -> `RELATE-001`, exit 1, message includes `999` and the DB path.
- `schema_version.version` < 8 -> `RELATE-014`, exit 1. (Step 1 reads the table; `PRAGMA user_version` is unused.)
- DB file missing or corrupt -> `RELATE-012`, exit 1.
- Migration 006 fails mid-apply -> `RELATE-013`, exit 1.

## 7. CLI check (Rule S1)

- `ember relate --item <id>` (after Step 3 lands): expected exit code depends on Phase 4 — but for Step 1 alone, the orchestrator stub exits 0 with the JSON shape `{"phase": 1, "new_item_id": <id>, "candidates": <count>}` so the wiring is visible end-to-end. Step 3 replaces the stub.
- `ember relate --latest` with no eligible item -> exit 0, prints "no unrelated items".

## 8. Out of Scope (this step)

- Embedder (Phase 2).
- AI propose (Phase 3).
- User confirm + write (Phase 4).
- Embedding cache reads (Phase 2 + `EmbeddingStorePort`).
- `change_log.link_id` FK (depends on migration 008, applied before Step 1 starts).
- Architecture test (`tests/test_architecture.py` extension per L2 §7.3 line 416) — Step 1 ships the first Relate engine-core module (`load_filter.py`), so the test ships with this step. Step 3 §6 cross-references; the test itself is Step 1's deliverable (b).

## 9. Next

Step 2 takes the `CandidateUniverse` and adds the 3 signals (content, graph, metadata) plus the merge. Step 3 runs the AI propose, user confirm, and atomic write.

## 10. Deferred Settings (from L2 §9)

- (L2 §9 #2) Graph signal BFS depth — Step 2 picks 1-hop (L2's default) or deeper. Step 1 does not pick.
- (L2 §9 #3) Metadata signal temporal window — Step 2 picks.
- Step 1 picks itself: how to query the "newest unlinked Active" for `--latest` (L2 deferred this in spirit by saying "L3 may pick"; no L2 §9 line for it). Encapsulated in the new `LinkLookupPort.find_latest_unlinked_active()` method; the SQL is `ORDER BY id DESC LIMIT 1` against `items WHERE status='Active' AND id NOT IN (SELECT source_item_id FROM links)`. No BFS, no time filter — simplest thing that satisfies the contract. The disqualifying condition is "any link status" (B6 fix from `status='Confirmed'`).
- **L2 amendment log entries recorded by this step** (for the next Relate plan revision to fold in):
  - L2 §4.5 needs 2 new `LinkLookupPort` methods: `list_other_items(new_item_id)` and `find_latest_unlinked_active()`. Without them, Phase 1 cannot enumerate candidates via the port pattern.
  - L2 §3 line 23 (says "PRAGMA user_version") is wrong; the source of truth is the `schema_version` table. Step 1 reads the table per `ember/adapters/sqlite.py:35-43`. L2 §6 line 358 trigger text also needs updating from "DB has not had migrations 006/007/008/009 applied" to "`schema_version.version` < 8".
  - L2 §6 line 359 trigger text for `RELATE-016 ItemsReadFailed` needs widening from "Reading items table failed" to "Phase 1 read failed (items or links table)", so Step 1's `find_existing` / `list_other_items` / `find_latest_unlinked_active` reads all map to the same code.

## 11. Rollback

No rollback — this step only reads. Per framework v2 L3 rule.

## 12. Build Notes (post-implementation)

TBD after code lands.

# L1 Hardening Phase Plan

Terse caveman style. Phase plan under `plans/master-plan.md` (L1 amendment in substance, see §7). Resolves the 16 open tracker issues left after the four engines shipped. Source: GitHub issues #1..#28 except #4 (excluded by maintainer choice). Process per `docs/ai version/planning-framework-ai.md`. No invention.

## 0. Status + Stack

- Four engines shipped and merged: capture (#3), relate (#13), maintain (#25), query (#29). V1 build complete.
- This phase = hardening. No new engine. No new dependency. No stack change — master plan §0 stands.
- Schema version moves past 10. New migrations continue the numbered sequence (D6). Migrations 001..010 exist.
- Boot floors today (verified): relate ≥ 9, maintain ≥ 10, query ≥ 10, capture has none. Nothing rejects a higher version.
- All 16 issues are `deferred` or `note` labelled. None is a wontfix (recorded 2026-10-28: rejections vs deferrals).
- #4 (external vector DB) stays out: parked by choice, not in this phase.

## 1. Phase Job (one job)

Make the guarantees real. Today most guarantees live in application code only (gatekeepers, write paths). One spec requirement has no implementation (`edit_item`, `remove_link`), and three read features are parked. This phase closes that gap with four work clusters.

## 2. The Four Clusters

### Cluster 1 — Schema enforcement (issues #17, #15, #20, #21, #23)

Job: the database guarantees what the gatekeepers already enforce. **Mechanism by default is triggers plus one `ADD COLUMN` — no table rebuild.** A rebuild enters scope only if issue #15 is decided "build" (see below); #15's own body defers it until a real workflow demands it.

- #17: link compatibility table enforced at DB level, as a trigger on `links`. Drift-test contract: the trigger's pair table is generated from / tested against `ember/relate/compat.py` (`TYPE_COMPAT` stays the single source; a test ties the two together). Plus the #17 test: a direct illegal INSERT raises.
- #20: reversed supersedes visible to every reader. Today only Maintain acts on the `change_log` marker; Query renders it but does not act on it. Mechanism: one `ADD COLUMN` carrying the reversal state on the `links` row.
- #21: corrective inverse after reversal. Today `RELATE-028` false-rejects. In scope: the cheap partial (better error message naming the blocking link). The boundary-crossing fix (Relate reading `change_log`) stays out unless the trigger column makes it free.
- #23: `Closed` implies `close_reason`, enforced by a trigger on `items`. **No items rebuild** — the rebuild would manufacture the "another reason" #23 says to wait for. A pre-step asserts existing rows satisfy the new rule before any trigger lands.
- #15: decide first, build only if decided. Today the UNIQUE triple (`source_item_id, target_item_id, link_type`, migration 006) blocks a re-supersede forever. Two outcomes: keep the block (spec 3.3 forbids duplicate links — then no schema work, issue stays deferred with its trigger), or relax it via a partial unique index on live rows only — that is a **table rebuild** and a recorded spec 3.3 deviation. Ruling recorded in an engine-relate-plan amendment before any build.

D3 ruling (reversal truth): `change_log` stays the source (master plan rule 7); the new `links` column is derived, labelled as such. Rebuildable is a contract, not a word: the L2 ships a named pure rebuild step (ledger replay → column value) plus a test that a replayed replay equals the live column on a real temp DB. Pairing rule: the column write and its ledger row land in one transaction (the `apply_status_origin` pattern).

Rebuild mechanics (apply only if #15 is decided "build"): SQLite-documented safe order — create new table, copy rows with explicit ids, drop old, rename last. The rename-first pattern migration 008 used is forbidden for these tables: on SQLite ≥ 3.26 a rename rewrites child foreign keys to the dead name. The merged CREATE TABLE is pinned verbatim, column order pinned. `sqlite_sequence` preserved. Tests: value-level row equality, `change_log` join intact, `PRAGMA foreign_key_check` empty, sequence preserved, failed migration leaves an intact v10 DB, fresh install applies the whole sequence.

S1 artifact: an `ember db-check` read-only command reports schema/replay drift (recorded at review as this cluster's CLI surface).

### Cluster 2 — Human edit commands (issues #19, #1)

Job: the two human-only operations the master plan names (`edit_item`, `remove_link`) exist as commands plus gatekeepers. **One ruling is recorded before any code.**

- The ruling: master plan rule 7 says historical items are immutable. #19 records that text editing has no answer. Outcome recorded as an ADR: either text edits are forbidden (then `edit_item` covers rationale/source + re-linking only, and #1 still gets its writer) or text edits are allowed with a `change_log` trail. Either way #1 gets a writer; only the width changes.
- `edit_item` writes `items.rationale` (Decision) + `items.source` (Finding) per master plan §5. No writer exists today (verified: the item INSERT writes 7 columns, never these).
- `remove_link`: deletion is forbidden as a DELETE — `change_log.link_id` carries a foreign key to `links` (migration 008), and deleting the row orphans history. Leading option: flip `links.status` to the existing `Rejected` value. Two problems that must be ruled on, not assumed: (a) the Maintain L2 says "Maintain never writes `links`" — that clause gets an explicit amendment; (b) a removed link becomes indistinguishable from a human-rejected proposal, and gatekeeper rule 9 + the UNIQUE triple then block re-creating it forever (the #15 pattern). The #15 ruling above must land first.
- Existing ruling carried forward: removing a `supersedes` link does not reopen the superseded item (engine-maintain-plan §8).
- Gatekeepers: `validate_edit_item`, `validate_remove_link` join the human-only list (master plan line 83). Error codes continue from MAINTAIN-013.

### Cluster 3 — Read surface (issues #26, #27, #28)

Job: query gains the read features it deferred. All read-only; never writes (Engine D contract). Proof: DB file hash identical before and after.

- #26: `--limit` on topic-search. Default stays no cap.
- #27: `--status` / `--type` filters on topic-search.
- #28: `--limit` / `--offset` or `--since` on history. Never a silent default cap.

Flags are data (typed parameters into the pure cores), never mode switches (I2). With no flags, output is byte-identical to today. Filter objects wrap the parameters where inputs exceed 4 (I3): a `TopicFilter` shape, a `HistoryPage` shape.

Ruling on #18 (plain-text export): the Engine D L2 records a **prior approved decision** — export belongs to a separate utility plan with its own `EXPORT-*` codes, "not ours", issue #18 stays with that plan. That decision stands unless the maintainer supersedes it here. Cluster 3 does not silently absorb #18.

### Cluster 4 — Decide-then-act singles (issues #5, #8, #12, #14, #16)

Job: resolve parked decisions. For each issue: record exactly one decision — build now, keep deferred with an updated trigger, or reject with an `.out-of-scope` note. Code only after a recorded decision. Default when nothing changes: stays deferred, issue updated with the current trigger, never silently closed.

- #5 `items.metadata`: the column does not exist in the schema at all. Decision is whether to add it, and who writes it.
- #8 Signals wrapper: trigger is a 4th signal. BM25 exists but does not feed relate (verified: no Query import anywhere in relate).
- #12 embedder model-change re-encode cost: a measurement, not a feature.
- #14 sticky manual clear: spec question — does a human clear cover one trigger or all future ones?
- #16 AI-proposed `close_item`: master plan §5 already defers it to V1.x with a written rationale.

## 3. Phase Contracts

1. **Migration contract, per change:** one numbered migration. Final table and column names unchanged (D5) — a temporary table name is allowed and expected when a rebuild runs. Every existing column preserved **with its exact type, CHECK, FK, UNIQUE and indexes**, proven by a before/after `sqlite_master` + `PRAGMA table_info/index_list/foreign_key_list` diff. Ids and values preserved row-for-row, proven by full-row comparison and join counts, not by row counts alone. Scripts stay plain SQL: the runner owns `BEGIN`/`COMMIT` and the foreign-keys pragma; a script-internal PRAGMA is a silent no-op.
2. **Backup contract (D7), owned by the migration runner:** before applying any migration above the current version, the runner copies the DB file to `<name>.bak-v<N>`. Rehearsal procedure: copy the production DB, migrate the copy, run the diff tests against the copy. Backup retention count decided at L2. This replaces "be careful" with a step a test can check.
3. **Boot-check contract:** each engine's schema check is a minimum. New floors recorded per engine in the same change. Any test that pins `version == 10` is a declared churn point when the floor moves.
4. **Gatekeeper contract:** new validators join the existing human-only list. The AI write path is unchanged (master plan rule 1: AI never writes).
5. **CLI contract (S1, I12):** one command per operation, explicit flags, exit 0 / non-zero, stdout data, stderr errors, inspectable output. Input click rejects before any code (unknown flag, non-integer) is tested by exit code, not by error code.
6. **Read-only contract:** cluster 3 writes nothing to the DB. Proof: DB file hash identical before and after.
7. **Ledger contract:** `change_log` stays append-only (master plan rule 7). No migration rewrites existing history rows.

## 4. Global Rules Touched

Grows: the human-only operations list gains `edit_item` and `remove_link` (rule 5 already names them; they had no implementation).

Pending cluster 2 ruling: rule 7 ("historical items immutable") — cluster 2 answers whether text edits exist; the ADR Either records a scoping amendment to rule 7 or rules edits out.

Unchanged: AI never writes (rule 1). Mutations pass gatekeepers (rule 2). `Challenged` resolution human-only (rule 6).

## 5. Test Strategy

Same pyramid as master plan §7. Per cluster:

- Migration integration tests: v10 → new version on a real temp DB. Contract 1's diffs, plus `test_failed_rebuild_leaves_intact_v10_database` for the case a rebuild fails mid-copy, plus the fresh-install path (all migrations in number order on an empty DB).
- Unit tests on pure cores (validators, filters, replay step). Fakes per T3, not mocks.
- CLI checks per S1 with exact exit codes and sample output.
- Read-only proof for cluster 3: DB file hash identical before and after.
- Architecture tests (T9): every new core module or subpackage is added to `tests/test_architecture.py`; the per-engine globs become recursive. Migration and rebuild code stays under `ember/adapters` (T9 does not apply there; B3 does) and a test asserts no engine core imports it.
- Error codes (I17, I21): **no new family.** Cluster 1 raises the existing per-engine migration codes at the call site (RELATE-012/013/014, MAINTAIN-007/008/009, QUERY-003/004). New codes continue from the highest existing number per family: CAPTURE-017, MAINTAIN-013, QUERY-006, RELATE-038. Removed RELATE numbers (002-004, 015, 020, 034) stay removed, per engine-relate-plan §7. Codes assigned at L2, never invented at L3.

## 6. Ordering

One shared decision gates two clusters, so it is recorded first: the #15 ruling (what happens to a UNIQUE triple containing a reversed or removed row). After that:

- Cluster 1 (schema) then cluster 2 (writers) — `remove_link`'s design sits on the #15 ruling and on the `links` immutability amendment.
- Cluster 3 and cluster 4 have no dependency on either and may interleave anywhere. Cluster 4's decisions are recordings, not code, and can land while 1 and 2 are in build.

## 7. L2 Breakdown (next level)

- Cluster 1 → one new L2, cross-engine storage work: `plans/hardening-schema-plan.md`. It owns the trigger design, the `links` reversal column, the #15 ruling's schema half, and the rebuild mechanics (only if #15 is decided "build"). Name deviates from the `engine-<name>` pattern deliberately — the work belongs to no single engine. Deviation recorded at this L1.
- Cluster 1 also records amendments to `plans/engine-relate-plan.md`: the links-immutability clause, gatekeeper rules 8 and 9, and the RELATE-028 message. A shipped L2 contract ("links immutable for life") is being narrowed here, and that must be written where it is frozen.
- Cluster 2 → amendment appended to `plans/engine-maintain-plan.md` (human-only ops already live there). It amends two clauses: "Maintain never writes `links`" (for `remove_link`) and the rule-7 scoping from the ADR. It also updates the issue-#1 owner cells in the maintain and query L2 §0 tables (both currently say Capture).
- Cluster 3 → amendment appended to `plans/engine-query-plan.md`: the three flags only. #18 is not absorbed; its standing decision is recorded in §2 (superseded or confirmed by the maintainer, then it either stays with its utility plan or gets its own L2 later).
- Cluster 4 → no L2. Decisions land as ADRs or notes referenced from master plan §5/§9 and the issues themselves. If a decision flips to "build", it gets its own L2 amendment then.
- Master plan: the pointer to this phase plan in §8 is the entry point (D3). The framework defines three levels; this document is an L1-scale phase plan recorded as an amendment in substance, with its own smaller L2 set declared here.

## 8. Out of Scope (whole phase)

- New engines, new AI ports, new dependencies.
- `items` table rebuild — explicitly out; #23 ships as a trigger.
- `links` table rebuild — only if #15 is decided "build".
- #4 external vector DB. Embedding model swap (master plan §9). Signals wrapper unless the trigger fires (#8). Boundary-crossing fix for #21 unless the reversal column makes it free.
- Pagination beyond explicit flags. Rework of shipped engine cores beyond what a cluster names.
- Link deletion by DELETE — forbidden; see Cluster 2.

## 9. Issue → Cluster Map (closure table)

| Cluster | Issues |
| --- | --- |
| 1 Schema enforcement | #15, #17, #20, #21, #23 |
| 2 Human edit commands | #1, #19 |
| 3 Read surface | #26, #27, #28 (+ #18 ruling only) |
| 4 Decide-then-act singles | #5, #8, #12, #14, #16 |

Total: 16 issues, each in exactly one cluster. #4 excluded by choice.

## 10. Next Step

This draft integrated 26 review findings (5 parallel reviewers: spec compliance, Constitution, error codes, over-engineering, migration safety). Human reviews and signals clean or requests changes (framework §3). Then L2s per §7, schema plan first, then L3 step plans, then tickets via the to-tickets skill.

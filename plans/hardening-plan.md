# L1 Hardening Phase Plan

Terse caveman style. Level: L1 (phase plan under `plans/master-plan.md`). Resolves the 16 open tracker issues left after the four engines shipped. Source: GitHub issues #1..#28 except #4 (excluded by maintainer choice). No invention — every item cites its issue.

## 0. Status + Stack

- Four engines shipped and merged: capture (#3), relate (#13), maintain (#25), query (#29). V1 build complete.
- This phase = hardening. No new engine. No new dependency. No stack change — master plan §0 stands.
- Schema version moves past 10. New migrations continue the numbered sequence (D6). Migrations 001..010 exist.
- All 16 issues are `deferred` or `note` labelled. None is a wontfix (recorded 2026-10-28: rejections vs deferrals).
- #4 (external vector DB) stays out: parked by choice, not in this phase.

## 1. Phase Job (one job)

Make the guarantees real. Today most guarantees live in application code only (gatekeepers, write paths). Two spec requirements have no owner (plain-text export, human edit commands). This phase closes that gap with four work clusters.

## 2. The Four Clusters

### Cluster 1 — Schema enforcement (issues #17, #15, #20, #21, #23)

Job: the database guarantees what the gatekeepers already enforce.

- #17: link compatibility table enforced at DB level. Today it lives only in Python; an illegal pair is one direct INSERT away.
- #20: reversed supersedes visible to every reader. Today only Maintain reads the `change_log` marker.
- #15: same-pair re-supersede after reversal decided. Today the UNIQUE triple blocks it forever.
- #21: corrective inverse after reversal. Today `RELATE-028` false-rejects; cheap partial = better error message.
- #23: `Closed` implies `close_reason`. Today enforced in the write path only.

Mechanism: new numbered migrations; `links` and `items` table rebuilds (D6). Engine boot checks are minimums, so schema growth is backward-compatible; each engine's minimum is re-verified, not rewritten.

Constitution tension to settle (D3): a reversal marker on the `links` row makes reversal truth live in two places (`change_log` + row). Ruling recorded here: `change_log` stays the source (D1); the row column is derived, rebuildable, labelled as such. Rebuilds never rewrite history rows.

### Cluster 2 — Human edit commands (issues #19, #1)

Job: the two human-only operations the master plan names (`edit_item`, `remove_link`) exist as commands plus gatekeepers.

- Spec question answered before any code, recorded as a decision: master plan rule 7 says historical items are immutable; #19 records that text editing has no answer. One ruling, then build.
- #1 rides on `edit_item`: it is the writer for `items.rationale` (Decision) and `items.source` (Finding) per master plan §5. No writer exists today (verified: the item INSERT writes 7 columns, never these).
- `remove_link` constraint: `change_log.link_id` carries a foreign key to `links` (migration 008). Deletion must not orphan history. Working direction, not a decision: a status change to the existing `Rejected` value instead of a DELETE keeps the FK and the ledger intact.
- Existing ruling carried forward: removing a `supersedes` link does not reopen the superseded item (engine-maintain-plan §8).
- Gatekeepers: `validate_edit_item`, `validate_remove_link` join the human-only list (master plan line 83).

### Cluster 3 — Read surface (issues #18, #26, #27, #28)

Job: query gains the read features the spec deferred. All read-only; never writes (Engine D contract).

- #18 plain-text export: spec 3.6 requirement, currently unowned. Output covers every item, link and `change_log` row. Writes a file, never the DB.
- #26: `--limit` on topic-search. Default stays no cap.
- #27: `--status` / `--type` filters on topic-search.
- #28: `--limit` / `--offset` or `--since` on history. Never a silent default cap.

Out of scope: BM25 retuning (`k1`/`b` stay), AI in query, ranking changes.

### Cluster 4 — Decide-then-act singles (issues #5, #8, #12, #14, #16)

Job: resolve parked decisions. For each issue: record exactly one decision — build now, keep deferred with an updated trigger, or reject with an `.out-of-scope` note. Code only after a recorded decision. Default when nothing changes: stays deferred, issue updated with the current trigger, never silently closed.

- #5 `items.metadata` column: no writer exists; needs a writer decision.
- #8 Signals wrapper: trigger is a 4th signal. BM25 exists but does not feed relate (verified: no Query import anywhere in relate).
- #12 embedder model-change re-encode cost: a measurement, not a feature.
- #14 sticky manual clear: spec question — does a human clear cover one trigger or all future ones?
- #16 AI-proposed `close_item`: master plan §5 already defers it to V1.x with a written rationale.

## 3. Phase Contracts

1. **Migration contract:** one numbered migration per schema change. Every rebuild preserves row counts and every existing column (D5: no renames). Rehearsal on a copy before production (D7). Failure rolls back (the migration runner already behaves this way).
2. **Boot-check contract:** each engine's schema check is a minimum. New minimums recorded per engine, checked in the same change. No engine is rewritten for this phase except where a cluster names it.
3. **Gatekeeper contract:** new validators join the existing human-only list. The AI write path is unchanged (master plan rule 1: AI never writes).
4. **CLI contract (S1, I12):** one command per operation, explicit flags, exit 0 / non-zero, stdout data, stderr errors, inspectable output.
5. **Read-only contract:** cluster 3 writes nothing to the DB. Proof method: DB file hash identical before and after (the same proof used to verify Engine D).
6. **Ledger contract:** `change_log` stays append-only (master plan rule 7). No migration rewrites existing history rows.

## 4. Global Rules Touched

Unchanged: AI never writes (rule 1). Mutations pass gatekeepers (rule 2). `Challenged` resolution human-only (rule 6). History immutable (rule 7).

Grows: the human-only operations list gains `edit_item` and `remove_link` (rule 5 already names them; they had no implementation). Nothing else in §4 changes.

## 5. Test Strategy

Same pyramid as master plan §7. Per cluster:

- Migration integration tests: v10 → new version on a real temp DB. Row counts and columns preserved, failure rolls back, idempotence.
- Unit tests on pure cores (validators, filters, export formatter). Fakes per T3, not mocks.
- CLI checks per S1 with exact exit codes and sample output.
- Read-only proof for cluster 3: DB file hash identical before and after.
- New error codes per I17: stable, named, never reused, family prefixes follow the existing per-engine pattern (`MAINTAIN-`, `QUERY-`, `RELATE-`, `CAPTURE-`). Codes assigned at L2, never invented at L3.

## 6. Ordering

Bottom-up, one cluster at a time (framework invariant 2):

1. Cluster 1 first (schema). It defines the shapes clusters 2 and 3 read.
2. Cluster 2 second (writers) — it must follow cluster 1: `edit_item` and `remove_link` write the new shapes, and the #15 ruling (what happens to a UNIQUE triple) constrains `remove_link`.
3. Cluster 3 and cluster 4 have no dependency on 1 or 2 and may interleave anywhere. Cluster 4's decisions can land while 1 and 2 are in build, since they are recordings, not code.

## 7. L2 Breakdown (next level)

- Cluster 1 → one new L2, cross-engine storage work: `plans/hardening-schema-plan.md`. Name deviates from the `engine-<name>` pattern deliberately — the work belongs to no single engine. Deviation recorded here at L1.
- Cluster 2 → amendment appended to `plans/engine-maintain-plan.md` (human-only ops already live there: close-item, set-status, reverse-supersedes). New section: "V1.x: human edit commands".
- Cluster 3 → amendment appended to `plans/engine-query-plan.md`. New section: "V1.x: read surface".
- Cluster 4 → no L2. Decisions land as ADRs or notes referenced from master plan §5/§9 and the issues themselves. If a decision flips to "build", it gets its own L2 amendment then.
- Master plan: a pointer to this phase plan is added to §8, so the top-level plan stays the single entry point (D3).

## 8. Out of Scope (whole phase)

- New engines, new AI ports, new dependencies.
- #4 external vector DB. Embedding model swap (master plan §9). Signals wrapper unless the trigger fires (#8).
- Pagination beyond explicit flags. Rework of shipped engine cores beyond what a cluster names.
- Link deletion by DROP-style API: forbidden; see Cluster 2 constraint.

## 9. Issue → Cluster Map (closure table)

| Cluster | Issues |
| --- | --- |
| 1 Schema enforcement | #15, #17, #20, #21, #23 |
| 2 Human edit commands | #1, #19 |
| 3 Read surface | #18, #26, #27, #28 |
| 4 Decide-then-act singles | #5, #8, #12, #14, #16 |

Total: 16 issues, each in exactly one cluster. #4 excluded by choice.

## 10. Next Step

Review gate on this L1: parallel sub-agents for spec compliance, Constitution alignment, error codes, over-engineering, migration safety. Human approves or requests changes (framework §3, budget 2-4 cycles). Then L2s per §7, schema plan first. L3 step plans after each L2 is clean. Tickets via the to-tickets skill only after L3 plans exist.

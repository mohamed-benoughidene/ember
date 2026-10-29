# Hardening Decisions — Cluster 4 (issues #5, #8, #12, #14, #16)

Decision brief under `plans/hardening-plan.md` §2 Cluster 4 (the L1 amendment, 2026-10-28). These five issues are decide-then-act: each one needs the maintainer to record exactly one decision — **build now**, **keep deferred with an updated trigger**, or **reject with an `.out-of-scope` note** (`hardening-plan.md` §2: "Code only after a recorded decision").

**This brief recommends. It does not decide.** Cluster 4 has no L2 (`hardening-plan.md` §7): a "build" decision gets its own L2 amendment at that moment. All five decisions were made by the maintainer on 2026-10-29, with no deferrals: #5 build, #8 build, #12 build (measurement), #14 option (c) timestamp shield, #16 build (pre-filtered).

Every code claim below was verified by reading the real file and symbol on branch `feat/hardening` on 2026-10-28. Where verification corrected a claim this brief inherited, the correction is stated in place.

---

## #5 — `items.metadata` column (project-area signal)

**Current state (verified).** The column does not exist. The `items` table is built by three migrations and none adds it: `ember/adapters/migrations/002_create_items.sql` (7 columns), `004_add_item_detail_columns.sql` (adds `rationale`, `source`), `010_add_item_close_reason.sql` (adds `close_reason`, `status_origin`). All three were read. Relate's metadata signal today is a time proxy: `_metadata_signal` in `ember/relate/candidate_pool.py` (line 164) keeps only items whose `created_at` sits within `METADATA_WINDOW` (±30 days, line 27) of the new item's `created_at`. There is also no writer anywhere: the capture AI proposal is checked to exactly four keys (`type`, `statement`, `source_quote`, `confidence` — `ItemProposal` in `ember/capture/item_proposal.py`, line 62), so nothing today could populate the column.

**The decision to make.** Add `items.metadata` (or a sibling table) and pick who writes it — a capture-time input, a human command, or a folder/tag convention — or keep the 30-day time proxy.

**Options.**

- **Build now:** one numbered migration (`ALTER TABLE items ADD COLUMN metadata TEXT`, no rebuild — fits the L1 migration contract; migration number = next free AFTER cluster 1's 011, and after 012 if the #15 relax branch builds; pinned at that moment's L2 amendment, not assumed), a writer (the hard part: which of capture / human / convention), and `_metadata_signal` extended to a third sub-signal under `metadata`.
- **Keep deferred:** no schema change. The time proxy stays the whole "metadata" signal. Updated trigger below.
- **Reject** (`.out-of-scope/items-metadata-column.md`): "`items.metadata` project-area column rejected 2026-10-28: project area has no writer and no demonstrated need at single-user scale; the 30-day `created_at` proxy in `ember/relate/candidate_pool.py:_metadata_signal` is the standing substitute. Rejected, not deferred — reopen as a new issue if a real tagging workflow appears."

**Recommendation: keep deferred.** The proxy works and the column's "Done when" on the issue is honest: nothing writes it, so adding the column alone changes no ranking — it would be an empty column. Picking a writer is the actual spec decision (capture-time? manual? convention?), and inventing one now violates P1 (no decorative architecture) and the phase rule of no new features. The honest cost of waiting: the proxy is coarse and will silently pull wrong-area candidates; that is acceptable at a corpus of dozens of items and detectable in `ember relate` output when it stops being acceptable.

**Cost if built.** One migration (cheap, per the L1 contract). The real cost is the writer: a capture-time input changes the AI schema and prompt (`item_proposal.py`), a human command is a new Maintain-surface operation, a convention needs documentation plus a reader rule. Plus a reader change in `candidate_pool.py` and its tests. Roughly: 1 migration + 1 writer path + 1 signal branch — a small L2 amendment, not a new engine.

**Decision: build (maintainer, 2026-10-29).** Writer: capture AI proposes a project label, the human can correct it inline in the existing [e]dit path of the confirm loop, and relate reads the column instead of the 30-day proxy. The L2 amendment and the migration number are pinned at build time (next free number).

---

## #8 — `Signals` wrapper object

**Current state (verified).** No `Signals` class exists anywhere in the repo (grep for `class Signals` / `Signals(`: zero hits). Phase 2 combines exactly three signals — `build_candidate_pool` in `ember/relate/candidate_pool.py` (lines 30–89; the signal composition block is lines 71–89) runs `_content_signal`, `_graph_signal`, `_metadata_signal` and merges via `_merge`. BM25 exists in the query engine (`ember/query/topic_search.py` scoring, `ember/query/tokenize.py`), and `ember/relate` imports nothing from `ember.query` (grep across `ember/relate/`: zero hits) — matching the L1 line "BM25 exists but does not feed relate".

**The decision to make.** Introduce the `Signals` wrapper now, or keep the flat three-signal core until the issue's trigger fires.

**Options.**

- **Build now:** wrap the three signal results in one `Signals` object at the `build_candidate_pool` boundary. Note what this costs: a wrapper holding three fields, read by exactly one consumer, purely restructured.
- **Keep deferred:** trigger stays a 4th signal, sharpened below.
- **Reject** (`.out-of-scope/signals-wrapper.md`): "`Signals` wrapper rejected 2026-10-28: the candidate pool core is stable at three signals and master plan §2 explicitly excludes BM25 from the pool; a wrapper for a fixed three-tuple is decoration. Rejected — a new issue may be filed if a 4th signal is ever approved into Phase 2 by L1 amendment."

**Recommendation: keep deferred, and say plainly why both "build" temptations fail P1.** P1 (no decorative architecture) cuts both ways here, and the brief weights it honestly: (a) the wrapper itself is decoration — one consumer, three fields, no hidden decision to make (B4 fails); (b) but so is adding BM25 *just to justify* the wrapper. BM25 as a 4th relate signal is **available-but-unwanted**: master plan §2 states "BM25 keyword search excluded from candidate pool" as an L1 decision, and tokenization is Engine D's module (B1/B2 — relate reaching into `ember.query.tokenize` would cross a module boundary for a scoring idea the L1 already rejected). So the only honest path to the wrapper runs through an L1 amendment that adds a 4th signal for its own reasons. Until that exists, the trigger cannot self-fire.

**Cost if built.** No new module, no migration, no port. One file (`candidate_pool.py`) plus its unit/integration tests, roughly half a day including churn to every `counts` assertion. This amends `plans/engine-relate-plan.md`'s frozen return shape (`Pool(ranked, counts, warning)`) and the CLI output test; per the brief's own rule this build option gets its own L2 amendment at that moment — priced here as 'small' only because the wrapper is shelling, not redesign. It is the cheapest "build" of the five — cheap is not the same as useful.

**Decision: build (maintainer, 2026-10-29), against this brief's defer recommendation.** Wrapper only: the three existing fields, no fourth signal, no BM25 into the pool. The recorded warning stands: at single-user scale this buys structure without behavior change. Pool's external shape stays Pool(ranked, counts, warning) unless the build-time L2 amendment says otherwise.

---

## #12 — embedder re-encode cost at scale (a measurement, not a feature)

**Current state (verified).** The wipe path is real and automatic: `_model_change_warning` in `ember/relate/candidate_pool.py` (lines 92–98) runs on **every** `ember relate` invocation (line 62, unconditional), reads one cached model name, and if it differs from the active model calls `store.wipe()` and returns the STDERR warning `MODEL_CHANGED_LINE` (lines 22–24: "one-time minutes-long cost on large DBs"). Scale has never been measured. **Correction to the ground truth this brief was given:** the largest seeded test corpus is not 4 items — integration test `test_seeded_pool_ranks_by_cosine_then_id_and_counts_all_three_signals` in `tests/relate/test_candidate_pool_integration.py` seeds 11 items (ids 1–11, docstring lines 122–127). Either way the conclusion holds: the tests use `FakeEmbedder` with fixed vectors, so the real `bge-base-en-v1.5` encode cost has never run in any test.

**The decision to make.** Run the measurement now (a scale test: synthetic large DB, model change, time the wipe + re-encode), or keep it deferred.

**Options.**

- **Build now:** one throwaway script/test that seeds a synthetic DB at 500–5,000 items (master plan §6.3's own scale range), forces a model-name change, and times the wipe + re-encode. This is T-honest: the stall is real, it fires mid-command with no progress output, and nothing measures it — an untested minutes-long freeze on real data.
- **Keep deferred:** the trigger is tied to the things that make the stall matter: a real model swap (master plan §9 defers the embedder swap) or a real corpus size.
- **Reject** (`.out-of-scope/embedder-scale-measurement.md`): "embedder re-encode scale measurement rejected 2026-10-28: the wipe warning already names the cost to the user and the model swap itself is deferred (master plan §9). Rejected — a new issue may be filed if a swap is scheduled."

**Recommendation: keep deferred — with the weakest conviction of the five, and the maintainer may reasonably flip this one to build.** The honest weighing: the measurement answers a question that only becomes decision-relevant when a model swap is on the table, and the swap is itself deferred (§9); a number gathered now goes stale with the embedder ecosystem anyway. But two facts argue the other way and should not be hidden: (1) the wipe fires **automatically** on a routine `ember relate` run — nobody confirms it — so a slow DB could freeze a command with no warning beyond one STDERR line; (2) the measurement is a single script, zero production risk, no migration. If the maintainer wants one thing out of Cluster 4 today, this is the cheapest genuine hedge. Still deferred by default: at the current tiny real corpus the stall is seconds, not minutes.

**Cost if built.** No production code. One `scripts/` measurement — one command, runnable alone (S1-style), result recorded as a number on the issue. NOT a regression test (T4 economics and T10; timing assertions are flaky). One synthetic-DB fixture; runtime is the point (minutes). It requires the `.[relate]` extra installed and a one-time HuggingFace model download (network + ~419 MB + load timeout); runs manually on the maintainer's machine, skipped in CI. No migration, no port, no new module. Prefer folding this into the already-reserved master-plan §6.3 #3 recall scale test (500–5,000 items) — same synthetic fixture, same encode cost — rather than seeding a second corpus; a separate throwaway needs a stated reason.

**Decision: build (maintainer, 2026-10-29).** One measurement script, synthetic 500-5000 item database, forced model change, timed wipe and re-encode, the number recorded on the issue. No production code.

---

## #14 — sticky manual clear: one trigger or all future triggers?

**Current state (verified).** The shield is `items.status_origin` (migration `010_add_item_close_reason.sql`, `CHECK (status_origin IN ('derived','manual'))`, default `'derived'`). It is written in exactly one place: `run_set_status` in `ember/maintain/run_maintain.py` (line 162) calls `apply_status_origin(item_id, "manual")` — and only on an applied `Challenged → Active` clear (condition lines 156–161). `apply_status_origin` (`ember/adapters/sqlite.py`, line 805) writes the column **and** a `change_log` row (`field_changed='status_origin'`, `trigger_cause='user_set_status'`, lines 826–834). No code path ever resets it to `'derived'` — the sole caller passes `"manual"` and nothing else. The consumer is `merge_and_filter` in `ember/maintain/derive.py` (line 68): a shielded item is skipped by every derived change, including a brand-new `contradicts` challenge from `_challenge_candidates` (lines 133–157, causes `contradicts_confirmed` / `dependency_closed`). So today a human clear is a **permanent veto over every future trigger** — the issue's description is accurate against the code.

**The decision to make.** A spec question, stated sharply: when a human clears a Challenged item, does that human judgment settle *the contradiction(s) that caused the flag*, or settle *the item*? Reading (a) — per-trigger acknowledgment — says a **different, later** trigger should re-flag; reading (b) — sticky as built — says the human looked at the item and closed the topic for it.

**Options.**

- **Build now (reading a):** Two concrete mechanisms, both defensible:
  1. *Timestamp comparison* (no migration): the sweep re-flags a shielded item when the triggering link's `created_at` is **newer** than the item's last `status_origin='manual'` `change_log` row (`sqlite.py:826` already records that timestamp). Test: seed cleared item with a `change_log` manual row at T1, confirm a `contradicts` link at T2 > T1, sweep → item `Challenged` again; and the mirror test at T2 < T1 → stays `Active`.
  2. *Per-trigger acknowledgment* (state, arguably a new column or a `change_log` read): record *which* trigger cause/link a clear acknowledged; only an unseen trigger re-flags. Test: clear item cleared under `contradicts_confirmed` link 5, confirm a *different* contradicts link 6, sweep → `Challenged`; re-confirm the *same* link's condition → stays `Active`. Needs a ruling on where the acknowledgment state lives (D3: one fact, one place).
- **Keep deferred:** the behavior ships as documented intent ("sticky"), not a bug. Updated trigger below.
- **Reject** (`.out-of-scope/sticky-manual-clear.md`): "sticky manual clear rejected 2026-10-28: Spec 3.5's 'until human clears them' is read as final — the human cleared the item, full stop; future triggers are mitigated by the human clearing again. Rejected, not deferred — the `status_origin` column semantics are frozen as 'permanent veto'."

**Recommendation: keep deferred — but flag hard: this is the one issue in Cluster 4 where the maintainer genuinely must choose between two defensible readings, and deferral only postpones the choice.** The steelman for each: reading (b) is what the code does and matches master plan §2's words "stay Challenged **until human clears them**" — a human resolver outranks the sweep (rule 6), and re-challenging what a human explicitly cleared could crowd the graph with noise the human already silenced. Reading (a) matches intent: the human answered *the old contradiction*; a new confirmed contradiction is new information the spec's rule 3 says must make the target `Challenged` — under (b), spec rule 3 has a silent, human-shaped exception no spec line grants. The brief leans (a) if forced, because (b) permanently mutes a *correctness* signal for zero implementation savings beyond doing nothing. But the honest default is deferral: no real usage has hit this, and the fix should be chosen with an actual incident in hand, not in the abstract.

**Cost if built.** Reading (a) mechanism 1 (timestamp compare): no migration; ~1 new port read or `change_log` join in the Maintain snapshot, a change to `merge_and_filter`'s shield skip, plus the two-tests-above. Mechanism 2 (per-trigger): a new migration (this phase's only additive-column candidate if chosen; migration number = next free AFTER cluster 1's 011, and after 012 if the #15 relax branch builds; pinned at that moment's L2 amendment, not assumed) + acknowledgment path. If the additive column is chosen, it inherits cluster 1's D3 ruling as written (`plans/hardening-schema-plan.md` §6): ledger stays source, column derived and labelled, one-transaction pairing, replay test. Add the clock-tie test: a contradicts link and the manual-clear ledger row sharing a timestamp resolve by `change_log.id` (the replay precedent). Either is a small L2 amendment to `plans/engine-maintain-plan.md` §2 Gap B.

**Decision: option (c), timestamp-scoped shield, full scope (maintainer, 2026-10-29).** A manual clear silences evidence older than the clear (its change_log timestamp). Evidence newer than the clear passes the shield, for every derived change (re-flags and closes alike). Ties break by change_log id, matching the history sort convention. No migration. Three-agent panel unanimous (contrariant, first-principles, practitioner).

---

## #16 — AI-proposed `close_item`

**Current state (verified).** `close_item` is human-only: `validate_close_item` in `ember/maintain/human_actions.py` (line 49) accepts only the two human-settable reasons — `HUMAN_SETTABLE_REASONS` at line 33 is `{invalidated, expired}`; anything else raises `MAINTAIN-003` (line 74). Those two reasons are the **only** path to `invalidated`/`expired` closes (rules 1 and 2 in `derive.py` produce only `superseded`/`answered`), which is exactly why the human command cannot be dropped. Engine C has no AI surface at all: no LLM import or `ai_responses` reference anywhere under `ember/maintain/` (grep: zero hits). Master plan §5 (line 131) records the standing deferral: "AI-proposed `close_item` deferred to V1.x … the human running the command is the confirmation."

**The decision to make.** Build the AI proposal path now (an AI port inside Maintain, an `ai_responses` row per D8, parse/retry per T7, per-call cost), or keep the human command as the only close path.

**Options.**

- **Build now:** new `LinkProposerPort`-style AI port under `ember/maintain/`, proposal → human confirm → existing `validate_close_item` path, raw response stored verbatim (D8/I16), fixture tests (T7). This also removes Maintain's "first engine with no live tier" property the deferral was protecting.
- **Keep deferred:** master plan §5 line stays; updated trigger below.
- **Reject** (`.out-of-scope/ai-proposed-close-item.md`): "AI-proposed `close_item` rejected 2026-10-28: close reasons `invalidated`/`expired` are low-frequency human judgments; an AI proposal adds a prompt, a parser, an `ai_responses` row (D8), retries and cost to produce a decision the human makes with one flag. Rejected — Engine C stays the no-live-tier engine; a new issue may be filed if close-item volume becomes a real bottleneck."

**Recommendation: keep deferred.** Steelman for building: capture mode B already sends the newest 50 items (`CONTEXT_WINDOW`) to the model, so it could notice "this Question was answered by item 12 long ago" and save the human from auditing stale items manually; and closing items is maintenance debt that silently grows. Steelman for keeping (the standing rationale, which still holds): at V1 scale a human reviews every proposal anyway — the AI's judgment would be *checked, then typed into the same command*, so the proposal adds a step instead of removing one; plus the cost of arming D8/I16/T7/T8 for Maintain and an L1 amendment (rule 3 currently lists only `add_item`/`add_link` as AI-callable). Value is negative at current scale: single user, low item turnover, and `ember close-item --item N --reason R` already exists. The trigger should be a volume number, not a vibe.

**Cost if built.** An AI port module + adapter under `ember/maintain/` (Maintain gains its first adapter — defeats its "no live tier" §7.7 property), `ai_responses` writes keyed how D8 dictates (`save()` already accepts `item_id` — migration 009 made `source_id` nullable and added a nullable `item_id REFERENCES items(id)`; the adapter enforces exactly-one-of, and Relate already saves by `item_id`. A closed item always HAS a `source_id`. The open question is narrower: whether a close *proposal* logs against the item before human acceptance, and which Maintain port owns the save), retry policy, fixtures + tests, and L1 amendments to BOTH §4 rule 3 and the §5 deferral line (master-plan line 131 freezes the human-only close-item decision). Roughly one step-plan's worth of work — the largest "build" of the five.

**Decision: build, pre-filtered (maintainer, 2026-10-29).** The sweep pre-filters stale candidates with deterministic rules (example: Active Questions with an old confirmed answers link), the AI sees only that shortlist (typically 0-3 cards, never a full-corpus scan), proposes close with reason, the human confirms through the existing validate path, one ledger row. Maintain gains its first AI port.

---

## Build order if multiple flip

#12 → #5 (writer ruling first) → #14 (after cluster 1's migration) → #16 (D8 ruling + L1 amendments first). #8 cannot start until an L1 amendment adds a 4th signal for its own reasons — 'build now' is not executable for it today.

## Default if no answer

If the maintainer answers nothing, the L1 rule applies: every issue **stays deferred, its trigger text refreshed, never silently closed**. No code is written. Each landed decision ALSO updates its master-plan §5/§9 line — they go stale the moment a decision lands. Below is the refreshed trigger text per issue, ready to paste into each issue body (replace only the trigger/re-open line; keep the rest of the issue as-is).

- **#5:** "Re-open trigger: build when the capture `ItemProposal` schema gains a project-area key in a recorded amendment, or a human labelling command ships in Maintain — or when the 30-day `created_at` proxy in `ember/relate/candidate_pool.py:_metadata_signal` is observed ranking wrong-area candidates above right-area ones on the live corpus. Not before either."

- **#8:** "Re-open trigger: a 4th signal is approved into Phase 2 by an L1 amendment (master plan §2 currently excludes BM25 from the candidate pool, so no existing component qualifies). Introduce the `Signals` wrapper in the same change as that 4th signal — not before, and not by adding a signal merely to justify the wrapper."

- **#12:** "Re-open trigger: run the scale measurement before the first embedder model swap on real data (master plan §9), or when the live database passes 1,000 items — whichever comes first. Until then this stays a measurement, not a feature."

- **#14:** "Re-open trigger: the first real daily-use incident where a newly confirmed `contradicts` link (or dependency close) is silently ignored for a hand-cleared item — decide the spec reading then: (a) per-trigger acknowledgment (timestamp comparison against the `change_log` `status_origin` row, or recorded trigger state) or (b) sticky forever (document current behavior). Spec decision first, code second."

- **#16:** "Re-open trigger: the human `ember close-item` workflow measurably bottlenecks — ≥ 3 `user_closed` change_log rows (`invalidated`/`expired`) in any rolling 7-day window, countable from the ledger (`trigger_cause='user_closed'`) — where an AI proposal would remove a review step rather than add one. Requires an L1 amendment and an `ai_responses` design for closes. Not before real close volume exists."

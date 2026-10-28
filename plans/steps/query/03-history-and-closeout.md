# L3 Query Step 3: History + Closeout (Phases 2+3+4 for mode 4, plus the engine closeout)

Implements L2 Query plan §4.6 (the `change_log` classifier), §4 Phase 2 history rules (union, global view), §4.7 (the `history --item` gate), §5 (CLI), and the L2 §11 closeout owned by step 03: README (§11.4) and the PROJECT_MAP code listings (§11.5), plus the tracker work (verify issues #7 #22 #24 closed with evidence; open the L2 §9 `deferred` issues). §11.1–11.3 cross-plan amendments were already applied by the planning commit — this step only verifies them. Builds entirely on step 01's seam and step 02's render/orchestrate shape — no port or model changes, no L2 amendments.

## 0. Constitution rules this step enforces

- **B1** — the classifier, the derivation, the renderer are separate pure modules; the closeout docs are not code.
- **B2 / B3 / P4** — history reads `change_log` + `links` only through the port.
- **D3** — `change_log` stays the one ledger of record; the classifier interprets rows, never rewrites or re-encodes them; `old_value` / `new_value` render verbatim (the one derived field is `close_reason`, computed by the documented splitter so the two cannot disagree).
- **I1** — named by job: `history`, `run_history`, `classify_change_row`.
- **I4** — returns `list[HistoryEvent]`; empty result is an empty list.
- **I8** — no result is a success with `count: 0`; only a *named-but-missing* item is an error.
- **I9** — `validate_query_item` runs only when an explicit `--item` is given; the global view validates nothing (the review decision recorded in L2 §4.7).
- **D4** — the `--item` flag is outside data, validated at the gate before the core sees it.
- **I17 / I21** — no new codes; QUERY-001 and QUERY-005 only.
- **P3** — Load → Derive (pure) → Render → CLI.
- **T1** — the classifier is a pure mapping on `(field_changed, trigger_cause)` pairs; the derivation is a pure union + sort.
- **T4** — this step's closeout includes the pyramid tally check against the actual suite.

## 1. Job

Show the ledger. `ember history --item ID` returns that item's events by the union rule; `ember history` with no `--item` returns the whole ledger including Capture's NULL-subject `proposed` rows. Then close the engine out: docs, map, amendments, issue closures.

## 2. Inputs

- `--item ID` (**optional**, `type=int`), `--db PATH`. With `--item`: `validate_query_item` raises QUERY-001 for an unknown id — same meaning as `why`, because the user named a specific item. Without: no gate, no lookup call — the global view never raises QUERY-001 (L2 §4.7, decided at review 2026-10-28).
- Reads (unchanged port, L2 §4.5): `list_change_log()` + `list_links()`.

## 3. Outputs

Row model (added to `ember/query/rows.py`, L2 §4.5):
- `HistoryEvent(timestamp, kind, cause, field_changed, item_id, link_id, link_source_item_id, link_target_item_id, link_type, old_value, new_value, close_reason)` — `item_id` means "the subject Engine C/B recorded"; the two `link_*_item_id` fields sit beside it so the two meanings never blur (L2 §4.6).

Envelope: `{"mode": "history", "item_id": N or null, "count": N, "events": [HistoryEvent, …]}` — `item_id` is `null` for the global view.

Signature (L2 §4 Phase 2): `history(rows, links, item_id) -> list[HistoryEvent]`.

## 4. Steps

1. Classifier (`ember/query/history.py`, pure), per the L2 §4.6 table — `kind` is derived from the **pair** `(field_changed, trigger_cause)`, never either half alone:
   - nine kinds: `created`, `proposed_rejected`, `validated`, `link_confirmed`, `link_rejected`, `status_changed`, `status_origin_changed`, `link_reversed`, `unknown`;
   - unrecognised `field_changed` → `unknown` with the raw pair visible, never a crash and never a dropped row;
   - `status_origin` and `link_reversed` rows are **not** status changes; their `close_reason` is null;
   - `close_reason` split: take `old_value` / `new_value`, split on the **first** `:`; no `:` → null reason; the literal segment `"None"` → null (the writer's `f"{status}:{reason}"` encoding, L2 §4.6).
2. Derivation (same module, pure), per L2 §4 Phase 2 history rules:
   - membership union: `row.item_id == N`, **or** `row.link_id` names a link where N is source or target; a row matching both appears **once**;
   - `item_id IS NULL` rows belong to no item — global view only;
   - order `(timestamp, id)` ascending, timestamps compared as opaque ISO text, `id` the tiebreak.
3. Renderer in `ember/query/render.py`: envelope above; Phase 3 does not re-sort.
4. `ember/query/run_query.py`: `run_history(lookup, item_id: int | None) -> str` — gate only when `item_id is not None` (I9), then load → derive → render.
5. `ember/cli.py`: `ember history [--item ID] [--db PATH]`; exit codes and stderr format as steps 01–02.
6. Closeout (code lands first, docs after, in the same step):
   - README (L2 §11.4): line 43 status → "Built and verified"; the four-command CLI block; the real test count **and the pyramid tally** (unit / integration / CLI / E2E) recorded from the actual run.
   - `PROJECT_MAP.md` (L2 §11.5): one line per new file (`ember/query/*`, `tests/query/*`), no new tables.
   - Cross-plan amendments §11.1–11.3: **verify only** — the planning commit already applied them (master plan lines 157/159; maintain §0/§8; relate §8). If any "from" text is still found, fix it; expected: none.
   - Issues **#7, #22, #24**: verify each is closed and add a closing comment with the test-run evidence (the tracker shows them closed since the L2 landed; the done-condition "built and verified" only becomes true now).
   - Open the `deferred` GitHub issues with the `deferred` label recorded during this engine's L3: step 02 §10's #2 (topic-search cap) and #3 (status/type filters), and this step's §10 #4 (history pagination).

## 5. Errors (codes only, per L2 §6)

- `QUERY-001` `QueryItemNotFound` — `history --item <unknown>`; context `item_id`; **never** from the global view. **L2 §4.7.**
- `QUERY-005` `ItemsReadFailed` — `list_change_log` / `list_links` failure. **L2 §4.5.**

No new codes. With this step every code 001–005 has at least one test target at the tier L2 §7.5 names (001/002 gatekeeper unit + CLI; 003/004/005 integration); QUERY-000 is the never-raised base, covered by the step-01 stable-values test.

## 6. Test Targets

Unit (pure core + fakes, no DB; all nine kinds per L2 §7.1):
- Each `(field_changed, trigger_cause)` pair in the L2 §4.6 table maps to its kind; the seven `status` causes are distinguished by `trigger_cause`; `user_set_status` and `reversal` each cover their two field types.
- `status_origin` / `link_reversed` get their own kinds and null `close_reason`.
- Splitter: `Closed:superseded` → (Closed, superseded); bare `Closed` → (Closed, null); **`Closed:None` → (Closed, null)**; NULL close_reason on a Closed item renders without failing.
- Union: item rule hit included; link-target hit included though `item_id` points at the source; unrelated row excluded; **both-conditions row appears once**; NULL-`item_id` row appears only in the global view.
- Order `(timestamp, id)`; unknown `field_changed` → `kind: "unknown"` with raw values, no crash.
- Gate on this mode (L2 §7.1, moved here where the behaviour lands): `history --item <unknown>` raises QUERY-001; the **global view makes no lookup call at all** and never raises QUERY-001 — a fake port whose `item_exists` raises if called proves it; a valid request returns without touching the core beyond the port reads.

E2E (L2 §7.6 — this step owns the engine's one E2E test):
- The house chain `capture → relate → maintain → query` on one temp DB via the existing fakes (`tests/fakes.py`), asserting JSON from all four query commands against that DB; the query phase leaves the file byte-identical.

Integration (real temp DB, migrations 001–010, writer-produced rows — the ledger is seeded through the real Capture/Relate write paths where practical, so the vocabulary matches §4.6):
- `history --item N` over a DB with a real ledger returns the expected events; the global view returns every row.

CLI (smoke, L2 §7.4):
- `ember history --item 99 --db <fixture>` → exit 1, `error: QUERY-001 …` on stderr.
- `ember history --db <fixture>` with no `--item` → exit 0, global ledger, parseable JSON.
- stdout carries nothing but the JSON document.

## 7. CLI check (Rule S1)

`ember history --item 1 --db tests/fixtures/query/current_state.db` → `{"mode": "history", "item_id": 1, "count": ≥1, "events": […]}`, exit 0; `ember history --db tests/fixtures/query/current_state.db` → the global ledger, exit 0.

## 8. Out of Scope (this step)

- Plain-text export (its own L2, not written; issue #18 stays with it — L2 §8).
- Writing anything: no `edit_item`, no `remove_link`, no schema change, no migration.
- Pagination of the global ledger (§10, deferred).

## 9. Next

None — the engine is complete and closed out. The only follow-ups are the `deferred` issues opened in §4.6.

## 10. Deferred Settings (from L2 §9) — resolved by this step

4. **#4 history pagination / limit: none in V1.** The ledger is one project's own history (hundreds of rows, not thousands); the global view's job is to show all of it, and a silent cap would hide ledger rows — the one failure mode a history must never have. Tracked as a `deferred` GitHub issue at closeout (§4.6).
5. **#5 the `unknown` kind: kept exactly as L2 defines it.** The fallback's raw-pair visibility guarantees a future vocabulary can never be silently dropped from the ledger view; a dedicated kind for a future vocabulary is a decision for the plan that writes that vocabulary.

## 11. Rollback

No rollback — Engine D writes no rows and ships no migration (L2 §2.6). The docs this step edits (README, PROJECT_MAP, other plans) revert with `git revert`; issue closures and the two `deferred` issues are tracker comments, undoable in the tracker.

## 12. Build Notes (post-implementation)

To be added after the code lands.

# L3 Query Step 5: History Window (Read Surface, Amendment §A–§F)

Implements the V1.x amendment (`plans/engine-query-plan.md`, "V1.x Amendment (hardening phase)") §A/§B/§C/§D/§E/§F for `history` only: `HistoryPage`, `validate_history_page` (QUERY-006 offset via the shared helper; QUERY-007 `since` with the UTC normalisation), the `--limit` / `--offset` / `--since` CLI flags on both the global and the `--item` view. Closes hardening issue **#28**. Builds on the shipped engine seam, steps 01–04; the union rule, the classifier and the `(timestamp, id)` order are untouched.

**Step invariant:** when this step ends, every module still runs, the whole suite passes, and the database file is byte-identical after every command.

## 0. Constitution rules this step enforces

- **D1** — the step writes nothing. Every flag path runs behind the same `open_query_database` `mode=ro` open (amendment §A); read-only proof stays (§F).
- **D4 / I9** — `--limit` / `--offset` / `--since` are outside data: Click type-checks, `validate_history_page` code-checks, the core trusts (§Z D4). Validation runs before the item check and before load (§C order).
- **I2** — flags are data, never mode switches. No boolean, no mode argument. The no-flag path is today's path, proven byte-identical (§F).
- **I3** — `history(rows, links, item_id, page=HistoryPage())` sits at the 4-input ceiling, I3-legal; `run_history(lookup, item_id, page=HistoryPage())` stays at 2 plus the defaulted page (§D).
- **I10** — the new parameter is keyword-with-default; the raw `item_id` param stays; every existing call site compiles unchanged (§D). The envelope gains no key (§B).
- **I17 / I21** — QUERY-007 continues from QUERY-006; QUERY-006 keeps its one shared raising helper (step 04); QUERY-007's single site is `validate_history_page` (§E). Each code keeps a named test (§F).
- **I18 / I19** — no `__init__` on the new error subclasses; QUERY-006 carries `field`, QUERY-007 carries `since_length` — never raw user text (a newline would break the one-line log; a `since` can hold a secret).
- **I12 / S1** — explicit flags, exit 0/1/2, JSON on stdout, `error: {log_line()}` on stderr; §7 runs the command alone.
- **P1 / P3** — shipped deficit (#28), not decoration; pipeline stays validate → load → derive (window inside) → render unchanged (§C).
- **T1 / T3** — windowing and `datetime.fromisoformat` are pure, deterministic, no clock; `FakeQueryLookup` untouched (§F).
- **B2 / B5** — the port slices nothing: `QueryLookupPort` grows no method (§D decided); windowing lives inside the pure core.
- **D3** — the ledger is read, never rewritten; `--since` filters *on* the stored ISO text, compares it the same way the sort already does (§D).

## 1. Job

Let `ember history` crop the events it shows: `--since` drops older rows, `--offset` skips, `--limit` caps — on the global view and on `--item`. Never a silent default cap (hardening L1 cluster 3; L2 §9 item 4). With no flags the output is byte-identical to the pre-amendment build, `history --item` included.

## 2. Inputs

CLI (amendment §B — all three work on both views):

```
ember history [--item <id>] [--limit N] [--offset N] [--since TS] [--db PATH]
```

- `--limit` / `--offset`: `type=int`; a non-integer never reaches Python — Click rejects it (exit 2, hardening contract 5, §E).
- `--since`: a string, parsed by the validator.
- `--item` and `--db` unchanged (`ember/cli.py:583-610` verified); the QUERY-001 gate still runs **only** when `--item` is given (L2 §4.7 stands, §C).

Shape (amendment §D), added to `ember/query/rows.py`:

```python
class HistoryPage(BaseModel):
    item_id: int | None = None   # None = global view
    limit: int | None = None     # None = no cap; ≥ 0
    offset: int | None = None    # None = no skip; ≥ 0
    since: str | None = None     # ISO-8601; normalised by the validator
```

**Recorded for review, not invented:** §D's shape carries `item_id` while §D's signature table keeps the raw `item_id` parameter on `run_history` / `history` ("the raw id stays, `page` is a defaulted final parameter") and says `render_history(events, item_id)` keeps the raw parameter "the runner already passes". So on the CLI path the raw parameter governs and the CLI never populates `page.item_id` (there is no second `--item` flag). The field's purpose is an open question for the maintainer; this step changes nothing about who owns the id.

## 3. Outputs

- `ember/query/errors.py`: `QuerySinceInvalid` — QUERY-007 (§E). (QUERY-006 landed in step 04.)
- `ember/query/query_gatekeeper.py`: `validate_history_page(page) -> HistoryPage` — pure (§D).
  - `limit < 0` or `offset < 0` → QUERY-006 (`field`), raised by the ONE shared non-negative helper from step 04 — the same single raising point (§E).
  - `since`: parse with `datetime.fromisoformat` — unparseable → QUERY-007 (`since_length` = the raw text's length, §E). Parse OK → normalise `astimezone(timezone.utc).isoformat()` (§D history-ordering contract) and return the page with `since` replaced, so the core compares normalised ISO text.
- `ember/query/history.py`: `history(rows, links, item_id, page=HistoryPage()) -> list[HistoryEvent]` — additive, 3 → 4 inputs (§D). After the unchanged classify → union → `(timestamp, id)` sort (verified `ember/query/history.py:110` — the amendment never changes it): `--since` keeps rows with `timestamp >= since` as opaque ISO text, the exact comparison the sort already uses (§D); then `--offset` skips, then `--limit` caps (`events[offset:]`, then `[:limit]`). `offset == None` → no skip; `limit == None` → no cap. **A stored timestamp that cannot parse renders everywhere today but is invisible to a `--since` view** (a hand-edited row; recorded, not hidden — §D).
- `ember/query/run_query.py`: `run_history(lookup, item_id, page=HistoryPage()) -> str` — validate page, item check only when the id was named (QUERY-001), load → derive → render (§C).
- `render_history(events, item_id)` untouched (§D): `{"mode": "history", "item_id": N or null, "count": N, "events": [HistoryEvent, …]}`.

**`count` semantics (§D, decided):** `count` = the number of rows returned (`len()` of the cropped list), not the total matching — the no-flag byte-identical requirement and the house rule `count == len(list)` (L2 §4 Phase 3) allow nothing else. A windowed caller cannot see there are more rows; `total_matching` is rejected for now (§G.3).

**Edge cases (§D):** `limit == 0` → zero rows, exit 0, explicit empty not an error; offset past the end → `[]`. Both fold into `test_offset_skips_then_limit_caps`.

**Port boundary (§D, decided):** the core slices; no windowed `list_change_log(page)` — it would duplicate the window rule outside the pure core, break every `FakeQueryLookup`, and change the load path the byte-identical test pins. Full loads are the only path today; flip only if a scale measure names it (§G.4).

## 4. Steps

1. `ember/query/errors.py`: add `QuerySinceInvalid` (QUERY-007, `since_length`). No `__init__` (I18). Codes stay contiguous 000–007 (I17).
2. `ember/query/rows.py`: add `HistoryPage` (§D shape above).
3. `ember/query/query_gatekeeper.py`: `validate_history_page(page) -> HistoryPage` per §3 — shared helper for the non-negative checks, `fromisoformat` + `astimezone(timezone.utc).isoformat()` for `since`.
4. `ember/query/history.py`: add the defaulted `page` parameter; window **behind** the existing sort: since-filter, then offset, then limit. Union, classifier, dedup and `(timestamp, id)` untouched.
5. `ember/query/render.py`: untouched.
6. `ember/query/run_query.py`: `run_history(lookup, item_id, page=HistoryPage())` — validator, optional item gate, load, derive, render (§C order).
7. `ember/cli.py` (`history_command`, verified `ember/cli.py:583-610`): add `--limit`, `--offset` (`type=int`, default `None`), `--since` (string, default `None`). Build `HistoryPage(limit=…, offset=…, since=…)` — the raw `item_id` param stays positionally first (§D signature table). Error handling unchanged.

## 5. Errors (codes only, per amendment §E)

- `QUERY-006` — `QueryFilterInvalid` — context `field`. Negative `--limit` or `--offset`; raised by the ONE shared non-negative helper (step 04's single raising point), called by `validate_history_page`.
- `QUERY-007` — `QuerySinceInvalid` — context `since_length`. `--since` does not parse as an ISO-8601 datetime; single site `validate_history_page`.
- Existing codes untouched: QUERY-001 (`--item <unknown>`, only when named, §4.7), QUERY-003/004/005 (boot + port).

No code for Click-rejected input: an unknown flag or a non-integer `--limit` / `--offset` never reaches Python — exit 2, no house `error:` log line, Click's usage block still prints (§E; hardening contract 5).

## 6. Test Targets

**Pre-code capture:** the byte-identical golden capture is step 04's (§F, `tests/fixtures/query/no_flags_golden.json`, taken before ANY amendment code). This step owns the history assertions against it: `ember history --db <fixture>` and `ember history --item <existing id> --db <fixture>` stdout stays byte-identical — `history --item` is the most-used path through the changed runner (§F).

Unit, pure cores, fakes per T3 (`tests/query/fakes.py` untouched) (§F):
- `test_history_page_windows_within_the_union_rule` — window applies **after** the union + sort, on both the global and the `--item` view; a row matching both union conditions still appears once; NULL-subject rows stay global-only.
- `test_since_drops_older_rows` — older rows dropped, newer kept, boundary row kept (`>=`); global and `--item` both; **the TZ case**: a ledger timestamp written tz-aware UTC and a `--since` given with a different offset (e.g. `+02:00`) compare equal after `astimezone(timezone.utc).isoformat()` — the boundary row is not lost to a spelling. (§G.2 leaves the accepted spellings to this test surface: date-only, space separator, fractional seconds — pin them here; the validator's rule is fixed: `fromisoformat` parses, `astimezone(timezone.utc)` normalises, anything unparseable is QUERY-007.)
- `test_offset_skips_then_limit_caps` — offset skips `offset` rows after the sort, then limit caps; `limit == 0` → empty; offset past the end → `[]`; global and `--item` both (§F, §D).
- `test_validate_history_page_raises_query_007` — `since = "yesterday"` / `""` → QUERY-007 with `since_length`, never the raw text; a valid `since` comes back normalised to `…+00:00`; `limit = -1` / `offset = -1` → QUERY-006 with `field=limit` / `field=offset` via the shared helper (step 04's `test_validate_topic_filter_raises_query_006` names the helper; this step covers its `offset` caller).

Integration / CLI, real temp DB (§F):
- `test_no_flags_output_is_byte_identical_to_pre_amendment` — the history assertions above; step 04 owns the topic-search assertion.
- `test_cli_flags_never_touch_the_database_file` — **extended** with every history flag set (`--limit`, `--offset`, `--since`, combined, on both views); the `mode=ro` write-attempt test stays green; the existing `test_query_leaves_the_database_byte_identical` (`tests/query/test_query_db_open.py`, sha256 mechanism) stays green exactly as written (§F read-only proof).
- CLI: exit 0 / 1 / 2 paths per §7; parse stdout with `json.loads`, match no strings; `count == len(events)` always.

## 7. CLI check (Rule S1)

Against a temp v10 DB built by the seed helpers (`tests/query/fakes.py::make_v10` + real write paths — no binary committed, per step 01's recorded deviation):

- `ember history --item 3 --limit 20 --offset 40 --db <fixture>` → exit 0, `{"mode": "history", "item_id": 3, "count": N, "events": [HistoryEvent, …]}` with `N ≤ 20` (amendment §B).
- `ember history --since 2026-10-01T00:00:00 --db <fixture>` → exit 0, `{"mode": "history", "item_id": null, "count": N, "events": […]}` — only rows at or after the window (amendment §B).
- `ember history --db <fixture>` and `ember history --item 1 --db <fixture>` with no flags → exit 0, byte-identical to `no_flags_golden.json`.
- `ember history --offset -1 --db <fixture>` → exit 1, `error: QUERY-006 QueryFilterInvalid | … | field=offset` on stderr; same for `--limit -1` (`field=limit`).
- `ember history --since "yesterday" --db <fixture>` → exit 1, `error: QUERY-007 QuerySinceInvalid | … | since_length=9` on stderr.
- `ember history --limit abc --db <fixture>` → exit 2, Click usage block, no house `error:` line (§E).
- `ember history --item 99 --db <fixture>` → exit 1, QUERY-001 (unchanged §4.7 gate).

## 8. Out of Scope (this step)

- The topic-search flags (step 04; #26/#27).
- A windowed port read — rejected, §D; `QueryLookupPort` grows no method (B2 stands).
- `total_matching` — rejected §G.3; both #26 and #28 voice the visibility concern, parked for maintainer sign-off, not absorbed here.
- A scale measurement for the full-ledger load — recorded trigger only, §G.4.
- Plain-text export (#18) — see §9.

## 9. Issue Closure + #18

- **This step closes #28** (`--limit` / `--offset` on history as one paging pair, plus `--since` — crop window and time window are different jobs, §A) — L2 §9 item 4, closed by amendment §G.1; comment with the §7 evidence.
- **#26 and #27 are step 04's** — this step does not touch them.
- **#18 non-absorption, one line:** plain-text export stays with its separate utility plan and its `EXPORT-*` codes (L2 §8; hardening L1 §2 cluster 3) — this step does not absorb #18.

## 10. Deferred Settings — resolved by this step

- L2 §9 item 4 (history pagination / limit) → `HistoryPage` flags, default `None` = no cap, never a silent default cap (§G.1; step 03's "none in V1" ruling is superseded by the approved amendment).
- §G.2 (`--since` grammar) → resolved into tests here: the validator's rule is fixed (`fromisoformat` + `astimezone(timezone.utc).isoformat()`); which spellings pass is pinned by `test_since_drops_older_rows`. No new setting.

## 11. Rollback

No rollback — the step writes no rows; the read-only contract is proven by the hash test (§F: `test_cli_flags_never_touch_the_database_file` with every history flag set, plus the existing `test_query_leaves_the_database_byte_identical` stays green).

## 12. Build Notes

(Empty — filled in after implementation.)

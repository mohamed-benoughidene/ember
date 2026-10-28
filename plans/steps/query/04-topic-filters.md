# L3 Query Step 4: Topic-Search Filters (Read Surface, Amendment §A–§F)

Implements the V1.x amendment (`plans/engine-query-plan.md`, "V1.x Amendment (hardening phase)") §A/§B/§C/§D/§E/§F for `topic_search` only: `TopicFilter`, `validate_topic_filter`, filter-before-scoring semantics, the `--status` / `--type` / `--limit` CLI flags. Closes hardening issues **#26** (`--limit`) and **#27** (`--status` / `--type`). Builds on the shipped engine seam, steps 01–03; no port change, no render change, no migration.

**Step invariant:** when this step ends, every module still runs, the whole suite passes, and the database file is byte-identical after every command.

## 0. Constitution rules this step enforces

- **D1** — the step writes nothing. Every flag path runs behind the same `open_query_database` `mode=ro` open (amendment §A); read-only proof stays (§F).
- **D4 / I9** — `--status` / `--type` / `--limit` are outside data: Click type-checks, `validate_topic_filter` code-checks, the core trusts (§Z D4). Validation runs before load (§C order).
- **I2** — flags are data, never mode switches. No boolean, no mode argument. The no-flag path is today's path, proven byte-identical (§F).
- **I3** — `TopicFilter` keeps `run_topic_search` at 3 inputs and `topic_search` at 3 (§D).
- **I10** — the new parameter is keyword-with-default; every existing call site compiles unchanged (§D). The envelope gains no key (§B), so the no-flag document is byte-identical.
- **I17 / I21** — QUERY-006 continues from QUERY-005, never reused (§E); one shared raising helper and one named test (§F).
- **I18 / I19** — no `__init__` on `QueryFilterInvalid` (I18 injection free); it carries `field`, never raw user text.
- **I12 / S1** — explicit flags, exit 0/1/2, JSON on stdout, `error: {log_line()}` on stderr; §7 runs the command alone.
- **P1 / P3** — shipped deficit (#26/#27), not decoration; pipeline stays validate → load → derive (filter inside) → render unchanged (§C).
- **T1 / T3** — filter logic is pure; `FakeQueryLookup` untouched (`tests/query/fakes.py`) (§F).
- **B1 / B5** — filtering lives inside the existing pure core; the surface grows by flags and one validator, no new module (§Z B5, B6).

## 1. Job

Let `ember topic-search` narrow what it scores: `--status` / `--type` pick the items handed to the BM25 scorer, `--limit` crops the ranked top N. Default: score every item, no cap (amendment §A; L2 §2.2 scope decision untouched when no filter is given). With no flags the output is byte-identical to the pre-amendment build.

## 2. Inputs

CLI (amendment §B):

```
ember topic-search --query "sqlite" [--status STATUS] [--type TYPE] [--limit N] [--db PATH]
```

- `--query` unchanged (required; gatekeeper QUERY-002 first, §C order).
- `--status` / `--type`: plain strings, exact case, legal values checked by the validator.
- `--limit`: `type=int`. A non-integer never reaches Python — Click rejects it (exit 2, hardening contract 5, §E).
- `--db` unchanged (`DEFAULT_DB_PATH`, `ember/cli.py:64`).

Shape (amendment §D), added to `ember/query/rows.py`:

```python
class TopicFilter(BaseModel):
    status: str | None = None    # one of Active | Challenged | Closed
    type: str | None = None      # one of Decision | Assumption | Finding | Question
    limit: int | None = None     # None = no cap; ≥ 0
```

## 3. Outputs

- `ember/query/errors.py`: `QueryFilterInvalid` — QUERY-006 (§E).
- `ember/query/query_gatekeeper.py`: `validate_topic_filter(tf) -> None` — pure (§D; MAINTAIN-002 precedent). Raises QUERY-006 (`field` says `status`, `type`, or `limit`) for a value outside the legal sets or a negative limit. Legal sets exact case: `ACCEPTED_STATUSES = {"Active", "Challenged", "Closed"}`, `ACCEPTED_TYPES = {"Decision", "Assumption", "Finding", "Question"}` (§D). The non-negative check lives in ONE shared helper inside the gatekeeper (name free at implementation, module-private) so QUERY-006 has one raising point `validate_history_page` will also call (step 05).
- `ember/query/topic_search.py`: `topic_search(items, query, topic_filter=TopicFilter()) -> list[SearchHit]` — 2 → 3 inputs, additive (§D).
- `ember/query/run_query.py`: `run_topic_search(lookup, query, topic_filter=TopicFilter()) -> str` — 2 → 3 inputs (§D).
- `render_topic_search` and the envelope are unchanged (§B): `{"mode": "topic_search", "query": "<text>", "count": N, "results": [SearchHit, …]}`.

**Semantics (amendment §C/§D):** validate text (QUERY-002) → validate `TopicFilter` → load `list_items()` → derive: the `--status` / `--type` filter (AND) selects the items handed to the scorer — **the filtered subset IS the corpus**, so `N`, `df` and `avgdl` recompute and the remaining scores differ from the unfiltered run; filtered-out items change `count`, they never appear with score 0 — then the existing score-desc / `item_id`-asc sort (verified `ember/query/topic_search.py:71`), then `--limit` crops the top N **behind the sort**. The no-flag path crops nothing. Filtered corpus empty or all-zero-token → the existing guards return `[]` (verified `topic_search.py:40-44`). `limit == 0` → zero rows, exit 0 — explicit empty, not an error (§D).

**`count` semantics (§D, decided):** `count` = the number of rows returned (`len()` of the cropped list), not the total matching. `total_matching` is rejected for now (§G.3).

## 4. Steps

1. `ember/query/errors.py`: add `QueryFilterInvalid` (QUERY-006, `field`). No `__init__` (I18). Codes stay contiguous 000–006 (I17).
2. `ember/query/rows.py`: add `TopicFilter` (§D shape above).
3. `ember/query/query_gatekeeper.py`: the shared non-negative helper + `validate_topic_filter(tf) -> None` per §3.
4. `ember/query/topic_search.py`: add the defaulted `topic_filter` parameter; filter the items list first; everything else (term handling, zero-token guard, `_idf`, sort) untouched.
5. `ember/query/run_query.py`: `run_topic_search(lookup, query, topic_filter=TopicFilter())` — text gate, validator, then load → derive → render (§C order).
6. `ember/cli.py` (`topic_search_command`, verified `ember/cli.py:530-555`): add `--status`, `--type` (string options), `--limit` (`type=int`, default `None`). Build `TopicFilter` and pass it through. Error handling unchanged: `error: {exc.log_line()}` to stderr, exit 1 (§B).
7. `render.py`: untouched.

## 5. Errors (codes only, per amendment §E)

- `QUERY-006` — `QueryFilterInvalid` — context `field`. Raised by the ONE shared non-negative helper and the legal-set checks in `validate_topic_filter` (§E). A negative `--limit`; an illegal `--status` / `--type`.
- Existing codes untouched: QUERY-002 (text gate, runs first per §C), QUERY-003/004/005 (boot + port, unchanged).

No code for Click-rejected input: an unknown flag or a non-integer `--limit` never reaches Python — exit 2, no house `error:` log line, Click's usage block still prints (§E; hardening contract 5).

## 6. Test Targets

**Pre-code capture (amendment §F, before ANY amendment code):** run the pre-amendment build and store stdout into `tests/fixtures/query/no_flags_golden.json` for the three commands: `ember topic-search --query sqlite --db <fixture>`, `ember history --db <fixture>`, `ember history --item <existing id> --db <fixture>`. This step owns the capture session (it is the first amendment step); step 05 asserts the history lines from the same file. If step 05 ever lands first, the capture moves there — the file must predate the first amendment commit.

Unit, pure cores, fakes per T3 (`tests/query/fakes.py` untouched) (§F):
- `test_default_topic_filter_scores_every_item` — `topic_search(items, query, TopicFilter())` equals `topic_search(items, query)`; `TopicFilter()` ≡ today, every item scores.
- `test_status_and_type_filter_the_items_handed_to_the_scorer` — both axes: a `Closed` hit is excluded under `--status Active` **and** the remaining scores recompute over the smaller corpus (differ from the unfiltered run); the reverse `--status Closed` case returns only the Closed item; `--type` alone filters; `--status` + `--type` combine as AND.
- `test_limit_windows_after_ranking` — top N by score, not first N by id; `limit = 0` → `[]` exit-0 semantics.
- `test_validate_topic_filter_raises_query_006` — illegal status → 006 `field=status`; illegal type → `field=type`; `limit = -1` → `field=limit`; each legal value passes; Purely data in, `None` out (validator returns `None`, §D).

Golden fixture (§F):
- `tests/fixtures/query/bm25_golden.json` stays green **untouched**: `tests/query/test_topic_search_unit.py::test_scores_match_the_hand_computed_golden_fixture` calls `topic_search(items, GOLDEN["query"])` with no filter (verified) — the defaulted `TopicFilter()` is a no-op, so every score is unchanged. The fixture file does not move.

Integration / CLI, real temp DB (§F):
- `test_no_flags_output_is_byte_identical_to_pre_amendment` — the captured `topic-search` command output, byte-identical after.
- `test_cli_flags_never_touch_the_database_file` — this step lands it; sha256 before/after with every new flag set (mechanism of the existing `_hash` in `tests/query/test_query_db_open.py::test_query_leaves_the_database_byte_identical`); extends the §7.2 proof (§F). Step 05 extends the same test.
- the `mode=ro` write-attempt test stays green (§F).
- CLI: exit 0 / 1 / 2 paths per §7; parse stdout with `json.loads`, match no strings.

## 7. CLI check (Rule S1)

Against a temp v10 DB built by the seed helpers (`tests/query/fakes.py::make_v10` — no binary committed, per step 01's recorded deviation):

- `ember topic-search --query "sqlite" --status Active --type Decision --limit 5 --db <fixture>` → exit 0, one JSON document `{"mode": "topic_search", "query": "sqlite", "count": N, "results": [SearchHit, …]}` with `N ≤ 5` (amendment §B).
- `ember topic-search --query "sqlite" --db <fixture>` (no flags) → exit 0, byte-identical to `no_flags_golden.json`.
- `ember topic-search --query "sqlite" --status Bogus --db <fixture>` → exit 1, `error: QUERY-006 QueryFilterInvalid | … | field=status` on stderr.
- `ember topic-search --query "sqlite" --limit -1 --db <fixture>` → exit 1, `field=limit`.
- `ember topic-search --query "sqlite" --limit abc --db <fixture>` → exit 2, Click usage block, no house `error:` line (§E).

## 8. Out of Scope (this step)

- The history window: `--limit` / `--offset` / `--since` on `ember history` (step 05; #28).
- A windowed port read — rejected, §D: the core slices; `QueryLookupPort` grows no method (B2 stands).
- `total_matching` in the envelope — rejected §G.3.
- Plain-text export (#18) — see §9.

## 9. Issue Closure + #18

- **This step closes #26** (`--limit` on topic-search, default no cap) and **#27** (`--status` / `--type` filters) — L2 §9 items 2 and 3, closed by amendment §G.1; comment on each with the §7 evidence.
- **#28 is step 05's** (history window) — this step does not touch it.
- **#18 non-absorption, one line:** plain-text export stays with its separate utility plan and its `EXPORT-*` codes (L2 §8; hardening L1 §2 cluster 3) — this step does not absorb #18.

## 10. Deferred Settings — resolved by this step

- L2 §9 item 2 (result cap) → `--limit`, default `None` = no cap (§G.1).
- L2 §9 item 3 (status/type filters) → `--status` / `--type`, exact case, AND (§G.1).
- §G.2's `--since` grammar is **not** this step's; step 05 owns it.

## 11. Rollback

No rollback — the step writes no rows; the read-only contract is proven by the hash test (§F: `test_cli_flags_never_touch_the_database_file`, plus the existing `test_query_leaves_the_database_byte_identical` stays green).

## 12. Build Notes

(Empty — filled in after implementation.)

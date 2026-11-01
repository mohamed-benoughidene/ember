# Batch 8 implementation plan: performance — one-pass search, fast history, batched relate
Spec: docs/Spec-Batch8.md
Branch: batch-8, cut from where Batch 7 merged (D-29 in archive/Plan.md: each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its "Done when" passes)
Needs first: Batches 0–7 (Plan.md order). Per `archive/spec-check-batch8.md` §4 no batch is a HARD blocker; two coordination points: Batch 7 edits the same lines of `ember/relate/candidate_pool.py` (4.8 #5–#9, incl. the wipe at `candidate_pool.py:112-118`) — whoever lands second rebases; Batch 4 touches the same `change_log` read path in `ember/adapters/sqlite.py` — Batch 8 only reshapes the read SQL.
Size: 30 steps, about 12 hours

## Before you start
- Tests this batch touches, exactly as typed (from the repo root `/home/mo/lab/ember`; `.venv/bin/pytest` exists, checked):
  - `.venv/bin/pytest tests/query/test_search_timing.py -q` (NEW in Chunk 1)
  - `.venv/bin/pytest tests/query/test_tokenize_unit.py tests/query/test_topic_search_unit.py -q`
  - `.venv/bin/pytest tests/query/test_history_window_sql.py -q` (NEW in Chunk 4)
  - `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py tests/relate/test_candidate_pool_integration.py tests/relate/test_relate_cli.py -q`
  - Whole suite at the end: `.venv/bin/pytest -q` (repo convention: `pyproject.toml` runs `tests/` with `-q -m 'not live'`, so live tests that need keys never run).
- Safety rules: no AI keys in the environment (unset `EMBER_AI_API_KEY` and `OPENROUTER_API_KEY` if set); never open the real knowledge base or `key.enc` — every test uses the `db_path` fixture from `tests/conftest.py` (a temp file) or a file under `/tmp/opencode/batch8/` (create it: `mkdir -p /tmp/opencode/batch8`); there are no e2e tests in this batch, but if you run the app's e2e suite for any reason it may only run under `xvfb-run`; the only manual real-model check in the Final check runs locally with no key.

## Chunk 1 of 10: search scores in one pass
Covers: finding 4.7 #3; user stories 1, 9 (search half). Decision D-15.

1. Add a NEW test file `tests/query/test_search_timing.py`. Two tests. (a) `test_10k_search_under_one_second`: build a temp db with `tests.query.fakes.make_v10` + `tests.fakes.insert_source`/`insert_item` (real `statement=` texts, 10,000 Active items whose statements mix the words `gateway`, `rewrite`, `cache` in different positions), run `CliRunner().invoke(main, ["topic-search", "--query", "gateway rewrite cache", "--limit", "10", "--db", db_path])` (import `main` from `ember.cli`), parse the JSON output, assert 10 hits, and assert the elapsed wall time is under 1.0 s. (b) `test_small_seed_matches_slow_reference`: seed 9 items, run `topic_search` (import from `ember.query.topic_search`) with the same 3-word query, and assert the top ids equal a slow reference implementation written inline in the test (same BM25 formula as the module docstring, per-term `sum(... if term in other)`). Mark the file NEW.
2. Run `.venv/bin/pytest tests/query/test_search_timing.py -q`. Expect: 1 failed (the 10k timing test — the old code rescans every item per term and takes tens of seconds), 1 passed (equivalence on the small seed). The red run takes a minute or more once; let it finish.
3. Rewrite `topic_search()` in `ember/query/topic_search.py`: tokenize each selected item once (as today), keep a `collections.Counter` of tokens per item, compute `document_frequency` ONCE per query term over the precomputed token sets, then score every item in one pass reading the counters. Keep everything else exactly as today: same `K1`/`B`, same `_idf`, same sort `(-score, item_id)`, same `--limit` crop behind the sort. The module header stays "no I/O, no clock, no DB, no printing".

Proof it's real: in `ember/query/topic_search.py`, plant the old line back — `document_frequency = sum(1 for other in tokens_per_item if term in other)` inside the item×term loop instead of the one-time computation. Rerun the timing test: it must go red again (over the 1.0 s bound). Revert the plant.
Done when: `.venv/bin/pytest tests/query/test_search_timing.py -q` prints `2 passed`. With the plant gone, nothing else changed.
Commit message: `search: score in one pass with per-term statistics computed once (Batch 8, 4.7 #3, D-15)`

## Chunk 2 of 10: tokenizer tests — encoding and case
Covers: finding 4.7 #6 (first part); user stories 2, 3, 4. Decisions D-17, N22. No code yet, tests first.

1. Append to the existing `tests/query/test_tokenize_unit.py` a new test `test_nfc_then_casefold`: `tokenize` of an NFD-`café` string equals the token list of the NFC spelling (both normalize to one token `café`); `tokenize("STRASSE") == tokenize("Straße")` (full case folding, `['strasse']`); `İstanbul` and `İSTANBUL` tokenize identically. All strings written with explicit escapes (e.g. `"caf\u00e9"`, `"caf\u0065\u0301"`) so the file stays byte-stable.
2. Append to the existing `tests/query/test_topic_search_unit.py` a search-level test `test_matching_ignores_encoding_and_case`: one item whose statement holds the NFC `café`, one holding `Straße`, one holding `İstanbul`. Assert: an NFD-`café` query finds the café item; query `STRASSE` finds the `Straße` item (casefold, section 4 of the spec); query `cafe` finds NONE of them (accents count, D-17); query `istanbul` finds NOTHING (the known limit N22), while query `İSTANBUL` finds the `İstanbul` item. In the test docstring, name N22 and say why the limit is pinned, not fixed.
3. Run `.venv/bin/pytest tests/query/test_tokenize_unit.py tests/query/test_topic_search_unit.py -q`. Expect: the 2 new tests fail (today NFD `café` tokenizes to `cafe` — the reproduced miss from report 4.7 #6), everything else passes.

Proof it's real: the failing run in step 2 is the red; it shows the encoding miss on the real code (no plant needed).
Done when: the run in step 2 shows exactly the 2 new tests failing. Write down the counts so Chunk 3 can compare.
Commit message: `tests: pin NFC + casefold tokenizer cases and the N22 Istanbul limit (Batch 8, 4.7 #6, D-17)`

## Chunk 3 of 10: tokenizer implementation
Covers: finding 4.7 #6 (first part); user stories 2, 3, 4.

1. In `ember/query/tokenize.py`, change `tokenize()`: first `unicodedata.normalize("NFC", text)`, then `.casefold()`, then the existing split-on-non-alphanumeric loop unchanged (add `import unicodedata`). Update the module docstring's one-line description (NFC normalize, full case fold, split on non-alphanumerics; no stemming, no accent stripping). This is the one tokenizer the gate and scorer share, so both sides change together.
2. Run `.venv/bin/pytest tests/query/test_tokenize_unit.py -q`. Expect: all pass, including the new `test_nfc_then_casefold`.
3. Run `.venv/bin/pytest tests/query/test_topic_search_unit.py -q`. Expect: all pass, including `test_matching_ignores_encoding_and_case`.

Proof it's real: remove only the `unicodedata.normalize("NFC", ...)` call (keep casefold) and rerun — the NFD-`café` assertions must go red again. Put the call back.
Done when: both test files from Chunk 2 are green; the counts equal the pre-change total minus 2 plus 2 (same tests as before plus the two new ones, none newly broken).
Commit message: `tokenizer: NFC-normalize then case-fold before splitting (Batch 8, 4.7 #6, D-17)`

## Chunk 4 of 10: history reads only what it needs — the port and the adapter
Covers: finding 4.7 #12 (core part); user story 5. The pure `history()` derivation does NOT change; only the read behind it does.

1. Add a NEW test file `tests/query/test_history_window_sql.py` with one test, `test_limited_read_scans_only_a_prefix`: on a `db_path` temp file, seed a small source and 100 items (`make_v10` + `tests.fakes.insert_source`/`insert_item`) and 20,000 `change_log` rows referencing item ids 1–100 (one `executemany` INSERT into `change_log` with strictly increasing ISO timestamps). Keep using item ids that exist as rows, so no trigger or foreign key can refuse the seed. Then open the connection again and set a progress counter on it (`conn.set_progress_handler`, counting calls) before building `SqliteQueryContext(conn)` (import from `ember.adapters.sqlite`), call `list_change_log(item_id=None, window=HistoryPage(limit=31))` (import `HistoryPage` from `ember.query.rows`, mark this keyword NEW), and assert: 31 rows come back and they are exactly the first 31 by `(timestamp, id)` (the same crop `history()` applies: it sorts ascending and keeps `events[:limit]`, so the SQL prefix must be the earliest rows, not the newest); the progress counter stayed under 2,000 (an unbounded scan of 20k rows costs at least ~20,000 steps); elapsed time under 5 s.
2. Run `.venv/bin/pytest tests/query/test_history_window_sql.py -q`. Expect: 1 failed — today `list_change_log(self)` takes no arguments (TypeError on `window=`).
3. Edit three files, one coordinated change: `ember/query/lookup.py` — the `QueryLookupPort.list_change_log` method gains two optional parameters `(item_id: int | None = None, window: HistoryPage | None = None)` (add `HistoryPage` to the existing `ember.query.rows` import; additive default keeps today's no-arg callers valid, I10). `ember/adapters/sqlite.py` — `SqliteQueryContext.list_change_log` implements it: filter `WHERE (item_id = ? OR link_id IN (SELECT id FROM links WHERE source_item_id = ? OR target_item_id = ?))` when `item_id` is not None (exactly the `_belongs_to` rule of `ember/query/history.py`), `AND timestamp >= ?` when `window.since` is set, `ORDER BY timestamp, id` (the same key the in-memory sort uses, so a prefix stays a correct prefix), and fetch at most `offset + limit` rows when `window.limit` is set (offset only widens the prefix; `history()` still applies the full window, so the final view is unchanged). Keep raising `QUERY-005 ItemsReadFailed` on a read failure. `tests/query/fakes.py` — mirror the same filter in `FakeQueryLookup.list_change_log` in memory.

Proof it's real: temporarily make the new `SqliteQueryContext.list_change_log` ignore `window` (return the unfiltered read) — the progress counter in `test_limited_read_scans_only_a_prefix` must explode to ≥20,000 and the test goes red. Restore the window.
Done when: `.venv/bin/pytest tests/query/test_history_window_sql.py -q` prints `1 passed`.
Commit message: `history: filter and bound the change_log read in SQL (Batch 8, 4.7 #12)`

## Chunk 5 of 10: history CLI passes the window down
Covers: finding 4.7 #12 (wiring); user story 5.

1. Run the baseline before touching code: `.venv/bin/pytest tests/query -q`. Write down the result line (e.g. `49 passed`). The golden byte tests in `tests/query/test_history_window_cli.py` and `tests/query/test_topic_filter_cli.py` pin that a `--limit/--offset/--since` page renders byte-identical output; they are the behavioral guard for this change.
2. In `ember/query/run_query.py`, change `run_history` to call `lookup.list_change_log(item_id, page)` instead of `lookup.list_change_log()`. One line, everything else untouched — `history()` still receives the same arguments and applies the same window, so the final events are identical.
3. Run `.venv/bin/pytest tests/query -q` again. Expect: the same counts as the baseline, all green (goldens prove byte-identical CLI output).

Proof it's real: plant the break — in `SqliteQueryContext.list_change_log`, ignore the `window` argument again. Chunk 4's `test_limited_read_scans_only_a_prefix` goes red (the unbounded scan), proving the new wiring is what limits the CLI's read. Restore.
Done when: a plain `ember history --limit 31` on a 20k-row temp db (`time .venv/bin/ember history --limit 31 --db /tmp/opencode/batch8/hist20k.db` after seeding with the Chunk-4 seed helper) returns 31 events and finishes in well under a second, and the full `tests/query` suite is green with byte-identical goldens.
Commit message: `history: pass the page window to the SQL read (Batch 8, 4.7 #12)`

## Chunk 6 of 10: relate batches its embedding calls — test
Covers: finding 4.8 #1; user stories 6, 9 (relate half). Tests first, per D-23's pytest seam.

1. In the existing `tests/relate/fakes.py`, extend `FakeEmbedder.embed` to record every call: add the attribute `self.embed_calls: list[list[str]] = []` in `__init__` and append `list(texts)` at the top of `embed()` (before the canned-vector logic). Additive — nothing existing reads it, every existing test keeps passing.
2. Append to the existing `tests/relate/test_candidate_pool_unit.py` a test `test_embedding_calls_are_batched`: build a universe of 40 universe items plus the new item, all with empty `FakeEmbeddingStore` (every vector a cache miss), call `build_candidate_pool` as the file's existing tests do, using the recording `FakeEmbedder` (define it inline by subclassing `tests.relate.fakes.FakeEmbedder` in the test file so the shared fake keeps its today's behavior). Assert: every recorded call's text list length is at most 32, and there was more than one text-less single-item call — that is, `len(fake.embed_calls) < 41` (today the code calls `embed([item.statement])` once per item = 41 one-text calls).
3. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py -k batched -q`. Expect: 1 failed (41 single-text calls), the rest of the file untouched.

Proof it's real: the failing run in step 2 is the red; the assert message prints the 41 single-text calls the old loop makes.
Done when: the run in step 2 prints `1 failed`, everything else in the file passing.
Commit message: `tests: pin that relate encodes in batches, not one item per call (Batch 8, 4.8 #1)`

## Chunk 7 of 10: relate batches its embedding calls — implementation
Covers: finding 4.8 #1; user story 6.

1. In `ember/relate/candidate_pool.py`, add a module-level constant `EMBED_BATCH_SIZE = 32` (NEW, N23 — not read from config or env) and restructure the vector resolution in `build_candidate_pool`/`_content_signal`: collect the items whose cache read is missing or under another model (the condition `_resolve_vector` checks today at `candidate_pool.py:130-131`), encode their statements together with the new item's statement in slices of `EMBED_BATCH_SIZE` via `embedder.embed(...)`, then upsert each vector into the store per item (keep the per-item `store.upsert(...)` so `FakeEmbeddingStore.upserts` and the cache contract of `embedding_store.py` stay unchanged) and keep every length check raising `RELATE-022 CosineComputeFailed` with the item id, and embedder failures propagating as `RELATE-018`. Cached items still come from the store as today.
2. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py tests/relate/test_candidate_pool_integration.py -q`. Expect: all green, including the new batching test.
3. Run `.venv/bin/pytest tests/relate -q`. Expect: all green (the fake-embedder CLI and read-failure suites prove the errors and cache writes survived the restructure).

Proof it's real: set `EMBED_BATCH_SIZE = 1` in `ember/relate/candidate_pool.py` — the batching test must go red again (back to 41 one-text calls). Set it back to 32.
Done when: `tests/relate` is green and the batching test shows the call count collapsed to 2 (⌈41/32⌉ batches of at most 32 texts).
Commit message: `relate: encode embedding misses in batches of 32 (Batch 8, 4.8 #1, N23)`

## Chunk 8 of 10: relate prints progress while encoding
Covers: finding 4.8 #2 (the silent part); user story 7.

1. Append to the existing `tests/relate/test_candidate_pool_unit.py` a test `test_progress_lines_report_done_and_total`: same 41-miss setup, but pass a NEW optional keyword `echo=<capture list>.append` to `build_candidate_pool`, and assert the capture holds at least two lines, every line matches the done/total shape `encoding embeddings: <n>/41`, and the last line reads `encoding embeddings: 41/41`. Also assert a pool built with NO `echo` argument (the default) captures nothing — today's calls must stay silent.
2. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py -k progress -q`. Expect: 1 failed — `build_candidate_pool` has no `echo` keyword yet (TypeError).
3. In `ember/relate/candidate_pool.py`: give `build_candidate_pool` the keyword-only parameter `echo: Callable[[str], None] | None = None` (add `from collections.abc import Callable`; additive default keeps every existing caller valid, I10), thread it into the batch loop from Chunk 7, and after each batch call `echo(f"encoding embeddings: {done}/{total}")` when `echo` is not None. `total` is the number of cache-miss texts in the run (new item included). Update the docstring's side-effect list (I11).

Proof it's real: comment out the `echo(...)` call inside the batch loop — `test_progress_lines_report_done_and_total` must go red (no lines captured). Restore the call.
Done when: `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py -k "batched or progress" -q` prints `2 passed`.
Commit message: `relate: print done/total progress while encoding (Batch 8, 4.8 #2)`

## Chunk 9 of 10: warn before the cache is wiped
Covers: finding 4.8 #2 (the late-warning part); user story 8. Spec decision: the warning line goes through the same `echo` callable, BEFORE `store.wipe()` runs.

1. Append to the existing `tests/relate/test_candidate_pool_unit.py` a test `test_model_change_warning_prints_before_wipe`: seed `FakeEmbeddingStore` with one vector under model `"other-model"` while the `FakeEmbedder` reports `"fake-model"`; in the test, subclass the store so that its `wipe()` appends the string `"WIPE"` to the same capture list that `echo` appends into. Call `build_candidate_pool(..., echo=capture.append)` and assert `capture` starts with `MODEL_CHANGED_LINE` (import from `ember.relate.candidate_pool`) followed by `"WIPE"`, and that `pool.warning == MODEL_CHANGED_LINE` still (the `Pool` contract does not change).
2. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py -k before_wipe -q`. Expect: 1 failed — today `_model_change_warning` wipes silently (`candidate_pool.py:117`) and the caller prints afterwards, so nothing arrives through `echo`, and `"WIPE"` lands first in the capture.
3. In `ember/relate/candidate_pool.py`, change `_model_change_warning` to accept `echo` and call `echo(MODEL_CHANGED_LINE)` BEFORE `store.wipe()` (when `echo` is not None). Keep returning the warning text unchanged, and keep the wipe only when the cached model differs.

Proof it's real: move the `echo(...)` call to AFTER `store.wipe()` — the order assert in `test_model_change_warning_prints_before_wipe` must go red. Move it back before the wipe.
Done when: `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py -q` prints all green (batching, progress, wipe order, and every pre-existing pool test).
Commit message: `relate: emit the model-change warning before wiping the cache (Batch 8, 4.8 #2, story 8)`

## Chunk 10 of 10: the CLI routes the warning and progress to the right stream
Covers: finding 4.8 #2 (the app-visible half); user stories 7, 8. Spec decision: under `--confirm json` the warning is a `message` event on stdout (the app never shows stderr); on the terminal it stays on stderr (I12).

1. Append to the existing `tests/relate/test_relate_cli.py` a test `test_json_mode_warning_is_a_stdout_message_event`: seed the six-item base with the file's own `_seed_six_items_two_links(db_path)`, then use `SqliteEmbedderStore` (already imported in the file) on the temp db to write ONE cached vector under a different model name (e.g. `"other-model"` for item 1), patch phase-2 ports with the file's `_patch_phase2_ports(monkeypatch, ...)` and phase 3 (`--confirm json` runs into Phase 3 after the pool, so also call `_patch_phase34_ports(monkeypatch)`), and run `runner.invoke(main, ["relate", "--item", "1", "--confirm", "json", "--db", db_path])`. Parse each stdout line as JSON and assert one event has `"event": "message"` whose text equals `MODEL_CHANGED_LINE` (import from `ember.relate.candidate_pool`). On today's code the warning is a bare stderr line (`ember/cli.py:482-483`), so no stdout message event appears — the test must fail.
2. Run `.venv/bin/pytest tests/relate/test_relate_cli.py -k json_mode_warning -q`. Expect: 1 failed.
3. In `ember/cli.py`, inside the `relate` command: build one `echo` callable — `sink.echo` when in JSON mode, `lambda text: click.echo(text, err=True)` on the terminal — pass it to `build_candidate_pool(..., echo=echo)`, and DELETE the old post-hoc block `if pool.warning: click.echo(pool.warning, err=True)` at lines 482-483 (the core now prints at the right moment, through the right stream; do not print twice).

Proof it's real: restore the old two lines in `ember/cli.py` (`click.echo(pool.warning, err=True)` after the pool) and remove the `echo=` argument — the new JSON test must go red again (warning back on stderr, no message event). Restore the wiring.
Done when: `.venv/bin/pytest tests/relate -q` is green, and a terminal run prints the warning exactly once on stderr. On a seeded temp db: `ember relate --latest --db /tmp/opencode/batch8/warn.db` shows the `embedding model changed: wiping cache...` line among stderr text, not on stdout.
Commit message: `relate: warning and progress ride stdout message events under --confirm json (Batch 8, 4.8 #2)`

## Final check
- Full suite, all green: `.venv/bin/pytest -q` from the repo root. Expected: every previously passing test still passes, plus the new files `tests/query/test_search_timing.py`, `tests/query/test_history_window_sql.py` and the new tests inside `tests/query/test_tokenize_unit.py`, `tests/query/test_topic_search_unit.py`, `tests/relate/test_candidate_pool_unit.py`, `tests/relate/test_relate_cli.py`. The `test_docs_in_sync.py` gate must also stay green: this batch adds no CLI flags (finding 1 in the check report), so no doc line changes.
- The batch's "Done when" from `archive/Plan.md` (Batch 8): each with its proving command.
  1. "The report's 10k-item search timing is under 1 s" (D-15, story 1): `.venv/bin/pytest tests/query/test_search_timing.py -q` — the timing test itself seeds 10k items on a temp db and asserts a 3-word search at `--limit 10` under 1.0 s. Manual confirmation, once: build a temp db under `/tmp/opencode/batch8/` with the same seed, then `time .venv/bin/ember topic-search --query "gateway rewrite cache" --limit 10 --db /tmp/opencode/batch8/seed10k.db` — real time must be under 1 s.
  2. "2,000 items prepare in under 10 minutes with progress lines" (testing decision 5 — MANUAL, allowed: encoding is local, no AI key involved): seed a 2,000-item temp db under `/tmp/opencode/batch8/`, then `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/ember relate --latest --db /tmp/opencode/batch8/seed2000.db` (or with `--confirm json` to see the message events). During the encode phase you must SEE repeated `encoding embeddings: <n>/2000` lines (the app's idle timer resets on every stdout line, `bridge-client.js:399-401`). The phase must finish well inside 10 minutes (measure from the first to the last progress line). After the pool, the run stops with the engine's own no-key error (RELATE-035) — that failure is EXPECTED and is not a failure of this check; the check is the encode phase's time and its progress lines. If the bound is missed, the first thing to tune is `EMBED_BATCH_SIZE` (`ember/relate/candidate_pool.py`, N23), then re-check.
  3. Encoding/case matching (D-17, stories 2–4): `.venv/bin/pytest tests/query/test_tokenize_unit.py tests/query/test_topic_search_unit.py -q` — both green, café/STRASSE/İstanbul cases pinned.
  4. History fast on a big ledger (story 5): `.venv/bin/pytest tests/query/test_history_window_sql.py -q` — green on 20k rows with limit 31.
  5. Relate batches, progresses, warns first (findings 4.8 #1, #2; stories 6–9): `.venv/bin/pytest tests/relate -q` — green.

## Unknowns
- D-29 (archive/Plan.md) fixes the branch rule: each batch on its own branch `batch-N`, cut from where the previous batch merged. Still unconfirmed: the concrete landing point of Batch 7 at the time batch-8 is cut.
- The exact progress-line wording (`encoding embeddings: <n>/<total>`) is NEW; the spec only pins "message event lines with done and total". The tests in Chunks 8 pin whichever wording is chosen — if the implementer prefers other words, change them in BOTH the code and the two tests.
- The CLI-level time bound for history (Chunk 5, generous 5 s) was NOT measured against today's 20k-row code; the old path builds 20k pydantic rows in memory and was expected to stay under 5 s here. That is why the deterministic red proof is the progress-counter scan bound (Chunk 4), not the clock. Do not tighten the clock bound without measuring on the CI runner first (flaky risk).
- Seeding 20,000 `change_log` rows: the migration-011 triggers reference `change_log` timestamps but I found no trigger that restricts plain ledger inserts; the plan seeds rows that reference existing item ids, which is safe under any foreign key. If an insert is refused when you get there, seed with the exact values an existing ledger row shape uses (`tests.fakes.FIXED_TIME`, cause `user_confirmed`) and note it.

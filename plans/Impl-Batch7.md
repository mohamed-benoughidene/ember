# Batch 7 implementation plan: AI calls and input limits
Spec: docs/Spec-Batch7.md
Branch: `batch-7`, per decision D-29 (`archive/Plan.md`): each batch builds on its own branch `batch-N`, cut from where the previous batch merged, and merges into `ember-interface` when its "Done when" passes. So batch-7 is cut from where batch-6 merged. Today the working branch is `ember-interface` at `3b84663` and no `batch-*` branch exists (`git branch -a`), so the exact cut point is still to confirm (Unknowns).
Needs first: Batch 6 (its code-keyed sentence table, decision D-08 — every new code from this batch needs exactly one sentence there: `archive/spec-check-batch7.md` section 4) and Batch 4 (its latest-schema-version pin — the new migration 014 below bumps the version that pin watches). Plan.md gives the order 0-9 but no explicit merge rule; the two touchpoints above are what actually break if those batches are not merged first.
Size: 19 chunks, 55 steps, about 17 hours (the same work as before the split per I11, cut into 3-step chunks).

## Before you start
- `.venv` exists (checked: `ls .venv/bin/pytest` runs). Run tests exactly like this:
  - One file: `.venv/bin/pytest tests/test_llm_adapter_unit.py`
  - Several files: `.venv/bin/pytest tests/test_llm_adapter_unit.py tests/relate/test_candidate_pool_unit.py`
  - A pattern inside files: `.venv/bin/pytest tests/test_llm_adapter_unit.py -k rate_limited`
  - Whole suite (live tests excluded always, and from Chunk 16 on the `slow` test too — both via `pyproject.toml` addopts): `.venv/bin/pytest`. CI (Chunk 16) instead runs `.venv/bin/pytest -m "not live"`, which includes the `slow` test.
  - Live tests NEVER run in a plain run (they need a real key and cost money). Do not run them in this batch. The one `slow` test (Chunk 16) costs about a minute; CI pays it, the local default run does not.
- Safety rules: no AI keys anywhere (the fake provider servers in this plan run on `127.0.0.1` only); never open the real knowledge base or `key.enc` — use `tests/conftest.py` `db_path` temp files; all temp files for manual checks go under `/tmp/opencode/batch7/`; no GUI/e2e is planned in this batch, and if one is ever added it runs only under `xvfb-run`.
- The one new schema change (Chunk 13) touches a migration. That step carries its own "Done when" line, as required.
- Code numbers: per decision I1, this plan pins no error-code numbers. Each new code takes the next free number in its family at implementation time (D-27). Where a chunk says it adds a code, the 02x capture numbers are taken by Batch 2 per I1.

## Chunk 1 of 19: new capture codes for AI rate-limit and AI timeout
Covers: stories 1, 2, 3 (the distinct-code halves); findings 4.5 #9, #10 (the code halves of the capture AI-call findings; the behavior halves are Chunk 2, and 4.5 #5 lands in Chunk 6, #16 in Chunks 6 and 7, #15 in Chunk 8, #19 in Chunks 8 and 9).

1. Add failing tests to `tests/test_llm_adapter_unit.py` (existing file; reuse the `_Boom`, `_FakeClient`, `_Completions` fakes at lines 37-80), two NEW tests: (a) a 429-shaped `_Boom` (give it a `status_code = 429`) raised on a plain `propose` call — assert the raised error carries the NEW capture rate-limit code (step 3 adds the class; the test imports it by name, the number is not pinned); (b) a timeout-shaped `_Boom` raised — assert the NEW capture timeout code.
2. Run `.venv/bin/pytest tests/test_llm_adapter_unit.py -k "rate_limited or timed_out"`. Expect: 2 failed (the code classes do not exist yet).
3. In `ember/capture/errors.py` (existing; today's high-water is CAPTURE-016 at lines 92-95, and Batch 2 adds CAPTURE-017 to 019) add the two NEW code classes: a capture rate-limit code and a capture timeout code. Each takes the next free number in the CAPTURE family at implementation time (02x numbers are taken by Batch 2 per I1).

Proof it's real: temporarily rename the new rate-limit class in the error raise path → the 429 test fails on the missing code; undo.
Done when: `.venv/bin/pytest tests/test_llm_adapter_unit.py -k "rate_limited or timed_out"` ends `2 passed, 0 failed` (print the number).
Commit message: `B7: new capture rate-limit and timeout codes (next free numbers)`

## Chunk 2 of 19: one retry policy for capture, with backoff, retry-after and a total budget
Covers: stories 1, 2, 3, 15; findings 4.5 #9, #10 (the behavior halves — backoff, budget, engine-reported timeout).

1. Add failing tests to `tests/test_llm_adapter_unit.py` (existing), two NEW tests: (a) a 429-shaped `_Boom` raised on every call — assert the fake saw exactly 2 calls and that a `sleep` the test controls was called between them (pass the sleep in, so no real waiting); (b) assert `propose` sends `temperature=0`.
2. Run `.venv/bin/pytest tests/test_llm_adapter_unit.py -k "backoff or temperature"`. Expect: 2 failed (no retry policy exists — a 429 today raises at once).
3. In `ember/adapters/llm.py` (existing) implement ONE retry policy used by `OpenAiItemProposer.propose` (line 54): at most 2 attempts, exponential backoff with jitter (jitter seeded/injected so tests are deterministic), honoring a 429 reply's retry-after up to a fixed cap, and ONE total budget of 90 s per AI call, retries included, enforced against the injected clock — 90 s is the spec's assumption, chosen under the app's 120 s capture idle limit (`app/main/bridge-client.js:138`). Write the budget, the 60 s request timeout (`REQUEST_TIMEOUT_SECONDS`, line 43) and the app's idle numbers in the module docstring — that docstring is the "one documented place both sides test against" the spec asks for (the app numbers come from `bridge-client.js:136-139` and `ember/adapters/llm.py` holds the engine side). Capture sends `temperature=0` through the policy.

Proof it's real: change the attempt limit from 2 to 1, run the file — the backoff test fails (it counted 2 calls); put 2 back.
Done when: `.venv/bin/pytest tests/test_llm_adapter_unit.py` ends with `N passed, 0 failed` (print the number).
Commit message: `B7: one capture retry policy with backoff, retry-after and a budget; temperature 0`

## Chunk 3 of 19: the same policy and codes for relate and maintain
Covers: stories 1, 2, 3 again (the "used by capture, relate and maintain" decision, spec line 50; N18).

1. Add failing tests to `tests/relate/test_link_proposer_adapter_unit.py` (existing): a 429 raised twice → exactly 2 calls, a controlled sleep between them, and the NEW relate rate-limit code; a timeout-shaped error → the NEW relate timeout code. Run `.venv/bin/pytest tests/relate/test_link_proposer_adapter_unit.py -k "rate_limited or timed_out"`: expect 2 failed (missing codes).
2. Add the same two tests to `tests/maintain/test_close_proposer_adapter.py` (existing; follow its `test_openai_close_proposer_maps_openaierror_to_close_ai_call_failed` at line 89, and assert `item_id` stays on the error, I19). Run `.venv/bin/pytest tests/maintain/test_close_proposer_adapter.py -k "rate_limited or timed_out"`: expect 2 failed.
3. In `ember/relate/errors.py` (existing, high-water RELATE-037, lines 163-165) add the NEW relate rate-limit and timeout codes; in `ember/maintain/errors.py` (existing, high-water MAINTAIN-028, per PROJECT_MAP line 323) add the NEW maintain rate-limit and timeout codes. Each code takes the next free number in its family at implementation time — numbers are not pinned in advance (I1). In `ember/adapters/llm.py` switch `OpenAiLinkProposer.propose_links` (line 113) and `OpenAiCloseProposer.propose_close` (line 173) onto the same retry function written in Chunk 2.

Proof it's real: temporarily point `propose_links` at the old raise-only path (no retry) — the relate 429 test fails; undo.
Done when: `.venv/bin/pytest tests/relate/test_link_proposer_adapter_unit.py tests/maintain/test_close_proposer_adapter.py` ends `0 failed`.
Commit message: `B7: the retry policy covers relate and maintain; their rate-limit and timeout codes`

## Chunk 4 of 19: the capture core calls the AI port once
Covers: stories 1-3 (the capture half of the retry moving across the port boundary — spec-check section 2, last row). Also N18's "one retry policy".

1. NEW file `tests/test_retry_ownership.py`: one test `test_propose_items_calls_the_port_once` asserting the capture wrapper `propose_items` (`ember/capture/item_proposal.py:172-185`) makes exactly ONE port call and propagates the error instead of retrying — counting fake like `tests/fakes.py` `FakeItemProposer`.
2. Run `.venv/bin/pytest tests/test_retry_ownership.py`. Expect: 1 failed (the wrapper still retries).
3. Remove the catch-and-retry from `propose_items` (it becomes a single call) and update its caller `ember/cli.py:1375` (`propose_items` in `_propose`). Update the capture unit test that pins the old one-retry behavior — `tests/test_item_proposal_unit.py` — and the port docstrings, including "Both are retried" at `ember/capture/item_proposal.py:121`.

Proof it's real: re-add a second call in `propose_items` → the ownership test fails again; undo.
Done when: `.venv/bin/pytest tests/test_retry_ownership.py tests/test_item_proposal_unit.py` ends `0 failed`.
Commit message: `B7: the capture core calls the AI port once`

## Chunk 5 of 19: the relate and maintain cores call the AI port once
Covers: stories 1-3 (the relate and maintain half); N18's "one retry policy".

1. Add two tests to `tests/test_retry_ownership.py` (the NEW file from Chunk 4): `test_propose_links_with_retry_calls_the_port_once` (relate wrapper, `ember/relate/link_proposal.py:93-106`) and `test_propose_close_with_retry_calls_the_port_once` (maintain wrapper, `ember/maintain/close_proposer.py:217-228`), each asserting exactly ONE port call and propagation — counting fakes like `tests/fakes.py` `FakeItemProposer` and `tests/maintain/fakes.py` `FakeCloseProposer`.
2. Run `.venv/bin/pytest tests/test_retry_ownership.py`. Expect: 2 failed (the wrappers still retry).
3. Remove the catch-and-retry from the two wrappers (each becomes a single call) and update their callers: `ember/relate/run_relate.py:76` (`propose_links_with_retry`), `ember/maintain/run_maintain.py:409` (`propose_close_with_retry`). Update the engine retry unit tests that pin the old one-retry behavior — `tests/relate/test_link_proposal_unit.py`, `tests/maintain/test_close_proposer_unit.py` — and the port docstrings, including the `max_retries=0` docstring notes in `ember/adapters/llm.py` (lines 148, 211) that now name the adapter's own policy (the capture-side note was Chunk 4's).

Proof it's real: re-add a second call in `propose_close_with_retry` → the maintain ownership test fails again; undo.
Done when: `.venv/bin/pytest tests/test_retry_ownership.py tests/test_item_proposal_unit.py tests/relate/test_link_proposal_unit.py tests/maintain/test_close_proposer_unit.py` ends `0 failed`.
Commit message: `B7: engine cores call the AI port once; retries live only in the adapter`

## Chunk 6 of 19: 5 MB cap on stdin, empty input refused before any AI call
Covers: stories 4, 5; findings 4.5 #5, #16 (the capture input findings); decision B7-D5.

1. NEW file `tests/test_capture_input_limits.py`: (a) 6 MB piped to `ember capture --db <temp>` (click `CliRunner`, like `tests/test_cli.py`) exits 1 with the EXISTING too-large code `CAPTURE-002 SourceFileTooLarge` (`ember/capture/errors.py:18-20`); (b) an empty `--file` and an empty stdin exit 1 with the NEW capture empty-input code (step 3 adds it), using the forbid pattern from `tests/bridge/test_confirm_json_cli.py:111` (`monkeypatch.setattr("ember.cli.build_item_proposer", ...)` raising on any use) to prove the fake AI received no request; (c) direct unit case on `read_raw_text` (`ember/capture/input_reader.py:24`). Run it: expect failures.
2. Run `.venv/bin/pytest tests/test_capture_input_limits.py`. Expect: failures (stdin is uncapped today — `_read_stdin_bytes` at `ember/capture/input_reader.py:54-58`; no empty check exists between read and AI call, `ember/cli.py:363-366`).
3. In `ember/capture/input_reader.py`: enforce the existing `MAX_SOURCE_BYTES` (line 16, today file-only, lines 46-50) in `_read_stdin_bytes`, and after the UTF-8 decode in `read_raw_text` refuse empty content with the NEW empty-input code added to `ember/capture/errors.py` — it takes the next free number in the family at implementation time (02x numbers are taken by Batch 2 per I1; Chunk 1 adds two more first).

Proof it's real: delete the size check from `_read_stdin_bytes` → test (a) fails; undo.
Done when: `.venv/bin/pytest tests/test_capture_input_limits.py tests/test_cli.py tests/test_cli_capture.py` ends `0 failed`.
Commit message: `B7: cap stdin at 5 MB; refuse empty input before any AI call (new capture code)`

## Chunk 7 of 19: title = first non-blank line
Covers: story 6; finding 4.5 #16 (the title half; its empty-input half is Chunk 6).

1. Add failing tests to `tests/test_source_storage_unit.py` (existing; it already tests `default_title` — `test_default_title_is_first_80_chars` at line 28): a note starting with blank lines gets its title from the first non-blank line; a long non-blank first line is still cut to `TITLE_LENGTH` = 80 (`ember/capture/source_storage.py:13`). Run the file: expect the new tests red.
2. Run `.venv/bin/pytest tests/test_source_storage_unit.py`. Expect: 2 failed.
3. Change `default_title` (`ember/capture/source_storage.py:52-54`, today `raw_text[:TITLE_LENGTH]` — empty for a leading blank line) to take the first non-blank line and cut it to 80 characters.

Proof it's real: revert `default_title` to `raw_text[:TITLE_LENGTH]` → red; undo.
Done when: `.venv/bin/pytest tests/test_source_storage_unit.py tests/test_capture_pipeline_integration.py` ends `0 failed`.
Commit message: `B7: source title is the first non-blank line, cut to 80`

## Chunk 8 of 19: meaningful quotes and a delimited note
Covers: stories 7, 8; findings 4.5 #15, #19 (cited at set level — see Unknowns). The minimum quote length is the planned initial value 3 words (spec line 59) — tuned after the batch (I11).

1. Add failing tests: to `tests/test_item_proposal_unit.py` (existing) — a proposal whose quote is one short word (under the minimum) is dropped with rule `quote`, mirroring the substring rule at `ember/capture/item_proposal.py:216`; and to `tests/test_llm_adapter_unit.py` — the user message (built by `_user_content`, `ember/adapters/llm.py:282-291`) wraps the raw note in two visible delimiter lines and the surrounding instruction states text inside them is data.
2. Run `.venv/bin/pytest tests/test_item_proposal_unit.py tests/test_llm_adapter_unit.py -k "quote_words or delimiter"`. Expect: failures.
3. Implement: the minimum-quote rule (constant, initial value 3 words — tuned after the batch, I11) and a matching one-line system-prompt instruction in `ember/capture/item_proposal.py` (check in `_check_entry`, :209-218; wording in `SYSTEM_PROMPT`, :24-37); the delimiters around `raw_text` in `_user_content` (`ember/adapters/llm.py:282-291`).

Proof it's real: delete one delimiter line from `_user_content` → the delimiter test fails; undo.
Done when: `.venv/bin/pytest tests/test_item_proposal_unit.py tests/test_item_proposal_fixtures.py tests/test_llm_adapter_unit.py` ends `0 failed`.
Commit message: `B7: grounding needs a real quote; the note is delimited in the prompt`

## Chunk 9 of 19: prompt-kind drift fails loud
Covers: story 9; findings 4.5 #19, 4.3 #27 (the prompt-drift findings, cited at set level — see Unknowns); decision N19 (choices parsed only from the three known prompt constants).

1. Add failing tests to `tests/bridge/test_json_confirm.py` (existing): a DRIFTED prompt fed to `JsonRelateConfirm` and `JsonMaintainConfirm` (`ember/adapters/json_confirm.py:238-239`, `:281-282`) emits prompt kind `unknown` instead of `choice` (the capture port already does this, `:212-222`).
2. Run `.venv/bin/pytest tests/bridge/test_json_confirm.py -k unknown_prompt`: expect failures.
3. Implement: anchor `_prompt_kind` of the relate and maintain JSON confirm ports to their REAL `PROMPT` constants (`ember/relate/confirm_write.py:19` and `ember/maintain/close_proposer.py:27`); any other prompt → kind `unknown` (capture's pattern, `ember/adapters/json_confirm.py:212-222`).

Proof it's real: point `_prompt_kind` for maintain back at always-`choice` → the maintain drift test fails; undo.
Done when: `.venv/bin/pytest tests/bridge/test_json_confirm.py` ends `0 failed`.
Commit message: `B7: drifted prompts in relate and maintain parse as unknown and fail loud`

## Chunk 10 of 19: relate pool — candidate cap and wipe order
Covers: stories 10, 14; findings 4.8 #5 (with the 300-labeled-items number as the sizing case), #9. The cap is the planned initial value 40 (spec line 63) — tuned after the batch (I11).

1. Add failing tests to `tests/relate/test_candidate_pool_unit.py` (existing; fakes in `tests/relate/fakes.py`), two tests: (a) 300 labeled items → the merged ranked pool carries at most 40 candidates, chosen dense-first, then graph, then labels (spec line 63; the cap is the planned initial value, tuned after the batch, I11); (b) with an EMPTY universe and a different cached model, `store.wipe` is NOT called and there is no warning (today the wipe runs first, `candidate_pool.py:81` before the empty check at `:83-84`).
2. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py`. Expect: 2 failed.
3. Implement in `ember/relate/candidate_pool.py`: move `_model_change_warning` after the empty-universe check; add the candidate cap (constant, initial value 40 — tuned after the batch, I11) ordered dense → graph → labels.

Proof it's real: raise the cap to 10000 → the 300-item test fails on the length; undo.
Done when: `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py` ends `0 failed`.
Commit message: `B7: cap relate candidates at 40; wipe the cache only when items exist`

## Chunk 11 of 19: relate pool — damaged cached vectors are repaired, not raised
Covers: story 11; the repair half of finding 4.8 #6 (the RELATE-022 path and the undecodable-blob path).

1. Add failing tests: to `tests/relate/test_candidate_pool_unit.py` — a cached vector of the wrong length (today `CosineComputeFailed` RELATE-022 at `ember/relate/candidate_pool.py:131-138`) is deleted and recomputed instead of raised, and a cache read failure (`EmbeddingReadFailed` RELATE-037 from an undecodable blob, raised today at `ember/adapters/sqlite.py:2108-2111`) is treated the same; and to `tests/relate/test_candidate_pool_integration.py` (existing) — a real temp DB whose cache row holds a wrong-length blob: after `build_candidate_pool` the row is rewritten (new blob and new `embedded_at`), the run succeeds, and `embedder.embed` was called for that item.
2. Run `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py tests/relate/test_candidate_pool_integration.py`. Expect: red.
3. Implement: extend `_resolve_vector` (`ember/relate/candidate_pool.py:121-149`) so the wrong-length and RELATE-037 paths delete the bad row and recompute. This needs ONE new method `delete(item_id)` on the `EmbeddingStorePort` (`ember/relate/embedding_store.py`) and on `SqliteEmbedderStore` (`ember/adapters/sqlite.py`, beside `wipe` at :2165-2174) — a new method on the port; the real store and every fake gain it in the same chunk (`tests/relate/fakes.py`).

Proof it's real: make the wrong-length path raise RELATE-022 again → the repair tests fail; undo.
Done when: `.venv/bin/pytest tests/relate/test_candidate_pool_unit.py tests/relate/test_candidate_pool_integration.py` ends `0 failed`.
Commit message: `B7: repair damaged cached vectors by delete-and-recompute on the port`

## Chunk 12 of 19: query vectors scored at the cache's float32 precision
Covers: story 12; finding 4.8 #8; decision N20 (spec-check D3 option A).

1. NEW file `tests/relate/test_vector_format_unit.py`: pack-then-unpack round-trips values at float32 precision (little-endian, same numbers `ember/adapters/sqlite.py:2192-2206` uses today). Run it: expect pass (it pins nothing yet — pure round-trip on the helpers this chunk moves).
2. Add one failing test to `tests/relate/test_candidate_pool_unit.py`: a fresh float64 query vector and the identical vector returned from a float32 cache hit produce the SAME cosine score. Run `-k same_score`: expect failed.
3. NEW `ember/relate/vector_format.py`: move the pack/unpack knowledge there as the ONE pure definition; `ember/adapters/sqlite.py` imports it for `_pack_vector`/`_unpack_vector` (:2192-2206, adapters may import core — T9 only forbids the other direction); `build_candidate_pool` (or `_resolve_vector`) round-trips the freshly encoded query vector through pack/unpack before any cosine. No schema change, no migration.

Proof it's real: comment out the round-trip call → the same-score test fails; undo.
Done when: `.venv/bin/pytest tests/relate` ends `0 failed`.
Commit message: `B7: one float32 vector format; query vectors scored at cache precision`

## Chunk 13 of 19: cache format tag — migration 014
Covers: story 17; finding 4.8 #7 (the cache has no format tag; the wrong-vector repair half of 4.8 #6 is Chunk 11); spec-check section 4 on Batch 4's pin.

1. NEW file `tests/test_migration_014.py`, modeled on `tests/test_migration_012.py`: on a real v13 temp DB — the NEW migration adds the optional column `item_embeddings.vector_format` (nullable, no default, no rebuild, no backfill — constitution D5), rows and values survive, schema diff clean, `.bak-v13` backup kept, failed migration rolls back to v13, fresh install lands at 14; missing/NULL format means today's float32 format. Run: expect red (no 014 exists). (If Batch 6 lands first and takes migration number 014, this batch takes the next free number instead — N14.)
2. NEW `ember/adapters/migrations/014_add_item_embeddings_format.sql` (follow the 012/013 pattern in the same folder) and bump the two version watchers: `ensure_relate_schema` (`ember/adapters/sqlite.py:152-153`, `version < 12` → `14`) and the floors table in `ember/adapters/db_check.py:32` (`("relate", 12)` → 14).
   Done when (this step touches a migration, so it carries its own check): `.venv/bin/pytest tests/test_migration_014.py tests/test_relate_db_open.py tests/test_db_check.py tests/test_v12_read_never_migrates.py` — the 014 tests pass; the v13-era floors assertions that pinned `12` are updated in this same step (they name the new floor; the tests above show the real red list before editing them).
3. Write the tag: `SqliteEmbedderStore.upsert` (`ember/adapters/sqlite.py:2113-2134`) stores `vector_format` with the value from the Chunk 12 format module; reads treat NULL/missing as today's float32. Add the upsert write assertion to `tests/relate/test_embedding_store_integration.py` first (test, then the write).

Proof it's real: delete the `vector_format` column line from the 014 SQL → the migration test fails; undo.
Done when: `.venv/bin/pytest tests/test_migration_014.py tests/test_migrations.py tests/relate/test_embedding_store_integration.py` ends `0 failed`.
Commit message: `B7: migration 014 tags the vector cache format; missing = today's float32`

## Chunk 14 of 19: offline fail-fast and positive timeout settings
Covers: stories 13, 16; findings 4.3 #17, #25; decisions N21 ("the load never starts").

1. Add failing tests to `tests/relate/test_embedder_adapter_unit.py` (existing): `EMBER_EMBEDDER_LOAD_TIMEOUT_SECONDS=0` and `-1` are refused by `validate_embedder_config` and `build_embedder` with the existing bad-setting code `RELATE-035 ConfigMissing` (the `_parse_timeout` path, `ember/adapters/embedder.py:138-148`); with the offline env (`HF_HUB_OFFLINE=1`) and a missing local model cache, `build_embedder` raises `EmbedderLoadFailed` (RELATE-017) IMMEDIATELY and the model-load thread never starts — test it by monkeypatching a NEW seam helper (step 3) so it answers "not cached", and asserting `_load_model` was never called.
2. Run `.venv/bin/pytest tests/relate/test_embedder_adapter_unit.py -k "offline or positive_timeout"`. Expect: failures (today `_parse_timeout` accepts any float, and nothing checks the local cache before the load, `:151-181`).
3. Implement in `ember/adapters/embedder.py`: `_parse_timeout` refuses values <= 0; a pre-load check reads the local model cache (the hub-cache reader is imported lazily exactly like `sentence_transformers` today, so the suite keeps working without the `relate` extra) BEFORE `_load_model` starts its thread; offline + missing cache → `EmbedderLoadFailed` RELATE-017, model-missing sentence — no wait, no orphan thread.

Proof it's real: change the check to `<= -1000` → the zero-timeout test fails; undo.
Done when: `.venv/bin/pytest tests/relate/test_embedder_adapter_unit.py` ends `0 failed`.
Commit message: `B7: refuse non-positive embedder timeouts; offline with no cached model fails at once`

## Chunk 15 of 19: the fake provider server and the CLI seams
Covers: the spec's Testing Decisions seams 1, 3 and 4 (spec lines 79-86; seam 2 is Chunk 16, seam 5 is Chunk 10's cap test, seam 6 is Chunk 11's integration test, seam 7 is Chunk 14's offline test); D-23 seam ("the `ember` CLI on temp databases with a fake provider server"). These are PIN-style tests: they characterize behavior Chunks 1-3, 6 and 8 already built — no code is left to write — so their green story is the mutation proof below.

1. NEW file `tests/fake_ai_server.py`: a localhost-only HTTP server speaking the OpenAI chat-completions shape (prior art: `app/test/helpers/fake-ai-server.js`, the JS side of report 4.5; there is NO Python fake HTTP server in `tests/` today — checked). Modes: always-429-with-retry-after, accept-and-hang (never answers), and a normal reply carrying a saved answer fixture; it records one arrival time per request.
2. NEW file `tests/test_ai_server_cli.py` on REAL temp DBs (capture, fake key), pointed at the fake through `EMBER_AI_BASE_URL` (already honored, `ember/adapters/llm.py:99`), with the test names given here so the `-k` patterns below match: (a) `test_429_twice_waits_then_the_family_rate_limit_code` — the fake saw 2 requests and the second arrived after the retry-after wait, then stderr carries the family rate-limit code and exit 1; (b) `test_6mb_stdin_and_empty_file_make_no_request` — 6 MB stdin and an empty file: the fake's request log is EMPTY after both refusals; (c) `test_one_letter_quote_is_dropped` — a note answered with a one-letter quote → that proposal is dropped with rule `quote`.
3. Run `.venv/bin/pytest tests/test_ai_server_cli.py`. Expect: all pass in seconds — they prove the retry policy (Chunks 1-3), the input limits (Chunk 6) and the quote rule (Chunk 8) hold together at the CLI edge.

Proof it's real: turn the fake's mode from "429 twice then answer" to "answer at once" → test (a) fails on the call count; undo.
Done when: `.venv/bin/pytest tests/test_ai_server_cli.py` prints all passed, in seconds.
Commit message: `B7: fake provider server; CLI seams for 429 backoff, oversized and empty input, quote rule`

## Chunk 16 of 19: the slow marker — the hung-provider test is skipped locally, run in CI
Covers: the spec's Testing Decisions seam 2 (fake hangs: the engine's own AI-timeout code arrives before the app's idle limit); decision I11 (marked `slow`, skipped in the default local run, included in CI); the timing bounds. The ~60 s cost comes from the request timeout constant (`REQUEST_TIMEOUT_SECONDS`, `ember/adapters/llm.py:43`).

1. Add to `tests/test_ai_server_cli.py` the hung-provider test `test_hung_provider_ends_in_the_family_ai_timeout_code`, marked with the NEW `@pytest.mark.slow`: the fake never answers; the engine's timeout code arrives from the 60 s request timeout, inside the app's 120 s idle limit (assert elapsed < 120 s). This is the ONE slow test. Run `.venv/bin/pytest tests/test_ai_server_cli.py -m slow --strict-markers`: expect an error — the `slow` marker is not declared yet.
2. Declare the marker and skip it in the default local run: in `pyproject.toml` (`[tool.pytest.ini_options]`, lines 31-36) add `markers = ["slow: costs about a minute; excluded from the default local run, included in CI"]` and change `addopts` to `-q -m 'not live and not slow'`. Check with `.venv/bin/pytest --collect-only -q | head` that the suite still collects (`tests/bridge/test_contract_table.py`-style tests do not pin addopts).
3. Include it in CI: change the test step in `.github/workflows/test.yml` (line 18) from plain `pytest` to `pytest -m "not live"` — a command-line `-m` overrides the addopts filter, so CI runs the `slow` hung-provider test while live tests stay excluded.

Proof it's real: run `.venv/bin/pytest tests/test_ai_server_cli.py` — the default run skips the hung-provider test (1 skipped); drop `not slow` from the addopts and the local default pays the minute — undo.
Done when: `.venv/bin/pytest tests/test_ai_server_cli.py -m "not slow"` passes in seconds; `.venv/bin/pytest -m slow` runs the one hung-provider test and passes in about a minute; the CI line reads `pytest -m "not live"` (pinned by Chunk 18).
Commit message: `B7: the hung-provider test is slow-marked — skipped locally, run in CI`

## Chunk 17 of 19: base-URL pins
Covers: story 18; finding 4.2 #13 (no test asserts the base URL). These are PIN tests: they characterize behavior Chunks 1-3 already built, so there is no code left to write — their red/green story is the mutation proof below, stated up front.

1. Add a base-URL pin test to `tests/test_llm_adapter_unit.py` (existing): `build_item_proposer` sends the default base URL, and an `EMBER_AI_BASE_URL` env override reaches the client (fake-OpenAI recording pattern from `tests/maintain/test_close_proposer_adapter.py:65-86`, `recorded["base_url"]`).
2. Add the same pin test for `build_link_proposer` to `tests/relate/test_link_proposer_adapter_unit.py` (existing).
3. Run `.venv/bin/pytest tests/test_llm_adapter_unit.py tests/relate/test_link_proposer_adapter_unit.py -k base_url`. Expect: 0 failed.

Proof it's real: temporarily change `DEFAULT_BASE_URL` in `ember/adapters/llm.py` to `http://wrong.example/v1` → both pin tests fail; undo.
Done when: the `-k base_url` run above prints `0 failed`.
Commit message: `B7: pin the AI base URL for capture and relate`

## Chunk 18 of 19: pins of the numbers
Covers: stories 2, 3; finding 4.2 #12; the "one documented place both sides test against" proof (spec line 52, backing stories 2-3).

1. NEW file `tests/test_ai_limits_doc.py`, three pins: (a) the engine's capture budget constant (written in Chunk 2's `ember/adapters/llm.py` docstring/constant, 90 s) is BELOW the app's session idle limit parsed from `app/main/bridge-client.js` `sessionIdleMs = 120_000` (line 138); (b) `pyproject.toml` `addopts` excludes `live` and `slow`; (c) `.github/workflows/test.yml` runs `pytest -m "not live"`, so the `slow` test runs in CI (Chunk 16).
2. Run `.venv/bin/pytest tests/test_ai_limits_doc.py`. Expect: 3 passed (it pins the state Chunks 2 and 16 created).

Proof it's real: temporarily change `sessionIdleMs` in `app/main/bridge-client.js` to `60_000` → the budget pin test fails; undo.
Done when: `.venv/bin/pytest tests/test_ai_limits_doc.py` prints `3 passed`.
Commit message: `B7: pin the budget under the app idle limit and the slow-marker run rules`

## Chunk 19 of 19: the docs and the full close-out
Covers: story 19; finding 4.2 #12 (the written-down half).

1. `README.md` Running tests section (lines 224-231): add one sentence — the `pytest -m live` tests call the real AI service, are skipped without a key, and are never run in CI. Story 19 / finding 4.2 #12. Run `.venv/bin/pytest tests/test_docs_in_sync.py` after the edit.
2. Full close-out run step (see Final check): `.venv/bin/pytest` over the whole suite.

Proof it's real: temporarily delete the new README sentence → `tests/test_docs_in_sync.py` (or the story-19 pin) fails; undo.
Done when: the full suite prints `N passed, 0 failed`; skips only `live`/`slow`; `tests/test_docs_in_sync.py` passes.
Commit message: `B7: live-AI tests are not CI, in words and pins; full suite green`

## Final check
- Full suite, from the repo root: `.venv/bin/pytest`. Expect `N passed`, 0 failed; skips only `live`/`slow`. Same suite in CI: `.github/workflows/test.yml` runs `pytest -m "not live"` — identical except the `slow` test runs too (Chunk 16, pinned in Chunk 18).
- The batch's "Done when" from `archive/Plan.md` (Batch 7): "a fake provider returning 429 twice shows a wait between attempts, and a hung provider is reported as the engine's own timeout code, not the app's idle timeout." Proven by:
  - `.venv/bin/pytest tests/test_ai_server_cli.py -m "not slow" -k 429_twice` — asserts 2 requests with a wait between them and ends in the family rate-limit code (Chunk 15, test `test_429_twice_waits_then_the_family_rate_limit_code`, NEW).
  - The hung provider, both invocations (I11): locally the default run excludes it — `.venv/bin/pytest tests/test_ai_server_cli.py -m "not slow"` shows `1 skipped`; the paying run is `.venv/bin/pytest -m slow`, which ends in the engine's own timeout code with elapsed < 120 s, so the app's idle timeout can never be what the user sees (Chunk 16, seam 2; in CI this is the standard invocation).
  - Unit backstops for the same two claims: `.venv/bin/pytest tests/test_llm_adapter_unit.py -k "backoff or timed_out"`.
- The spec's other seams, each with its command: oversized/empty input → `.venv/bin/pytest tests/test_capture_input_limits.py` plus the no-request proof in `tests/test_ai_server_cli.py`; one-letter quote → the quote tests in `tests/test_item_proposal_unit.py` and the CLI seam in `tests/test_ai_server_cli.py`; 300 labeled items → the cap test in `tests/relate/test_candidate_pool_unit.py` (Chunk 10); wrong-length cached vector → `tests/relate/test_candidate_pool_integration.py` (Chunk 11, row rewritten); offline with no model → `tests/relate/test_embedder_adapter_unit.py -k offline` (RELATE-017 within seconds, thread never started; Chunk 14).

## Unknowns
- **Where batch-7 is cut from is still unconfirmed.** D-29 now states the rule (each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its "Done when" passes), but no `batch-*` branch exists today (`git branch -a`) and Batch 6's merge point is not yet a fact. The plan assumes the `ember-interface` line (all spec checks ran there). Confirm with the founder before creating `batch-7`.
- **Whether Batches 6 and 4 are actually merged first.** Plan.md gives order, not merge rules. Two hard touchpoints: new codes need Batch 6's sentence table (else the app falls back to the family sentence), and migration 014 needs Batch 4's latest-version pin updated if Batch 4 lands after this one (spec-check section 4).
- **Code numbers are settled.** Decision I1 (accepted 2026-11-01): Batch 2 keeps CAPTURE-017 to 019; every new code in this batch takes the next free number in its family at implementation time (D-27). No numbers are pinned in this plan. Checked free ranges: capture high-water CAPTURE-016 today, relate RELATE-037, maintain MAINTAIN-028.
- **Per-number mapping of the 4.5 findings is not restated anywhere.** Plan.md lists "4.5 #5, #9, #10, #15, #16, #19" as one set; the check report does not say which number is "no backoff" vs "stdin cap" etc. The plan therefore cites them at the set level per topic (Chunks 2, 6, 7, 8), not per line.
- **The offline cache-check reader.** N21 says check the local model cache before the load; the exact hub-cache API to use is not pinned anywhere in the repo (`huggingface_hub` arrives only with the `relate` extra). The plan keeps the reader behind a lazy import and a monkeypatchable seam; the true cache-scan call gets confirmed against the installed library's docs during Chunk 14.

# Batch 6 implementation plan: wording and new interface features
Spec: docs/Spec-Batch6.md
Branch: `batch-6`, per D-29 ("Each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its 'Done when' passes."). Batch 5 merges into `ember-interface`; batch-6 is cut from that merge point. Today `ember-interface` sits at `3b84663`.
Needs first: Batches 2, 4 and 5 (required: Batch 2's `EMBER-000` and the QUERY-003 split codes must exist before the sentence-table test can pass; Batch 4's one-transaction pattern and "scripts == 1..LATEST" rule host the new migration; Batch 5's xvfb e2e harness and stop mechanism are used in Chunks 13–15 and 19). Batch 1 is needed only for the About box's engine version (Chunk 18); without it that story falls back to app version only, per `archive/spec-check-batch6.md` §4.
Size: 20 chunks of 3 steps (60 steps), about 50 hours.

## Before you start
- Python tests (from the repo root):
  - All offline: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest`
  - One file: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest tests/test_cli.py`
  - (`ls .venv/bin/pytest` verified — it exists. CI runs plain `pytest` after install, per `.github/workflows/test.yml`.)
- App unit tests (from `app/`): `npm test` (node built-in runner via `test/run.js`; one file: `npm test -- plain-sentences`, the argument is a filename filter).
- App e2e (from `app/`): `npm run e2e -- <filename words>`, e.g. `npm run e2e -- forget`. This is Linux-only dev tooling; on CI it runs on a virtual screen (the Batch 5 xvfb job). Dev-run e2e under `xvfb-run -a npm run e2e -- <words>` when no real display is present.
- Full green before every commit: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest` and `cd app && npm test`.
- Safety rules (Constitution + Batch 0):
  - NEVER set or export `EMBER_AI_API_KEY` / `OPENROUTER_API_KEY`; strip them with `env -u …` on every command. Never call the real AI service.
  - NEVER open, export, back up or point at the real knowledge base or a real `key.enc`. All databases are fresh temp files.
  - Temp files go under `/tmp/opencode/batch6/` only.
  - Do not modify anything in `app/dist/` (staged build trees, not source).
  - Test wording rule (I10): the sentence table's own unit tests MAY check wording — the registry walk in `app/test/plain-sentences.test.js` and the words tables' own tests (`capture-words`, `maintain-words`, `undo-labels`, `keep-safe-words`). Every OTHER test — engine pytest, CLI pytest, e2e, flow and screen tests — asserts codes, data and screen elements only, never sentence text (Constitution T7/I21).
- New-code rule (I17): codes are never reused. Highest codes today, verified by grep: CAPTURE-016 (`ember/capture/errors.py`), RELATE-037, MAINTAIN-028, QUERY-007, EMBER-000 is the base default (`ember/errors.py:12`). Where this plan says "the next free number", take the next unused number at implementation time and record it in the commit body.

## Chunk 1 of 20: the registry test — every engine code has exactly one sentence, no fallback
Covers: user stories 1, 32; findings 4.10 #3, 4.10 #12.

1. In `app/test/plain-sentences.test.js`, replace the subtest `every code in ember/**/errors.py has sentences (spec §5.6 walk, F5)` with a subtest that (a) keeps the same regex walk `/code = "([A-Z]+-\d{3})"/g` over the six files `ember/errors.py` + the five per-area `errors.py` (N15, per check-report 1.2 option A), (b) requires `sentenceFor(code)` to return that code's OWN entry for every engine code (no family fallback reachable: the fallback title format `A problem … was reported.` must never appear for a real code), and (c) requires `EMBER-000` to have an entry.
2. Run `cd app && npm test -- plain-sentences`. Expect: 1 subtest failed, on the first fallen-back code (assert message `… has no plain-sentence entry anywhere` or the fallback-title assertion).
3. Do NOT fix yet — this red test drives Chunks 2–4.

Proof it's real: in `app/shared/plain-sentences.mjs` temporarily change `'QUERY-001'`'s entry key to `'QUERY-00x'`, re-run `npm test -- plain-sentences` — the walk must go red on QUERY-001; undo.
Done when: `cd app && npm test -- plain-sentences` reports exactly one failing subtest, naming the missing/fallen-back codes.
Commit message: none yet (commit with Chunk 2).

## Chunk 2 of 20: one sentence table in the app
Covers: user stories 1, 32; findings 4.10 #3, 4.10 #12.

1. Add to `ERROR_SENTENCES` in `app/shared/plain-sentences.mjs` an entry for every code its `sentenceFor` still falls back on: the `MAINTAIN-` entries and `CAPTURE-016` moved out of `app/shared/maintain-sentences.mjs` (lines 28–133 today), plus `EMBER-000` ("something inside Ember broke"), plus any new codes Batches 2/4/5 merged into the six `errors.py` files (run the Chunk 1 walk to list them).
2. Turn `app/shared/maintain-sentences.mjs` into a shim: `maintainSentenceFor` and `undoNoteFor` stay (imported by `app/renderer/screens/fix-close.mjs`), but look-ups delegate to `sentenceFor` from `plain-sentences.mjs`; delete the duplicated table.
3. Update the merged-table test of `app/test/undo-labels.test.js` (it reads `MAINTAIN_SENTENCES` directly at line 74) to read the one table instead. Run `cd app && npm test -- plain-sentences` and `npm test -- undo-labels`. Expect: all green.

Proof it's real: delete the `CAPTURE-016` entry from the one table and re-run `npm test -- plain-sentences` — the walk goes red (code with no entry); undo.
Done when: `cd app && npm test -- plain-sentences` passes with zero fallen-back codes; `grep -c "code = " ember/**/errors.py` codes minus `APP-` equals `Object.keys(ERROR_SENTENCES)` count.
Commit message: `Batch 6: one sentence table, every engine code has its own sentence`

## Chunk 3 of 20: the engine's split codes (missing key, relate-017 model split)
Covers: user stories 2, 3; findings 4.10 #7, 4.8 #3.

1. Write the failing tests: in `tests/test_llm_adapter_unit.py` (exists) add two cases — the missing-key raise of `build_item_proposer` and of `build_link_proposer` carries a NEW dedicated code (no longer the shared CAPTURE-008 / RELATE-035 detail-string), and in a NEW file `tests/test_embedder_load_split.py` the embedder's missing-package case and its load-timeout/live-thread case (`ember/adapters/embedder.py`, the join-timeout and `EmbedderLoadFailed` raise sites) carry two DIFFERENT new codes.
2. Run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest tests/test_llm_adapter_unit.py tests/test_embedder_load_split.py`. Expect: failures showing the old shared codes/strings raised.
3. In `ember/capture/errors.py`, `ember/relate/errors.py` and `ember/adapters/embedder.py` + `ember/adapters/llm.py`, add the new classes and point the raise sites at them — take the next free numbers (CAPTURE-01x, RELATE-03x); do not touch the old codes. Where the app matched Python's words (`'ai api key missing'` in `ember/adapters/llm.py:96,154,217`), the code itself now decides.

Proof it's real: revert one new class to its old code and re-run — the new test goes red; undo.
Done when: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest tests/test_llm_adapter_unit.py tests/test_embedder_load_split.py` passes; `.venv/bin/python -c "from ember.cli import main"` still imports.
Commit message: `Batch 6: split codes for missing key and embedder load-timeout (D-08, I17)`

## Chunk 4 of 20: the app stops matching Python's words
Covers: user stories 2, 3; findings 4.10 #7, 4.8 #3.

1. Write the failing JS tests: in `app/test/add-flow.test.js` and `app/test/relate-flow.test.js`, add cases asserting the NEW codes produce the right outcome (missing-key → the setup path opens; load-timeout → the retry branch, NOT the missing-package branch) — asserted by the code passed through `addErrorSentence` / `relateErrorSentence` and which advice block it selects, never the sentence wording (I10; the words are pinned only in the sentence-table tests).
2. Run `cd app && npm test -- add-flow` and `npm test -- relate-flow`. Expect: failures (today they branch on `'ai api key missing'` detail text, `app/shared/capture-words.mjs:31`, `app/shared/relate-words.mjs:63`).
3. In `app/shared/capture-words.mjs` and `app/shared/relate-words.mjs` remove the detail-substring branches and branch on the new codes only; add the new codes' entries to the one table in `app/shared/plain-sentences.mjs` (RELATE-017's entry becomes the missing-package one; the load-timeout code gets its own). Re-run the Chunk 1 registry test too.

Proof it's real: send the new code's entry title through `sentenceFor` unchanged but delete one new code entry — registry test red; undo.
Done when: `cd app && npm test -- add-flow relate-flow plain-sentences` green; `grep -n "ai api key missing" app/shared/*.mjs` returns only comments or nothing.
Commit message: `Batch 6: app advice keyed by code only, no Python-word matching (D-08)`

## Chunk 5 of 20: the untrue sentences (rejected note, MAINTAIN-003, sweep summary)
Covers: user story 4; findings 4.5 #6 (sentence half; the Forget button is Chunks 12–15), 4.6 #9, 4.6 #10.

1. Write the failing words-table unit tests (these MAY pin wording — I10's exception): in a NEW `app/test/capture-words.test.js` (the capture words table's own test) TEXT_KEPT must not say "nothing was created" when the note WAS saved (the true facts per `ember/cli.py:364-367`: the text is saved as a source before proposing; after all items are rejected no ITEMS were made); in `app/test/maintain-words.test.js` the zero-count sweep must not say "Nothing changes" after a finished run (4.6 #10); in `app/test/undo-labels.test.js` (or the maintain table's test) MAINTAIN-003's words must be about the reason not being human-settable (4.6 #9).
2. Run `cd app && npm test -- capture-words maintain-words undo-labels`. Expect: the pinned old wording fails the new cases.
3. Correct the sentences in `app/shared/capture-words.mjs` (TEXT_KEPT and its CAPTURE-008 branches), `app/shared/maintain-words.mjs` (`sweepCountsSentence`, lines 81–92) and the MAINTAIN-003 entry now living in the one table. Keep every other branch's facts unchanged.

Proof it's real: put the old `Nothing changes.` string back in `sweepCountsSentence`'s zero branch — the new test goes red; undo.
Done when: `cd app && npm test -- capture-words maintain-words undo-labels` green, and the full `cd app && npm test` stays green.
Commit message: `Batch 6: untrue sentences corrected (rejected note, MAINTAIN-003, sweep summary)`

## Chunk 6 of 20: history — the two missing kinds, newest first, derived close reasons
Covers: user stories 21, 22; findings 4.7 #4, 4.7 #13, 4.7 #14.

1. Write the failing pytest: in `tests/query/test_history_unit.py` add — (a) a row with `('rationale','user_edit_item')` classifies as `item_edited`, not `unknown`, and `('link_removed','user_remove_link')` as `link_removed` (the real writer causes, `ember/maintain/human_actions.py:314,359`); (b) `history()` returns events newest first (`(timestamp, id)` descending) and `--offset` pages back in time; (c) a `Closed:expired` status row renders `close_reason: "expired"` with the raw `Closed:expired` no longer the rendered value.
2. Run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest tests/query/test_history_unit.py`. Expect: 3 failures.
3. In `ember/query/history.py`: add the two pairs to `_KIND_BY_PAIR`, flip the sort at line 136 to `reverse=True`, and render the derived `close_reason` (already computed via `split_status_value`, `ember/maintain/rows.py:129`) as the event's status value — the raw encoded string stays only in the ledger. Then update the app side that assumed oldest-first: `app/test/fake-ember.js` + `app/test/e2e/fixtures/steps-04.json` history ordering, and `app/renderer/screens/lookup.mjs` Ledger pager labels (lines 398–408: after the flip, "Older lines" walking `offset+` now walks back in time). Update `app/test/e2e/first-run-home-lookup.js` where it pins ledger order.

Done when (this step renders derived data over raw ledger values — reversible code change, no data touched): `.venv/bin/pytest tests/query/` green, `cd app && npm run e2e -- first-run` still green.

Proof it's real: revert the sort to ascending — the new order test goes red; undo.
Done when: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest tests/query/ && cd app && npm test` all green.
Commit message: `Batch 6: history kinds for edit/remove-link, newest first, derived close reasons`

## Chunk 7 of 20: topic-search total and --offset
Covers: user story 20; finding 4.7 #5.

1. Write the failing pytest: in `tests/query/test_topic_filter_cli.py` assert `topic-search --format json` carries `total` (the pre-page count) and accepts `--offset`; today there is no `--offset` flag and the envelope has only `count` (`ember/query/render.py:40-50`, `ember/cli.py:1088-1116`).
2. Run `.venv/bin/pytest tests/query/test_topic_filter_cli.py`. Expect: 1 failed (unknown option --offset and/or missing total key).
3. Add `--offset` to the `topic-search` command in `ember/cli.py`, thread a page through `run_topic_search` (the filter already exists in `ember/query/rows.py` `TopicFilter`), and add `"total"` to `render_topic_search` (additive field, D5/I10). Then the app: in `app/main/command-args.js` add `offset` to `topicSearchArgs`, update the pin in `app/test/command-args.test.js` ("topic-search has no --offset" — this pin is deliberately changed), and in `app/renderer/screens/lookup.mjs` (lines 186–206) show `N of M matches` and page through search results with the existing pager buttons. Update `app/test/fake-ember.js`'s topic-search shape.

Proof it's real: remove `"total"` from `render_topic_search` again — the pytest and the e2e count test go red; undo.
Done when: `.venv/bin/pytest tests/query/ && cd app && npm test && npm run e2e -- first-run` green; in the e2e a 60-item base shows the numbers 50 and 60 in the search results header — numbers and elements only, not the header wording (I10).
Commit message: `Batch 6: topic-search total and --offset, app shows "N of M" (4.7 #5)`

## Chunk 8 of 20: CLI honesty — refused flags
Covers: user stories 23, 24, 25; findings 4.5 #8, 4.10 #9, 4.10 #6, 4.6 #13.

1. Write the failing pytest (add to `tests/test_cli.py` and `tests/bridge/test_fmt_json_cli.py`, CliRunner per repo convention): `capture --format json` and `relate --format json` exit 2 with a usage error naming the flag (N6: usage errors keep click's exit 2, no code); `capture --file ""` exits 2 (`ember/cli.py:360` treats the empty string as stdin today); `maintain --format json` with the default `--confirm terminal` exits 2 (today `_confirm_io` at `ember/cli.py:216-239` mixes text into stdout).
2. Run `.venv/bin/pytest tests/test_cli.py tests/bridge/test_fmt_json_cli.py`. Expect: the new cases fail (flags accepted and ignored / stdin read).
3. Implement the three refusals in `ember/cli.py` with `click.UsageError` before any child work starts (I7/I12), and list the refused combinations in `docs/commands.md` (`tests/test_docs_in_sync.py` reads it).

Proof it's real: delete the `--file ""` refusal — `env … .venv/bin/pytest tests/test_cli.py -k empty_file` goes red (stdin is read); undo.
Done when: `.venv/bin/pytest tests/test_cli.py tests/bridge/ tests/test_docs_in_sync.py` green; `env -u EMBER_AI_API_KEY … .venv/bin/ember capture --help` shows the refusal note.
Commit message: `Batch 6: refuse --format json on capture/relate, empty --file, json+terminal confirm (D-20)`

## Chunk 9 of 20: JSON summary carries the human line
Covers: user story 33; finding 4.3 #26.

1. Write the failing pytest in `tests/bridge/test_json_confirm.py`: a `summary` event must carry `line` (the exact human summary line) NEXT to the fields, additive (D5) — today `JsonSink.summary` at `ember/adapters/json_confirm.py:134-135` drops it.
2. Run `.venv/bin/pytest tests/bridge/test_json_confirm.py`. Expect: 1 failed (missing `line` key).
3. Change `summary()` to emit `{"event": "summary", "line": line, **fields}` and update the app-side summary readers if they validate keys (check `app/shared/confirm-view.mjs` and `app/shared/maintain-words.mjs` — both read engine files, mark the additive field; unknown-key-tolerant readers need no change).

Proof it's real: drop `"line"` from the emitted dict — the new pytest goes red; undo.
Done when: `.venv/bin/pytest tests/bridge/ && cd app && npm test` green; `contract table` test (`tests/bridge/test_contract_table.py`) still green.
Commit message: `Batch 6: JSON summary carries the human summary line (4.3 #26)`

## Chunk 10 of 20: migration — optional source_id on the ledger
Covers: user stories 9, 10, 11 (groundwork); decision N14, D-07.

1. Write the failing pytest `tests/test_migration_source_id.py` (NEW), following `tests/test_migration_013.py`: a hand-built ledger gains a nullable `source_id` column, all existing rows and values preserved, fresh install applies all scripts through the new LATEST, the safety copy is written.
2. Run `.venv/bin/pytest tests/test_migration_source_id.py`. Expect: 1 failed (no such migration yet).
3. Add the migration to `ember/adapters/migrations/` with the NEXT FREE number (run `ls ember/adapters/migrations/` first — today the highest is 013; if Batch 7 already landed one, take the next free — N14's rule). Copy the pattern of `013_add_change_log_group_id.sql` (nullable column, no rename).
   Done when (touches schema): on a throwaway copy of a v13 database run `env -u EMBER_AI_API_KEY … .venv/bin/ember db-check --db /tmp/opencode/batch6/copy.db`; the report says version 14 and OK, and the file's old copy is preserved as the runner's `.bak-v` file. Delete the copy afterwards.
Note — no step needed: `ember/adapters/db_check.py` floors print but do not hard-stop (verify with the db-check run in step 3; only update `_floors_line`/required-version call sites IF a test fails).

(The chunk above has 3 numbered steps plus a verify note inside step 3.)

Proof it's real: make the migration's column NOT NULL — the preserve-rows test goes red; undo.
Done when: `env … .venv/bin/pytest tests/test_migrations.py tests/test_migration_source_id.py tests/test_migration_013.py tests/test_schema_enforcement.py` green.
Commit message: `Batch 6: migration <NNN> — nullable change_log.source_id (N14, D5)`

## Chunk 11 of 20: the engine's forget-source command and its history line
Covers: user stories 10, 11, 12; findings D-07 (engine half), D-26.

1. Write the failing pytest `tests/test_forget_source.py` (NEW, CliRunner on a temp DB seeded through the existing capture helpers): (a) `ember forget-source --db DB --source ID` on a note WITH items exits 1 raising a NEW code (next free CAPTURE number); (b) on a note with NO items: source row gone, its `ai_responses` rows (linked by `ai_responses.source_id`, migration 005/009) gone, exactly one ledger line carrying the source id and time, `group_id NULL` (invisible to undo per migration 013's own rule), field/cause pair NEW, no text; (c) a missing id exits 0 (I8: delete-missing = success); (d) `ember history` classifies the new pair as a NEW kind and the event carries `source_id` with no note text.
2. Run `.venv/bin/pytest tests/test_forget_source.py`. Expect: 4 failures (unknown command).
3. Implement: the pure forget rule (a small NEW module in `ember/capture/`, e.g. `forget_source.py`, validation + the one transaction per Batch 4's pattern), the store method on the adapters side (`ember/adapters/sqlite.py`, near `SqliteMaintainStore`), the `forget-source` command in `ember/cli.py`, and the pair→kind entry in `ember/query/history.py::_KIND_BY_PAIR`. Document the command in `docs/commands.md`.

Proof it's real: write the ledger line with a `group_id` — the "invisible to undo" test goes red; undo.
Done when: `env … .venv/bin/pytest tests/test_forget_source.py tests/test_migration_source_id.py tests/test_docs_in_sync.py` green; then `.venv/bin/ember export --db /tmp/opencode/batch6/demo.db` shows the note text BEFORE and not AFTER a forget (story 9's engine half).
Commit message: `Batch 6: ember forget-source — permanent, one transaction, one textless ledger line (D-07, D-26)`

## Chunk 12 of 20: list sources with no items
Covers: user story 6 (engine half), 11; D-09.

1. Add to `tests/test_forget_source.py` a failing case for the new read command (NEW): it lists source ids (`id`, `created_at`, first words of `full_text`) of sources that have ZERO items, empty list instead of None (I4), read-only (`--format json` supported on this read).
2. Run `.venv/bin/pytest tests/test_forget_source.py -k without_items`. Expect: 1 failed (unknown command).
3. Add the command in `ember/cli.py` over one new read in `ember/adapters/sqlite.py`; document it in `docs/commands.md`.

Proof it's real: make the read count items with a wrong join (e.g. return every source) — the test's "source with items is not listed" case goes red; undo.
Done when: `env … .venv/bin/pytest tests/test_forget_source.py tests/test_docs_in_sync.py` green.
Commit message: `Batch 6: read command listing sources with no items (Cleanup)`

## Chunk 13 of 20: "Forget this note" on the Add screen
Covers: user stories 4, 5, 7, 8, 9; findings 4.5 #6 (interface half), D-09, D-10.

1. Write the failing e2e `app/test/e2e/forget-note.js` (NEW; filename filter word "forget"; over the REAL `ember` + venv, temp KB, fake AI server per `app/test/e2e/add.js` conventions): reject every item in the Add confirm loop → the summary shows the forget button, found by its element/accessible name existing, its wording not pinned (I10; shown ONLY when every item was rejected, story 11); press it → an inline confirm `role="group"` with an accessible name and a cancel + confirm pair — the confirm's sentences come from `sentenceFor`, so their wording is checked in the sentence-table tests, not here (story 8, D-10); confirm → the note is gone (verify through the Cleanup list, `list-items`-style read, and an export).
2. Run `cd app && xvfb-run -a npm run e2e -- forget`. Expect: timeout waiting for the forget button.
3. Wire it: two NEW ipc channels in `app/main/ipc.js` (forget + list-sources, both gated like the existing ones), an ipc/preload allowlist update (`app/preload/preload.js` — its pinned allowlist has a node test, `app/test/preload-allowlist.test.js`), the button and inline confirm in `app/renderer/screens/add.mjs` (summary stage, ~line 210), using `sentenceFor` for any refusal.

Proof it's real: in `add.mjs` remove the "shown only when every item was rejected" condition — the e2e's zero-proposals case goes red; undo.
Done when: `cd app && xvfb-run -a npm run e2e -- forget add` green, and the a11y scan inside the e2e is clean.
Commit message: `Batch 6: Forget this note after rejecting every item (D-07, D-09, D-10)`

## Chunk 14 of 20: "Notes with no items" in Cleanup and the history line
Covers: user stories 6, 10; findings D-09 (Cleanup half).

1. Extend `app/test/e2e/forget-note.js` with the failing Cleanup case: the Clean up screen shows the sources-with-no-items list (found by its section element, its heading wording not pinned — I10; read-only until Forget is pressed); the same inline confirm; after forgetting, the item disappears from the list AND Home/Ledger gains exactly ONE new ledger event of the forgotten-note kind (story 10), found by its kind/kind code and carrying the source id and date (the line's sentence wording is NOT pinned in the e2e — I10), and the note's text appears nowhere on the screen.
2. Run `cd app && xvfb-run -a npm run e2e -- forget`. Expect: the new Cleanup case fails (no list rendered).
3. Add the list to `app/renderer/screens/cleanup.mjs` (a section beside the sweep, reading the Chunk 12 command through the new ipc channel), the sentence-table entry for the forgotten-note kind's label and pattern in `app/shared/plain-sentences.mjs` (`HISTORY_KINDS` + `historyEventSentence`), keeping the registry test green.

Proof it's real: temporarily render the list from `list-items` (items, not sources) — the e2e's "note with no items appears, item-bearing note does not" case goes red; undo.
Done when: `cd app && xvfb-run -a npm run e2e -- forget && npm test` green (the `plain-sentences` walk covers the new kind automatically).
Commit message: `Batch 6: Cleanup "Notes with no items" and the forgotten-note history line`

## Chunk 15 of 20: first run in 2 steps, file checked before saving
Covers: user stories 13, 15; findings 4.9 #9, F7c.

1. Edit the failing e2e expectations in `app/test/e2e/first-run-home-lookup.js`: first run shows TWO steps; the "Ready" third step is gone (verified: `STEPS = ['Knowledge base file', 'AI connection', 'Ready']` at `app/renderer/screens/first-run.mjs:17`; "Skip for now" now flows straight to finish); and a refused file (a non-Ember file picked) leaves the PREVIOUS path in the input (today `saveSettings` at `first-run.mjs:74` runs before the file check at :83-87).
2. Run `cd app && xvfb-run -a npm run e2e -- first-run`. Expect: failures on the step count and the refused-file case.
3. In `app/renderer/screens/first-run.mjs`: drop step 3 (`stepReadyHtml`), renumber the "Step N of 3" text and progress bar (`first-runHtml` lines 176-203) to 2, move the `kbStatus` check BEFORE `saveSettings` so a refused file keeps the previous choice, and route "Skip for now" + "Continue" straight to finish.

Proof it's real: keep step 3 but hide it from the list — the e2e step-count test stays red; undo.
Done when: `cd app && xvfb-run -a npm run e2e -- first-run` green including the a11y scan and Reduce Motion cases.
Commit message: `Batch 6: first run in 2 steps; file checked before it is saved (4.9 #9, F7c)`

## Chunk 16 of 20: one key box with an eye toggle
Covers: user story 14; finding F7d.

1. Write the failing e2e cases: in `app/test/e2e/first-run-home-lookup.js` and `app/test/e2e/settings.js` — exactly ONE key input per screen (`setup-key-input` / `settings-key-input`), with an eye toggle INSIDE the field (aria-label "Show key"/"Hide key"), and no separate Show/Hide button (today `first-run.mjs:235,238` and `settings.mjs:671-672`).
2. Run `cd app && xvfb-run -a npm run e2e -- first-run settings`. Expect: the new assertions fail (two buttons, no eye toggle).
3. Build the eye-toggle key field: a shared renderer component (NEW file `app/renderer/components/key-field.mjs`, styled from `tokens.css` only) used by `first-run.mjs` and `settings.mjs`; remove both Show/Hide buttons. Add its contract to `app/test/design-components.test.js`.

Proof it's real: render two key inputs in first run — the e2e "exactly one key input" case goes red; undo.
Done when: `cd app && xvfb-run -a npm run e2e -- first-run settings && npm test` green.
Commit message: `Batch 6: one key box with an eye toggle (D-14, F7d)`

## Chunk 17 of 20: the About box shows versions, not paths
Covers: user story 16; finding F7a (= 4.9 #22).

1. Update the failing pin in `app/test/menu-template.test.js`: `aboutCreditsText({ version, fontsPath })` must produce NO path and NO fonts folder (today `app/shared/menu-template.mjs:210-222`), and MUST show an engine version line when one is given. Add the main-process wiring test stating `app/main/main.js` passes app version + engine version (from `ember --version`, Batch 1) — or app version only when the engine does not answer.
2. Run `cd app && npm test -- menu-template`. Expect: failures on the path-free assertion.
3. Change `aboutCreditsText` (drop `fontsPath`, name the two `-OFL.txt` files instead), update the caller at `app/main/main.js:346-350`, and (only if Batch 1's `ember --version` is merged) read the engine version once through the existing bridge client.

Proof it's real: print `fontsPath` again — the menu-template test goes red; undo.
Done when: `cd app && npm test -- menu-template preload-allowlist` green; the About text contains a version and no `/`-path.
Commit message: `Batch 6: About shows versions and licence file names, no install path (F7a)`

## Chunk 18 of 20: the Link screen — label, Stop, named fields
Covers: user stories 17, 18, 19; findings 4.8 #11, 4.8 #4, 4.8 #10.

1. Write the failing tests: `app/test/relate-args.test.js` — the bad-id refusal names `--item` (today `app/main/relate-args.js:36` calls `requireId(item)` with no label, `app/main/require-id.js:16-24`); `app/test/relate-flow.test.js` — the no-more-suggestions button sends the SAME `n` answer/key as today (N16/D-18; the label change from "Reject" at `app/renderer/screens/link.mjs:166` is applied in code and checked visually, not pinned in the test — I10) and stops further suggestions; and a stop during preparation leaves NO APP-002 code in the rendered error (today rendered at `link.mjs:462-468`), riding Batch 5's N3 mechanism.
2. Run `cd app && npm test -- relate-args relate-flow`. Expect: 3 failures.
3. Implement: pass the label into `requireId` in `relate-args.js`, change the button label in `link.mjs` (keep the same `n` key/answer), and mark the self-initiated stop (Batch 5's sentinel) so the prepare phase resolves as "Stopped" instead of an error; any OTHER kill without a result uses Batch 5's "Ember stopped unexpectedly" app code entry in the one table.

Proof it's real: make the no-more-suggestions button send a different answer key than `n` — the relate-flow test goes red; undo.
Done when: `cd app && npm test && xvfb-run -a npm run e2e -- link` green.
Commit message: `Batch 6: Link label names the consequence; stop during prepare is not a crash (4.8 #4, #10, #11)`

## Chunk 19 of 20: error codes only behind Details
Covers: user story 26; finding 4.9 #23.

1. Write the failing static test: a subtest in `app/test/screen-logic.test.js` (exists) scans `app/renderer/screens/*.mjs` and `app/shared/*.mjs` and refuses any bare `(code ${…})`/`code APP-…` interpolation rendered OUTSIDE a Details block; expect failures for `app/renderer/screens/first-run.mjs:64` (the browse refusal) and any other hit `grep -rn "code \${" app/renderer/screens` finds.
2. Run `cd app && npm test -- screen-logic`. Expect: failures listing the offending lines.
3. Move each found code behind the existing Details affordance (`state-block.mjs`'s error block already does this for blocks) — in first run the file-picker message keeps its plain words only.

Proof it's real: re-add `(code ${chosen.error.code})` to a message — the scan fails at that file; undo.
Done when: `cd app && npm test` green and `grep -rn "code \${" app/renderer/screens/` returns only Details paths.
Commit message: `Batch 6: codes behind Details only (4.9 #23)`

## Chunk 20 of 20: design — gallery toolbar, Keep safe role, type scale, Home class, narrow windows
Covers: user stories 27, 28, 29, 30, 31; findings 11 #1, 11 #2, 11 #3, 11 #4, 4.9 #21.

1. Write the failing tests: (a) subtest in `app/test/design-type-scale.test.js` — no `font-size: <literal rem>` in `app/renderer/styles/*.css` outside the five named styles (hits today: `components.css:137-138` `.btn .kbd`, `app.css:50-53` `.nav button .t small`, `app.css:337-339` `.nav .count`, `app.css:105-109` `label`, `app.css:152` `.finding strong`); (b) `app/test/e2e/keep-safe.js` — the open-file confirm carries `role="group"` with a label, not `role="alertdialog"` (`app/renderer/screens/keepsafe.mjs:133`); (c) `app/test/e2e/design.js` — the demo-bar buttons are styled `.btn` with light label ink (`app/renderer/gallery.html:21-32`, `app/renderer/styles/gallery.css:6-15`).
2. Run `cd app && npm test -- design && xvfb-run -a npm run e2e -- design keep-safe`. Expect: the new assertions fail.
3. Implement: replace the five literal sizes with the named style variables (`tokens.css`), add the `.btn` class to the gallery demo buttons and their CSS, change `keepsafe.mjs:133` to `role="group"` + `aria-label`, and fix the duplicate class attribute in `app/renderer/screens/home.mjs:180` (`<tr><td class="dim" class="nowrap">` → one valid class). Then ONE visual check below 800 px: launch the gallery and Home under `xvfb-run` with a 700 × 900 window, confirm no horizontal overflow and no clipped labels, and record the result in the session notes (11 #4; a manual check, not an automated test).

Proof it's real: set `.finding strong` back to `1.05rem` — the type-scale scan fails; undo.
Done when: `cd app && npm test -- design && xvfb-run -a npm run e2e -- design keep-safe` green; the manual narrow-window note is written down.
Commit message: `Batch 6: design audit fixes — toolbar, inline group role, type scale, Home class (11 #1-#4, N17)`

## Final check
- Full suites, all green, no AI keys in the environment:
  1. `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest` — expected: all pass, 0 failed.
  2. `cd app && npm test` — expected: all pass.
  3. `cd app && xvfb-run -a npm run e2e` — expected: all e2e files pass.
  4. Update `PROJECT_MAP.md` for newly added/removed files (constitution of this repo; `tests/test_docs_in_sync.py` checks it).
- The batch's "Done when" from archive/Plan.md, with proving commands:
  1. "the registry test passes with zero codes falling back to a family sentence" → `cd app && npm test -- plain-sentences` green, including the Chunk 1 no-fallback subtest.
  2. "An e2e test rejects every item, forgets the note, and export no longer contains it" → `cd app && xvfb-run -a npm run e2e -- forget` green; its final assertion greps the export file for the note text and finds nothing.

## Unknowns
- Exact new code numbers: deliberately NOT fixed in the plan (I17: next free at implementation time; Batches 2/4/5/7 may already have taken numbers). The registry test, not the plan, pins the final mapping.
- The new engine command names `forget-source` and the list-sources read are chosen by this plan (marked NEW); if Batch 5's or Batch 4's merged work introduced a naming clash, rename at implementation and update the doc-sync test.
- e2e under xvfb in CI depends on Batch 5's sandbox fix (D-13) having landed; the local commands above assume a dev Linux box. If Batch 5 changed the e2e runner (`app/test/e2e/run-all.js`), re-verify the invocation before Chunk 13.
- The exact report text of findings 4.10 #3 and #12 was not re-read in this planning pass (Plan.md's mapping was used); re-read `archive/Problems.md` sections 4.10 during Chunks 1–2 to make sure no half of the finding is missed.
- Whether `app/shared/confirm-view.mjs`/`maintain-words.mjs` validate the summary event's key set (Chunk 9) — checked up to a point; the contract-table test (`tests/bridge/test_contract_table.py`) may need the `line` field added to its pinned row.

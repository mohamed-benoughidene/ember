# Batch 3 implementation plan: a failed Add keeps the form and its text; Home shows one notice per error code

Spec: docs/Spec-Batch3.md
Branch: `batch-3`, cut from `ember-interface` at the point where Batch 2 merged into it, and merged back into `ember-interface` when this plan's Done-when checks pass (decision D-29 in `archive/Plan.md`: each batch on its own branch `batch-N`, cut from where the previous batch merged).
Needs first: Batch 2 (the spec says "Depends on Batch 2": story 4's real error codes and story 5's crash sentence are Batch 2's work). Batch 0's e2e harness and fake engine (`app/test/e2e/`, `app/test/fake-ember.js`) already exist today, per `archive/spec-check-batch3.md` section 4.
Size: 14 steps in 5 chunks, about 8 hours.

## Before you start

Commands this batch touches, exactly as typed (from the repo root `/home/mo/lab/ember`):
- Unit tests (node runner, filter by file name): `npm --prefix app test` (all) and `npm --prefix app test -- home-failures` (the new file only).
- The Add e2e: `xvfb-run --auto-servernum npm --prefix app run e2e -- add`
- The Home e2e (its full name today is `first-run-home-lookup.js`, so the filter word is `first-run`): `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run`
- Python regression (untouched by this batch, run once at the end): `.venv/bin/pytest tests/ -q`
- `.venv` exists (`ls .venv/bin/pytest` confirmed); `app/node_modules/.bin/playwright` exists.

Safety rules: no AI keys anywhere (the fake key string inside `app/test/e2e/add.js` is not a real key); never open a real knowledge-base file or `key.enc`; every e2e runs only under `xvfb-run`; all temp files go under `/tmp/opencode/batch3/` (every e2e already makes its own `os.tmpdir()` workspace, which you leave alone).

## Chunk 1 of 5: a failed Add shows the error AND the form, box text kept (F2)

Covers: user stories 1, 2, 4, 9 (the Add half of story 9); check-report findings 4.9 #11 and 4.2 #9. Story 5 is NOT built or tested here: it is Batch 2's app side by decision N5 (`archive/Plan.md`), so this batch only keeps tests 1-3 scoped as `docs/Spec-Batch3.md` says.

1. In `app/test/e2e/add.js`: (a) extend `startFakeAi` to record each request body it receives (the same "records every request" behavior `app/test/helpers/fake-ai-server.js` has — here only the body string, on the local 127.0.0.1 server); (b) add a NEW scenario function `failKeepsForm(ai)` copied from the `aiUnreachable` shape (fake AI answers 500, `goToAdd`, `addText(win, NOTE)`): after `[data-testid="add-error"]` appears, assert `[data-testid="add-text-input"]` is visible AND holds the text of `NOTE`, and the error text matches the CAPTURE-008 words today (`/could not answer/i`); (c) call it from `main()` after `aiUnreachable(unreachable)`; (d) update the file's final "all nine scenarios green" line to the new count (one more scenario).
2. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- add`. Expect: the new scenario FAILS inside `failKeepsForm`, because today the failure path never brings the form back (`add.mjs:415` clears the form at session start and the error phase renders only `flowEl`) — the textarea line throws.
3. In `app/renderer/screens/add.mjs`, in `renderFlow()`'s `state.phase === 'error'` branch: re-render the draft form (`renderGateAndForm()`) and keep the error block in `flowEl` as it already does. `state.text` still holds the draft (only `resetToForm` clears it, `add.mjs:523`), and `renderGateAndForm` already restores `textarea.value = state.text` with the input listener attached (`add.mjs:320-324`) — no new state, per the check report answer 2.1.

Proof it's real: in `renderGateAndForm`, temporarily change `textarea.value = state.text;` to `textarea.value = '';` — the new scenario must turn red on the box-contents assertion. Then undo.
Done when: `xvfb-run --auto-servernum npm --prefix app run e2e -- add` ends green and prints, among the scenarios, `form kept OK: the error and the form show together, text still in the box` and the file's own final `e2e add OK` line (now one scenario more).
Commit message: `Batch 3 F2: a failed Add brings the form back with the text still in the box`

## Chunk 2 of 5: Retry sends exactly the text in the box

Covers: user story 3; finding 4.2 #9.

1. In `app/test/e2e/add.js`, extend the `failKeepsForm` scenario: after the box is visible, change the text (`win.fill('[data-testid="add-text-input"]', ...)` — a different note), switch the fake AI to a working answer (200, one valid proposal), then click the error's Retry (`[data-action="add-retry"]`), wait for `[data-testid="proposal"]`, and assert the fake AI's recorded request body contains the edited note text and NOT the original.
2. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- add`. Expect: green already — the chunk-1 form re-render binds the box to `state.text` (input listener, `add.mjs:322-324`) and Retry's `startSession()` sends exactly `state.text` (`add.mjs:440`). This test pins behavior; it guards future drift, nothing to fix.

Proof it's real: temporarily make Retry send a frozen copy captured before the session started (add `state.frozenText` in `startSession` and send that) — the scenario must turn red on "contains the edited text". Then undo.
Done when: `xvfb-run --auto-servernum npm --prefix app run e2e -- add` ends green and prints `form kept OK: ... Retry sent the edited text` (the scenario's own output line) plus the final `e2e add OK` line.
Commit message: `Batch 3 F2: Retry sends exactly what is in the box`

## Chunk 3 of 5: the pure grouping core (one row per error code)

Covers: user stories 6, 7, 8 (the counting/grouping logic under them); finding 4.2 #8 (logic half).

1. Create `app/test/home-failures.test.js` (NEW, node:test, same conventions as `app/test/plain-sentences.test.js`): it imports `groupFailuresByCode` from `../shared/home-failures.mjs`, and pins: grouping by `code` keeps first-seen order; the count equals the number of failed blocks per code (a 3-item input of one code -> one group, count 3; a 2+1 input of two codes -> two groups, counts 2 and 1); each group carries the plain words from `sentenceFor(code)` (`app/shared/plain-sentences.mjs`) so two different codes get visibly different titles; a null/shapeless error still lands in a group, never blank (fall back to `sentenceFor(null)` words); and the pins also fix the count sentence's exact wording — the wording is decided inside `home-failures.mjs` and pinned ONLY here, because the e2e checks the number and the codes on screen and never the wording (decisions I7 and I10: the sentence's own unit test may check wording, every other test checks codes only).
2. Run `npm --prefix app test -- home-failures`. Expect: 1 failed, cannot find module `../shared/home-failures.mjs`.
3. Create `app/shared/home-failures.mjs` (NEW, pure module per T1 — strings in, objects out, no DOM, no I/O; same header style as `app/shared/capture-words.mjs`) exporting `groupFailuresByCode(failures)`, where `failures` is a list of `{ what, error }` (`what` names the block, `error` the plain info shape `{code, name, where, detail}`) and the result is one object per distinct code: `{ code, count, blocks, words }` in first-seen code order. In the same commit, add one `PROJECT_MAP.md` line per NEW file (this module and its test file, from step 1) in the Interface App section, each saying it serves Batch 3's F4 grouping (the house rule: every file has a map line).

Proof it's real: in the unit test, change the expected count 3 to 2 on the one-code case — the test must go red on the count assertion. Then undo (the red must be the assertion, not a crash).
Done when: `npm --prefix app test -- home-failures` prints `pass 6` (or more, never fewer) with 0 fail, and `npm --prefix app test` is green (the suite's own pass count; nothing else moved).
Commit message: `Batch 3 F4: the home failure grouping core (pure)`

## Chunk 4 of 5: the e2e that catches one notice, not three cards (F4)

Covers: user stories 6, 7, 8, 9 (the Home half of story 9); findings 4.2 #8 and 4.9 #11's sister on-screen half (the "replaces the cards" decision B3-1).

1. In `app/test/fake-ember.js`, in `runAppMode` (mode `app`): support a NEW env `FAKE_APP_FAIL` (e2e-only, same style as `FAKE_ERROR_DETAIL`) — a comma list of `command:CODE` pairs (e.g. `list-items:QUERY-003,history:QUERY-005`); when the command name matches a pair, emit the house error line with that code and exit 1. Everything else in `runAppMode` stays.
2. In `app/test/e2e/helpers/shell.js`, extend `launchShell` with an optional `extraEnv` argument (plain object, merged into `env` after the defaults) — so a scenario can set `FAKE_APP_FAIL` and `FAKE_SPAWN_LOG` (the spawn log the fake already writes, `fake-ember.js:33-37`) without touching the other callers.
3. In `app/test/e2e/first-run-home-lookup.js`, rewrite the Home error part of `emptyAndError` (today `first-run-home-lookup.js:413-437`, which only waits for `>= 2` `[data-testid="state-error"]`): (a) round (a) launches mode `error` with `FAKE_SPAWN_LOG` set — all three engine-fed blocks (attention, counts, ledger, per `home.mjs`) fail with one code (QUERY-003); assert exactly ONE notice element `[data-testid="home-failure-notice"]` (NEW testid), its text contains the code `QUERY-003` and the count as the number 3 (a `/\b3\b/`-style match on that notice's text — number + code only, never the "N blocks" wording, per decision I7), the pane has ZERO `[data-testid="state-error"]` cards inside the three block hosts (`attention`, `home-counts`, `home-ledger`), and Details reveals QUERY-003; then click the notice's Try again and read the spawn log: the NEW spawn lines must include every command of a full Home load (`list-items`, `current-state`, `maintain`, `history`) — every block reloaded, not one block (decision B3-1). (b) Round (b) is a second launch with `FAKE_APP_FAIL=list-items:QUERY-003,history:QUERY-005` (list-items fails -> attention AND counts, one code; history fails -> ledger): assert exactly TWO notices — the notice whose text names QUERY-003 matches the number 2 (`/\b2\b/` on that one notice) and the notice naming QUERY-005 matches the number 1 — number + code only, never wording (decision I7); and Details reveals QUERY-003 on one and QUERY-005 on the other. Keep the a11y scan (`assertCleanScan`) on the notice state. Keep the existing empty-KB part of the scenario unchanged.

Proof it's real: the step-3 run IS the red proof — Detail: after step 3, run the e2e BEFORE the chunk-5 screen change: Home still renders three per-block cards (`home.mjs` calls `showErrorBlock` per block) and no notice, so both rounds must fail (the notice count 0 != 1, and the card count 3 != 0).
Done when: `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run` FAILS exactly in the rewritten scenario with the notice-count line printed (e.g. `one notice expected, saw 0`), proving the test can fail.
Commit message: `Batch 3 F4: e2e pins one notice per error code on Home (B3-1)`

## Chunk 5 of 5: the banner component takes a testid; Home renders the grouped notices

Covers: user stories 6, 7, 8 (on screen); findings 4.2 #8 and 4.9 #11's Home half; decision I6 (the banner component gets a testid option and the Home failure notice uses it — an optional field, so existing callers and tests are untouched, per the constitution's additive rule D5/I10).

1. In `app/renderer/components/banner.mjs`: give `bannerHtml` an optional `testid` prop that defaults to `"banner"` — the hard-coded `data-testid="banner"` becomes the default value of the new prop (decision I6; optional field per the constitution D5/I10, additive). Nothing else in the signature changes. Every existing caller keeps `data-testid="banner"`, so the banner pins in `app/test/design-components.test.js` (`:95-99`) and the e2e selectors `[data-testid="banner"]` (`app/test/e2e/menus.js:503`, `app/test/e2e/design.js:67`) must stay green unchanged.
2. In `app/renderer/screens/home.mjs`: stop calling `showErrorBlock`/`dataOrNull` from the three engine-fed loaders (`loadAttention` — including its sweep-preview failure branch at `home.mjs:113-116` — `loadCounts`, `loadLedger`); on failure each loader records `{ what, error }` into a screen-level list, clears its own block host, and calls `renderFailures()`; `renderFailures` fills a NEW host `<div data-testid="home-failures">` (add it to the frame HTML, below `home-notice`) with one banner per group from `groupFailuresByCode` — each banner is built with `bannerHtml({ ..., testid: 'home-failure-notice', actionLabel: 'Try again', action: 'home-failures-retry' })` (the prop from step 1), the banner words carry the count sentence and the code's plain words, and the banner's one action is wired to `load()` — the same path a visit runs, every block (`home.mjs:31-33,59`). Failed blocks show nothing of their own (B3-1: the notice replaces the cards). The knowledge-base gate error (`APP-006`, `home.mjs:79-84`) and the no-key banner keep their current shapes — they are not engine-fed blocks.
3. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run`. Expect green.

Proof it's real: in `renderFailures`, temporarily render one banner for `groups[0]` only (drop the loop / the `join('')`) — round (b) of the e2e must turn red expecting exactly two notices. Then undo.
Done when: `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run` ends green and prints the scenario's own lines `home grouping OK (a): one notice, count 3, no cards, Try again reloads every block` and `home grouping OK (b): two notices, counts 2 and 1` (the OK lines carry the numbers and codes only, like the assertions — decision I7).
Commit message: `Batch 3 F4: Home shows one notice per error code instead of per-block cards`

## Final check

- `npm --prefix app test` — green (all suite files, no new failures).
- `xvfb-run --auto-servernum npm --prefix app run e2e -- add first-run` — both touched e2e files green.
- `xvfb-run --auto-servernum npm --prefix app run e2e` — every e2e file green (the runner runs files in name order; nothing else should break).
- `.venv/bin/pytest tests/ -q` — green (Python untouched, run as proof).
- The batch's "Done when" from `archive/Plan.md` Batch 3, each with its command:
  - "an e2e test fails Add on purpose and finds the form with the original text" -> `xvfb-run --auto-servernum npm --prefix app run e2e -- add` prints `form kept OK: ... text still in the box` (Chunk 1).
  - "fails three blocks with one code and finds exactly one notice" -> `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run` prints `home grouping OK (a): one notice, count 3, ...` (Chunk 5 round (a)).

## Unknowns

- The starting branch. D-29 (`archive/Plan.md`) now fixes the rule — each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` — so the branch names and merge target are settled. Still open in practice: `git branch` today shows only `main`, `ember-interface`, `bridge/b2`, `lane/*`, `spike/app-stack` — no batch branch exists yet, so confirm with the founder that Batches 0-2 landed on `ember-interface` (D-29 style) before starting.
- Story 5's coverage: decision 1.2 of the check report is still open on the Batch 2 side ("which pane runs Batch 2's seam-3 crash-button e2e"). Per N5, Batch 3 builds and tests nothing for it; if Batch 2's e2e ends up NOT running on the Add pane, story 5 has no coverage at all — a Batch 2 question, flagged here so it is not lost.
- The output line `pass 6` in Chunk 3's Done when counts the pins listed in its step 1; if the implementer writes more cases, the number goes up — the real check is `0 fail`.

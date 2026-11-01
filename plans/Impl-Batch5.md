# Batch 5 implementation plan: bridge and screen lifetime

Spec: docs/Spec-Batch5.md
Branch: `batch-5`, cut from where batch-4 merged into `ember-interface`, per D-29 (archive/Plan.md: "Each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its 'Done when' passes"). Today all work sits on `ember-interface` and batch-4 has not merged, so batch-5 starts from the `ember-interface` tip.
Needs first: Batches 0, 2 and 3 must be merged first (archive/spec-check-batch5.md §4 "Dependencies": Batch 2's crash boundary D-06/EMBER-000, Batch 3's one-notice-per-code grouping, Batch 0's key-stripped env and temp-config harness and 5000 ms timings). In Plan.md's order Batch 5 comes after Batches 0-4 anyway.
Size: 61 steps, about 45 hours.

## Before you start

- Commands the batch touches, exactly as typed (run from the repo root):
  - `.venv/bin/pytest tests/bridge -q` (all engine bridge tests; `.venv/bin/pytest` exists, verified by `ls .venv/bin/pytest`)
  - `npm test --prefix app` (all app unit tests; one file: `npm test --prefix app -- bridge-client`)
  - `xvfb-run --auto-servernum npm --prefix app run e2e -- smoke` (one e2e file by name word; all: `npm --prefix app run e2e`)
  - `xvfb-run --auto-servernum npm run check:launch --prefix app` (the launch check the CI fixes build on)
- Safety rules: no AI keys — prefix engine commands with `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY`; never touch the real DB or `key.enc` — every test uses a temp knowledge base made by the existing helpers; e2e and launch checks only under `xvfb-run`; all throwaway files under `/tmp/opencode/batch5/`; no new npm or pip packages (N12 explicitly requires none).

## Chunk 1 of 21: CI runs e2e on a virtual screen

Covers: story 34; findings 4.2 #6 ("npm run e2e never runs in CI") and the chrome-sandbox blocker (Plan.md Batch 5, first two bullets; D-13).

1. Edit `.github/workflows/test.yml`: in the `app-launch-check` job, add one step just before "Launch check (story 109) — Linux needs a virtual display": `sudo chown root:root app/node_modules/electron/dist/chrome-sandbox && sudo chmod 4755 app/node_modules/electron/dist/chrome-sandbox`.
2. Same file: add a new Linux job `app-e2e`: checkout, setup-python + venv install, `npm ci --prefix app`, the same chrome-sandbox step, then `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY XDG_CONFIG_HOME=$(mktemp -d) xvfb-run --auto-servernum npm run e2e --prefix app` (the fake engine and temp config come from the existing `app/test/e2e/helpers/shell.js`).
3. Verify the harness locally before pushing: `xvfb-run --auto-servernum npm --prefix app run e2e -- smoke`. Expect exit 0.

Proof it's real: on CI, `app-launch-check (ubuntu-latest)` is red today [Fact: `gh run view 41292204414`, checked in archive/spec-check-batch5.md]. Revert step 1 on a throwaway branch, push, and the same job fails again on `chrome-sandbox`; put it back and it goes green. Undo the revert (keep it on a scratch branch only).
Done when: after push, `gh run list --branch batch-5` shows `app-e2e` and `app-launch-check (ubuntu-latest)` green; step 3's local run exits 0.
Commit message: `Batch 5 CI: fix chrome-sandbox in CI; run the e2e suite on a virtual screen`

## Chunk 2 of 21: the test-hygiene gate (N12)

Covers: story 35; finding 4.2 #24 (no guard against an un-awaited `t.test` — silently cancelled on node 22+).

1. Demonstrate the hole: create `app/test/zz-floating-demo.test.js` (NEW, throwaway — deleted in step 3) containing one `t.test('floating', async () => { await new Promise(() => {}); })` subtest that is NOT awaited. Run `npm test --prefix app -- zz-floating-demo`. Expect: it today prints pass (or the suite ends) without waiting for the subtest — the hole the report names.
2. Add the gate to `app/test/run.js` (existing thin wrapper): before spawning `node --test`, run the small check that fails a test file whose async subtests are not awaited/returned; a failing file prints one named line and stops the run. No new dependency (N12, check-report decision 4, option B).
3. Run `npm test --prefix app -- zz-floating-demo`. Expect: the gate refuses the file. Then delete `app/test/zz-floating-demo.test.js` (throwaway demo file; nothing else is touched — Done when: `ls app/test/zz-floating-demo.test.js` fails and `git status` shows no stray files). Run `npm test --prefix app`: green, same pass count as before the demo was planted.

Proof it's real: the planted zz-floating-demo file must flip from "silently passes" (step 1) to "refused by the gate" (step 3); removing the gate check would let it pass again.
Done when: the full `npm test --prefix app` is green after the demo file is deleted.
Commit message: `Batch 5: the app test runner refuses un-awaited subtests (N12)`

## Chunk 3 of 21: whole streamed lines in both JS readers

Covers: stories 18, 19, 30; findings 4.4 #1 (both files), 4.4 #11.

1. Extend the existing `app/test/fake-ember.js` with two NEW env modes and add the tests. `FAKE_STDERR_SPLIT=1`: write the house error line in two piecewise writes; `FAKE_STDOUT_SPLIT=1`: write a JSON line split across two writes with a multi-byte character cut at the boundary, then a final line WITHOUT `\n`. Add to `app/test/bridge-client.test.js`: "a house error line split across two writes parses to the engine's code" and "a stderr line split mid-multi-byte character is intact" and "the final unterminated stdout line is read". Run `npm test --prefix app -- bridge-client`. Expect: the three new tests fail (4.4 #1/#11 reproduce).
2. Fix `app/main/bridge-client.js`: `spawnOnce` and `runConfirmSession` decode stdout and stderr with a streaming `TextDecoder` plus a carry buffer; lines commit only on `\n`; the final partial line flushes on child close (spec Bridge bullet: "stdout and stderr are decoded as streams… a final unterminated line is read").
3. Extend `app/test/db-check-runner.test.js` with "a stderr house line split across two reads parses", run it red, then fix `app/main/db-check-runner.js` (`:117-121`, the per-chunk split) with the same carry-buffer reader. Run `npm test --prefix app -- bridge-client` and `npm test --prefix app -- db-check-runner`. Expect: all green.

Proof it's real: revert step 2's carry buffer to the per-chunk split → the three step-1 tests fail again; restore. Same for step 3 against db-check-runner.
Done when: both filtered test runs end green with the new cases listed in the output.
Commit message: `Batch 5: the bridge reads stderr and stdout in whole streamed lines (4.4 #1, #11)`

## Chunk 4 of 21: the app never trusts the backup's reported path

Covers: stories 31, 32; findings 4.4 #14. (4.4 #13 / 4.10 #14 — db-check exit 1 carries a valid report — is already true of `app/main/db-check-runner.js:144-165` and pinned by its test suite; chunk 3 keeps that suite green and no code change is needed. Story 31's proof is the existing `app/test/db-check-runner.test.js` "exit 1 DRIFT/UNREADABLE come back as report DATA" cases.)

1. Add to `app/test/keep-safe-ipc.test.js` (existing file): "a backup summary whose path differs from the chosen target is refused". Run `npm test --prefix app -- keep-safe-ipc`. Expect: fail — `app/main/ipc.js` `ember:backupTo` (`:376-385`) checks only that `summary.path` is a string.
2. Fix `app/main/ipc.js` `ember:backupTo`: compare the reported `summary.path` against the chosen `targetPath` (resolved, as the backup report names the absolute copy) and return `APP-002` "the backup reported a different path than the chosen target" when they differ. Run `npm test --prefix app -- keep-safe-ipc` and `npm test --prefix app -- keep-safe-contract` (real temp KBs prove the honest path still passes).

Proof it's real: delete the target check from ipc.js → the new test fails with the trusted wrong path shown; restore.
Done when: `npm test --prefix app` fully green.
Commit message: `Batch 5: the app verifies the backup report's path (4.4 #14)`

## Chunk 5 of 21: stdin survives, sessions cap their bytes

Covers: stories 21 (cap side), 33; findings 4.4 #2, 4.4 #5, 4.2 #14.

1. Extend `app/test/fake-ember.js` with `FAKE_FLOOD=1` (streams ~40 MB to stdout in drain-aware chunks, then exits — the db-check F8 test at `app/test/db-check-runner.test.js:157-173` shows the pattern; avoid its `process.exit` mistake, 4.2 #2). Add to `app/test/bridge-client.test.js`: "confirm-session stdout beyond the 32 MB cap settles with a named error" (4.2 #14, story 33), "writing an answer to a session whose stdin closed is an error event, not a crash" (4.4 #2), and "one-shot output beyond the cap returns the cap error" (the `MAX_OUTPUT_BYTES` branch at `bridge-client.js:191` was untested). Run `npm test --prefix app -- bridge-client`. Expect: the new tests fail.
2. Fix `app/main/bridge-client.js` `runConfirmSession`: track session output bytes against `MAX_OUTPUT_BYTES` and end the session with a cap error; add `child.stdin.on('error', ...)` that emits the named error and finishes the session; the idle timer resets only on COMPLETE lines (chunk 3's line reader feeds `bumpIdle`), so a chatty child still times out on idle (4.4 #5).
3. Run `npm test --prefix app -- bridge-client` and `npm test --prefix app -- db-check-runner`. Expect: green.

Proof it's real: remove the `child.stdin.on('error')` handler after step 2 → the EPIPE test ends the node process (the report's reproduced exit-7 class); restore.
Done when: `npm test --prefix app -- bridge-client` green including the cap and EPIPE cases.
Commit message: `Batch 5: confirm sessions cap output and survive a broken stdin (4.4 #2, #5; 4.2 #14)`

## Chunk 6 of 21: timeouts are hard bounds

Covers: stories 20, 21; finding 4.4 #6 (grandchild keeps pipes open; an engine that exits early must not hang the call).

1. Extend `app/test/fake-ember.js` with `FAKE_GRANDCHILD=1` (spawns `node -e "setInterval(()=>{},1000)"` inheriting the pipes, then exits) and `FAKE_EXIT_EARLY=1` (exits with no output). Add to `app/test/bridge-client.test.js`: "with a short timeout, a session whose grandchild holds the pipes settles within a short bound after the kill, not when the grandchild dies" (story 21), and "an engine that exits early settles the session, it does not hang" (story 20). Run: red.
2. Fix `app/main/bridge-client.js`: spawn both one-shot and session children with `detached: true`; on timeout kill the whole process group (`process.kill(-child.pid, 'SIGTERM')`, then SIGKILL); `finish()` settles on process `exit` with a short hard bound (a few seconds) for pipe close, per the spec bullet "the engine is started in its own process group… a short hard bound for pipe close".
3. Run `npm test --prefix app -- bridge-client`. Expect: green. Also run `xvfb-run --auto-servernum npm --prefix app run e2e -- smoke` to prove real boot paths still spawn fine.

Proof it's real: delete the group kill so the code waits on `'close'` → the grandchild test fails with a settle time near the fake grandchild's lifetime; restore.
Done when: `npm test --prefix app -- bridge-client` green.
Commit message: `Batch 5: engine children run in their own process group; timeouts kill it (4.4 #6)`

## Chunk 7 of 21: one settle rule for engines that die unexpectedly (N3)

Covers: stories 22, 29; findings 4.4 #9, 4.4 #10.

1. Add to `app/test/bridge-client.test.js` (session cases): "a stop() the app asked for settles with NO error" (story 22), "a signal-killed child settles with the new Ember-stopped-unexpectedly code" (4.4 #10, story 22), "an exit with no summary settles with the same code" (story 29). Expect: red — the code does not exist yet.
2. Add the new code to `app/shared/errors.js` after APP-008 (`APP-009`, name `EmberStoppedUnexpectedly` — fixed by decision I9, archive/Plan.md "Decisions from the implementation-plan check (2026-11-01)") and its full entry to `app/shared/plain-sentences.mjs` (the plain-sentences test requires every APP- code to have a full sentence). Implement in `app/main/bridge-client.js` `finish()`: a flag the app's own `stop()` sets; any other kill (signal, timeout group kill, exit with no summary event) emits exactly this one code.
3. Run `npm test --prefix app -- bridge-client`, `npm test --prefix app -- errors`, `npm test --prefix app -- plain-sentences`. Expect: green.

Proof it's real: make `stop()` not set the flag → the "no error on stop" test fails with the new code emitted; restore.
Done when: the three filtered runs are green.
Commit message: `Batch 5: one settle rule and code for engines that end unexpectedly (N3; 4.4 #9, #10)`

## Chunk 8 of 21: one shared event fixture, every field checked

Covers: stories 27, 28; findings 4.4 #7, 4.4 #8.

1. Create `tests/fixtures/bridge/event_schema.json` (NEW — one file both sides read): each event name (`block`, `prompt`, `message`, `summary` as produced by `ember/adapters/json_confirm.py:127-151`) with its required keys and value types per the spec's per-type field schemas. Create `tests/bridge/test_event_schema.py` (NEW): a real `--confirm json` session (the existing `tests/bridge/harness.py` seam) must satisfy every schema entry. Run `.venv/bin/pytest tests/bridge/test_event_schema.py`. Expect: green — the fixture is written FROM the engine's real events; this pins the engine side.
2. Add to `app/test/event-line.test.js`: the test loads the SAME fixture file and asserts `app/shared/parse-event-line.js` requires exactly those fields — `{"event":"summary"}` with no numbers must be refused (4.4 #7's masking case). Run `npm test --prefix app -- event-line`. Expect: red.
3. Implement the per-event field validation in `app/shared/parse-event-line.js` (a missing or wrong field is APP-002 with the field named — spec Bridge bullet). Run `npm test --prefix app -- event-line` and `npm test --prefix app -- add-flow` (the confirm-view folds validated events). Expect: green.

Proof it's real: drop one required key from a fixture entry → the engine test fails against real events; restore. Remove the field check from parse-event-line.js → the app test fails; restore.
Done when: `.venv/bin/pytest tests/bridge/test_event_schema.py` and `npm test --prefix app -- event-line` both green.
Commit message: `Batch 5: one shared event fixture; every event's fields are checked (4.4 #7, #8)`

## Chunk 9 of 21: the engine caps its stdin lines (N13)

Covers: story 33's engine half; finding 4.4 #12; decision N13.

1. Add to `tests/bridge/test_json_confirm.py` (existing): an oversized answer line (~10 MB) on stdin comes back as the BRIDGE-001/user-abort path without unbounded memory; an undecodable byte sequence on stdin raises the same house path, never a raw `UnicodeDecodeError`. Run `.venv/bin/pytest tests/bridge/test_json_confirm.py`. Expect: the new tests fail.
2. Fix `ember/adapters/json_confirm.py` `_read_answer_line` (`:181-189`): read stdin with a bounded reader (cap the line length; over-long or undecodable input maps to `BRIDGE-001 AnswerLineInvalid`, which the existing re-ask/abort flow already handles).
3. Run `.venv/bin/pytest tests/bridge/test_json_confirm.py tests/bridge/test_confirm_json_cli.py`. Expect: green, and the terminal confirm behavior unchanged.

Proof it's real: revert the bound to the plain `readline()` → the oversized-line test hangs or balloons; restore.
Done when: the two pytest runs are green.
Commit message: `Batch 5: the engine caps its confirm stdin lines (N13; 4.4 #12)`

## Chunk 10 of 21: one engine call returns all four Home counts (N11)

Covers: story 17 (engine half); findings 4.9 #25 (the 8-processes half); decisions N11, check-report decision 2, option A.

1. Create `tests/bridge/test_list_items_counts.py` (NEW, pytest on a real temp knowledge base seeded the way `tests/bridge/harness.py` temp KBs are made): `ember list-items --db <temp> --counts` prints one document whose summary carries the four counts (`active`, `challenged`, `closed`, `total`) and they equal the per-status `list-items` CLI totals. Run `.venv/bin/pytest tests/bridge/test_list_items_counts.py`. Expect: red — no such flag exists [Fact: `ember/cli.py:1403` has only --status/--type/--limit/--offset/--db].
2. Implement: a pure per-status counter in `ember/query/list_items.py`, the `--counts` flag in the `list-items` command in `ember/cli.py`, and the new summary key recorded in the `docs/commands.md` row for `list-items` (this file edit is an overwrite of docs only, no data touched — Done when: `git diff docs/commands.md` shows only that row's flags/summary table extended).
3. Run `.venv/bin/pytest tests/bridge/test_list_items_counts.py tests/test_docs_in_sync.py tests/bridge/test_contract_table.py`. Expect: green.

Proof it's real: revert the flag in cli.py → the new pytest fails with "no such option"; restore.
Done when: the three pytest runs are green.
Commit message: `Batch 5: list-items --counts answers the four Home counts in one call (N11)`

## Chunk 11 of 21: Home reads counts in one call

Covers: story 17 (app half); findings 4.9 #25 (the escaping half: "engine counts into HTML without esc()").

1. Extend the fake ember's `app` mode in `app/test/fake-ember.js` to serve `list-items --counts` from the `FAKE_FIXTURE`, and extend `app/test/home-contract.test.js` (real temp KB): the counts document equals the per-status CLI totals. Run `npm test --prefix app -- home-contract`. Expect: red (the app has no counts call yet).
2. Fix the chain: `app/main/command-args.js` (listItems builder gains the counts-only form), `app/main/ipc.js` `ember:listItems`, `app/renderer/screens/home.mjs` `loadCounts` (`:141-149` today makes 4 calls + an attention call) — one call, and every number rendered through `esc()`.
3. Run `npm test --prefix app -- home-contract` and `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run home lookup`. Expect: green (the e2e drives counts through the fake engine).

Proof it's real: restore the four `listItems` calls in home.mjs → the contract test's one-call pin fails; restore the single call.
Done when: both runs green.
Commit message: `Batch 5: Home gets its counts in one call and escapes them (N11; 4.9 #25)`

## Chunk 12 of 21: only the current screen's token can paint (F5)

Covers: stories 1, 2; findings 4.9 #1, 4.9 #2, 4.2 #7.

1. Create `app/test/e2e/screen-lifetime.js` (NEW; uses the existing `app/test/e2e/helpers/shell.js` `launchShell` and fake engine): case A — open Keep safe (the health check auto-runs), navigate to Settings within 200 ms; after the health check returns, assert Settings is still on screen and text typed into a Settings field is intact (the Plan.md "Done when" case; story 2's "typed key text" uses the AI-connection pane's key field).
2. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime`. Expect: case A fails — Keep safe's late repaint overwrites Settings (F5 reproduced at `app/renderer/screens/app.mjs:57-61`).
3. Fix `app/renderer/screens/app.mjs`: `navigate()` bumps a render token; `renderFrame()` refuses to paint a stale token; screens drop every in-flight result whose token is stale (extends the per-screen pattern at `app/renderer/screens/settings.mjs:159` to the shell, closing 4.2 #7). Run `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime` and `npm test --prefix app`. Expect: green.

Proof it's real: after step 3, remove the token check from renderFrame → case A fails again; restore.
Done when: the e2e case A passes ("Settings is still on screen after the health check returns") — the first half of Plan.md Batch 5's "Done when".
Commit message: `Batch 5: a render token guards the shared pane (F5; 4.9 #1, #2)`

## Chunk 13 of 21: dispose on navigation; keys scoped to the live screen

Covers: stories 3, 4; findings 4.9 #3, 4.9 #4, 4.9 #5, 4.9 #17 (sweep keys act from any pane).

1. Extend `app/test/e2e/screen-lifetime.js`: case B — visit Add three times, press y → only the CURRENT session reacts; case C — leave Clean up mid-sweep → no further sweep events arrive after leaving (spec seam 1, story 4). Run `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime`. Expect: B and C fail (listeners pile at `add.mjs:530-551`, `link.mjs`, `cleanup.mjs:489`).
2. Fix the shell contract: `ctx.navigate` calls the current screen's dispose() (navigation is the single entry `app/renderer/screens/app.mjs:62`); the screens `add.mjs`, `link.mjs`, `cleanup.mjs` return a dispose that removes their keydown listeners and DOM timer work; cleanup's dispose stops the running sweep session (story 4); screens attach document-level keys through the shell's active-screen scope so a hidden screen's keys are dead (stories 3, 4).
3. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime`, `xvfb-run --auto-servernum npm --prefix app run e2e -- cleanup` (a sweep still works when STAYING on the screen), and `npm test --prefix app`. Expect: all green.

Proof it's real: make dispose() a no-op → cases B and C fail again; restore.
Done when: the three runs are green.
Commit message: `Batch 5: leaving a screen disposes its listeners and stops its sweep (4.9 #3, #4, #5, #17)`

## Chunk 14 of 21: small screen-lifetime fixes

Covers: stories 10, 11, 12; findings 4.9 #10, 4.9 #12, 4.9 #13.

1. Fix `app/renderer/screens/fix-close.mjs` `applyUndoRedo` (`:209-218`): set the busy flag BEFORE the `await refreshUndoBar()` so two fast Ctrl+Z presses do not both pass (story 11, 4.9 #12). Verify: `npm test --prefix app` and `xvfb-run --auto-servernum npm --prefix app run e2e -- fix-close-undo` (existing e2e exercises rapid undo; prior art — no new test needed).
2. Fix the boot-snapshot reads: `app/renderer/screens/settings.mjs` (`:221`) and `app/renderer/screens/keepsafe.mjs` read the CURRENT knowledge-base path (a fresh `window.ember.kbStatus()`) each render instead of `ctx.state.effectiveKbPath` (story 10, 4.9 #10). Verify: `xvfb-run --auto-servernum npm --prefix app run e2e -- settings` and `-- keep-safe`.
3. Fix `app/renderer/screens/keepsafe.mjs` `wire()` (`:266-270`, `:287`): replace the eight `.catch(() => {})` wirings with the error shown in the action's own block, so "Writing the backup copy…" can never hang forever (story 12, 4.9 #13). Verify: `xvfb-run --auto-servernum npm --prefix app run e2e -- keep-safe`.

Proof it's real: for each step, revert the one-line fix and the named existing e2e still cannot catch the delay/race — which is why each step reruns its e2e; the batch's regression guard is the suite staying green. (These three are behavior corrections no cheap unit test can pin; marked accordingly.)
Done when: `npm test --prefix app` and the three e2e runs are green.
Commit message: `Batch 5: undo busy first, live knowledge-base paths, honest Keep safe errors (4.9 #10, #12, #13)`

## Chunk 15 of 21: no window navigation; KB values escaped

Covers: stories 23, 24; findings 4.9 #15, 4.9 #16.

1. Extend `app/test/preload-allowlist.test.js` (the existing static pin on main.js's window build): add assertions that main.js registers `will-navigate` (denied) and `setWindowOpenHandler` (denied). Run `npm test --prefix app -- preload-allowlist`. Expect: red.
2. Fix `app/main/main.js` `createWindow` (`:60-94`): deny navigation (`will-navigate` → `event.preventDefault()`) and deny new windows (`setWindowOpenHandler` → deny), per spec "Window: deny navigation and new windows" (story 24; D-24's safety half).
3. Fix `app/renderer/screens/fix-close.mjs`: route `sideText` old/new values through `esc()` (`:445,455-458`; story 23, 4.9 #15). Run `npm test --prefix app` and `xvfb-run --auto-servernum npm --prefix app run e2e -- fix-close-undo`. Expect: green.

Proof it's real: remove the deny handlers → the static pin fails; remove `esc()` → no test pins prose, so this stays a code review item with the e2e guarding no regressions (the report's planted-XSS proof is Manual check: in Fix and close, edit an item whose rationale contains `<b>hi</b>` and see literal text, not bold).
Done when: `npm test --prefix app -- preload-allowlist` green and the fix-close e2e green.
Commit message: `Batch 5: the window never navigates; knowledge-base values escaped (4.9 #15, #16)`

## Chunk 16 of 21: Ctrl+Z inside a text box edits text

Covers: story 13; finding 4.9 #14.

1. Add to `app/test/menu-template.test.js`: when a text field has focus, the Edit menu's Undo/Redo render as Electron role items (`role: 'undo'` / `'redo'`), never as Ember job actions (story 13 — app-menu.js `:40` already keeps role items). Run `npm test --prefix app -- menu-template`. Expect: red.
2. Fix `app/main/app-menu.js` / `app/shared/menu-template.mjs` context: the Undo/Redo entries become role items while a text field holds focus (the shell knows the focus state; `app/renderer/screens/app.mjs:130-135` stops silently swallowing the request). Run `npm test --prefix app -- menu-template` and `xvfb-run --auto-servernum npm --prefix app run e2e -- menus` and `-- fix-close-undo` (Ember's own undo still lands on the Fix and close bar when no text field has focus).

Proof it's real: revert one entry to a plain action id → the new template test fails.
Done when: the three runs are green.
Commit message: `Batch 5: Ctrl+Z in a text field means text undo (4.9 #14)`

## Chunk 17 of 21: EMBER_APP_COMMAND is a JSON array

Covers: stories 25, 26; findings 4.9 #18.

1. Add to `app/test/ember-command.test.js`: `EMBER_APP_COMMAND` set to a JSON array (`["/path/with space/ember"]`) resolves to that exact argv, and a space-separated value is still accepted (backward compatibility). Run `npm test --prefix app -- ember-command`. Expect: red.
2. Fix `app/main/ember-command.js` `resolveEmberCommand` (`:88-95`): parse a value starting with `[` as a JSON array; otherwise keep the whitespace split. argv spawn was already shell-free (bridge holds: "argv spawn, never a shell"), so a spaced path now survives end to end (story 26).
3. Update the writers to the new shape: `app/test/e2e/helpers/shell.js` (`:41`) and `app/test/launch-check.js` now write `EMBER_APP_COMMAND` as a JSON array. Run `npm test --prefix app -- ember-command`, `xvfb-run --auto-servernum npm --prefix app run e2e -- smoke`, and `xvfb-run --auto-servernum npm run check:launch --prefix app`. Expect: green.

Proof it's real: feed `"bad json"` as the array value → resolution must fall back to the split (test asserts no crash); remove the JSON branch → the new test fails.
Done when: the three runs are green.
Commit message: `Batch 5: EMBER_APP_COMMAND is a JSON array; paths with spaces work (4.9 #18)`

## Chunk 18 of 21: no raw errors, every boot notice

Covers: stories 14, 25; findings 4.9 #19, 4.9 #20.

1. Create `app/test/ipc-catchall.test.js` (NEW): a throwing IPC handler returns `{ok:false, error:{code:'APP-002', ...}}` whose detail contains a generic sentence and NO part of the thrown message (register a handler with `registerIpcHandlers`'s fakes, make it throw a message containing `/home secrets/`). Run `npm test --prefix app -- ipc-catchall`. Expect: red — `app/main/ipc.js:657-663` puts `err.message` in the detail.
2. Fix `app/main/ipc.js` catch-all: return the code and a generic message; the raw error goes to `process.stderr` with the code (one line, I20), never to the renderer (story 25, 4.9 #19). Run `npm test --prefix app -- ipc-catchall` and `npm test --prefix app -- keep-safe-ipc` (handlers still behave).
3. Fix `app/renderer/screens/app.mjs` `showNotices` (`:293-310`): render one grouped notice per code — every boot notice shows (story 14, 4.9 #20; it reuses Batch 3's grouping where it exists; the loop structure works regardless). Run `npm test --prefix app` and `xvfb-run --auto-servernum npm --prefix app run e2e -- first-run` (boot banners render).

Proof it's real: restore the `err.message` detail → ipc-catchall fails with the raw path visible; restore `notices[0]`-only rendering → the boot-notice case in the e2e output shows one banner dropped. Undo.
Done when: `npm test --prefix app` green; the e2e runs green.
Commit message: `Batch 5: the IPC edge leaks no paths; every boot notice shows (4.9 #19, #20)`

## Chunk 19 of 21: closing the window keeps Ember in the tray (D-24)

Covers: stories 5, 6, 7, 8; findings 4.9 #6, 4.9 #7, 4.9 #8 (the registration part is chunk 21; here the second-launch part).

1. Extend `app/test/e2e/screen-lifetime.js`: case D — close the main window → the app process stays alive and "Open Ember" (via the preload route, story 6) shows the window again; case E — launch a second instance → the FIRST window is focused and there is still one main process (stories 5, 7, 8). This is the second half of Plan.md's "Done when". Run: red.
2. Fix `app/main/main.js`: `app.requestSingleInstanceLock()` at boot — a second instance exits after the first one gets `second-instance` and focuses its window (story 8, 4.9 #7); the main window's `close` is intercepted (visible: hide to the tray per D-24; story 5), leaving the process alive; `window-all-closed` keeps quitting ONLY when a real quit is in progress (the popup hides, never destroys — `app/main/popup.js` — so window-all-closed stays the app-lifetime edge, 4.9 #6).
3. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime`, `xvfb-run --auto-servernum npm --prefix app run e2e -- popup` (parking rules interplay), and `xvfb-run --auto-servernum npm run check:launch --prefix app` (it calls `app.exit` directly, unaffected). Expect: green.

Proof it's real: remove `requestSingleInstanceLock` → case E starts a second window and fails; restore the plain `close` behavior → case D fails with a dead process. Undo.
Done when: case D and E pass ("closing the window keeps the process; a second launch focuses the first window").
Manual check (not covered by e2e — tray menus do not work under xvfb): on the real desktop, close the window, use the tray's Open Ember, then Quit — the process must end.
Commit message: `Batch 5: Ember lives in the tray, one instance only (D-24; 4.9 #6, #7)`

## Chunk 20 of 21: the quick popup polls only while visible

Covers: stories 15, 16; finding 4.9 #24.

1. Fix `app/renderer/screens/quick-popup.mjs` (`:162-175`): the setup-needed button calls `openMain('setup')` instead of `openMain('ember')` (story 16, the "wrong pane id" half of 4.9 #24).
2. Fix the same file's 300 ms stopped-state interval: run it only while `document.visibilityState === 'visible'`, restarted on the existing `visibilitychange` listener (story 15, the "polls while hidden" half of 4.9 #24).
3. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- popup` (the step-11 e2e covers the setup state and the stopped close) and `npm test --prefix app`. Expect: green.

Proof it's real: point the setup button back at `'ember'` → the popup e2e's setup-path case fails; undo.
Done when: both runs green.
Commit message: `Batch 5: the popup polls only while visible; setup opens setup (4.9 #24)`

## Chunk 21 of 21: the capture shortcut works right after first run

Covers: story 9; finding 4.9 #8.

1. Extend `app/test/e2e/popup.js` (existing, has the "no boot registration before first run" case): after first run saves a knowledge base in the main window, pressing the default accelerator opens the quick popup in the SAME session (story 9). Run `xvfb-run --auto-servernum npm --prefix app run e2e -- popup`. Expect: the new case fails — registration happens only at boot (`app/main/main.js:547-548`).
2. Fix `app/main/main.js`: on a settings save (the existing `onSettingsSaved` hook, which also fires at the end of first run), register the accelerator from `bootShortcutFor` when a knowledge-base path is set — the same `shortcutManager` seam, refusing registration still lands in the shipped APP-005 tray fallback.
3. Run `xvfb-run --auto-servernum npm --prefix app run e2e -- popup` and `xvfb-run --auto-servernum npm --prefix app run e2e -- settings` (saves and re-registrations), and `npm test --prefix app -- shortcuts` and `-- settings-screen` (the registration seam stays honest on fakes). Expect: green.

Proof it's real: guard the re-registration to never fire on first run's save → the new popup case fails; undo.
Done when: the popup e2e including the new case is green.
Commit message: `Batch 5: the capture shortcut registers as soon as a knowledge base is set (4.9 #8)`

## Final check

- Full suites, all green, exactly as typed:
  - `.venv/bin/pytest tests -q` (whole engine suite; bridge subset as run per chunk)
  - `npm test --prefix app`
  - `xvfb-run --auto-servernum npm --prefix app run e2e` (every e2e file, including the new `screen-lifetime.js`)
  - `xvfb-run --auto-servernum npm run check:launch --prefix app`
- Plan.md Batch 5 "Done when", each with the command that proves it:
  1. "an e2e test opens Keep safe, switches to Settings within 200 ms, and Settings is still on screen after the health check returns" → `xvfb-run --auto-servernum npm --prefix app run e2e -- screen-lifetime` (case A) passes.
  2. "A second app launch focuses the first window instead of starting a new process" → the same e2e (case E) passes.

## Unknowns

- Fixed by decision I9 (archive/Plan.md, "Decisions from the implementation-plan check (2026-11-01)", accepted by the founder): the new app code is `APP-009 EmberStoppedUnexpectedly`, and the engine counts option is `list-items --counts` with summary keys `active`/`challenged`/`closed`/`total`. These two points are settled; chunks 7 and 10 proceed as written.
- The N12 gate's mechanism is owner's choice (check-report decision 4 says option B is a text-level check that "can miss shapes"); the plan pins only the observable result: the planted demo file must flip from pass to refused.
- Story 2's "typed key text" is verified in e2e by typing into the Settings AI-connection key field; no real key is used (shape rule applies to gibberish fine).
- The screen-lifetime keyboard cases assume the fake engine's session events can pace the e2e (the existing `FAKE_SESSION_SCRIPT` seam exists in `app/test/fake-ember.js`); if the Add screen e2e harness proves easier for case B, reuse `app/test/e2e/add.js` patterns instead.
- 4.9 #14's ratio of role-vs-Ember undo: the plan puts the decision in the menu context (`menu-template.mjs` derivation); the exact API (Electron roles rendered by `app-menu.js:40`) is confirmed, but the focus-state plumbing in a hidden-window popup is not verified.

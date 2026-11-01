# Batch 9 implementation plan: honest tests (contrast numbers, undo-label walk, launch check, e2e hygiene, docs gate)

Spec: docs/Spec-Batch9.md
Branch: batch-9, cut from where batch-8 merged (D-29 in archive/Plan.md: each batch gets its own branch `batch-N`, cut from where the previous batch merged, and merges into `ember-interface` when its "Done when" passes).
Needs first: Batches 0–8, in archive/Plan.md's batch order. Content-wise the spec needs nothing from them (archive/spec-check-batch9.md §4), with one coordination point: the unused `RTI_FAKE_WORKDIR` in `app/test/launch-check.js:67` — if Batch 0 has landed first and now reads it, KEEP the variable (spec decision); if not, remove it.
Size: 14 steps, about 8 hours

## Before you start

- The tests this batch touches, exactly as typed (from the repo root `/home/mo/lab/ember`):
  - `.venv/bin/pytest tests/test_docs_in_sync.py`
  - `npm --prefix app test -- contrast` (runs only `app/test/design-contrast.test.js`)
  - `npm --prefix app test -- undo-labels` (runs only `app/test/undo-labels.test.js`)
  - `xvfb-run --auto-servernum npm --prefix app run test:e2e:design`
  - `xvfb-run --auto-servernum npm --prefix app run test:e2e:09` (keep-safe e2e)
  - `xvfb-run --auto-servernum npm --prefix app run test:e2e:04` (first-run-home-lookup e2e)
  - `xvfb-run --auto-servernum npm --prefix app run check:launch` (the launch check)
  - Whole suites, at the end: `.venv/bin/pytest` and `npm --prefix app test`
- `.venv/bin/pytest` exists (verified with `ls .venv/bin/pytest`).
- `xvfb-run` is installed on this machine (I2: the founder installed xvfb locally), so the e2e and launch-check commands below run as typed, locally.
- Safety rules: no real AI calls (run engine commands with `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY`), never open `~/.config/ember-app/ember.db` or `key.enc`, no GUI launch except under `xvfb-run`, temp files only under `/tmp/opencode/batch9/` (create it if missing).
- This batch touches only test files, `app/test/launch-check.js` (a check script) and prose in `docs/DESIGN.md`. No engine code, no palette colours, no migrations.

## Chunk 1 of 5: the contrast test compares each quoted number (doc corrected first)

Covers: user story 1; report finding 4.2 #15 (N24 + I3 decided in archive/Plan.md: correct the doc's quoted numbers, colours unchanged — five numbers in total, because `4.2:1`'s real ratio is 4.25 and rounds to 4.3).

1. Rewrite the last test in `app/test/design-contrast.test.js` (the block at lines 82–98, currently named `contrast: the DESIGN.md quoted numbers are true (printed, not guessed)`): instead of only asserting each computed ratio is `>= 3`, read `docs/DESIGN.md` (the file lives one directory above `app/` — build the path the same way the test already builds the `tokens.css` path at line 17), find each of the 8 quoted ratios ("12:1", "6.4:1", "5.1:1", "6.8:1", "4.2:1", "7.5:1", "7.1:1", "10.2:1" as the doc quotes them today), and assert the computed ratio, rounded to the precision the doc shows (integer "12:1" → whole number, "6.4:1" → one decimal), equals the quoted number. The Ember Heat pair's real ratio is 4.25; at one-decimal precision normal JS rounding gives 4.3 (`4.25.toFixed(1)` is `"4.3"`), so once the doc is corrected in step 3 the test holds it to `4.3` — no rounding-mode special case anywhere. Keep the printed line.
2. Run `npm --prefix app test -- contrast`. Expect: the 21 passing pair/mark tests stay green, and the quoted-numbers test FAILS on 5 numbers — 6.4 (computes 6.50), 5.1 (computes 5.26), 7.5 (computes 8.29), 7.1 (computes 7.58), and 4.2 (computes 4.25, which normal JS rounding gives as 4.3, while the doc still says 4.2). The other three (12, 6.8, 10.2) pass because they round true.
3. In `docs/DESIGN.md`, correct the 5 wrong quoted ratios in the same N24 correction step (the fifth is I3): line 115 `6.4:1` → `6.5:1` and `5.1:1` → `5.3:1`; line 117 `4.2:1` → `4.3:1` (the real value is 4.25); line 121 `7.5:1` → `8.3:1` and `7.1:1` → `7.6:1`. Touch nothing else: keep all hex values, keep 12:1, 6.8:1 and 10.2:1 (they round true already).

Proof it's real: edit one corrected doc number back to its old wrong value (line 115: `6.5:1` → `6.4:1`), run `npm --prefix app test -- contrast` — the quoted-numbers test must FAIL. Put the number back and re-run — all green.
Done when: `npm --prefix app test -- contrast` prints `pass 22/22`-style output with the quoted-numbers test green and a printed line showing the five corrected computed ratios (6.5, 5.3, 4.3, 8.3, 7.6).
Commit message: `Batch 9: the contrast test reads every quoted DESIGN.md ratio; the 5 wrong doc numbers corrected (N24, I3)`

## Chunk 2 of 5: the undo-labels test reads the engine's real action list

Covers: user story 2; report finding 4.2 #16.

1. In `app/test/undo-labels.test.js`, subtest `every engine source_action has a label; unknown ones fail loudly` (lines 38–46): replace the hardcoded 7-action array on line 40 with a walk of `ember/maintain/undo.py` (the repo root path comes from `REPO_ROOT`, already imported at line 17), collecting the strings returned by `_source_action` (returns at undo.py:401–416) and `_source_action_of_undo` (returns at undo.py:432–448) — the same read-the-source way this file's later subtest walks `errors.py` (lines 92–104). Assert the walk finds all 7 known actions (an empty walk must fail, so the regex cannot rot silently), then call `undoActionWords(action)` for each.
2. Run `npm --prefix app test -- undo-labels`. Expect: all pass, with the walk finding exactly close-item, set-status, set-validated, clear-validated, edit-item, remove-link, reverse-supersedes.

Proof it's real: temporarily edit `ember/maintain/undo.py` — in `_source_action`, change `return "close-item"` (line 401) to `return "close-item-new"` — run `npm --prefix app test -- undo-labels`: the test must FAIL with `unknown source_action: close-item-new` (today's hardcoded list would have passed green). Revert the edit.
Done when: `npm --prefix app test -- undo-labels` passes with no action list written by hand anywhere in the test; `grep -n "close-item', 'set-status" app/test/undo-labels.test.js` finds nothing.
Commit message: `Batch 9: the undo-labels test walks the engine's real source_action returns`

## Chunk 3 of 5: the launch check loses the dead variable and the copied handler

Covers: user stories 3 and 4 (the launch-check half); report finding 4.2 #17.

1. Run `grep -rn RTI_FAKE_WORKDIR app/`. If any file other than `app/test/launch-check.js` now reads it (Batch 0 landed and uses it), KEEP the variable and skip step 2 — the spec's conditional. Only continue when the grep shows the single hit at `app/test/launch-check.js:67`.
2. In `app/test/launch-check.js`, delete the line `RTI_FAKE_WORKDIR: workDir,` (inside the child `env`, line 67). Nothing reads it (confirmed read-only today by grep and by archive/spec-check-batch9.md §2).
3. In the same file, replace the two identical stream handlers (lines 79–84: `child.stdout.on('data', ...)` appending to `stdout`, `child.stderr.on('data', ...)` appending to `stderr`) with ONE shared helper (for example `const appendTo = (sink) => (chunk) => { sink += String(chunk); }` used as `child.stdout.on('data', appendTo(stdoutRef))` — but note plain strings cannot be shared by reference in JS, so the helper must wrap where the text lands, e.g. an `append(child, 'stdout')` helper closure over both `let` variables, exactly the two lines' behaviour: each stream still read exactly once). Behaviour must not change: `stdout` and `stderr` still accumulate the same bytes.

Proof it's real: point the shared helper's stdout branch at `stderr` instead (one-line deliberate break), run `xvfb-run --auto-servernum npm --prefix app run check:launch` — the check must FAIL with `exit 0 but no "items: N" line on stdout`. Undo the break.
Done when: `xvfb-run --auto-servernum npm --prefix app run check:launch` ends with `check:launch OK — window started, one read command answered: items: N` and `grep -n RTI_FAKE_WORKDIR app/` prints nothing; the two `on('data', ...)` calls both route through the one helper.
Commit message: `Batch 9: the launch check shares one append helper; unused RTI_FAKE_WORKDIR removed`

## Chunk 4 of 5: e2e removes the dead helper and stops swallowing timeouts

Covers: user stories 4 (the unused-helper half) and 5; report findings 4.2 #18 and 4.2 #19.

1. In `app/test/e2e/design.js`, delete the whole unused `waitFor` helper (lines 31–37). Verified: its only occurrence is the definition; every wait in the file already uses `win.waitForSelector` / `win.waitForFunction`.
2. In `app/test/e2e/keep-safe.js`, line 364: replace `.catch(() => {})` on the `waitForSelector('[data-testid="keepsafe-pane"]', { timeout: 60000 })` call with a rethrow that names the step, e.g. `.catch((err) => { throw new Error(`keep_safe scenario 5 (open different file): the app did not return to the Keep safe pane within 60 s: ${err.message}`); })` — matching the file's existing `fail(...)` message style.
3. In `app/test/e2e/first-run-home-lookup.js`, line 435: replace `.catch(() => {})` on the `block-retry` click with the same kind of rethrow naming the step (the error-states Home scenario).

Proof it's real: in `keep-safe.js`, temporarily change the awaited selector at line 364 to the bogus name `[data-testid="no-such-pane"]` and run `xvfb-run --auto-servernum npm --prefix app run test:e2e:09` — the run must FAIL after 60 s with the step name in the message (today it sails past and fails later, or worse passes on a half-load). Revert.
Done when: all three e2e files pass under xvfb: `xvfb-run --auto-servernum npm --prefix app run test:e2e:design`, then `test:e2e:09`, then `test:e2e:04` — each ending with its `... OK` summary line; and `grep -n "catch(() => {})" app/test/e2e/keep-safe.js app/test/e2e/first-run-home-lookup.js | grep -v "app.close()"` prints nothing (11 hits remain, all the intended `app.close()` cleanup calls: 6 in keep-safe.js, 5 in first-run-home-lookup.js).
Commit message: `Batch 9: e2e drops the unused waitFor and rethrows swallowed waits with the step name`

## Chunk 5 of 5: the docs-in-sync gate fails in CI when git is missing

Covers: user story 6; report finding 4.2 #21.

1. In `tests/test_docs_in_sync.py`, add two NEW tests right after `_tracked_files()` (line 75): `test_missing_git_fails_in_ci` and `test_missing_git_skips_outside_ci`. Both monkeypatch `subprocess.run` to raise `OSError("git is gone")`; the first sets `monkeypatch.setenv("CI", "true")` and asserts `pytest.raises(pytest.fail.Exception)`, the second deletes the CI variable (`monkeypatch.delenv("CI", raising=False)`) and asserts `pytest.raises(pytest.skip.Exception)`. (GitHub Actions sets `CI=true` — confirmed feasible by archive/spec-check-batch9.md §2.)
2. Run `.venv/bin/pytest tests/test_docs_in_sync.py -k missing_git`. Expect: `test_missing_git_fails_in_ci` FAILS (today `_tracked_files` always skips, lines 67–75) and `test_missing_git_skips_outside_ci` passes.
3. In `_tracked_files()` in the same file: keep the `except (OSError, subprocess.CalledProcessError)` but branch inside it — when `os.environ.get("CI")` is set call `pytest.fail("git is not available, and CI never skips this gate")`, otherwise keep `pytest.skip("git is not available here")`. Add `import os` (the file does not import it today).

Done when (this step changes how an existing gate can fail, so it gets its own line): `.venv/bin/pytest tests/test_docs_in_sync.py -k missing_git` shows exactly `2 passed`, and the full file `.venv/bin/pytest tests/test_docs_in_sync.py` stays green (all pre-existing tests included).
Commit message: `Batch 9: the docs-in-sync gate fails with git missing in CI, skips only outside`

## Final check

- Full suites, all green:
  - `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/pytest` — expect `passed` count with `0 failed` (was 1174 passed, 4 deselected at the review tip — the count may differ slightly, but failures must be 0).
  - `npm --prefix app test` — the whole app unit suite, 0 failures.
- The batch's "Done when" from archive/Plan.md (`Batch 9 ... each of these tests fails when the behavior it guards is broken on purpose`), each with its proof command from the chunks above:
  - 4.2 #15 — plant a wrong quoted number back into `docs/DESIGN.md` → `npm --prefix app test -- contrast` fails; undo. (Chunk 1 proof.)
  - 4.2 #16 — rename one `source_action` return in `ember/maintain/undo.py` → `npm --prefix app test -- undo-labels` fails with `unknown source_action`; undo. (Chunk 2 proof.)
  - 4.2 #17 — point the shared append helper at the wrong stream → `npm --prefix app run check:launch` fails; undo. (Chunk 3 proof.) Refactor + dead variable: no behaviour guards it beyond the check itself, which is the guard.
  - 4.2 #18 — the dead helper is deleted outright; `grep -n "waitFor" app/test/e2e/design.js` finds nothing and `test:e2e:design` stays green.
  - 4.2 #19 — point the keep-safe wait at a bogus selector → `test:e2e:09` fails naming the step; undo. (Chunk 4 proof.)
  - 4.2 #21 — simulate missing git with `monkeypatch` + `CI=true` → the gate fails, never skips (the two NEW tests prove it every run, no manual break needed).
- After every proof: `git status` shows only the intended files, and the changed files' suites re-run green.

## Unknowns

- **Which batches have landed at implementation time.** The `RTI_FAKE_WORKDIR` keep-or-remove rule (Chunk 3, step 1) depends on whether Batch 0 has merged first. Both orders are allowed (archive/spec-check-batch9.md §4); the grep step is the guard.
- **The exact shared-helper shape in Chunk 3 step 3.** The template above the behaviour is right (each stream read exactly once, both accumulate), but JS strings are immutable, so the helper's exact closure shape is the implementer's choice; the spec pins only the one-helper outcome.

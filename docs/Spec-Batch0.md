# Batch 0: stop the bleeding

**Source:** `archive/Plan.md` Batch 0, decisions D-05 and D-22. Findings from `archive/Problems.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-batch0-check.md`). Not yet published.

## Problem Statement

Running Ember's own tests and scripts can hurt the person running them.

- Two test harnesses can spend real money and read a real secret. The cleanup e2e passes the founder's AI key to the engine. The launch check uses the real app config folder and can read the real encrypted key.
- One measurement script deletes the knowledge base it is pointed at, with no prompt. It also cannot start at all, because of a broken import.
- The key wizard can leave the AI key in a file that other users can read, and checks whether that file is gitignored only after the key is already written.
- The app test suite fails 4 tests on one run and passes on the next, with no code change. Some tests leave temp folders behind, and one silently falls back to the founder's own Python path.

Until these are fixed, every later batch that runs tests carries the same risks.

## Solution

- The test harnesses never see an AI key and never touch the real app config.
- The measurement script refuses any database it did not create in a temp folder, and starts correctly.
- The key wizard writes the key file with owner-only permission every time, checks gitignore before writing, and reports the key length correctly. It is Linux-only, and says so.
- The flaky tests become deterministic. Every test cleans up its temp folders. No test falls back to a machine-specific path.

## User Stories

1. As the founder, I want the cleanup e2e to run with no AI key in its environment, so that a test can never spend my real credit.
2. As the founder, I want the launch check to use a temp config folder, so that a test never reads my real `key.enc`.
3. As the founder, I want the launch check to see no stored key, so that its outcome does not depend on what is stored on my machine.
4. As a contributor, I want the harnesses to behave the same on every machine, so that my results match the founder's.
5. As a coding agent, I want to run the e2e harnesses without risk to the founder's secrets, so that I can run them unattended.
6. As the founder, I want `measure_model_change.py` to refuse a `--db` path that already exists outside a temp folder, so that it can never delete my knowledge base.
7. As the founder, I want a clear error and a non-zero exit when the measurement script refuses, so that I know nothing was touched.
8. As the founder, I want the measurement script to start at all, so that I can measure a model change when I need to.
9. As the founder, I want the measurement script to clean up its temp database even when the measured run fails, so that no stray database or open handle is left behind.
10. As the founder, I want the measurement report to state "CPU only" only when that was checked, so that the report is true.
11. As a user setting up a key, I want the wizard to make the key file readable only by me, even when the file already existed, so that other accounts on the machine cannot read my key.
12. As a user setting up a key, I want the wizard to check that the key file is gitignored before writing the key, so that I don't commit my key by accident.
13. As a user setting up a key, I want the wizard to refuse to write when the key file is not gitignored, so that a warning I miss cannot leak my key.
14. As a user setting up a key, I want the reported key length to match the key I entered, so that I can trust the check.
15. As a user on Linux, I want the wizard to state it is Linux-only, so that I am not misled about where it works.
16. As a contributor, I want the bridge client tests to pass on every run of an unchanged tree, so that a red result means a real bug.
17. As a contributor, I want slow-machine timing not to change which error code a test sees, so that tests check behavior, not machine speed.
18. As a contributor, I want the short timeouts kept only in the tests that are about hung reads, so that those tests still prove the timeout works.
19. As a contributor, I want the output-cap test to actually reach the cap, so that the cap is really tested.
20. As a contributor, I want the retry test to let the child finish its work before judging it, so that the test measures retries, not a kill race.
21. As a contributor, I want every test that makes a temp folder to remove it, so that repeated runs don't fill my disk.
22. As a contributor, I want the keep-safe contract test to fail with a clear message when it can't find Python, so that it never runs against the founder's own environment by accident.
23. As the founder, I want the app suite to pass 5 runs in a row, so that I can trust it as the gate for every later batch.

## Implementation Decisions

### Test harnesses (findings 4.2 #10, 4.2 #11)

- The cleanup e2e harness builds its child environment by copying the parent environment and then removing every AI key variable. At minimum `EMBER_AI_API_KEY` and `OPENROUTER_API_KEY`.
- The launch check sets `XDG_CONFIG_HOME` to a fresh temp folder for the app it launches. The temp folder contains no `key.enc`, so the launched app's own key provider reports "no key". A function cannot be passed into the launched app (it is a separate process), so the injection point is the environment: the same mechanism the cleanup e2e already uses for its config folder.
- Both harnesses remove their temp folders when they finish, pass or fail.

### Measurement script (findings 4.1 #3, #4, #23, #24)

- The script accepts `--db` only when the path does not exist yet, or lives inside the system temp folder. Anything else is refused before any file operation, with a clear error on stderr and a non-zero exit.
- No `--force` flag. The report suggested one. It is left out because the script's purpose is measurement on throwaway data, and the constitution forbids editing production data without a backup. [Inference]
- The import of the embedding store port comes from the relate module that owns it, through its public interface.
- The measured run sits inside the cleanup step, so a failure still removes the temp database.
- The report states "CPU only" only after checking that no accelerator was used. Otherwise it states what was used.

### Key wizard (findings 4.1 #11 to #14, decision D-22)

- Writing the key file always sets owner-only permission (mode 600), including when the file existed before.
- The gitignore check runs before the key is written. If the key file is not gitignored, the wizard refuses to write and exits non-zero.
- The reported length counts only the key characters, not quotes or the newline.
- Linux-only (D-22). The wizard's banner states it is Linux-only. The "cross-platform incl. WSL" comment is removed. The browser opener uses only the Linux opener. The WSL, Windows and macOS branches are removed.

### Flaky and leaky tests (findings 4.2 #1, #2, #3, #20, #23)

- The bridge client test helper defaults both timeouts to 5000 ms. Tests about hung reads set their own short timeout explicitly.
- The app test command runs test files one at a time (`--test-concurrency=1`).
- The output-cap fake writes with backpressure and ends by closing its output, never by forcing the process to exit. So every byte reaches the reader and the cap is really hit.
- The retry test gives each attempt enough time to write its marker before it is judged.
- Every test that creates a temp folder removes it in its cleanup.
- The keep-safe contract test finds Python from the project's configured environment. If it can't, it fails with a message naming what is missing. It has no machine-specific fallback.

## Testing Decisions

**What a good test is here.** It checks what the person running it can observe: what a child process received, whether a file changed, the exit code, the error code, file permissions. It never checks private helpers or exact wording. The constitution rules "test observable behavior" and "tests assert codes, not prose" apply.

**Seams under test (agreed):**

1. **Test harness boundary.** Run the cleanup e2e and the launch check against a fake engine that records the environment and config folder it received. Assert: no AI key variable present, config folder is under the temp folder. Both harnesses must run under a virtual screen (xvfb) locally, so no real window opens.
2. **Measurement script command line.** Run it on an existing file outside the temp folder: non-zero exit, file hash unchanged. Run `--help`: exits 0. Force a failure in the measured run: no temp database left.
3. **Key wizard on a temp folder.** Run a COPY of the wizard script from inside the temp working folder (the script derives its key-file path from its own location, so the real repo's `.env` is never touched). It runs with piped answers today: three lines, one for the opening "Ready to start?", one for the key, one empty for the model. Cases: an existing `.env` at mode 644 ends at 600. A key file that is not gitignored makes it refuse, with no key on disk. The reported length matches the input.
4. **Existing app test suites.** The app suite passes 5 runs in a row with zero failures (story 23, and Plan.md Batch 0's Done-when line). The timing fixes show up first in the bridge client and db-check runner suites; the cap test reaches the cap branch, shown by its error code. After the run, no test temp folders remain.

**Prior art:**
- `app/test/bridge-client.test.js` and `app/test/db-check-runner.test.js`, the suites being fixed.
- `app/test/launch-check.js` already has an unused fake workdir variable, a starting point for the fake engine. [Fact: report 4.2 #17]
- `tests/test_architecture.py`, an example of a test that reads files and asserts a rule.

**Check each test is real.** Before calling a fix done, break the fixed behavior on purpose (for example, put the key variable back into the child environment) and confirm the test goes red.

## Out of Scope

- Everything in Batches 1 to 9 of `archive/Plan.md`. In particular, the packaging fixes, the error boundary, and CI e2e (D-13) are not in this batch.
- Making the key wizard portable to macOS or WSL (D-22 rules it out).
- A `--force` flag for the measurement script.
- The other test-hygiene findings in Batch 9 (4.2 #15 to #19, #21).

## Further Notes

- **Unchecked against code.** This draft was written from the review and the plan only. The step-4 check by an agent with repo access must confirm every file and behavior named here.
- **Open question (answered 2026-11-01):** can the key wizard run non-interactively with piped answers today? Yes — verified by running a copy of the script in a temp folder (evidence in `archive/spec-batch0-check.md`). No engine change is needed for seam 3.
- **Safety rules for whoever implements this:** no real AI calls, never open `~/.config/ember-app/ember.db` or `key.enc`, no GUI launch except under xvfb, temp files only.

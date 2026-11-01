# Batch 0 implementation plan: stop the bleeding — safe harnesses, safe measurement script, safe key wizard, honest test suite
Spec: docs/Spec-Batch0.md
Branch: `batch-0`, cut from `ember-interface` (D-29: every batch works on its own branch `batch-N`, cut from where the previous batch merged, and is merged back into `ember-interface` when its "Done when" passes — Batch 0 is the first batch, so there is no previous branch and `batch-0` cuts from `ember-interface` itself)
Needs first: nothing (Batch 0 is the first batch — D-29's chain starts here, with `batch-0` cut from `ember-interface`)
Size: 18 chunks (54 steps), about 19 hours

Every number below was checked in the code today: the broken import (`scripts/measure_model_change.py:41-44`, protocol really lives at `ember/relate/embedding_store.py:12`), the wizard's path (`scripts/ember-key-wizard.sh:210-211`), the harness env builds (`app/test/e2e/cleanup.js:184-192`, `app/test/launch-check.js:60-70`), the app key provider (`app/main/main.js:592-595`), the test defaults (`app/test/bridge-client.test.js:37-38`), the runner fakes (`app/test/db-check-runner.test.js:135-176`), the Python fallback (`app/test/keep-safe-contract.test.js:31-33`) and the temp-dir leaks (the three the report names — `app/test/kb-schema-version.test.js:78-79`, the `db-check-runner` marker dir, and all six `keep-safe-contract` tests whose `seed()` dir is never removed, the file has no cleanup code at all — plus, counted on 2026-11-01 for decision I4, 58 orphaned folders across 11 more files: `bridge-client` 14, `key-store` 12, `settings` 7, `bundle-layout` 5, `fix-close-contract` 5, `cleanup-contract` 4, `ember-command` 3, `add-session` 3, `home-contract` 3, `bridge-contract` 1, `app-icon` 1; `keep-safe-ipc` was checked and cleans up after itself, so it is not on the list).

## Before you start
- Make the scratch folder: `mkdir -p /tmp/opencode/batch0`
- Run the Python tests this batch touches (from the repo root):
  - New files you will create: `.venv/bin/pytest tests/test_measure_model_change.py` and `.venv/bin/pytest tests/test_key_wizard.py` (both NEW).
  - Full engine suite: `.venv/bin/pytest` (pytest config in `pyproject.toml` already skips `live`).
- Run the app's node tests: `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test` (one file so far: `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bridge-client`).
- xvfb is installed locally (decision I2 — the founder installed it), so every e2e, launch check and app-suite command below runs under `xvfb-run --auto-servernum`. This batch never needs `sudo apt install xvfb` and adds no CI setup. From Chunk 8 on the app suite launches Electron once, which is why the `npm --prefix app test` form above carries `xvfb-run` from the start; chunk commands below show it in full.
- Run the e2e this batch touches: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run e2e -- cleanup`
- Run the launch check: `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run check:launch`
- Safety rules: never set a real AI key; strip it with `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY` in every manual run. Never open `~/.config/ember-app/ember.db` or any real `key.enc`. No GUI launch outside `xvfb-run`. All temp files under `/tmp/opencode/batch0/`. The wizard tests run on a COPY of the script inside a temp git repo — never in the real repo (the wizard writes `.env` next to itself).
- `.venv/bin/pytest` exists (checked). Commit style matches the repo's history: a short imperative line, sometimes with a tag prefix (`Batch0 N: ...` here).

## Chunk 1 of 18: the measurement script starts and refuses a real database
Covers: stories 6, 7, 8; report findings 4.1 #3, 4.1 #4.

1. Add NEW `tests/test_measure_model_change.py` with two subprocess tests (out of system temp only):
   - `help_exits_zero`: run `.venv/bin/python scripts/measure_model_change.py --help` with `subprocess.run`; assert return code 0. (Red today: the module-level import fails, so even `--help` dies.)
   - `refuses_an_existing_db_outside_temp`: create a real file outside the temp dir — `Path(__file__).parent / '_measure_refusal_target.db'`, sha256 it, run the script with `--db <that file>`, assert return code non-zero and the sha256 unchanged; remove the file in a `finally`. (Note: the deletion red is NOT observable today — the script cannot even start, see `help_exits_zero`, so it never reaches the file. Once step 3's import fix is in, removing only the refusal block makes the script unlink the file and this test fail; that break is the red proof below.)
2. Run `.venv/bin/pytest tests/test_measure_model_change.py -k "help or refuses"`. Expect: 1 failed (`help_exits_zero`, ImportError traceback); `refuses_an_existing_db_outside_temp` passes today for the wrong reason (non-zero exit from the import crash, file untouched because nothing ran). The refusal's own red comes from the break in "Proof it's real".
3. In `scripts/measure_model_change.py`, function `main` (and the module imports): move the port import to the module that owns it — `from ember.relate.embedding_store import EmbeddingStorePort` (keep `SentenceTransformerEmbedder` from `ember.adapters.embedder`); and before any file operation (`db_file.parent.mkdir` / `delete_database`): refuse when the resolved `--db` path already exists AND is not inside `tempfile.gettempdir()` — print one clear error line to stderr and `return 1`.
   Done when: `draft/refusal-proof.db` (a file the proof creates outside temp; `draft/` does not exist yet — the proof's `mkdir -p` makes it, and the fixed script must NOT create anything for a refused path) survives a refused run unchanged.

Proof it's real: `mkdir -p draft && printf seed > draft/refusal-proof.db`, run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/python scripts/measure_model_change.py --db draft/refusal-proof.db` — expect exit non-zero, file still there with the same bytes; then delete `draft/refusal-proof.db`. To see it red again: comment out the refusal block and rerun the test — the file gets unlinked and `refuses_an_existing_db_outside_temp` fails, then put the block back.
Done when: `.venv/bin/pytest tests/test_measure_model_change.py` prints `2 passed`, and the proof command above exits non-zero without deleting the target.
Commit message: `Batch0 1: the measurement script starts and refuses a live database`

## Chunk 2 of 18: the measured run always cleans up, and the CPU claim is checked
Covers: stories 9, 10; report findings 4.1 #23, 4.1 #24.

1. Extend `tests/test_measure_model_change.py` with `failed_run_leaves_no_database`: load the script as a module (it already puts the repo on `sys.path`), monkeypatch its `SentenceTransformerEmbedder` with a class that raises on construction, call `module.main()` with `--db` under pytest's `tmp_path`, assert the return is not 0 and no `*.db`, `-wal`, `-shm`, `-journal` or `.bak-v*` file remains in that folder. (Red today: the failure escapes before the cleanup `try`.)
2. Run `.venv/bin/pytest tests/test_measure_model_change.py -k leaves_no_database`. Expect: 1 failed, an exception from the embedder, the database file still present.
3. In `scripts/measure_model_change.py`: move the whole measured section (warm-up through the `MODEL_CHANGED_LINE` check) inside the existing `try` block, so `conn.close()` and `delete_database(db_file)` in the `finally` run on every failure; and replace the hardcoded `"environment: cpu only, ..."` report line (line 270) with a checked statement: a small pure helper that asks the loaded setup whether an accelerator exists (`torch.cuda.is_available()`, `torch.backends.mps.is_available()`; torch 2.15.0+cpu is installed — checked) and prints "CPU only" only when both are false, otherwise what it found.
   Done when: no leftover database in `/tmp/opencode/batch0` after an intentionally failed run: `.venv/bin/pytest tests/test_measure_model_change.py` prints `3 passed`.

Proof it's real: comment out the `delete_database(db_file)` call inside the `finally` — `failed_run_leaves_no_database` goes red with the leftover file; put it back. For the CPU line: temporarily hardcode `True` for the accelerator check — the report can no longer claim "CPU only" on this CPU-only machine and the helper test goes red; restore.
Done when: `.venv/bin/pytest tests/test_measure_model_change.py` prints `3 passed`, 0 failed.
Commit message: `Batch0 2: the measured run cleans up on any failure and the CPU claim is checked`

## Chunk 3 of 18: the key wizard refuses a key file that is not gitignored — before writing
Covers: stories 12, 13; report finding 4.1 #12. (Check report §2.3: the wizard derives its key-file path from its own location, `ember-key-wizard.sh:210-211`, so the tests run a COPY inside a temp git repo.)

1. Add NEW `tests/test_key_wizard.py` with a helper that copies `scripts/ember-key-wizard.sh` into a fresh temp git repo (`git init`, an owned `.gitignore`), runs the COPY with piped answers `"yes\n<key>\n\n"` (pause answer, the key, an empty model line — verified working today, check report §3), and removes the folder after. First test `not_gitignored_refuses_and_writes_nothing`: the temp repo's `.gitignore` deliberately does NOT cover `.env`; assert the exit code is non-zero and no `EMBER_AI_API_KEY=` line exists on disk. (Red today: the wizard warns but still writes.)
2. Run `.venv/bin/pytest tests/test_key_wizard.py -k gitignored`. Expect: 1 failed, the key found on disk.
3. In `scripts/ember-key-wizard.sh`, stage 1 of `run_wizard`: before `ask_secret EMBER_AI_API_KEY`, run `git -C "$REPO_ROOT" check-ignore -q "$ENV_FILE"`; when it fails, print one error line to stderr and `exit 1` — nothing is written.

Proof it's real: move the check back below `write_env` (today's order) — `not_gitignored_refuses_and_writes_nothing` goes red (key on disk, exit 0); put it back before the write.
Done when: `.venv/bin/pytest tests/test_key_wizard.py -k gitignored` prints `1 passed`; `bash -n scripts/ember-key-wizard.sh` exits 0.
Commit message: `Batch0 3: the key wizard refuses an un-ignored key file before writing`

## Chunk 4 of 18: the key file is mode 600 before the key is written (no 644 window), and the reported length is true
Covers: stories 11, 14; report findings 4.1 #11, 4.1 #14; decision I13 (no 644 window exists at any moment).

1. Extend `tests/test_key_wizard.py`:
   - `existing_env_file_644_ends_at_600` (regression pin): the temp repo's `.env` is pre-created mode 644; after the piped run, mode is 600 and the key is present.
   - `reported_length_matches_the_key`: a 29-character key of plain letters and digits; parse the printed "`N chars`" number from stdout; assert N == 29. (Red today: it prints 31 — quotes and newline counted, `ember-key-wizard.sh:244-245`.)
2. Run `.venv/bin/pytest tests/test_key_wizard.py -k "600 or length"`. Expect: 1 failed (length), 1 passed (mode).
3. In `scripts/ember-key-wizard.sh`: inside `write_env`, lock the file BEFORE any key byte is written — first `umask 077`, then `touch "$ENV_FILE" && chmod 600 "$ENV_FILE"` at the very top of the function (this covers both a fresh file and a pre-existing 644 file: the mode ends as 600 before the key line is appended, so no 644 window exists — decision I13) — and only then write the key line; in stage 3 report the key length as `${#EMBER_AI_API_KEY}` characters instead of the `grep -oP ... | wc -c` count.

Proof it's real: run the piped wizard test on its COPY with `bash -x` and read the trace: `chmod 600` must appear BEFORE the first line that writes the key. Break it by moving the `chmod` back below the append (today's shape) — the trace order reverses; the end-state test still passes, which is exactly why the trace order is the proof here and the end state alone is not enough; put it back. Then revert the length expression to the old `grep -oP ... | wc -c` print — `reported_length_matches_the_key` fails (31 vs 29); restore.
Done when: `.venv/bin/pytest tests/test_key_wizard.py -k "600 or length"` prints `2 passed`.
Commit message: `Batch0 4: the key file is 600 before the key is written and the length count is true`

## Chunk 5 of 18: the key wizard is Linux-only (D-22)
Covers: story 15; report finding 4.1 #13; decision D-22.

1. Extend `tests/test_key_wizard.py` with `banner_states_linux_only_and_no_other_openers`: after a piped run, assert the wizard's own output contains a Linux-only statement (the banner) and is free of "WSL" and "macOS"; and read the script text to assert the opener branches `wslview`, `explorer.exe` and `open ` are gone (`xdg-open` remains) — the branches are only observable on other systems, so the branch removal is pinned as text (same style as `tests/test_architecture.py`). (Red today: branches exist, the banner claims nothing about Linux.)
2. Run `.venv/bin/pytest tests/test_key_wizard.py -k linux_only`. Expect: 1 failed.
3. In `scripts/ember-key-wizard.sh`: the banner gains one line stating it is Linux-only; `open_url` keeps only the `xdg-open` branch; remove the WSL/Windows/macOS branches and the "cross-platform incl. WSL" comment on `open_url`.
   Done when: `bash -n scripts/ember-key-wizard.sh` exits 0 and the source has exactly one opener (`xdg-open`).

Proof it's real: re-add the `explorer.exe` branch to `open_url` — `banner_states_linux_only_and_no_other_openers` goes red on the branch check; remove it again.
Done when: `.venv/bin/pytest tests/test_key_wizard.py` prints `4 passed` (all wizard tests from chunks 3-5).
Commit message: `Batch0 5: the key wizard is Linux-only (D-22)`

## Chunk 6 of 18: the launch check runs in a throwaway config with no AI key
Covers: stories 2, 3, 4; report finding 4.2 #11.

1. In `app/test/launch-check.js`, function `main`: build the child's env so the app never sees the real config and never sees a key — create `configDir = path.join(workDir, 'config')` (already inside the removed temp work folder), set `XDG_CONFIG_HOME: configDir` in the spawn env (the same mechanism `app/test/e2e/cleanup.js:186` already uses), `delete` `EMBER_AI_API_KEY` and `OPENROUTER_API_KEY` from the copied env, fail with `fail()` if either key survives, and print the config dir used in the harness's OK line. No `key.enc` can exist in the fresh folder, so the app's own key provider (`app/main/main.js:592-595`) reports no key. Leave the unused `RTI_FAKE_WORKDIR` line untouched (finding 4.2 #17 is Batch 9).
2. Run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY EMBER_AI_API_KEY=sk-or-v1-SENTINEL-NEVER-SPEND TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run check:launch`. Expect: `check:launch OK — ... config: /tmp/opencode/batch0/ember-launch-check-.../config` and exit 0. (Decision I5: this sentinel scenario is not a manual-only check — from Chunk 8 on, `npm --prefix app test -- harness-no-key` runs it inside the suite, with a fake engine recording the child's environment and config folder.)
3. Break: comment out only the two `delete` lines — the guard names the sentinel key and the check fails red before Electron starts; put the lines back.

Proof it's real: the step-3 break is the red run (sentinel key survives into the child env and the guard stops the harness). The config proof is in the OK line: it prints a `/tmp` path, never `~/.config`.
Done when: the command in step 2 prints the OK line with a temp `.../config` path and exits 0, with a sentinel key in the environment.
Commit message: `Batch0 6: launch-check runs in a throwaway config with no AI key`

## Chunk 7 of 18: the cleanup e2e strips inherited AI keys
Covers: stories 1, 4, 5; report finding 4.2 #10.

1. In `app/test/e2e/cleanup.js`, function `launch` (`:184-192`): copy the parent env, then `delete env.EMBER_AI_API_KEY` and `delete env.OPENROUTER_API_KEY` BEFORE the scenario's own fake assignment (`if (apiKey) env.EMBER_AI_API_KEY = apiKey;` stays last), and fail with `fail()` if any AI key variable would still reach the child (any AI key in the final env must be the scenario's explicit fake value, and `OPENROUTER_API_KEY` must be absent).
2. Run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY OPENROUTER_API_KEY=sk-or-v1-SENTINEL-NEVER-SPEND TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run e2e -- cleanup`. Expect: all four scenarios print their `--- clean up: ...` headers and the run exits 0.
3. Break: comment out the two `delete` lines — the sentinel reaches the guard and the e2e fails red before any window opens; put them back.

Proof it's real: the step-3 break is the red run (a real-looking key survives into the launched app's environment; the guard names it). Decision I5 on this side: the assertion lives in the harness's own guard, not in the operator's eye — the gate run (Chunk 18) re-runs this command with sentinel keys, and the guard is what stops a leaking key; the launch side additionally gets a fully automated suite test in Chunk 8.
Done when: the command in step 2 runs green end to end with sentinel key variables in the shell.
Commit message: `Batch0 7: the cleanup e2e strips inherited AI keys`

## Chunk 8 of 18: an automated suite test proves no AI key reaches the harness child (I5)
Covers: decision I5 (no manual-only check); the automated half of stories 2, 3, 4.

1. Add NEW `app/test/harness-no-key.test.js` with one test, `no AI key reaches the launch-check child — a recording fake engine proves the environment`: the test writes a recorder fake engine into its own temp folder under `/tmp/opencode/batch0` — a tiny node script that dumps its whole `process.env` (variable names, plus the `XDG_CONFIG_HOME` value) to the file given as `argv[2]`, prints `items: 1` (the line the app's `EMBER_APP_LAUNCH_CHECK` mode forwards to `check:launch`), and exits 0; then it spawns `node test/launch-check.js` with `EMBER_AI_API_KEY=sk-or-v1-SENTINEL-NEVER-SPEND` and `OPENROUTER_API_KEY=sk-or-v1-SENTINEL-NEVER-SPEND` in the parent env and `EMBER_TEST_ENGINE=node <recorder> <dump file>`, and asserts: `check:launch` exits 0, its OK line names a `/tmp/opencode/batch0/...` config path, the dump's env names contain neither AI-key variable, and the recorded `XDG_CONFIG_HOME` points inside the check's own `ember-launch-check-` work folder, never `~/.config`. Give the test a 180000 ms timeout (the check itself waits up to 90000 ms). (Red today: no `EMBER_TEST_ENGINE` hook exists, so the recorder never runs and no dump file appears.)
2. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- harness-no-key`. Expect: 1 failed — the dump file is never created, because `launch-check` has no `EMBER_TEST_ENGINE` hook yet and hands `EMBER_APP_COMMAND` the real venv `ember`, so the child env stays unproven inside the suite (the Chunk 6 strip is already in — the recording is what is missing).
3. In `app/test/launch-check.js`, function `main` (extends the Chunk 6 edit): when `process.env.EMBER_TEST_ENGINE` is set, use it as `commandEnv` — a test-only hook, so a fake engine can record the final child environment. Nothing else changes: the Chunk 6 strip, guard and config-dir OK line are the assertion that keeps running on every real launch.

Proof it's real: the step-2 red run (sentinels in the env, recording impossible) plus a break: comment out the `EMBER_TEST_ENGINE` lines after the fix — the test fails again with no dump file; restore them. (The e2e side of I5 stays asserted by its own guard, Chunk 7: the harness fails itself on any surviving key; no manual eyeball is the check anywhere.)
Done when: the command in step 2 prints `1 passed`, 0 failed; and `grep -rn "EMBER_TEST_ENGINE" app/test app/package.json` shows the variable is only ever READ by `launch-check` and SET by the new test, never by `check:launch` itself.
Commit message: `Batch0 8: an automated test pins no AI key in the harness child (I5)`

## Chunk 9 of 18: a slow-but-healthy read must survive the default limit (test first)
Covers: stories 16, 17, 18 (test half); report finding 4.2 #1.

Commit only in Chunk 10 (test and fix land together, so no green tree ever carries a red test).

1. In `app/test/fake-ember.js` add a NEW mode `slow`: sleep 400 ms, then print the usual `list-items` document and exit 0 (a normal small edit to the fake's mode table).
2. In `app/test/bridge-client.test.js` add one test `a slow-but-answering read succeeds with the default limit` that uses `makeClient()` unchanged with `FAKE_MODE: 'slow'` and asserts `result.ok === true` and a real `data.total` (never APP-008).
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bridge-client`. Expect: 1 failed — the new test ends as APP-008 because `makeClient` still defaults both timeouts to 150 ms.

Proof it's real: this chunk's red run IS the proof (a read that merely takes 400 ms dies at 150 ms).
Done when: the command in step 3 shows the new test failed with APP-008.
Commit message: (see Chunk 10)

## Chunk 10 of 18: the 5000 ms defaults and one test file at a time
Covers: stories 16, 17, 18 (fix half); report finding 4.2 #1 (including its `--test-concurrency=1`).

1. In `app/test/bridge-client.test.js`, function `makeClient` (`:37-38`): default `timeoutReadMs` and `timeoutWriteMs` to 5000. The hung-read/hung-write tests already set their 150 ms explicitly (`:162`, `:181`, `:200`), so their behavior is unchanged.
2. In `app/test/run.js` (line 35): add `'--test-concurrency=1'` to the arguments of `node --test`, so the app suite runs test files one at a time.
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bridge-client`. Expect: `# pass 15` (or more), `# fail 0` — the chunk-9 test is green and nothing else moved.

Proof it's real: set the `makeClient` defaults back to 150 ms and run the bridge-client suite five times — at least one run goes red (a normal read reported as APP-008, the flake from report 4.2 #1); restore 5000 ms.
Done when: `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bridge-client` prints `# fail 0` including the new slow-read test.
Commit message: `Batch0 10: 5000 ms test defaults, one test file at a time (with the Chunk 9 regression test)`

## Chunk 11 of 18: the output-cap fake really reaches the cap, and the retry test sees both tries
Covers: stories 19, 20; report findings 4.2 #2, 4.2 #3.

1. In `app/test/db-check-runner.test.js`, test `oversized stdout ends with the bridge-client kind of error (F8)` (`:157-176`): rewrite the fake so it writes each 1 MB chunk with backpressure (wait for `drain` before the next write) and ends by closing its output (`process.stdout.end()`), never by `process.exit(0)` — so every byte reaches the reader and the 32 MB cap is really hit. Keep the assertions unchanged.
2. In the same file, test `a timed-out child retries once, then comes back as APP-008 (a read, I15)` (`:135-155`): raise `timeoutMs: 150` to `timeoutMs: 1000` so each attempt has time to write its marker before it is judged, and tighten `calls >= 2` to exactly `2` (one retry).
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- db-check-runner`. Expect: `# pass 9` (all 9 tests in the file), `# fail 0`.

Proof it's real: put the old fake body back (`setInterval` + `process.exit(0)`, no drain handling) and run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- db-check-runner` five times — at least one run goes red because pending bytes are dropped and the cap is never reached (the detail match fails); then set `timeoutMs` back to 150 and the retry test can lose the marker (call count red); restore both.
Done when: `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- db-check-runner` prints `# fail 0` on five consecutive runs.
Commit message: `Batch0 11: the cap fake reaches the cap and the retry test sees both tries`

## Chunk 12 of 18: the report's three temp leaks are removed, and no machine-specific Python
Covers: stories 21, 22; report findings 4.2 #23, 4.2 #20; decision I4 starts here (the report's named files only — Chunks 13-16 cover the rest).

1. Remove the remaining temp-dir leaks in the three files this chunk names: `app/test/db-check-runner.test.js` (the retry test's marker `mkdtemp` dir — remove it in the existing `finally` alongside `fake.cleanup()`), `app/test/kb-schema-version.test.js` (the test `a missing path fails closed`, `:78-79`, creates a temp dir and never removes it), and `app/test/keep-safe-contract.test.js` — every test that calls `seed()` (`:65`, `:87`, `:97`, `:109`, `:124`, `:137`) seeds a temp dir and NOTHING in the file ever removes it (no `rmSync`/`unlink`/`finally` exists there today).
2. In `app/test/keep-safe-contract.test.js` (`:31-33`): replace the hardcoded fallback `/home/mo/lab/ember/.venv/bin/python` — take `process.env.EMBER_PYTHON` (NEW variable) when set, else `REPO_ROOT/.venv/bin/python`; when neither exists, fail with one clear message naming what is missing and what to set. No machine-specific path anywhere.
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- keep-safe` and `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- kb-schema`. Expect: `# fail 0` in both.

Proof it's real: run `EMBER_PYTHON=/no/such/python TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- keep-safe` — the suite fails with one clear message naming the missing interpreter (before this change it silently used the hardcoded path); unset the variable. Temp proof: after a suite run, `ls /tmp | grep -c ember-dbrun-marker` prints `0` (run with `TMPDIR=/tmp/opencode/batch0` and it stays empty by construction).
Done when: both commands print `# fail 0`, and `ls /tmp | grep ember-dbrun-marker; ls /tmp/opencode/batch0 | grep -E 'kscontract|kbschema|dbrunner'` prints nothing.
Commit message: `Batch0 12: test temp dirs always cleaned, no machine-specific python`

## Chunk 13 of 18: the three real-database contract tests remove their seeded temp folders (I4)
Covers: story 21 extended by decision I4 (every leaking test file, not only the ones the report names); report finding 4.2 #23.

1. In `app/test/bridge-contract.test.js`: the test's `fs.mkdtempSync(..., 'ember-contract-')` folder (`:25`) is created and never removed — remove it (`fs.rmSync(dir, { recursive: true, force: true })`) in a `finally` around the run.
2. In `app/test/cleanup-contract.test.js` and `app/test/home-contract.test.js`: each `seed()` (`cleanup-contract.test.js:100`, `home-contract.test.js:28`) mkdtemps a folder and returns only the db path, so nothing ever removes the folder (the `finally` at `cleanup-contract.test.js:264` deletes only env keys). Make `seed()` hand back the folder alongside the path (or push it onto a tracked list) and remove every seeded folder in each test's `finally` — 4 seeded folders in cleanup-contract, 3 in home-contract (counted today).
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bridge-contract`, then again with `-- cleanup-contract` and with `-- home-contract`. Expect: `# fail 0` in all three.

Proof it's real: comment out the new removals, run the three suites, and `ls /tmp/opencode/batch0 | grep -E 'ember-contract|ember-cleanup'` shows the 8 leftover folders, restore.
Done when: the three commands print `# fail 0`, and that `ls | grep` prints nothing after a full run.
Commit message: `Batch0 13: contract tests remove their seeded temp folders (I4)`

## Chunk 14 of 18: the suite's biggest leak — bridge-client, ember-command and add-session (I4)
Covers: story 21 extended by decision I4; report finding 4.2 #23.

1. In `app/test/bridge-client.test.js`: `tempPath()` (`:27-29`) mkdtemps a fresh `ember-bridge-` folder for EVERY call — 14 call sites today, 14 orphaned folders per suite run, nothing removes them. Push each created folder onto a list and remove them all in one `after()` hook at the end of the file (node:test runs it once, after all tests in the file).
2. In `app/test/ember-command.test.js`: three `ember-kb-` folders (`:38`, `:55`, `:66`) are created and never removed — remove each in a `finally`.
3. In `app/test/add-session.test.js`: three `ember-addsess-`/`ember-temptext-` folders (`:72`, `:235`, `:253`) are created and never removed — the file inside is unlinked (via `removeTempFile` / the test), the folder is left behind. Remove the folder too, in a `finally`; for the `writeTempText` fake at `:72`, remove the fake's folder when the test ends (the fake already tracks what it created in `tempCalls`).

Proof it's real: comment out the three removals, run `npm --prefix app test -- bridge-client`, `-- ember-command` and `-- add-session` (all with `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum`), and `ls /tmp/opencode/batch0 | grep -E 'ember-bridge|ember-kb|ember-addsess|ember-temptext'` shows 20 leftover folders (14+3+3 — counted), restore.
Done when: the three commands print `# fail 0`, and that `ls | grep` prints nothing after a full run.
Commit message: `Batch0 14: bridge-client, ember-command and add-session tests clean their temp folders (I4)`

## Chunk 15 of 18: key-store, settings and app-icon remove their temp folders (I4)
Covers: story 21 extended by decision I4; report finding 4.2 #23.

1. In `app/test/key-store.test.js`: `tempFile()` (`:44-47`) mkdtemps a fresh `ember-key-` folder per call — 12 call sites today, none removed. Push each folder onto a list and remove them all in one `after()` hook.
2. In `app/test/settings.test.js`: `tempDir()` (`:15-17`) makes a fresh `ember-settings-` folder per call — 7 call sites today; the `finally` at `:127` only restores a chmod, the folder stays. Track every folder and remove them all in one `after()` hook.
3. In `app/test/app-icon.test.js`: the `ember-icons-` folder (`:30`) is created and never removed — remove it in a `finally`.

Proof it's real: comment out the three removals, run `npm --prefix app test -- key-store`, `-- settings` and `-- app-icon` (all with `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum`), and `ls /tmp/opencode/batch0 | grep -E 'ember-key|ember-settings|ember-icons'` shows 20 leftover folders (12+7+1 — counted), restore.
Done when: the three commands print `# fail 0`, and that `ls | grep` prints nothing after a full run.
Commit message: `Batch0 15: key-store, settings and app-icon tests clean their temp folders (I4)`

## Chunk 16 of 18: bundle-layout and fix-close-contract remove their temp folders (I4)
Covers: story 21 extended by decision I4; report finding 4.2 #23.

1. In `app/test/bundle-layout.test.js`: `tempAppDir()` (`:30-32`) makes a fresh `ember-bundle-` folder per call — 5 call sites today, none removed. Track the folders and remove them all in one `after()` hook.
2. In `app/test/fix-close-contract.test.js`: `freshDir()` (`:65-67`) makes a fresh `ember-fix-` folder per call — 5 call sites today, none removed (each test seeds its twin databases inside). Track the folders and remove them all in one `after()` hook.
3. Run `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test -- bundle-layout`, then again with `-- fix-close-contract`. Expect: `# fail 0` in both.

Proof it's real: comment out the two hooks, run both suites, and `ls /tmp/opencode/batch0 | grep -E 'ember-bundle|ember-fix'` shows the 10 leftover folders (5+5 — counted), restore.
Done when: both commands print `# fail 0`, and that `ls | grep` prints nothing after a full run.
Commit message: `Batch0 16: bundle-layout and fix-close-contract tests clean their temp folders (I4)`

## Chunk 17 of 18: map the new test files
Covers: the PROJECT_MAP rule (one line per file); no story or finding number (bookkeeping).

1. Add one line each to the `Tests` section of `PROJECT_MAP.md` for `tests/test_measure_model_change.py` (the measurement script's command-line and cleanup tests), `tests/test_key_wizard.py` (the key wizard run on a temp copy), and `app/test/harness-no-key.test.js` (the automated key-leak check of the launch harness).
2. Run `.venv/bin/pytest tests/test_docs_in_sync.py`. Expect: all pass, 0 failed (this test keeps the map honest).
3. Run `.venv/bin/pytest`. Expect: the full engine suite passes (about 1179 passed, 4 deselected live tests, 0 failed).

Proof it's real: delete one of the three new lines — `tests/test_docs_in_sync.py` fails saying a tracked file has no line in the map; re-add it.
Done when: `.venv/bin/pytest tests/test_docs_in_sync.py` prints `N passed`, 0 failed, with all three new lines present.
Commit message: `Docs: map the three new Batch 0 test files`

## Chunk 18 of 18: the gate — five green runs
Covers: story 23; Plan.md Batch 0's "Done when" line.

1. Run the app suite five times: `for i in 1 2 3 4 5; do TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test || echo "RUN $i FAILED"; done`. Expect: no `RUN ... FAILED` line, `# fail 0` five times.
2. Run the batch's two harness commands once more (see Before you start): the cleanup e2e and the launch check. Expect: exit 0 on both, the OK lines naming a `/tmp/opencode/batch0/...` config path.
3. Re-run the refused-database proof from Chunk 1 (`draft/refusal-proof.db` round trip) and the wizard suite. Expect: non-zero exit, file untouched; `4 passed` in the wizard file.
   Done when: the three commands above all report success; nothing in `/tmp/opencode/batch0` left behind afterwards (`rm -rf /tmp/opencode/batch0/*` at the very end is allowed — it is the batch's own scratch folder).

Proof it's real: nothing to break — this chunk only runs the gates everything else proved. (The breaks are in earlier chunks.)
Done when: five consecutive `# fail 0` lines for the app suite and both harness commands green.
Commit message: no commit (verification only; nothing changed)

## Final check
- `.venv/bin/pytest` — full engine suite, all green (0 failed; `live` deselected as always).
- `TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app test` — all green (includes the I5 automated test from Chunk 8).
- `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run e2e -- cleanup` — green.
- `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY TMPDIR=/tmp/opencode/batch0 xvfb-run --auto-servernum npm --prefix app run check:launch` — green, OK line shows a temp config path.
- `.venv/bin/pytest tests/test_measure_model_change.py` and `.venv/bin/pytest tests/test_key_wizard.py` — green.

The batch's "Done when" from `archive/Plan.md`, each with its command:
1. "The cleanup e2e and launch check run with no AI key in their environment and a temp config folder." → the two xvfb commands above, both green in one shell where `EMBER_AI_API_KEY=sk-or-v1-SENTINEL-NEVER-SPEND` is exported; the launch check's OK line names a temp config path.
2. "`measure_model_change.py --db <existing real file>` refuses and exits non-zero." → `mkdir -p draft; printf seed > draft/refusal-proof.db; env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY .venv/bin/python scripts/measure_model_change.py --db draft/refusal-proof.db; echo rc=$?` → prints `rc=1` (non-zero) and the file's sha256 unchanged; then `rm draft/refusal-proof.db`.
3. "The app suite passes 5 runs in a row with zero failures." → the `for i in 1 2 3 4 5 ...` loop from Chunk 18: five `# fail 0` lines.

## Unknowns
- The exact device check for the "CPU only" report line is the implementer's choice (`torch.cuda.is_available()` / `torch.backends.mps.is_available()` suggested; torch 2.15.0+cpu is installed and both report false here). The spec pins only that the claim must be checked, not the mechanism.
- The exact expected pass counts in the suites (`# pass 15`, "about 1179 passed") are estimates from today's counts; the real gate is `# fail 0`, never a specific total.
- Whether node's `process.stdout.end()` is tolerated by the db-check runner's child handling was not verified (the Electron/Node docs support closing the write side of a piped stdout; the chunk's red/green cycle will confirm it — if it hangs instead, the fallback is writing bytes in drained chunks and simply never exiting while the runner kills it at the cap, which still ends by the reader's term, not the writer's exit).

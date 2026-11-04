# Batch 1 implementation plan: release artifact — a `.deb` anyone with an amd64 machine can install safely
Spec: docs/Spec-Batch1.md
Branch: batch-1. Cut from where Batch 0 merged, merged into `ember-interface` when this batch's "Done when" passes (D-29).
Needs first: Batch 0 (for its test fixes and the run-a-script-on-a-temp-folder pattern; nothing in Batch 1's code imports from it)
Size: 11 chunks, 33 steps, about 16 hours (plus one real ~20-minute build by the founder in the Final check)

## Before you start
- Tests this batch touches, exactly as typed (from the repo root):
  - `.venv/bin/pytest tests/test_cli_version.py` (new in Chunk 1; `.venv` confirmed: `ls .venv/bin/pytest` exists)
  - `.venv/bin/pytest` (the whole Python suite; `pyproject.toml:33` already adds `-q -m 'not live'`, so no live AI calls)
  - `npm --prefix app test -- packaging` (filter convention from `app/test/run.js:9-12`: one filename filter)
  - `npm --prefix app test -- runtime-gate` / `-- runtime-build` / `-- pack-staging` / `-- check-deb` (all new in this batch)
  - `npm --prefix app test` (the whole app suite)
- Safety rules: no AI keys — run every child `ember`/engine command with `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY` (the gate and tests strip them). Never open the real `~/.config/ember-app/ember.db` or `key.enc`. No e2e is planned in this batch; if you ever run one, only under `xvfb-run`. Keep all test temp files under `/tmp/opencode/batch1/` — EXCEPT fixture runtimes for the full build-script flow: `app/scripts/build-ember-runtime.sh:68-75` creates its own multi-GB scratch NEXT TO `EMBER_RUNTIME_OUT` on purpose (never in `/tmp` tmpfs), so point `EMBER_RUNTIME_OUT` for those tests at a folder on the normal disk, e.g. under `/tmp/opencode/batch1/` only if that is not a small tmpfs — check `df /tmp/opencode` first.
- Never touch the existing real artifact `app/dist/ember-app_0.2.0-1_amd64.deb` when planting bad files; fixtures are built fresh in `/tmp/opencode/batch1/`.
- Every chunk is test-first: the failing test is added and seen red (or seen failing on the bench command) BEFORE the code change.

---

## Chunk 1 of 11: `ember --version` exists
Covers: story 17; finding 4.10 #10 (part: the missing `--version`); spec-check section 1 Decision 2's "one source first" prerequisite.

1. Add a failing test `tests/test_cli_version.py` (NEW): `from click.testing import CliRunner`; `from ember import __version__`; `from ember.cli import main`; one test invoking `CliRunner().invoke(main, ["--version"])` asserting `exit_code == 0` and `__version__` (today `0.1.0`, `ember/__init__.py:3`) appears in the output. Copy the import style of `tests/test_cli.py:8-10`.
2. Run `.venv/bin/pytest tests/test_cli_version.py`. Expect: 1 failed — today `ember/cli.py:295` is a bare `@click.group()` with no version option (live run confirmed: `Error: No such option '--version'.`, exit 2).
3. In `ember/cli.py`, on the `main` group (lines 295-297), add `@click.version_option(version=__version__, prog_name="ember")` with `from ember import __version__` at the top of the file. Read the engine version ONLY from `ember/__init__.py` (the one source; Chromium-click 8.5.0 is installed — confirmed via `.venv/bin/python -c "import click"`).

Proof it's real: comment out the new `@click.version_option` decorator in `ember/cli.py` → the test goes red; undo the comment.
Done when: `.venv/bin/ember --version` prints `ember, version 0.1.0` and `echo $?` prints `0` (the build script's dead smoke at `app/scripts/build-ember-runtime.sh:160` becomes real).
Commit message: `Batch 1: ember --version from the one engine source`

## Chunk 2 of 11: one engine version source + the version pin test
Covers: stories 18, 27; findings 4.10 #10, 4.2 #22; decision N2.

1. In `app/test/packaging.test.js`, replace the test `the version is a plain x.y.z in package.json and in ONE place only` (lines 18-34) with its successor (N2): (a) `ember/__init__.py` defines `__version__` (the ONE engine source); (b) `ember/cli.py` contains `from ember import __version__` (Chunk 1); (c) `pyproject.toml` declares `dynamic = ["version"]` with `attr = "ember.__version__"`; (d) `app/package.json` version is `x.y.z` and the known hardcoded app-version copies — exactly `docs/T50-live-test.md:3` and `:203` — still say that app version. Keep test 2 (`main.js reads the version from app.getVersion`, lines 36-41) untouched.
   Done when (of this step): the file still parses — `node --check app/test/packaging.test.js`.
2. Run `npm --prefix app test -- packaging`. Expect: failing — today `pyproject.toml:7` hardcodes `version = "0.1.0"`, not a dynamic attr.
3. In `pyproject.toml`, replace `version = "0.1.0"` (line 7) with `dynamic = ["version"]` and add `[tool.setuptools.dynamic]` `version = {attr = "ember.__version__"}`. This is a packaging-config change (no package added or removed, no code data touched); unset env and no database involved.
   Done when (of this step): `.venv/bin/pytest tests/test_cli_version.py` still passes and `.venv/bin/python -c "import ember; print(ember.__version__)"` prints `0.1.0`.

Proof it's real: revert `pyproject.toml` to the hardcoded `version = "0.1.0"` → assertion (c) goes red; undo.
Done when: `npm --prefix app test -- packaging` passes (5 tests) and `.venv/bin/ember --version` still prints `ember, version 0.1.0`.
Commit message: `Batch 1: one engine version source and a version pin test`

## Chunk 3 of 11: the runtime gate as its own script
Covers: stories 16, 28; findings 4.1 #10, 4.1 #20; decision N1; test seam 4; constitution I7/I21 (exact code, not prose).

1. Add a failing test `app/test/runtime-gate.test.js` (NEW): for each case, build a stub runtime folder in `/tmp/opencode/batch1/` containing a stub executable `ember` (a small shell script), then run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY bash app/scripts/gate-ember-runtime.sh <stub-dir>` (pioneered for the app test pattern by `app/test/fake-ember.js`). Stub behavior: on `capture ... --file ... --db ...` print nothing on stdout, write `error: CAPTURE-008 ... ai api key missing` on stderr and exit 1; on `db-check --db ... --format json` print lines containing `version: 13` and `result: OK` and exit 0 (this mirrors the real gate at `app/scripts/build-ember-runtime.sh:174-202`). Cases: (a) pass → gate exit 0; (b) a second stderr line → non-zero; (c) first line `error: CAPTURE-999` → non-zero; (d) a Python traceback line → non-zero; (e) gate on a missing runtime folder → non-zero with one clear message. Assert exit codes and log survival (gate log folder still present after a failure), never prose beyond the code.
2. Run `npm --prefix app test -- runtime-gate`. Expect: failing — `app/scripts/gate-ember-runtime.sh` does not exist.
3. Create `app/scripts/gate-ember-runtime.sh` (NEW): ONE argument = the runtime folder; moves the gate block out of `app/scripts/build-ember-runtime.sh:162-202` (the build keeps working until Chunk 5 wires it); requires the capture to exit 1 with EXACTLY ONE stderr line starting `error: CAPTURE-008` (fixes the any-`error:`-prefix acceptance at `:186-189` and the 200-byte truncation at `:184, :191`); requires db-check `version: 13` + `result: OK`; keeps its gate log folder on failure and prints the FULL error; cleans up its temp files only on success (fixes the log deletion by the build's trap at `:74-75`, finding 4.1 #20). Creates its own scratch under the same rule as the build (next to the runtime, or `/tmp/opencode/batch1/` for tests).

Proof it's real: temporarily loosen the script's check back to the old `"error: "*` prefix → case (c) goes red; undo.
Done when: `npm --prefix app test -- runtime-gate` passes (5 cases), and alone on sample input (S1): `bash app/scripts/gate-ember-runtime.sh /nonexistent` exits non-zero with one message line.
Commit message: `Batch 1: runtime gate as its own script (N1)`

## Chunk 4 of 11: build refuses bad paths and a weightless cache before the slow step
Covers: stories 7, 13, 14, 15; findings 4.1 #6, 4.1 #7, 4.1 #8.

1. Add a failing test `app/test/runtime-build.test.js` (NEW): a stub pack venv in `/tmp/opencode/batch1/` (`bin/python` = a `#!/bin/sh` script that exits 0, so the `check_pkg` probes at `app/scripts/build-ember-runtime.sh:50-55` and the torch check at `:59-66` pass without torch), then run `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY EMBER_PACK_VENV=<stub venv> bash app/scripts/build-ember-runtime.sh` with: (a) `EMBER_RUNTIME_OUT=relative-path` → non-zero, refusal BEFORE any output folder is created (story 14); (b) `EMBER_RUNTIME_OUT=<temp out>`, `EMBER_MODEL_CACHE=<temp holding a foreign models--* tree with no models--BAAI--bge-base-en-v1.5 / model.safetensors>` → non-zero naming the model (story 13); (c) `EMBER_RUNTIME_OUT=/` → non-zero and `/` untouched (story 15 — no `rm -rf` on an unchecked path).
2. Run `npm --prefix app test -- runtime-build`. Expect: failing — today `:41` accepts a relative path raw, `:126` `ls ... | grep -q "^models--"` accepts ANY model cache (`MODEL_ID` at `:43` is never used), and `:112` `rm -rf "$RUNTIME_OUT"` runs unguarded.
3. Edit `app/scripts/build-ember-runtime.sh`: canonicalize `RUNTIME_OUT` at the top (line 41) and refuse an empty, relative or unsafe path (for example `/` or the repo root) before anything else; refuse unless `EMBER_MODEL_CACHE` (when set) holds `models--BAAI--bge-base-en-v1.5` with a `model.safetensors`, using `MODEL_ID` (line 43), replacing the bare `grep -q "^models--"` (line 126); these refusals run before the PyInstaller call (line 93) and before the `rm -rf "$RUNTIME_OUT"` (line 112).

Proof it's real: change the new model check back to `grep -q "^models--"` → case (b) goes red; undo.
Done when: `npm --prefix app test -- runtime-build` shows the three refusal cases green; and on the bench: `env -u EMBER_AI_API_KEY EMBER_PACK_VENV=<stub venv> EMBER_RUNTIME_OUT=relative bash app/scripts/build-ember-runtime.sh` exits non-zero within seconds (no 20-minute build started).
Commit message: `Batch 1: runtime build refuses bad paths and a weightless cache`

## Chunk 5 of 11: build runs the gate in the scratch dir, then swaps — old runtime survives failure
Covers: stories 11, 12 (build side), 21 (build side), 22; findings 4.1 #5, 4.1 #9.

1. Extend `app/test/runtime-build.test.js`: add a stub `bin/pyinstaller` to the stub venv (it creates `<distpath>/ember-runtime/ember-runtime` as a stub `ember` answering `--help`, the gate capture, `db-check`, and `--version`) plus a fixture model cache (`models--BAAI--bge-base-en-v1.5/snapshots/<sha>/model.safetensors`, snapshot layout as in the real hub). Cases: (d) happy path — build exit 0, `<out>/ember` exists and runs, `<out>/models/hub` carries the weights, a gate-passed marker file (`.gate-ok`) exists in `<out>`; (e) the stub `ember` fails the gate (wrong capture code) → build non-zero, `.gate-ok` absent, and a canary file pre-placed inside the OLD `<out>` is STILL THERE (story 11).
2. Run `npm --prefix app test -- runtime-build`. Expect: (d) fails (no marker, gate not called there) and (e) fails (today `:112` deletes the old runtime BEFORE the gate at `:174-202`, so the canary is gone).
3. Edit `app/scripts/build-ember-runtime.sh`: build the PyInstaller onedir into the scratch dir (`BUILD_DIR`, line 74) and copy the weights there; run `bash "$SCRIPT_DIR/gate-ember-runtime.sh" "$BUILD_DIR/dist/..."` BEFORE touching `$RUNTIME_OUT`; write `.gate-ok` only after the gate passes; only then remove the old `$RUNTIME_OUT` and move the new tree in (marker included); drop the dead smoke at line 160 — `"$RUNTIME_OUT/ember" --version > /dev/null || true` becomes a real call without `|| true` (it works since Chunk 1; fixes 4.1 #9).
   Done when (of this step): `npm --prefix app test -- runtime-build` — (d) and (e) green, canary intact.

Proof it's real: in the script, write `.gate-ok` BEFORE the gate call → case (e) goes red (marker present despite a failed gate); undo.
Done when: `npm --prefix app test -- runtime-build` passes (5 cases) and the stub build completes in seconds, no torch, no PyInstaller on the machine.
Commit message: `Batch 1: replace the runtime only after the gate passes`

## Chunk 6 of 11: retire the F1 text-grep test
Covers: story 26; finding 4.2 #4 (the grep-script-text test replaced by behavior tests).

1. Delete the test `the runtime build bundles the migrations package and runs the F1 build gate` from `app/test/packaging.test.js` (lines 67-91). Its needles moved with the gate in Chunk 5 and its subject is now covered by behavior tests in `runtime-gate.test.js` and `runtime-build.test.js` (migrations presence is proven by the gate's real `db-check` in the stub flow plus Pack Chunk's fixture flow; the Batch 2 rebuild re-proves it for real).
   Done when (of this step, a deletion): `git diff --stat` shows only `app/test/packaging.test.js` lost lines, and `npm --prefix app test -- packaging` passes with 4 tests.
2. Run `npm --prefix app test` (whole app suite). Expect: all green, nothing else changed.

Proof it's real: F1-class proof — temporarily make the stub `ember` in `runtime-gate.test.js` print a traceback → that suite goes red (the crash class is still caught without the deleted text test); undo.
Done when: `npm --prefix app test` passes; `npm --prefix app test -- packaging` reports 4 tests (was 5).
Commit message: `Batch 1: replace the F1 text-grep test with behavior tests`

## Chunk 7 of 11: bundle hygiene — no `__pycache__`, size report can't fail the build, pipefail-safe trims
Covers: stories 23, 24, 25; findings 4.1 #19, 4.1 #21, 4.1 #22.

1. Extend `app/test/runtime-build.test.js` with: (f) after the happy-path build, NO folder named `__pycache__` exists anywhere under `<out>` (the real `--add-data` at `app/scripts/build-ember-runtime.sh:109` copies `ember/adapters/migrations/__pycache__` — confirmed by `ls ember/adapters/migrations/`; the stub pyinstaller simulates one inside its dist); (g) with a fake `du` placed earlier on `PATH` that always exits 1, the build still exits 0 (story 24).
2. Run `npm --prefix app test -- runtime-build`. Expect: (f) red (the copy keeps `__pycache__` today), (g) red (the last `du -sm ... || du -sm ...` at `:205-206` still fails under `set -e` when both calls fail).
3. Edit `app/scripts/build-ember-runtime.sh`: after the weights copy, delete every `__pycache__` folder from the runtime tree (finding 4.1 #21, story 23); make the closing size report (lines 204-206) never change the exit code (you can drop or guard the whole block — the report is informative, finding 4.1 #22); rewrite the symlink/blob trim loops (`:139-146`) so no `grep -q` runs under `pipefail` (SIGPIPE can invert the result and delete a needed link, finding 4.1 #19, story 25).

Proof it's real: comment out the new `__pycache__` purge in the script → case (f) goes red; undo.
Done when: `npm --prefix app test -- runtime-build` passes (7 cases); `find <out> -name __pycache__` (the test's own output folder, printed by the test) prints nothing.
Commit message: `Batch 1: bundle hygiene (no pycache, safe size report, pipefail-safe trims)`

## Chunk 8 of 11: the packer's staging step becomes a testable seam
Covers: stories 1, 2, 3, 12 (packer side), 19, 21 (packer side); findings 4.1 #1, 4.1 #2, 4.1 #15, 4.1 #18; decision D-19; test seam 2.

1. Add a failing test `app/test/pack-staging.test.js` (NEW): requires the NEW exported staging function from `app/scripts/pack.js` on a small fixture tree in `/tmp/opencode/batch1/` (a relative symlink `link -> real-file`, a mode-777 regular file, a mode-777 executable, a subdirectory). Cases: (a) the staged tree's link is still relative (`readlink` gives a relative target — fixes `verbatimSymlinks: false` at `pack.js:42`, finding 4.1 #1); (b) no staged file is world-writable: files 0644, executables 0755, dirs 0755, and the packer REFUSES a mixed-in world-writable file (fixes 4.1 #2; `chrome-sandbox` itself stays 0755 in the stage — the postinst at `pack.js:121-127` sets setuid 4755 at install); (c) staging refuses a runtime folder WITHOUT the `.gate-ok` marker (story 12); (d) staging refuses when the machine is not amd64 (stub the arch input, D-19, finding 4.1 #15); (e) staging reads the runtime from the ONE location the build reports (`EMBER_RUNTIME_OUT`, `pack.js:60`, finding 4.1 #18 — the test passes it explicitly). Also assert: merely requiring the module builds nothing (no `dist/ember-app` created).
2. Run `npm --prefix app test -- pack-staging`. Expect: failing — `pack.js` exports nothing; today it is one `main()` with fixed inputs (`pack.js:49-119`) and runs at load (`pack.js:215-219`).
3. Refactor `app/scripts/pack.js`: export the staging step as a function (fixture tree + runtime dir as arguments, per seam 2); copy with `verbatimSymlinks: true`; normalize modes while staging (dirs 0755, executables 0755, other files 0644); before handing to `dpkg-deb --build` (line 184), assert no staged file is world-writable and refuse otherwise; require `.gate-ok` on the runtime; refuse unless the build machine is amd64 (check the machine, not the label — e.g. `dpkg --print-architecture`); keep writing `bundle.json` for now; guard `main()` behind `if (require.main === module)` so `npm --prefix app run package` is unchanged.

Proof it's real: set `verbatimSymlinks` back to `false` → case (a) goes red; undo.
Done when: `npm --prefix app test -- pack-staging` passes (6 assertions across cases a-e + loader-only) and `npm --prefix app test` (whole suite) stays green.
Commit message: `Batch 1: packer stages verbatim symlinks, safe modes, marked runtime (amd64 only)`

## Chunk 9 of 11: `bundle.json` records both versions + a content hash; `Depends` gains the four libs
Covers: stories 18, 20; findings 4.1 #16, 4.1 #17.

1. Extend `app/test/pack-staging.test.js`: (f) the staged `bundle.json` records the app version from `app/package.json`, the engine version from `ember/__init__.py` (may differ — that is the spec's rule), and a deterministic content hash of the runtime tree; the test recomputes the hash and compares (finding 4.1 #16); (g) the NEW exported control-builder function's `Depends:` line contains `libnotify4`, `libatspi2.0-0`, `libuuid1`, `libsecret-1-0` beside today's list at `pack.js:137` (finding 4.1 #17, story 20 — `libsecret-1-0` is what safeStorage needs). This checks the function's output (data), not grep over script text.
2. Run `npm --prefix app test -- pack-staging`. Expect: failing — `bundle.json` (written at `pack.js:101-108`) records only `{kind, version, emberRuntime, model}` and the control string lists none of the four libs.
3. Edit `app/scripts/pack.js`: add `engineVersion` (read from `ember/__init__.py`) and a runtime content hash to `bundle.json`; export a small control-builder function used by `main()` and add the four libs to its `Depends` list.

Proof it's real: remove `libsecret-1-0` from the new list → case (g) goes red; undo.
Done when: `npm --prefix app test -- pack-staging` passes; the test's printed staged `bundle.json` shows `engineVersion: "0.1.0"`, the app version, and a hash.
Commit message: `Batch 1: bundle.json carries both versions + hash; Depends gains 4 libs`

## Chunk 10 of 11: the `.deb` check script
Covers: stories 3 (check side), 4, 5, 6, 7 (check side), 8, 9, 10, 26 (check side); decisions D-11, D-12, D-21; implementation-check decision I12; finding 4.2 #5; test seam 1; constitution S1.

1. Add a failing test `app/test/check-deb.test.js` (NEW): builds tiny fixture packages with `dpkg-deb --build` in `/tmp/opencode/batch1/` (no fakeroot — the check reads modes, not ownership; `dpkg-deb` is standard on the CI runners, `dpkg-deb` is already used by `pack.js:184`). Fixtures: (a) clean (has relative symlinks only, no 777 files, one `001_create_sources.sql`-style `.sql` file at the migrations path, a dummy `model.safetensors`, `Architecture: amd64`) → check exit 0 and a dated report written; (b) one absolute symlink pointing at `/home/mo/lab/ember/...` → non-zero naming the link; (c) one world-writable regular file → non-zero; (d) migrations `.sql` files missing → non-zero; (e) `model.safetensors` missing under the hub path → non-zero; (f) control `Architecture: arm64` → non-zero; (g) retention + save policy: after 4 passing checks in the release folder, exactly the 3 newest `.deb`s + reports remain and the oldest is deleted (D-21); a failing check saves the report but NOT the `.deb` (D-12).
2. Run `npm --prefix app test -- check-deb`. Expect: failing — the script does not exist.
3. Create `app/scripts/check-deb.sh` (NEW): one argument = a `.deb` path; inspects with `dpkg-deb --info` + `--contents` (plus a real extraction of modes via `dpkg-deb` output parsing); refuses when: a symlink target leaves the package — this includes any link to a system path such as `/usr/lib/...`, not only links to build-box paths; every library is bundled (DECIDED, I12 from the implementation-plan check) —, any regular file is world-writable, the runtime's migrations path lacks `.sql` files, `models/hub` lacks a `model.safetensors`, or the control `Architecture:` is not `amd64`; writes a dated report next to each check; on PASS saves the `.deb` + report into `app/dist/release/` (gitignored — confirmed: `git check-ignore app/dist/release/x.deb` → `.gitignore:28 dist/`) and deletes builds beyond the newest 3; on FAIL exits non-zero and never saves the `.deb`. Runs alone on any `.deb` (S1) and is NOT run in CI (D-11).

Proof it's real: temporarily delete the world-writable rule from the script → fixture (c) passes → test red; undo.
Done when: `npm --prefix app test -- check-deb` passes (7 cases); and the visible proof on the real bad package: `bash app/scripts/check-deb.sh app/dist/ember-app_0.2.0-1_amd64.deb` exits non-zero listing the 22 absolute links and 70 world-writable files (the existing artifact is untouched, read-only inspection).
Commit message: `Batch 1: .deb check script (D-11, D-12, D-21)`

## Chunk 11 of 11: the pack ends with the check
Covers: stories 4, 9, 10 (wiring); D-11, D-12, D-21 wiring.

1. In `app/scripts/pack.js`, `main()`: after `dpkg-deb --build` (line 184), run `bash "$APP_ROOT/scripts/check-deb.sh" "<built deb path>"` so a failed check fails the pack (the existing `try/catch` → `fail()` at `pack.js:215-219` turns the child's non-zero exit into a pack failure).
2. Run `npm --prefix app test` (whole app suite). Expect: all green.
3. Run `.venv/bin/pytest tests/test_cli_version.py tests/test_architecture.py`. Expect: all green (the Python side untouched since Chunk 2).

Proof it's real: point the packer at a runtime folder with the marker deleted → `npm --prefix app run package` exits non-zero naming the marker (pack-staging case c proves the same rule; the full-pack break is the bench variant, no 20-minute build needed for the refusal since it fires before PyInstaller).
Done when: `npm --prefix app test` all green; the wiring's real-build proof is the founder's manual build in the Final check (a full pack needs `EMBER_PACK_VENV` + `EMBER_MODEL_CACHE` and ~20 minutes — Not covered by tests).
Commit message: `Batch 1: the pack ends with the .deb check`

---

## Final check
- All green, exactly as typed:
  - `.venv/bin/pytest` (whole Python suite; `-q -m 'not live'` from `pyproject.toml:33`)
  - `npm --prefix app test` (whole app suite, including the four new files)
- The batch's "Done when" from archive/Plan.md line 127: *"the check script passes on a fresh build, and fails on a .deb with one planted absolute link and one planted world-writable file."*
  - Fresh build (founder, ~20 min): with `EMBER_PACK_VENV` (a COPY of the venv with CPU torch + pyinstaller — never the maintainer's `.venv`) and `EMBER_MODEL_CACHE` set, run `bash app/scripts/build-ember-runtime.sh`, then `npm --prefix app run package`. Expected: the pack ends with `check-deb` passing, and `ls app/dist/release/` shows 1 `.deb` + 1 dated report.
  - Planted bad `.deb`: `npm --prefix app test -- check-deb` — fixtures (b) and (c) are exactly "one planted absolute link" and "one planted world-writable file"; both fail the check with their named reasons. Zero-setup variant on the existing artifact: `bash app/scripts/check-deb.sh app/dist/ember-app_0.2.0-1_amd64.deb` → non-zero (the shipped 0.2.0 has 22 links + 70 777 files).
- Keep-3 promise visible: after building 4 times across the batch, `ls app/dist/release/*.deb | wc -l` prints `3` (D-21).

## Unknowns
- **Batch 0 merge state.** D-29 now fixes the branch rule for every batch: `batch-N` cut from where the previous batch merged, merged into `ember-interface` when the batch's "Done when" passes. What is still not known: where Batch 0 actually stands right now (it merges onto `ember-interface`). Check its state before cutting `batch-1`; if Batch 0 has not merged yet, cut `batch-1` from `ember-interface` after it does.
- **Names chosen by this plan, not fixed by the spec:** the gate script `app/scripts/gate-ember-runtime.sh` (spec offers this as "for example"), the marker file `.gate-ok`, the check script `app/scripts/check-deb.sh`, the release folder `app/dist/release/` (any folder under `dist/` is gitignored via `.gitignore:28`; re-verify with `git check-ignore`), and the new test file names `tests/test_cli_version.py`, `app/test/runtime-gate.test.js`, `app/test/runtime-build.test.js`, `app/test/pack-staging.test.js`, `app/test/check-deb.test.js`. All are NEW; nothing by these names exists today (checked by glob and read).
- **Click's exact `--version` output** (`ember, version 0.1.0`) follows click 8.5.0's standard template; click 8.5.0 confirmed installed, but the exact string was not executed. The test asserts only that `__version__` appears and exit is 0.
- **The gate's expected code after Batch 2.** The gate pins `error: CAPTURE-008` for the no-key capture. archive/spec-check-batch1.md section 4 flags: if Batch 2's `EMBER-000` handling changes the no-key path's code, re-check this rule in Batch 2.
- **Not covered by tests:** the full real build (`build-ember-runtime.sh` with real torch + PyInstaller, then `npm run package`) — needs ~20 min, `EMBER_PACK_VENV` and `EMBER_MODEL_CACHE`, and is the founder's manual check in the Final check. Everything else above has an automated test or a seconds-long bench command.

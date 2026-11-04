# Ember fix plan (T50)

**Date:** 2026-11-01
**Source:** `archive/Problems.md`, the ten-area review at tip `3b84663` on `ember-interface`.
**Rules:** `Constitution.md`. Every batch must follow it.
**Status:** planning only. No code was changed. Four assumptions were checked read-only against the repo (section 6).

---

## 1. Summary

- **Scope:** every finding in the report. That is 192 code findings plus 4 design findings, 196 in total. The report says "~168". The real count is higher. [Fact: counted per section]
- **Order:** safety first, then the release, then the error boundary, then the three UI steps already approved. Data integrity, screen lifetime, wording, AI limits, speed, and test hygiene follow.
- **Shape:** 10 batches. Each batch has a goal, its findings by report number, and a "Done when" check.
- **How to read the numbers:** `4.3 #7` means report section 4.3 (adapters), item 7. `11 #2` means the design audit, item 2.

---

## 2. Decisions

Each line is one settled decision. "Rec" means it was the recommended option.

| ID | Decision | Answer |
|---|---|---|
| D-01 | Fix order | A. Safety and release blockers first, rebuild and verify the .deb, then the approved Steps 2-4. (Rec) |
| D-02 | Who installs the .deb in ~2 months | Other people, soon. All packaging fixes are in scope. (Rec) |
| D-03 | Two processes writing one database | Yes. A coding agent may run `ember` while the user works in the app. Plan full multi-writer safety. |
| D-04 | Where the plan lives | This file, next to Problems.md in `archive/`. (Rec) |
| D-05 | Which findings | Everything. All 196. |
| D-06 | Unexpected Python error | One short error line `EMBER-000` with where it broke. Full trace, secrets removed, saved to a crash file. Non-zero exit. (Rec) |
| D-07 | Raw note after every item is rejected | Keep it, because the constitution says keep raw input. Add "Forget this note" in the app interface, not only as a command. |
| D-08 | How the app finds error sentences | One sentence table in the app, looked up by error code only. Where the app now matches Python's wording, Python raises a new separate code. A test checks every code has exactly one sentence. (Rec) |
| D-09 | Where "Forget this note" appears | On the Add screen right after all items are rejected, and in a "Notes with no items" list in Cleanup. (Rec) |
| D-10 | Is forgetting permanent | Yes. Inline "Forget for good?" confirm. Undo cannot bring it back. The confirm says older backup copies still hold the text. (Rec) |
| D-11 | Where the .deb is checked | A local check script only. No CI build. |
| D-12 | What the check keeps | Both the .deb and its check report, in one gitignored folder inside the repo. |
| D-13 | Screen tests (e2e) in CI | Yes, on a virtual screen (xvfb), with fake AI and a temp config. (Rec) |
| D-14 | First run and the key box (F7c, F7d) | First run has 2 steps. The third step is removed. One key box, with an eye icon inside the field, replaces both Show/Hide buttons. |
| D-15 | Knowledge base size target | Up to about 10k items. Keep the current search, rewrite it to score in one pass. Target under 1 s at 10k. (Rec) |
| D-16 | What the app shows for a crash | "Copy crash report" and "Show file" under Details. (Rec) |
| D-17 | Search matching | Same text in any case matches, including text typed in different hidden encodings. Accents still count: `cafe` does not find `café`. (Rec) |
| D-18 | "No" on a suggested link pair | The button says "No, don't suggest again" (changed by N16). No undo for it. (Rec) |
| D-19 | Machine type for the .deb | amd64 only. The packer refuses to build anywhere else. (Rec) |
| D-20 | `--format json` on capture and relate | Refuse the flag with a clear error. (Rec) |
| D-21 | How many .debs the release folder keeps | The last 3, about 1.6 GB. The check script deletes older ones. (Rec) |
| D-22 | Key wizard platforms | Linux only. Remove the "cross-platform incl. WSL" claim and the WSL, Windows and macOS opener branches. Follows from checked fact 3. |
| D-23 | Test seams for Batches 1-9 | Only existing entry points: the `ember` CLI on temp databases, the bridge client with a fake engine, app e2e under xvfb with a fake engine. Batch 1 adds the packer and the .deb check script. (Rec) |
| D-24 | Closing the main window | Ember keeps running in the tray. Shortcut and tray keep working. "Open Ember" reopens the window. Quit from the tray menu. (Rec) |
| D-25 | Creating a new knowledge base | A separate `ember init --db PATH` command. Every other command refuses a missing file. The app runs init when the first Add needs it. (Rec) |
| D-26 | History after a note is forgotten | One line with the note id and date, no text. Nothing of the note or its AI reply is kept. (Rec) |

### Decisions from the spec check (2026-11-01)

From `archive/spec-check-all.md` and the per-batch reports. The founder accepted every pick below.

| ID | Batch | Decision |
|---|---|---|
| N1 | 1 | Move the runtime build gate into its own script, called by the build and by tests. |
| N2 | 1 | Keep a version test in Batch 1. It checks the one engine source, `app/package.json`, and a fixed list of known copies (fixed or allow-listed). |
| N3 | 5 | The app's own Stop shows "Stopped", no error. Any other kill, or an exit with no result, gets one new app code meaning "Ember stopped unexpectedly". 4.4 #10 moves from Batch 2 to Batch 5. Batch 6's "stop during preparation" uses the same mechanism. |
| N4 | 2 | Crash files go in `$XDG_STATE_HOME/ember/crashes`, default `~/.local/state/ember/crashes`, on both the engine and app side. |
| N5 | 2 | Batch 2's e2e tests the crash sentence and both buttons on the Add screen. Batch 3 does not re-test them. |
| N6 | 2 | CLI usage errors keep click's exit 2 with no code. Story 16 covers engine failures only. |
| N7 | 2 | Error context shows only the file name, never the full path. The crash file keeps the full path. |
| N8 | 4 | `init` succeeds on an existing, healthy, current Ember database. It refuses a non-Ember file or an older version. |
| N9 | 4 | Relate reads through a read-only connection. A short-lived write connection saves cache vectors and the raw AI reply. Relate never migrates. |
| N10 | 4 | Item ids are still shown before saving. Allocation, insert and ledger row run in one `BEGIN IMMEDIATE` transaction, with retry on id conflict. Edits stop taking a new id. |
| N11 | 5 | New engine option returns all four Home counts in one call. |
| N12 | 5 | A small check inside the app test runner fails test files with un-awaited subtests. No new dependency. |
| N13 | 5 | The engine's stdin reader caps line length and maps decode errors to a house code. |
| N14 | 6 | A new migration adds an optional `source_id` column to the change log, for the forgotten-note line. The migration number goes to whichever of Batch 6 or 7 lands first. |
| N15 | 6 | The sentence-table test keeps today's file scan as the engine's code list. |
| N16 | 6 | Link's reject button says "No, don't suggest again". D-18 updated. |
| N17 | 6 | Off-scale text sizes are folded into DESIGN.md's five named styles. The doc stays the rule. |
| N18 | 7 | New codes for "AI rate-limited" and "AI timed out" in each family that calls AI. Each gets a sentence in Batch 6's table. |
| N19 | 7 | Choices are parsed only from the three known prompt constants. Any other prompt is kind "unknown" and fails loudly. |
| N20 | 7 | Query vectors pass through the same float32 format as the cache. No schema change. |
| N21 | 7 | The embedder checks the local model cache before loading and fails at once if missing. The "thread stops" wording is replaced by "the load never starts". |
| N22 | 8 | The `İstanbul` split stays and is documented as a known limit. |
| N23 | 8 | Batch size 32 as a constant. Tune after the 2,000-item check. |
| N24 | 9 | Correct the 4 wrong contrast numbers in DESIGN.md. Colors unchanged. |
| B3-1 | 3 | One notice per error code replaces the per-block cards on Home. Its "Try again" reloads Home. |
| B7-D5 | 7 | Empty input gets a new capture code. Oversized stdin reuses the existing "too large" code. |
| D-27 | All | Every new error code takes the next free number in its family when its batch is implemented. Numbers are never reused. Example: "Ember stopped unexpectedly" becomes APP-009 if that is still free. |
| D-28 | All | Specs (`docs/Spec-Batch*.md`) and implementation plans (`plans/Impl-Batch*.md`) are committed, each with a `PROJECT_MAP.md` line in the same commit. |
| D-29 | All | Each batch on its own branch `batch-N`, cut from where the previous batch merged, merged into `ember-interface` when its "Done when" passes. |

### Decisions from the implementation-plan check (2026-11-01)

From `plans/impl-plans-check.md`. Accepted by the founder.

| ID | Batch | Decision |
|---|---|---|
| I1 | 2, 7 | Batch 2 keeps CAPTURE-017 to 019. Batch 7 takes the next free numbers when built (D-27). Plans do not pin numbers in advance. |
| I2 | 0, 4, 9 | The founder installs xvfb locally. e2e and launch checks run under `xvfb-run`. |
| I3 | 9 | DESIGN.md's `4.2:1` becomes `4.3:1` (real value 4.25), on top of N24. |
| I4 | 0 | Every test that leaks temp folders gets cleanup, not only the two named in the report. |
| I5 | 0 | Seam 1 gets an automated test that no AI key reaches the harness child. No manual-only check. |
| I6 | 3 | The banner component gets a testid option. The Home failure notice uses it. |
| I7 | 3 | The e2e checks the count number and codes only, never the "N blocks" wording. |
| I8 | 4 | `PRAGMA busy_timeout` set explicitly to 5000 ms on every connection. Relate's write connection also saves confirmed links. |
| I9 | 5 | New app code `APP-009 EmberStoppedUnexpectedly`. Engine option `list-items --counts`. |
| I10 | 6 | The sentence table's own unit tests may check wording. All other tests check codes only. |
| I11 | 7 | Long chunks are split to the 3-step rule. The hung-provider test is marked slow, skipped locally, run in CI. The 3-word and 40-candidate values are tuned after the batch. |
| I12 | 1 | The .deb check refuses any symlink to a system path. Everything is bundled. |
| I13 | 0 | The key wizard sets owner-only permissions before writing the key, so no 644 window exists. |

### What the constitution changed

These were read from Constitution.md and applied without a separate question. Each one is my reading of the rule. [Inference]

- **Raw notes are correct to keep.** The rule "store original input untouched" means report item 4.5 #6 is a wording bug, not a storage bug. D-07 builds on this.
- **Crashes stay loud.** The rule "code bugs crash loudly" is why D-06 keeps the full trace in a file instead of hiding it.
- **Error names come from code.** The rule "module and function name injected into the error, never a hardcoded string" makes 4.10 #11 required, not cosmetic.
- **Retries need backoff.** The rule "external services: timeout, retry limit with backoff" makes 4.5 #10 required.
- **No secrets in errors.** The rule "zero secrets in errors" makes 4.3 #23 and 4.10 #4 required.
- **Tests check behavior and codes, not wording.** This makes 4.2 #4 (packaging test greps script text) and 4.10 #7 (app matches Python's words) required. It also means `add-session.test.js:180`, which pins the sentence "nothing was half-written", must assert a code or an outcome instead.
- **Inject dependencies.** The rule "inject DB, clock, clients" makes 4.2 #11 (launch check reads the real config) required.
- **One error handler at the edge.** cli.py has 19 copies of the same error block (4.10 #13). The rule "handle errors at the edge, not in core" plus the warning sign "multi-file edits for one change" mean Batch 2 collapses them into one handler.
- **No boolean behavior flags in functions.** The dry-run fix uses a separate preview function, not a `dry_run=True` parameter. The CLI flag `--dry-run` itself stays.

---

## 3. Batches

### Batch 0. Stop the bleeding

**Goal:** no test can spend money or read your real key. No script can delete a real knowledge base. The test suite stops flaking.

- Tests that touch real secrets: 4.2 #10, 4.2 #11, 4.2 #20.
- Script that deletes a real database: 4.1 #3, 4.1 #4, 4.1 #23, 4.1 #24.
- Key wizard file safety: 4.1 #11, 4.1 #12, 4.1 #13, 4.1 #14. For 4.1 #13, apply D-22: make the script Linux-only rather than portable.
- Flaky timing and leaky temp dirs: 4.2 #1, 4.2 #2, 4.2 #3, 4.2 #23.

**Done when:**
- The cleanup e2e and launch check run with no AI key in their environment and a temp config folder.
- `measure_model_change.py --db <existing real file>` refuses and exits non-zero.
- The app suite passes 5 runs in a row with zero failures.

### Batch 1. Release artifact

**Goal:** a .deb anyone with an amd64 machine can install safely.

- Packer: 4.1 #1, 4.1 #2, 4.1 #15 (now: refuse non-amd64, D-19), 4.1 #16, 4.1 #17, 4.1 #18.
- Runtime build script: 4.1 #5, 4.1 #6, 4.1 #7, 4.1 #8, 4.1 #9, 4.1 #10, 4.1 #19, 4.1 #20, 4.1 #21, 4.1 #22.
- Version sources: 4.10 #10. One version source and a real `ember --version`, which the build script's dead version call needs.
- Tests that prove nothing: 4.2 #4, 4.2 #5, 4.2 #22.
- **New:** a local `.deb` check script (D-11). It checks for links pointing at build-box paths, world-writable files, migration `.sql` files, model weights, and the correct architecture. It saves the .deb and a dated report in one gitignored repo folder (D-12), and keeps only the last 3 builds (D-21). One .deb is about 540 MB, model included. [Fact: checked fact 2]

**Done when:** the check script passes on a fresh build, and fails on a .deb with one planted absolute link and one planted world-writable file.

### Batch 2. Error boundary

**Goal:** no Python traceback ever reaches a user as "unreadable answer".

- One edge handler and the crash file (D-06, D-16): 4.10 #2, 4.10 #13, 4.4 #3. (4.4 #10 moved to Batch 5 by N3.)
- Paths that crash today: 4.5 #1, 4.5 #3, 4.5 #4, 4.3 #4, 4.3 #6, 4.3 #11, 4.3 #24, 4.6 #12, 4.10 #15, 4.10 #17.
- Error content: 4.10 #4, 4.10 #11, 4.3 #23.
- Wrong or hidden cause: 4.7 #7, 4.10 #16.
- **New:** `EMBER-000 InternalError` gets a sentence. Crash file path and the "Copy crash report" and "Show file" buttons in Details.

**Then:** rebuild the .deb and run the Batch 1 check script. This closes decision A.

**Done when:** the five crash paths in report section 6 (bad `--db`, non-SQLite file, corrupt UTF-8, bad base URL, unpaired surrogate) each produce exactly one stderr line with a house code, a non-zero exit, and, for `EMBER-000`, a crash file with no secrets.

### Batch 3. The approved Steps 2-4

**Goal:** the three UI fixes already approved before this review.

- Real error text on Add: covered by Batch 2. This batch adds the screen side.
- F2, failed Add returns to the form with the text: 4.9 #11, 4.2 #9.
- F4, one notice when blocks fail with the same code: 4.2 #8.

**Done when:** an e2e test fails Add on purpose and finds the form with the original text. Another fails three blocks with one code and finds exactly one notice.

### Batch 4. Data integrity and multi-writer safety

**Goal:** one user action is one transaction. Two writers at once (D-03) never corrupt, merge, or lose anything. `db-check` checks rules, not just names.

- Dry-run writes: 4.6 #2 and 4.10 #1 (same finding), 4.10 #5, 4.8 #12, 4.7 #8.
- Wrong file silently created: 4.10 #8.
- One action, one transaction: 4.3 #9 and 4.5 #2 (same finding), 4.6 #1, 4.4 #4, 4.6 #3.
- Migration safety: 4.3 #1, 4.3 #2, 4.3 #5, 4.3 #18, 4.7 #1.
- Health check (`db-check`): 4.3 #7, 4.3 #8, 4.3 #12.
- Backups and export: 4.3 #3, 4.3 #10, 4.3 #13, 4.3 #14, 4.3 #15, 4.3 #16, 4.3 #28, 4.3 #29, 4.5 #17.
- Two writers: 4.3 #19 and 4.6 #4 (same race), 4.3 #20, 4.3 #22, 4.5 #11, 4.6 #5.
- Reads that race a write: 4.7 #2.
- Smaller engine correctness: 4.3 #21, 4.3 #30, 4.5 #7, 4.5 #12, 4.5 #13, 4.5 #14, 4.5 #18, 4.6 #6, 4.6 #7, 4.6 #8, 4.6 #11, 4.7 #9, 4.7 #10, 4.7 #11.

**Done when:** the report's own repros all fail safe. Four and eight threads opening a new file all succeed, none crashes, and the file ends at version 13. Today every round ends at version 13 but 3 of 4 openers crash, so the "no crash" part is the real test. [Fact: checked fact 1] Four parallel `capture` runs on a fresh path also all succeed. A dropped migration file makes `db-check` say not OK. A forced ledger failure leaves no item behind. Dry-run leaves the file hash unchanged. Two writers adding at once both succeed with different ids and separate undo groups.

### Batch 5. Bridge and screen lifetime

**Goal:** a late result never paints over the screen you moved to. The app never crashes or runs twice in the background.

- **First:** run e2e in CI on a virtual screen (D-13): 4.2 #6. The fixes below then have coverage.
- **Blocker for that step:** CI's `app-launch-check (ubuntu-latest)` already fails today on Electron's sandbox helper (`chrome-sandbox` needs root-owned mode 4755). [Fact: checked fact 4, latest run on `ember-interface`] E2e on CI will hit the same wall. Fix it in CI setup first, by giving `chrome-sandbox` the right owner and mode in the job. Do not turn the sandbox off in the shipped app.
- Bridge reading: 4.4 #1, 4.4 #10 (moved here by N3), 4.4 #2, 4.4 #5, 4.4 #6, 4.4 #7, 4.4 #8, 4.4 #9, 4.4 #11, 4.4 #12, 4.4 #13 and 4.10 #14 (same finding), 4.4 #14.
- F5 and screen lifetime: 4.9 #1, 4.9 #2, 4.9 #3, 4.9 #4, 4.9 #5, 4.9 #10, 4.9 #12, 4.9 #13, 4.2 #7.
- Shortcut pile and background process: 4.9 #6, 4.9 #7, 4.9 #8.
- Safety in the window: 4.9 #15, 4.9 #16, 4.9 #17, 4.9 #18, 4.9 #19.
- Smaller app fixes: 4.9 #14, 4.9 #20, 4.9 #24, 4.9 #25.
- Untested caps: 4.2 #14, 4.2 #24.

**Done when:** an e2e test opens Keep safe, switches to Settings within 200 ms, and Settings is still on screen after the health check returns. A second app launch focuses the first window instead of starting a new process.

### Batch 6. Wording and new interface features

**Goal:** every error has one sentence, found by code. The new features from this planning session exist.

- One sentence table by code (D-08): 4.10 #3, 4.10 #7, 4.10 #12, 4.6 #9, 4.6 #10, 4.8 #3, 4.7 #4, 4.7 #14, 4.3 #26.
- Forget this note (D-07, D-09, D-10): 4.5 #6. Engine command plus the Add button plus the Cleanup list.
- First run and key box (D-14): 4.9 #9, plus F7c and F7d. F7a is 4.9 #22.
- Link "no" says what it does (D-18): 4.8 #11.
- Stop during preparation is not a crash: 4.8 #4, 4.8 #10.
- History and search display: 4.7 #5, 4.7 #13.
- CLI honesty: 4.5 #8 and 4.10 #9 (same finding, D-20), 4.10 #6, 4.6 #13.
- Small screen fixes: 4.9 #21, 4.9 #23.
- Design audit: 11 #1, 11 #2, 11 #3, 11 #4.

**Done when:** the registry test passes with zero codes falling back to a family sentence. An e2e test rejects every item, forgets the note, and export no longer contains it.

### Batch 7. AI calls and input limits

**Goal:** AI calls have backoff, real timeouts below the app's limit, and bounded input.

- Capture: 4.5 #5, 4.5 #9, 4.5 #10, 4.5 #15, 4.5 #16, 4.5 #19.
- Adapters: 4.3 #17, 4.3 #25, 4.3 #27.
- Relate pool and cache: 4.8 #5, 4.8 #6, 4.8 #7, 4.8 #8, 4.8 #9.
- AI test gaps: 4.2 #12, 4.2 #13.

**Done when:** a fake provider returning 429 twice shows a wait between attempts, and a hung provider is reported as the engine's own timeout code, not the app's idle timeout.

### Batch 8. Performance

**Goal:** search under 1 s at 10k items (D-15). Relate's first run on a large base finishes inside the app's limit with visible progress.

- Search: 4.7 #3, 4.7 #6 (D-17), 4.7 #12.
- Relate: 4.8 #1, 4.8 #2.

**Done when:** the report's 10k-item search timing is under 1 s, and 2,000 items prepare in under 10 minutes with progress lines.

### Batch 9. Test-suite hygiene

**Goal:** tests that stay honest after this plan is done.

- 4.2 #15, 4.2 #16, 4.2 #17, 4.2 #18, 4.2 #19, 4.2 #21.

**Done when:** each of these tests fails when the behavior it guards is broken on purpose.

---

## 4. Coverage check

Every finding appears in exactly one batch. [Fact: counted per section]

| Section | Items | Batches |
|---|---|---|
| 4.1 scripts | 24 | 0, 1 |
| 4.2 tests | 24 | 0, 1, 3, 5, 7, 9 |
| 4.3 adapters | 30 | 2, 4, 6, 7 |
| 4.4 bridge | 14 | 2, 4, 5 |
| 4.5 capture | 19 | 2, 4, 6, 7 |
| 4.6 maintain | 13 | 2, 4, 6 |
| 4.7 query | 14 | 2, 4, 6, 8 |
| 4.8 relate | 12 | 4, 6, 7, 8 |
| 4.9 app | 25 | 3, 5, 6 |
| 4.10 root | 17 | 1, 2, 4, 5, 6 |
| 11 design | 4 | 6 |
| **Total** | **196** | |

---

## 5. Fixes to the report itself

The report is the input spec, so these should be corrected in `Problems.md`. [Fact: read from the report]

- **Count.** It says ~168 findings. There are 196.
- **Severity clashes.** F5 is BLOCKER in 4.9 #1 and #2, but BUG in the top ten (rank 10). The key-strip item is RISK in 4.2 #10, but BLOCKER in the top ten (rank 8). Rank 5 is a BUG listed above rank 6, a BLOCKER.
- **Duplicates.** 4.6 #2 = 4.10 #1. 4.3 #9 = 4.5 #2. 4.4 #13 = 4.10 #14. 4.5 #8 = 4.10 #9. 4.3 #19 and 4.6 #4 describe the same race. Each pair is planned once.
- **Not a bug as written.** 4.5 #6 calls saving the raw note a bug. Under the constitution the saving is correct, and the sentence is the bug (D-07).

---

## 6. Checked facts

The four planning assumptions were checked read-only against the repo on 2026-11-01. Full evidence is in `archive/assumption-check.md`. [Fact: that report]

| Fact | Result | What changed in this plan |
|---|---|---|
| 1. Can engine processes open the database before first run creates it? | **Disproved.** First run never creates the database. Home, the tray, the shortcut and all reads are gated and open read-only. Only Add (`capture`) creates the file. | The first-run brick has no trigger from the app alone. The real triggers are two Add sessions at once, or Add plus a coding agent's CLI (D-03). Batch 4's lock stays. Its "Done when" now tests that no opener crashes, because today the file still reaches version 13 while 3 of 4 openers crash. |
| 2. How big is one .deb? | **About 540 MB**, not 1 GB. The model ships inside it (about 483 MB of 1.82 GB installed). | Batch 1 keeps the last 3 builds (D-21). |
| 3. Does the key wizard need macOS and WSL? | **No.** The claim is one comment and the opener branches. GNU-only commands already break it there. No user doc promises macOS for the CLI. | D-22: Linux only. Applied to Batch 0. |
| 4. Is there a test that core never imports adapters? | **Yes.** `tests/test_architecture.py`, 7 checks, green locally and in CI. | Nothing. |

### New facts found during the check

- **CI is red today** on `app-launch-check (ubuntu-latest)`, because of Electron's sandbox helper permissions. This blocks running e2e in CI (D-13). Added to Batch 5 as its first step. [Fact: checked fact 4]
- **`maintain --dry-run` is already read-only.** Only the `close-item`, `edit-item` and `remove-link` dry-runs still write. Batch 4 already lists only those (4.6 #2). [Fact: checked fact 1, `cli.py:553-559`]
- **Home starts 6 engine processes at once, then 2 more**, 8 per visit. This matches report 4.9 #25. [Fact: checked fact 1]

---

## 7. Next step

Run `to-spec` on Batch 0 to turn it into a buildable spec, then implement it.

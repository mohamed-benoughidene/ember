# Batch 2: error boundary

**Source:** `archive/Plan.md` Batch 2. Decisions D-06, D-08, D-16, D-23, and N3–N7 from the 2026-11-01 spec check. Findings from `archive/Problems.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch2.md`); that check's decisions N3–N7 are applied here. Nothing in this spec waits on a decision.

## Problem Statement

When the engine hits an error nobody planned for, the user sees "unreadable answer (APP-002)" and the real cause is thrown away.

- The engine has no last-resort handler. A bad `--db`, a non-SQLite file, damaged text in the database, a bad AI base URL, or an unpaired character in an edit all print a Python traceback. [Fact: report section 6]
- The app already scans every stderr line for a house line (`findHouseError`, `app/main/bridge-client.js:42-49`), so a house line is never missed. The real gap: when no line matches, it reports the FIRST stderr line (`Traceback (most recent call last):`, `bridge-client.js:265,276`) and throws away the useful last line. The db-check runner is worse: it parses only the first stderr line (`app/main/db-check-runner.js:168`), so a house line after line 1 is missed entirely. [Fact: read at this tip]
- Some engine errors leak raw messages with full paths, or the whole provider message, and redaction removes only the exact key.
- cli.py repeats the same error block 19 times, with two spellings.
- Error `name` values are hardcoded strings that disagree with class names in 11 places.

## Solution

- One handler at the edge of the CLI catches every unexpected exception. It prints one house line, `error: EMBER-000 InternalError`, naming where it broke, and exits non-zero (D-06). House errors exit 1; the user abort keeps exit 2 (today's contract, `ember/cli.py:402,526`).
- The full trace, with secrets removed, goes to a crash file. The app shows "Copy crash report" and "Show file" under Details (D-16).
- Every known failure path gets its own house code instead of a crash.
- Error lines carry codes, names taken from the code, entity ids and file names — never a full home path — and no secrets.
- At the end, the `.deb` is rebuilt and checked with the Batch 1 script. This closes decision A (D-01).

## User Stories

1. As a user, I want a plain message when Ember fails unexpectedly, so that I know it was Ember and not something I did.
2. As a user, I want a "Copy crash report" button, so that I can send the details to the founder or an agent.
3. As a user, I want a "Show file" button, so that I can find the crash file without searching.
4. As a user, I want the crash file to contain no AI key or other secret, so that sharing it is safe.
5. As the founder, I want the full trace kept in the crash file, so that bugs stay loud for me even when the user sees a short line.
6. As the founder, I want the house line to say which module and function failed, so that I can start from the right place.
7. As a user, I want a wrong `--db` path to give a clear "can't open" error, so that I can fix the path.
8. As a user, I want a file that is not an Ember database to be refused clearly, so that I know I picked the wrong file.
9. As a user, I want damaged text in the database to give the same clear error on Export as on every other read, so that Export behaves like the rest.
10. As a user, I want a malformed AI base URL to give a clear setup error, so that I know to fix my settings.
11. As a user, I want an edit containing a broken character to be refused clearly, so that I don't lose the item silently.
12. As a user, I want a broken pipe to end with a house line, so that output never stops without a reason.
13. As a user, I want `db-check` to report a broken version value as a finding, not crash, so that the health check always answers.
14. As a user, I want "database busy" and "needs recovery" to be told apart from "file missing", so that the message names the real problem.
15. As a user, I want a bad `--out` path for Export to give the same exit code however it is bad, so that scripts can rely on it.
16. As an agent using the CLI, I want every engine failure (a raised error) to be exactly one stderr line with a code, so that I can parse it. CLI usage errors — a missing flag, a typo in a command — are not engine failures; they keep click's own one-line message and exit 2 with no code, as today.
17. As the app, I want the no-house-line fallback in Details to keep the real cause (the last non-empty stderr line, e.g. `sqlite3.OperationalError: ...`), not the first line (`Traceback (most recent call last):`), so that the real cause is never discarded.
18. As the app, I want APP-002 used only for truly unreadable output, so that it still means something.
19. As the founder, I want one error handler in cli.py instead of 19 copies, so that one change fixes every command.
20. As the founder, I want error names to come from the error classes, not hardcoded strings, so that names never drift.
21. As the founder, I want error context to carry entity ids and only the file name — never a full home path — and no keys, so that logs follow the "zero secrets" rule. The crash file is where the full path stays.
22. As the founder, I want provider error details scrubbed of any key-looking text, not only the exact key, so that a changed key format still can't leak.
23. As the founder, I want database connections closed when opening fails, so that failed opens leak nothing.
24. As the founder, I want reading the AI reply payload to be inside the mapped error path, so that a strange reply gives a house code.
25. As the founder, I want a rebuilt and checked `.deb` at the end of this batch, so that the release carries the new error boundary.

## Implementation Decisions

### Engine edge handler
- One handler at the CLI entry point wraps every command. Known house errors print their line and exit with their code. Any other exception becomes `EMBER-000 InternalError`.
- The house line format stays `error: <CODE> <Name>` plus context. For `EMBER-000` the context names `module.function` of the failing frame and a crash id. File names only, never full paths; no secrets (N7).
- The crash file holds the full traceback, engine version, command name (no arguments with paths), and time. The full traceback keeps real full paths — this file is where the path stays (N7), even though the on-screen error context shows file names only. It is written to `$XDG_STATE_HOME/ember/crashes` (default `~/.local/state/ember/crashes` when that variable is unset), on both the engine side and the app side, named by crash id (N4).
- Secret scrubbing runs on the crash text and on every error context: the configured key, plus any token that looks like an API key.
- The 19 per-command error blocks are removed. Commands raise. The edge handler prints.
- Error names are taken from the error class automatically (constitution: names injected, never hardcoded). The 11 mismatched names change to match (`ember/capture/errors.py:13-96`; the only mismatched module at this tip). Codes stay the same (codes are never reused or renamed). Unexpected exceptions have no Ember class, so the edge handler supplies the `EMBER-000 InternalError` line itself; the base class's own name is not renamed.

### Known paths become house errors
- Opening a database: any SQLite error on open maps to a house code, and the connection is closed. Covers bad path, non-SQLite file, and the backup and query openers.
- Export maps SQLite decode errors to the same code other reads use.
- AI base URL is validated when config is loaded, at startup (constitution: config loaded once, validated, fail fast). Malformed gives a setup code.
- Edited text is validated where it enters (constitution: validate outside data at the boundary). An unpaired surrogate gives a house code before any write.
- `db-check` treats a non-numeric version as a finding.
- QUERY-003 is split: busy and recovery-needed get their own codes, new numbers (codes never reused).
- Export uses one exit code for every bad `--out`.
- A broken output pipe prints a house line where stderr is still open, and exits non-zero.

### App side
- The bridge client and db-check runner read stderr whole, then take the last line that matches the house format. If none matches, APP-002, with the last non-empty line kept for Details. (A signal-killed child is a separate case, 4.4 #10 — moved to Batch 5 by N3; nothing here claims or touches it.)
- `EMBER-000` gets a sentence in the app. Details shows "Copy crash report" (copies the crash file text) and "Show file" (opens its folder). The app finds the file by crash id. The sentence is written once here and carried into Batch 6's single sentence table when the per-area tables merge (Batch 6 must not drop it).

### Release
- After this batch, rebuild the `.deb` and run the Batch 1 check script. Must pass.

## Testing Decisions

**Good tests here** assert the error code, the exit code and the number of stderr lines. Never the sentence text (constitution: tests assert codes, not prose).

**Seams (D-23):**
1. **The `ember` CLI on temp databases.** The five repro paths from report section 6 (bad `--db`, non-SQLite file, damaged UTF-8, bad base URL, unpaired surrogate) each give exactly one stderr line, a house code, and a non-zero exit. A forced unexpected exception gives `EMBER-000` and a crash file that contains the traceback and does not contain a planted fake key. Forcing mechanism, so no test hook ships in the product: the test monkeypatches one module-level helper that a command calls (for example a store method) to raise `RuntimeError`, then invokes the CLI entry point in-process. Nothing new is added to the CLI for it.
2. **The bridge client with a fake engine.** A fake that prints a traceback then a house line yields that house code. A fake that prints only garbage yields APP-002 with the last line in details.
3. **App e2e under xvfb with a fake engine.** On the Add screen, a fake `EMBER-000` failure shows the crash sentence and both buttons (N5). "Copy crash report" puts the crash text on the clipboard. Batch 3 does not re-test this sentence or these buttons.

**Prior art:** the existing house-line tests in `app/test/bridge-client.test.js`. The Python CLI tests under `tests/`.

## Out of Scope

- Wording for every other code (Batch 6).
- The screen side of real error text on Add (Batch 3). Exception, per N5: the crash sentence and the two buttons are built and e2e-tested here, on the Add screen; Batch 3 does not re-test them.
- Data integrity fixes like two-commit writes (Batch 4).
- A signal-killed engine child reading as APP-002, and any own code or sentence for a killed child or an exit with no result (4.4 #10 — Batch 5, per N3).

## Further Notes

- Where the crash folder lives was an open question (check report decision 1.1). Decided 2026-11-01 (Plan N4): `$XDG_STATE_HOME/ember/crashes`, default `~/.local/state/ember/crashes`, on both the engine and the app side. The check had found the app's folder is a config folder (`~/.config/ember-app`, holds `settings.json` and `key.enc`) and the engine has none of its own; engine children inherit the app's environment (`app/main/bridge-client.js:144-156`).
- The other open decisions from the check report are settled too: CLI usage errors keep click's exit 2 with no code, and story 16 now covers engine failures only (1.3 → N6); error context shows only the file name while the crash file keeps the full path (1.4 → N7); the signal-killed child (1.2) is not decided here — it moved to Batch 5 with 4.4 #10 (N3).
- The crash id must be something the app can map to a file without the engine printing a path. Today's house-line parser already carries every trailing context token to the app (`rest` group, `app/shared/parse-error-line.js:36-58`), so a crash id inside the house line reaches Details without any new channel.
- **Safety rules for whoever implements this** (same as Batch 0): no real AI calls (`env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY` in every engine run), never open `~/.config/ember-app/ember.db` or `key.enc`, no GUI launch except under xvfb, no Electron launch outside the e2e harness, temp files only.

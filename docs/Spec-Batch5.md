# Batch 5: bridge and screen lifetime

**Source:** `archive/Plan.md` Batch 5. Decisions D-13, D-23, D-24, plus N3, N11, N12, N13. Findings from `archive/Problems.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch5.md`). Not yet published.

## Problem Statement

- **Late repaints (F5).** Screens write to one shared pane with no check that they are still the current screen. A slow health check on Keep safe paints over Settings, and wipes typed key text.
- **Piling listeners.** Add, Link and Cleanup add keyboard listeners on every visit and never remove them. Old handlers answer y/n/e/q into old sessions from any pane.
- **Ghost process.** Closing the main window leaves the app running invisibly. "Open Ember" fails. A second launch starts a second app with its own shortcut, tray and temp cleanup. The shortcut is only registered at boot.
- **Bridge reading.** Error lines split across reads become APP-002. Multi-byte characters break at read boundaries. An early pipe close kills the whole app. Timeouts wait for every grandchild. Event payloads aren't checked. A chatty child never times out.
- **Window safety.** Unescaped knowledge-base text in HTML. No navigation lock. A raw error message with paths reaches the page.
- **No coverage.** Screen tests never run in CI, and CI's launch check is already red on Electron's sandbox helper. [Fact: checked fact 4]

## Solution

- CI runs e2e on a virtual screen, with the sandbox helper set up correctly in CI (D-13).
- Every screen render gets a token. Only the current token can paint. Each screen returns a dispose function that removes its listeners and stops its work.
- One app instance. Closing the main window hides to the tray. "Open Ember" reopens it. Quit from the tray (D-24). The shortcut registers as soon as a knowledge base is set.
- The bridge reads whole lines across chunks, decodes text as a stream, handles pipe errors, uses hard timeouts, caps output, and validates every event's payload.

## User Stories

1. As a user, I want the screen I opened to stay on screen, so that late results never replace it.
2. As a user, I want what I type in Settings to stay, so that a background check can't wipe it.
3. As a user, I want keys like y and n to act only on the screen I'm looking at, so that I never answer an old session by accident.
4. As a user, I want leaving a sweep to stop it, so that it doesn't keep running unseen.
5. As a user, I want closing the window to keep Ember in the tray, so that my capture shortcut still works.
6. As a user, I want "Open Ember" to always bring the window back, so that I can reach the app.
7. As a user, I want Quit in the tray to end Ember fully, so that I can stop it when I choose.
8. As a user, I want launching Ember twice to bring up the open window, so that I never have two apps fighting.
9. As a user, I want the capture shortcut to work right after first run, so that I don't need to restart.
10. As a user, I want Settings and Keep safe to name my current knowledge base after I switch, so that they act on the right file.
11. As a user, I want two fast Ctrl+Z presses to undo one step at a time, so that undo never runs twice by accident.
12. As a user, I want a failed backup to show an error, so that "Writing the backup copy" never hangs forever.
13. As a user, I want Ctrl+Z inside a text box to undo my typing, so that normal editing works.
14. As a user, I want every boot notice shown, so that a second problem isn't hidden.
15. As a user, I want the quick popup to stop polling while hidden, so that it costs nothing in the background.
16. As a user, I want the popup's setup button to open the right settings pane, so that it does what it says.
17. As a user, I want Home to start fewer engine processes (one engine call returns all four counts, N11), so that visiting Home is light.
18. As a user, I want long error lines read correctly, so that I see the real error.
19. As a user, I want non-English text in errors shown correctly, so that no characters are mangled.
20. As a user, I want the app to survive an engine that exits early, so that one failure doesn't close everything.
21. As a user, I want timeouts to end on time, so that a stuck helper process can't hang the app.
22. As a user, I want pressing Stop to show "Stopped" with no error, and any other engine death to say Ember stopped unexpectedly, so that the message is always true.
23. As a user, I want my knowledge-base text shown as text, never as HTML, so that content can't change the page.
24. As a user, I want the app window never to navigate to another site, so that the app's powers never reach outside pages.
25. As a user, I want the app's own error messages to come without file paths, so that screenshots of the app don't expose my folders. (The engine's error-log lines are Batch 2's finding 4.10 #4.)
26. As a user, I want an engine path containing a space to work, so that installs in such folders run.
27. As the founder, I want every event checked against its expected fields, so that a malformed event fails loudly.
28. As the founder, I want one shared fixture of event names and fields for engine and app, so that renaming a field breaks a test.
29. As the founder, I want "ended without a summary" reported by the same new app code as every unexpected engine death (N3), so that all three paths agree.
30. As the founder, I want the last unterminated output line read, so that nothing is silently dropped.
31. As the founder, I want `db-check` treated as a command whose exit 1 still has a valid report, so that drift findings reach the screen.
32. As the founder, I want the backup summary's path checked against the chosen target, so that the app never trusts a wrong path.
33. As the founder, I want the output caps tested, so that the 32 MB limit is proven.
34. As a contributor, I want e2e in CI on a virtual screen, so that screen bugs are caught on every push.
35. As a contributor, I want un-awaited subtests caught, so that tests can't be silently cancelled. (N12: the check lives in the app's own test runner, no new dependency.)

## Implementation Decisions

### CI
- First step: fix `chrome-sandbox` owner and mode in the CI job, so the launch check passes. The shipped app keeps its sandbox on.
- Run e2e under xvfb in CI with a fake engine, fake AI and temp config (D-13).

### Screen lifetime
- The app shell keeps a render token that changes on every navigation. Screens receive it and must check it before painting. A stale token paints nothing.
- Each screen returns a dispose function. The shell calls it on navigation. It removes listeners, stops timers and stops sweeps.
- Screen keyboard listeners attach through the shell, scoped to the active screen, and ignore keys while focus is in a text field unless the screen asks for them.
- Every DOM lookup after an await checks the element still exists.
- Settings and Keep safe read the current knowledge-base path when they render, not a boot snapshot.
- Undo sets its busy flag before awaiting. Backup actions show their error instead of swallowing it.
- Text-box undo: menu Undo and Redo use Electron's built-in roles when a text field is focused, and Ember's undo otherwise.

### Main process (D-24)
- Single-instance lock. A second launch focuses the existing window.
- Closing the main window hides it. The tray and shortcut stay. "Open Ember" recreates or shows the window. Tray Quit exits.
- The shortcut registers whenever a knowledge base path is saved, including at the end of first run.
- Window: deny navigation and new windows.
- The IPC catch-all returns a code and a generic message, never `err.message`.
- `EMBER_APP_COMMAND` is a JSON array of argv, not a space-split string.
- Boot notices use Batch 3's grouping and show every code.
- Quick popup polling runs only while visible. The setup button opens the correct pane id.
- Home gets its counts in fewer calls. Decided (N11; check-report decision 2, option A): a small new engine option returns all four Home counts in one call. [Checked 2026-11-01: the engine has no such option today — `list-items` takes one `--status` filter and returns one `total` per call (`ember/cli.py:1403`, `ember/query/list_items.py:12-34`).]

### Bridge
- stdout and stderr are decoded as streams and split into lines with a carry buffer. The same fix lands in `db-check-runner.js`, which splits per chunk today (report 4.4 #1 names both files).
- `stdin` has an error handler. A pipe error ends the call with a house code.
- The engine is started in its own process group. A timeout kills the group and settles on process exit, with a short hard bound for pipe close. A timeout kill is not the app's own Stop, so its settled result follows the same two-way rule as below.
- Confirm sessions get a byte cap. The idle timer resets only on complete lines.
- Each event type has a field schema. A missing or wrong field is APP-002 with details.
- One fixture file lists event names and their fields. The engine's tests and the app's tests both read it.
- Settle rule for an ended child (N3; check-report decisions 1 and 3; finding 4.4 #10, moved here from Batch 2): the app's own Stop shows a "Stopped" message and no error. Any other kill — a signal, a timeout group kill — or an exit with no result settles on ONE new app code meaning "Ember stopped unexpectedly". The exact number of that app code is still open.
- A final unterminated line is read.
- `db-check` is treated as a command where exit 1 can carry a valid document.
- `fix-close` escapes old and new values. Home escapes counts.
- The backup summary path must equal the chosen target.
- The engine's own stdin reader caps line length (4.4 #12): a flooding feeder cannot grow memory without bound (N13).

## Testing Decisions

**Good tests here** check what the user sees or what the bridge returns, never internal call counts.

**Seams (D-23):**
1. **App e2e under xvfb with a fake engine.** Keep safe → Settings within 200 ms: Settings stays, typed text stays. Visit Add three times, press y: only the current session receives it. Leave Clean up mid-sweep: no further events arrive after leaving (story 4). Close the main window: process alive, tray works, "Open Ember" shows the window. Launch a second instance: first window focused, one process.
2. **Bridge client with a fake engine.** A house line split across two writes: correct code. A multi-byte character split across writes: intact. Fake closes stdin early: no crash, house code. Fake leaves a grandchild holding the pipe: timeout settles within the bound. Event missing a field: APP-002. Output beyond the cap: cap code. Fake stopped by the app's own Stop: "Stopped" message, no error. Fake killed by a signal, or exits with no summary: the one new Ember-stopped-unexpectedly code.
3. **Shared event fixture.** Engine and app tests both load it. Renaming a field in one side fails a test.

**Test-hygiene gate (N12):** `app/test/run.js` (the app test runner) gets a small check that fails any test file with un-awaited async subtests. No new dependency (check-report decision 4, option B).

**Engine side (N13):** the engine's stdin reader tests cover finding 4.4 #12: one oversized line and one undecodable byte sequence each come back as a house code, not a crash (`ember/adapters/json_confirm.py`).

**Prior art:** `app/test/bridge-client.test.js`, the existing e2e harness (`app/test/e2e/`, cleaned up by Batch 0), `app/test/e2e/keep-safe.js`.

## Out of Scope

- Wording and new features (Batch 6).
- Relate progress (Batch 8).

## Further Notes

- **Open question (answered 2026-11-01):** does the shell already have a navigation function every screen goes through? Yes — `ctx.navigate` (`app/renderer/screens/app.mjs:62`) is the single navigation entry (sidebar, Comma shortcut, menu requests) and routes every pane through `renderPane` over the shared pane write in `ctx.renderFrame` (`app.mjs:57-61`). What it lacks is exactly this batch's work: a render token, dispose calls, focus-scoped keys. `settings.mjs:159` has a per-screen refresh token only. No new navigation function is needed; this batch extends the existing one.
- Resolutions of the check's open decisions (2026-11-01, by `archive/Plan.md` decisions N3, N11, N12, N13 — all five check decisions are resolved): decision 1 — 4.4 #10 lives in Batch 5, moved out of Batch 2 (N3). Decision 2 — a small new engine option returns the four Home counts in one call (N11). Decision 3 — "ended without a summary" is covered by N3's new app code, via story 29. Decision 4 — a small check in the app test runner, no new dependency (N12). Decision 5 — the engine caps its stdin line length and maps decode errors to a house code (N13). **Still open:** the exact number of the new "Ember stopped unexpectedly" app code — the spec deliberately does not pick it.

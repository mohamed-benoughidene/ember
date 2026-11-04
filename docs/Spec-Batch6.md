# Batch 6: wording and new interface features

**Source:** `archive/Plan.md` Batch 6. Decisions D-07, D-08, D-09, D-10, D-14, D-18, D-20, D-23, D-26. Findings from `archive/Problems.md`, design audit section 11.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch6.md`). The check's four open points are settled (N14–N17 in `archive/Plan.md`); none still open.

## Problem Statement

- **Wording has no single home.** Python owns 96 codes. App sentences are spread over several tables. 18 codes fall back to a generic sentence, `CAPTURE-016` sits in the wrong table, and `EMBER-000` has none. The app picks some sentences by matching Python's error text, so a rewording silently changes the help shown.
- **Wrong sentences.** A rejected note says "nothing was created" though the note was saved. RELATE-017 always says "run pip install", even for a model timeout. MAINTAIN-003 and the sweep summary say untrue things. History calls edits and link removals "a change Ember has no words for".
- **No way to forget a note.** A note whose items were all rejected stays forever and is exported (D-07).
- **First run and key box (F7).** First run has a useless third step. There are two key boxes and two Show/Hide buttons. The About box shows the raw install path. A failed file check during first run still saves the bad path.
- **Smaller honesty gaps.** Link's "no" hides a pair forever without saying so. Stop during relate preparation looks like a crash. Search says "50 matches" when there are 60. History's "Older" button walks forward. `--format json` is accepted and ignored. `--file ""` silently reads stdin.
- **Design audit.** The gallery toolbar is unreadable, Keep safe uses a pop-up role for an inline confirm, some text sizes are off the documented scale, and narrow windows were never checked.

## Solution

- One sentence table in the app, looked up by code only (D-08). Where the app matched Python's words, Python raises a new separate code. A test checks every engine code has exactly one sentence.
- "Forget this note": on the Add result after all items are rejected, and in a "Notes with no items" list in Cleanup (D-09). Permanent, with an inline confirm that mentions older backups (D-10). History keeps one line with the note id and date, no text (D-26).
- First run has 2 steps. One key box with an eye icon inside the field (D-14). About shows versions, not paths.
- Each smaller gap is fixed as listed below.

## User Stories

1. As a user, I want every error to have its own clear sentence, so that I always know what happened.
2. As a user, I want the help for a missing key to be right even if the engine's wording changes, so that I'm never sent the wrong way.
3. As a user, I want a model timeout and a missing model to get different advice, so that I don't reinstall for no reason.
4. As a user, I want the sentence after rejecting every item to say my note was saved and no items were made, so that I know the truth.
5. As a user, I want a "Forget this note" button right after I reject every item, so that private text I pasted by mistake is gone.
6. As a user, I want a "Notes with no items" list in Cleanup, so that I can forget a note later.
7. As a user, I want "Forget for good?" asked inline before deleting, so that I don't delete by accident.
8. As a user, I want the confirm to say older backups still hold the text, so that I know where it may remain.
9. As a user, I want a forgotten note gone from exports and search, so that it is really gone.
10. As a user, I want history to show "Note 12 was forgotten" with a date, so that the record is honest without keeping the text.
11. As a user, I want only notes with no items to be forgettable, so that I can't break items by deleting their source.
12. As an agent, I want a CLI command to forget a note, so that I can do it without the app.
13. As a user, I want first run to have 2 steps, so that setup is quick.
14. As a user, I want one key box with an eye icon inside it, so that it works like other apps.
15. As a user, I want a rejected file in first run to keep my previous choice, so that a wrong pick doesn't break my setup.
16. As a user, I want the About box to show versions, not install paths, so that it's clean to share.
17. As a user, I want the Link "no" button to say the pair won't be suggested again, so that I choose knowingly.
18. As a user, I want Stop during preparation shown as stopped, so that I don't think it crashed.
19. As a user, I want a missing item number in Link to name what's missing, so that the message makes sense.
20. As a user, I want search to say "50 of 60 matches" and let me see more, so that I know results were cut.
21. As a user, I want history to show newest first, with "Older" going back in time, so that the button means what it says.
22. As a user, I want closed items to show their reason once, in plain words, so that history isn't cluttered with raw codes.
23. As an agent, I want `--format json` refused where it isn't supported, so that I never parse plain text by mistake.
24. As an agent, I want `--file ""` refused, so that an empty path never reads stdin.
25. As an agent, I want `maintain --format json` to refuse terminal confirm, so that stdout is pure JSON.
26. As a user, I want error codes shown only behind Details, so that body text stays readable.
27. As a user, I want Home's layout attributes valid, so that labels don't wrap wrongly.
28. As a screen-reader user, I want Keep safe's confirm announced as an inline group, so that I'm not told a dialog trapped me.
29. As the founder, I want the design gallery's toolbar readable, so that I can review the design.
30. As the founder, I want every text size on the documented scale, folded into the five named styles, so that design rules match the code.
31. As the founder, I want narrow windows checked once, so that I know they work.
32. As a contributor, I want the sentence-table test to fail when a code has none, two, or a fallback, so that drift can't return.
33. As the founder, I want the JSON summary to carry the human summary line too, so that both outputs agree.

## Implementation Decisions

### Sentence table (D-08)
- One app module owns all sentences, keyed by full code. The old per-area tables become entries in it.
- Substring branches are removed. Each case they handled becomes its own engine code with a new number. Codes are never reused.
- RELATE-017 is split into model-missing and model-load-timeout codes.
- New entries: `EMBER-000`, the new codes from Batches 2, 4, 5 and 7 (Batch 5's new code is the app code "Ember stopped unexpectedly", whose sentence lives in this table too), and every code that now falls back. The exact code numbers are chosen in those batches.
- A test builds the engine's code list by today's regex file scan over the six engine error files (N15 — the scan `app/test/plain-sentences.test.js` already does), and compares it with the app table: every engine code has exactly one sentence, and no app entry lacks an engine code (the app's own `APP-` namespace excepted: `APP-000` to `APP-008` live in `app/shared/errors.js`, not in the engine).
- Corrected sentences: rejected note (D-07), MAINTAIN-003, the sweep summary after a finished run. History kinds added for edit-item and remove-link, and for the new forgotten-note line (story 10; without a kind it would render as "a change Ember has no words for"). Derived close reasons replace raw `Closed:expired`.

### Forget this note (D-07, D-09, D-10, D-26)
- Engine command `forget-source --db PATH --source ID`. Refuses a source that has any items, with its own code. Deleting a source that no longer exists succeeds (constitution: design errors away).
- One transaction: deletes the source row and its stored AI replies, and adds one ledger line with the source id and time, no text. The line is not undoable. A new migration adds an optional `source_id` column to the change log to hold that source id (N14). The migration number goes to whichever of Batch 6 or 7 lands first.
- Engine command or option to list sources with no items, for the Cleanup list.
- Add result: "Forget this note" shown when every item was rejected. Cleanup: "Notes with no items" list, each with Forget.
- Inline confirm "Forget for good?" stating that older backup copies still hold the text. Uses the inline-group pattern, not a pop-up.

### First run and key (D-14)
- First run has 2 steps. The third step is removed. [Assumption: which step is third is confirmed in the code check.]
- One key input with an eye toggle inside the field. It is the same single key-box pattern in first run and in Settings (D-14); both Show/Hide buttons go.
- First run checks the chosen file before saving it. A refused file keeps the previous path.
- About shows app and engine versions and the correct license file name. No install path.

### Smaller fixes
- Link "no" button label: "No, don't suggest again" (D-18, updated by N16).
- Stop during preparation: uses the Batch 5 stop mechanism (N3). The app knows it sent Stop and shows "Stopped", no error. Any other kill, or an exit with no result, gets the one new app code "Ember stopped unexpectedly".
- Link argument errors name the field.
- Topic search returns `total` and accepts `--offset`. The app shows "N of M".
- History is newest first — flipped where the events are sorted (the engine's `history` returns newest first, so `--offset` pages walk back in time; the app is the only consumer today). "Older" moves back in time.
- Home: the ledger rows carry one valid `class` attribute (4.9 #21).
- `capture` and `relate` refuse `--format json` with a clear error (D-20). `--file ""` is refused. `maintain --format json --confirm terminal` is refused.
- Error codes appear only in Details.
- JSON summary includes the human line.
- Design: gallery toolbar uses the button style and light label ink. Keep safe confirm uses `role="group"` with a label. Off-scale text sizes are folded into the five named styles (N17 — decided; DESIGN.md stays the rule). One visual check below 800 px.

## Testing Decisions

**Good tests here** assert codes, screen elements and data presence. Not sentence text (constitution).

**Seams (D-23):**
1. **The `ember` CLI on temp databases.** `forget-source` on a source with items: refused code. On a source with none: source and AI replies gone, export lacks the text, one ledger line without text. On a missing id: success. Refused flags give their codes.
2. **App e2e under xvfb with a fake engine.** Reject all items, Forget, confirm: note gone from the Cleanup list. First run shows 2 steps. Settings has one key input with an eye toggle. Search with 60 hits and limit 50 shows a count of 60.
3. **Sentence-table test** whose engine code list is today's regex file scan over the six engine error files (N15 — the existing scan, e.g. the pattern `app/test/plain-sentences.test.js:57-60` used over `ember/errors.py` + the five per-area `errors.py` files). No engine command and no exported list is added.

**Prior art:** `app/test/plain-sentences.test.js` (its hardcoded directories and counts are replaced by that same file scan with stronger assertions). `app/test/design-contrast.test.js`.

## Out of Scope

- Undo for forgetting (D-10).
- Removing the text from existing backup files.
- Python owning sentences (D-08 rejected it).

## Further Notes

- Open questions for the code check: which first-run step is the useless one? Does the engine already expose its code list? Where do stored AI replies link to sources?

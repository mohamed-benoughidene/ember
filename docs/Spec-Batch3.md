# Batch 3: approved Steps 2-4 (Add errors, F2, F4)

**Source:** `archive/Plan.md` Batch 3. Decisions D-01, D-23. Findings 4.9 #11, 4.2 #8, 4.2 #9.
**Rules:** `Constitution.md`.
**Status:** draft. Not yet checked against the code. Depends on Batch 2.

## Problem Statement

- When Add fails, the form disappears and only the error is shown. The note text survives in memory, but the box never comes back (F2). Retry restarts from memory without showing the form.
- When several Home blocks fail for the same reason, several cards appear (F4). Only the first notice is kept, so a second, different failure is hidden.
- Add's error text was planned to be real words, not "unreadable answer". Batch 2 gives the engine side. This batch gives the screen side.
- None of this has a test that can fail.

## Solution

- A failed Add shows the error and the form again, with the user's text still in the box.
- Home shows one notice per distinct error code. The notice replaces the failed blocks' own error cards. Different codes each get their own notice.
- Add shows the sentence for the real error code from Batch 2.

## User Stories

1. As a user, I want my note still in the box after Add fails, so that I don't retype it.
2. As a user, I want to see the error and the form together, so that I can fix the cause and try again.
3. As a user, I want Retry to use exactly what is in the box now, so that my edits after the failure count.
4. As a user, I want Add errors to say what went wrong in plain words, so that I know what to do.
5. As a user, I want Add to show "Something went wrong inside Ember" with the crash buttons for an unexpected failure, so that I can report it.
6. As a user, I want one notice to replace the failed blocks' error cards when they fail with the same code, so that the screen isn't filled with copies.
7. As a user, I want a separate notice for each different failure, so that no problem is hidden.
8. As a user, I want the notice to say how many blocks it affects, so that I know the scale.
9. As a contributor, I want e2e tests that fail if the form doesn't come back or notices aren't grouped, so that F2 and F4 can't return.

## Implementation Decisions

- The Add screen keeps the note text as part of its state. On failure it renders the form with that text plus the error block. Retry reads the box at click time.
- Add looks up the sentence by error code, through the app's existing lookup (`addErrorSentence` in `capture-words.mjs`, which falls back to `sentenceFor(code)`). Until the single table arrives in Batch 6, that lookup keeps its one existing detail branch: `CAPTURE-008` plus the "ai api key missing" detail picks the no-key words (finding 4.10 #7, Batch 6 replaces it).
- Home groups failed blocks by error code. One notice per code, with a count of affected blocks. All codes are shown, not only the first. The notice replaces the failed blocks' own error cards: a failed block shows no error card of its own. The notice's "Try again" reloads all of Home (the same load path a visit runs, all blocks), not just the failed blocks. (Plan decision B3-1; it resolves spec-check decision 1.1.)
- Boot notices follow the same rule (4.9 #20 is in Batch 5 and uses this grouping).

## Testing Decisions

**Good tests here** check what is on screen: the box contents, the number of notices, the codes shown.

**Seam (D-23):** app e2e under xvfb with a fake engine.
1. Fake capture fails with a house code (not `EMBER-000` — that case, with its sentence and crash buttons, is Batch 2's seam 3 per N5). The form is visible, the box holds the original text, the error shows the code's sentence.
2. Edit the text, click Retry. The fake engine receives the edited text.
3. Two rounds against Home's three engine-fed blocks (attention, counts, ledger — `home.mjs`): (a) the fake fails all three with one code — exactly one notice, with a count of 3; (b) the fake fails two blocks with one code and one block with another — exactly two notices, one with a count of 2. (A fourth failing block is not reachable on Home today, so the two codes must share three blocks.) Each round also checks that no per-block error card remains: the notice replaces the cards (B3-1). Clicking a notice's "Try again" reloads all of Home — every block loads again — not a single block (B3-1).

**Prior art:** the existing Home-error e2e that counts error blocks (`app/test/e2e/first-run-home-lookup.js:413-437`; it waits for ≥ 2 error blocks but never asserts an exact count or grouping; it becomes the base of test 3). The Add e2e error scenarios (`app/test/e2e/add.js:550-618`) are prior art for tests 1-2. The e2e harness and fake engine from Batch 0.

Story 5 (the crash sentence and the "Copy crash report" / "Show file" buttons) is Batch 2's app side, per decision N5: Batch 2's e2e (its seam 3, on the Add pane) tests the crash sentence and both buttons. This batch does not re-test them; its tests pin the Add form and notice behavior only.

## Out of Scope

- The crash sentence and the "Copy crash report" / "Show file" buttons on Add, and their e2e test (Batch 2's app side, decision N5).
- The single sentence table (Batch 6).
- Screen lifetime and late repaints (Batch 5).

## Further Notes

- Open question for the code check: does the Add screen already have a state object the text can live in, or is the text only in the module-level `state.text`?

# Batch 9: test-suite hygiene

**Source:** `archive/Plan.md` Batch 9. Decision D-23. Findings 4.2 #15, #16, #17, #18, #19, #21.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch9.md`); the check's one decision (the DESIGN.md contrast numbers) is settled — N24 in `archive/Plan.md`. Not yet published.

## Problem Statement

Some tests pass while the thing they guard is broken.

- The contrast test claims to check that quoted contrast numbers are true, but only checks the ratio is at least 3. The quoted numbers in `docs/DESIGN.md` do not all match the computed ratios either (measured 2026-11-01, see Implementation Decisions).
- The undo-labels test hardcodes the action list, so a new engine action ships green and the screen throws at runtime.
- The launch check has an unused environment variable nothing reads, and its stdout and stderr appends are two identical copies of the same handler. The appends themselves are correct (each stream is read exactly once), so its logs are true today.
- An e2e helper is defined and never used.
- Two e2e tests swallow timeouts, hiding the real failure.
- The docs-in-sync test skips when git is missing, so the gate is green without running.

## Solution

Each test checks what it claims, uses the engine's real lists, and fails loudly when it can't run.

## User Stories

1. As a contributor, I want the 5 wrong quoted contrast numbers in the design doc corrected first (N24 + I3), so that the contrast test can compare each quoted number with the computed one, and the design doc can't drift.
2. As a contributor, I want the undo-labels test to read the engine's action list, so that a new action without a label fails.
3. As a contributor, I want the launch check's stdout and stderr handlers to share one append helper, so that the test code is not written twice.
4. As a contributor, I want unused helpers and variables removed, so that the test code says only what it does.
5. As a contributor, I want e2e timeouts to fail with their cause, so that I see the real failure.
6. As a contributor, I want the docs-in-sync test to fail in CI when git is missing, so that the gate never passes by skipping.

## Implementation Decisions

- Contrast test: the quoted ratios in `docs/DESIGN.md` are first corrected to the computed ones (N24, decided 2026-11-01 — the check's needs-a-decision 1, option A; measured 2026-11-01 against `tokens.css`: iron/ledger 12.22, faded/ledger 6.50, faded/ground 5.26, white/brick 6.83, heat/ledger 4.25, soot-faded 8.29, soot-heat 7.58, apricot/charred 10.24 — so 7.5, 7.1, 5.1, 6.4, and 4.2 must change (I3, decided 2026-11-02: 4.25 rounds to 4.3 under normal JS rounding, so the doc's 4.2:1 must read 4.3:1); 12 is within rounding of 12.22). The palette itself is not touched; it passes every 4.5:1 gate already. Then the test parses each quoted ratio from the design doc and asserts it equals the computed ratio, rounded to the precision the doc shows.
- Undo-labels test: read the engine's real action strings from `ember/maintain/undo.py` (the `source_action` returns of the undo and redo dispatches, `undo.py:401-416` and `:432-448`), the same source-walk way this test already reads `errors.py` files (`app/test/undo-labels.test.js:92-104`). The engine has no single exported action list today, and Batch 6's list is an error-code registry, not an action list, so nothing is taken from Batch 6. [Fact, checked]
- Launch check: one shared append helper for stdout and stderr. Remove the unused variable (Batch 0 may already use it for the fake engine; if so, keep it — confirmed today: Batch 0 is not implemented and nothing in `app/` reads `RTI_FAKE_WORKDIR`).
- Remove the unused e2e `waitFor`, or use it where a test waits by hand.
- e2e waits rethrow with the step name instead of swallowing.
- Docs-in-sync: skip only outside CI. In CI, a missing git fails.

## Testing Decisions

**Good tests here** go red when the guarded thing breaks.

**Seams (D-23):** the existing test suites themselves. For each fix, break the guarded behavior on purpose (wrong quoted number, an engine action with no label, a forced e2e timeout, no git in CI) and confirm the test goes red.

**Prior art:** the tests being fixed: `app/test/design-contrast.test.js`, `app/test/undo-labels.test.js`, `app/test/launch-check.js`, `app/test/e2e/design.js`, `app/test/e2e/keep-safe.js`, `app/test/e2e/first-run-home-lookup.js`, `tests/test_docs_in_sync.py`.

## Out of Scope

- The flaky tests (Batch 0), packaging tests (Batch 1), and un-awaited subtests (Batch 5).
- Changing the palette colours so that the quoted contrast numbers become true. The colors stay as they are (N24); the rejected option and its costs are in the spec check (`archive/spec-check-batch9.md`, needs-a-decision 1, option B).
- An architecture test. It already exists and passes. [Fact: checked fact 4]

## Further Notes

- **Checked against the code 2026-11-01** (report: `archive/spec-check-batch9.md`). HEAD is still the review tip `3b84663`, so the review's line cites were re-verified against the same tree.
- **Open questions:** the draft said "None"; none were found by the check either.
- **One premise of the earlier draft was disproved:** "the launch check appends output twice" does not reproduce. Each stream is appended exactly once (`app/test/launch-check.js:79-84`); only the code duplication and the unused `RTI_FAKE_WORKDIR` are real. The story and decision were reworded.
- **One dangerous premise was disproved:** the DESIGN.md quoted numbers are not all true today (soot pairs off by 0.5–0.8). Without correcting them first, the new contrast test would go red on the unchanged design. The correction was decided (N24, 2026-11-01) and is listed in the decisions above.
- **Safety rules for whoever implements this:** no real AI calls, never open `~/.config/ember-app/ember.db` or `key.enc`, no GUI launch except under xvfb, temp files only.

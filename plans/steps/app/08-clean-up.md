# L3 App Step 8: Clean up (job 5, the sweep)

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.2. Spec stories 63 to 69. Needs steps 03, 04 and bridge steps 01, 03.

## Constitution rules this step enforces
B3 (the sweep rules stay in Python), D3 (badge count = dry-run count), T5, I7, P2.

## Deferred settings resolved by this step
- Whether AI close proposals (Phase 5 of `maintain`) are shown in this job. Contract: yes, after the sweep summary, through the same confirm UI as Add, because `maintain` runs them in the same command; with no key and an empty shortlist nothing is asked (the engine decides; the app does not).

## 1. Boundary shapes (commands used)
- Preview: `maintain --dry-run --format json` → table "which item becomes what and why" with heat marks (before → after) and the rule/cause per row (story 64).
- Apply stays disabled until a preview has been shown in this window session (story 65), and says how many changes it will make (story 66). Apply runs `maintain --confirm json`; the result shows changed items with new heat marks (story 67); the heat mark settles.
- Badge on the sidebar: shown only when the last preview count > 0 (story 68); refreshed after any write. The count comes from a `--dry-run` call, never computed by the app.
- Nothing to update → a calm message (story 69).
- Not undoable (spec 12.2): the screen says so in one line.

## 2. Tests
- Contract: preview rows equal `maintain --dry-run` JSON; Apply result equals the terminal run on a copy (parity, DB dump compare).
- E2E: Apply disabled before preview; badge appears only when pending; Phase-5 proposal accept/decline with a fake close proposer; stale shortlist cap note.
- Not covered: sweep correctness (Python tests already cover it).

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- cleanup   -> pass, real numbers
```

## 4. Error codes raised
MAINTAIN-007 to 012, 018 to 022 via the table; APP-001, 002.

## 5. Rollback
The sweep is derived from links and is not undone (spec 12.2); to reverse one result, fix the cause (reverse a replacement, remove a link) and sweep again. Code: revert the commit.

## 6. Done when
E2E and parity tests pass with real counts.

# L3 App Step 12: menu bar, keyboard and the accessibility pass

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.7, §5.8. Spec §9, §10, stories 96 to 104. Needs steps 04 to 11.

## Constitution rules this step enforces
T1 (menu builder pure), T5, B5, I1.

## Deferred settings resolved by this step
- Help menu content: out of scope (spec). The item stays visible and disabled.
- Command+1 to 7 for Jobs: marked *Inference* in the spec (not on Apple's standard list). The founder confirms or removes at this gate.

## 1. Boundary shapes
- One menu definition from the spec §9 table: Ember (Mac), File, Edit, View, Jobs, Window, Help. Same items always; disable, never hide. Undo/Redo labels name the action (from the undo dry-run). On Windows/Linux the same menus sit in the window with Ctrl.
- Every control reachable and operable by keyboard with a visible focus ring; every control and mark has an accessible name (HeatMark says "Active", "Challenged", "Closed").
- Disabled controls say why (story 103). Errors say what failed and what to do next, with the code on request (story 102).
- Nothing animates except the heat-mark settle; Reduce Motion turns it off (stories 99, 104).
- A written manual checklist (`plans/steps/app/12-manual-checklist` section in Build Notes): screen reader pass of one flow per job, 200% text on every screen, keyboard-only pass.

## 2. Tests
- Unit: menu builder output equals the spec table (labels, shortcuts, enabled state by context).
- E2E: tab order and focus ring on each screen; no unnamed interactive element (automatic scan of the accessibility tree); no horizontal overflow at the Largest size on every screen at 1360 px; Reduce Motion media query honoured.
- Contrast: re-run the step 03 contrast test on real screens.
- Not covered: real screen readers and the Mac menu bar (a person with a Mac). Automatic menu-template check on macOS in CI (step 13).

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- a11y menus   -> pass, real numbers
```

## 4. Error codes raised
None new.

## 5. Rollback
Revert the commit.

## 6. Done when
Automatic checks pass with real counts; the manual checklist is run on Debian and its results are in Build Notes.

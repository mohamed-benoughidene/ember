# L3 App Step 12: menu builder and the manual accessibility checklist

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.7, §5.8. Spec §9, §10, stories 96 to 104 (the automatic scans for 96, 97, 98, 100, 101, 103, 104 already run in every screen step through the step 03 helper). Needs steps 04 to 11.

## Constitution rules this step enforces
T1 (menu builder pure), T5, B5, I1.

## Deferred settings resolved by this step
- Help menu content: out of scope (spec). The item stays visible and disabled.
- Command+1 to 7 for Jobs: *Inference* in the spec (not on Apple's standard list). The founder confirms or removes at this gate.

## 1. Boundary shapes (cite L2 §5.7)
- One menu definition from the spec §9 table: Ember (Mac), File, Edit, View, Jobs, Window, Help. Same items always; disable, never hide. Undo/Redo labels name the action from the `undo --dry-run --format json` fields `source_action` and `target_label` ("Undo Close item 3"). File -> Add text opens the popup (the always-available route, L2 §5.5). On Windows/Linux the same menus sit in the window with Ctrl.
- Story 99: Reduce Motion turns the one animation off (checked here once; the scan itself is in the helper).
- Story 102: "code on request" (a Details control) exists on every error block.
- A written manual checklist in Build Notes: one flow per job with a screen reader, 200% text on every screen, keyboard-only pass of one flow, Reduce Motion on, and the Mac menu bar by a person with a Mac.

## 2. Tests
- Unit: menu builder output equals the spec table (labels, shortcuts, enabled state by context).
- E2E: Reduce Motion media query honoured; Details control present on error blocks; File -> Add text opens the popup.
- Contrast: re-run the step 03 test on real screens.
- Not covered by tests: real screen readers and the Mac menu bar (a person with a Mac). An automatic menu-template check on macOS runs in CI at step 13.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- menus   -> pass, real numbers (the accessibility scans run inside every earlier screen step)
```

## 4. Error codes raised
None new (L2 §6).

## 5. Rollback
Revert the commit.

## 6. Done when
Automatic checks pass with real counts; the manual checklist is run on Debian and its results are in Build Notes.

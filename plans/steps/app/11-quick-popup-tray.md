# L3 App Step 11: quick popup, global shortcut, tray

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.5. Spec stories 90 to 95. Needs steps 05, 10 and the step 01 results.

## Constitution rules this step enforces
P4 (shortcut and tray behind a small interface with a fake), B1, T2, T3, I7 (a failed registration never crashes the app).

## Deferred settings resolved by this step
- Popup placement options and default (L2 §9). Contract: choices come from the spike's findings; default centre of the screen where the mouse is.
- Popup look and close rules (spec "Still open"): the founder reviews the screenshot at the gate. Defaults: closes on Esc or after Stop; keeps text if closed by accident (draft kept until the next open).

## 1. Boundary shapes
- Shortcut service: `register(accelerator) -> ok | APP-005`, `unregister()`. Defaults per spec §10 (Option+Command+E on a Mac, Ctrl+Alt+E elsewhere).
- Popup window: the Add component only (same proposal buttons and keys, story 92), a link "Open Ember" to the full window (story 93).
- Missing setup or key: a message in the popup with a path to fix it (story 94); never a silent failure.
- Tray: menu "Quick add / Open Ember / Quit". Two more always-available routes (a tray may not show on every desktop, L2 §2): the menu item File -> Add text, and the launch option `--quick-add`. On Wayland where registration fails, Settings says which routes work.

## 2. Tests
- Unit with a fake shortcut service: registration success, failure → tray shown, re-register after a setting change.
- E2E (Linux X11/headless where possible): popup opens by calling the same handler, Add works end to end with a fake AI, Esc closes, draft restored.
- Not covered by tests: the real global shortcut on every system and on Wayland. Manual checklist: press the shortcut from another program on Debian and report `echo $XDG_SESSION_TYPE`. Windows and macOS: CI launch check only; a person with those machines confirms later.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- popup   -> pass, real numbers
```

## 4. Error codes raised
APP-005 (L2 §6), plus the Add codes.

## 5. Rollback
Revert the commit. Nothing stored except settings.

## 6. Done when
E2E pass; manual Debian checklist result recorded in Build Notes.

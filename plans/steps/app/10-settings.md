# L3 App Step 10: Settings

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.3, §5.4. Spec stories 78 to 89. Needs steps 02, 03.

## Constitution rules this step enforces
I13 (settings loaded once, passed down), D5/D6 (schema number), T1 (conflict warnings pure), T5, B3.

## Deferred settings resolved by this step
- Shortcut conflict detection beyond the three warnings of story 86 (Control on a Mac, no modifier, standard Mac shortcut): not attempted; spec "Open: conflicts not detected". The pane says the shortcut is untested on the system.

## 1. Boundary shapes (cite L2 §5.3, spec §9, §10)
- Four panes: Appearance (Text size to 200% in five steps, spacing follows, Light / Dark), Quick popup (shortcut and position), Menu (hide/reorder jobs; Home and Settings always present), AI connection (paste/test/replace/remove key; remove marked careful).
- Opens with Cmd+Comma on a Mac and Ctrl+Comma elsewhere; the window title names the pane; last pane remembered; every change saves itself with a quiet "Saved" (stories 79 to 81).
- Applying a change takes effect at once (text size, theme); shortcut re-registration failure → `APP-005` message and the tray fallback; key store without OS storage → `APP-003` message and session-only option.
- Key "test": follows L2 §3 decision 5 (same as step 04). Key storage follows decision 4.

## 2. Tests
- Unit: warnings table (Ctrl on Mac, bare key, Cmd+Q/W/C/V/Z etc.); schema validation; atomic write; settings survive a restart (E2E: change, relaunch, same values).
- E2E: 200% text → no horizontal overflow on every screen (automatic); keyboard-only pane switching; Reduce Motion path.
- Security: the key never appears in logs, errors, the settings file, or the ledger (test greps these after a full session).

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- settings   -> pass, real numbers
```

## 4. Error codes raised
APP-003, APP-004, APP-005 (L2 §6).

## 5. Rollback
Settings are one file; deleting it restores defaults. Code: revert the commit.

## 6. Done when
Tests pass with real counts; the grep-for-key test passes.

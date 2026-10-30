# L3 App Step 7: Fix and close (job 4) with Undo and Redo

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.7. Spec stories 49 to 62 and 111 to 123. Needs steps 03, 04 and Undo L2 built.

## Constitution rules this step enforces
B3 (the app shows rules, never decides them), D3, I2-style choices (reason is a choice), T5, P2.

## Deferred settings resolved by this step
- **D1, close confirmation** (spec 12.7): keep preview + final confirm (recommended until Undo is tested), or preview + Undo only. The founder decides at this step's review; default is KEEP.

## 1. Boundary shapes (commands used)
- Pick an item from a list (`list-items`); actions available come from the item's state and the written rules (spec §2): status buttons off for Closed with the reason shown; "verified" only on Assumptions; edit only rationale on a Decision and source on a Finding, others off with a reason.
- Preview = the command's `--dry-run --format json` (`close-item`, `edit-item`, `remove-link`, `undo`, `redo`) shown as "what changes"; Apply runs the same command without `--dry-run`. The dependent count and list in the preview come straight from the dry-run changes (story 57).
- Reverse a replacement: `reverse-supersedes`. Remove a link: `remove-link`; words are Reject/Close/Replaced by, never Delete.
- Undo/Redo: buttons here, Edit menu items, Command/Ctrl+Z; the label comes from `undo --dry-run --format json` ("Undo Close item 3"); refusal `MAINTAIN-025` shown in plain words; `MAINTAIN-023` shows the "older changes cannot be undone" note (stories 118, 123). The heat mark settles on every status change including undo.
- After Add, Link confirm or sweep, the Undo button is honest: those are not undone (story 119); the note says how to reverse each.

## 2. Tests
- Contract: each action through the app equals the matching command on the same KB; each forbidden action stays forbidden (disabled with reason, and, if forced, the engine's code is shown).
- E2E: close with preview then Undo then Redo; set-status with shield then Undo (sweep afterwards behaves as before: compare with control KB); refusal path after a sweep; Undo label text; keyboard Ctrl/Cmd+Z.
- Accessibility: disabled controls expose their reason (screen reader name/description).
- Not covered: hand-feel of the settle motion (founder reviews).

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- fix undo   -> pass, real numbers
```

## 4. Error codes raised
MAINTAIN-001 to 006, 013 to 017, 023 to 027 via the table; APP-001, 002.

## 5. Rollback
Every change here is undoable or recorded; code: revert the commit.

## 6. Done when
E2E pass with real counts; D1 answered and recorded; the prototype's behaviours for this job match.

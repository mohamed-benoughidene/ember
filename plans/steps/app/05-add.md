# L3 App Step 5: Add (job 1) and the confirm UI

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.1. Spec stories 16 to 29. Needs steps 02 to 04 and bridge step 03.

## Constitution rules this step enforces
P4 (the confirm screen is an adapter for the confirm session), D4, D8 stays in Python, I7 (a quit never leaves a half write; engines write only after a confirm), T2, T5.

## Deferred settings resolved by this step
- Drag and drop of a file onto the window (spec "Still open"): not in this step unless decided.

## 1. Boundary shapes (cite bridge L2 §5.4)
- Paste text, press Add. **Fact (read 2026-10-30, `ember/capture/input_reader.py`):** `capture` without `--file` reads ALL of stdin until it ends, so stdin cannot also carry confirm answers. Decision: the app writes the pasted text to a temp file in the user-data folder, runs `capture --file <temp> --confirm json --db <kb>`, keeps stdin for answers, and deletes the temp file afterwards (also on a crash at next start).
- Events drive the UI: `block` (kind item) → ProposalBlock with type, statement, quote, warning; `prompt` → Confirm / Reject / Edit / Stop (Return = confirm, Esc = stop, `e`, `n`, `y`, `q`); edit sub-prompts render as a small form (type, statement, metadata) that answers the three `prompt` events in order.
- "Saved so far" list from accepted answers; summary from the `summary` event; one-click path to Link items.
- Messages (stories 27 to 29): AI unreachable (text is kept, nothing created, Retry), zero proposals, no key (link to AI connection setting). The engine, not the app, decides each; the app maps the code through the plain-sentence table.
- Notice before sending: text is kept word for word and goes to the AI service (story 17).

## 2. Tests
- E2E with a fake AI: a local HTTP server on `EMBER_AI_BASE_URL` (the only seam across a process boundary; the in-process seam used by `CliRunner` tests is not available to a child process): confirm, reject, edit-then-confirm, stop part-way; DB state equals the terminal run on the same input (contract parity).
- Keyboard-only: Return confirms, Esc stops (automatic).
- Failure: fake child dies mid-session → the UI shows the error, no item half-created (DB check).
- Not covered: real AI; manual run with a real key on Debian.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- add    -> pass, real numbers
```

## 4. Error codes raised
APP-001, 002, 008; CAPTURE-xxx (all current codes via the table, L2 §5.6); BRIDGE-001 never reaches the user (a client bug if it does; a test asserts it).

## 5. Rollback
Items are never deleted: a wrong add is reversed by Fix and close (close the item). Code: revert the commit.

## 6. Done when
E2E pass; parity test equal; the manual real-key run recorded in Build Notes.

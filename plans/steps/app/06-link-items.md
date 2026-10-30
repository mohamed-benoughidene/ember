# L3 App Step 6: Link items (job 3)

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.1. Spec stories 42 to 48. Needs step 05.

## Constitution rules this step enforces
P4, D4, I15 (long first run), I7, T2, T5.

## Deferred settings resolved by this step
None.

## 1. Boundary shapes (cite bridge L2 §5.4)
- Start: `relate --latest --confirm json` or `relate --item N --confirm json` (the user picks from a list, never types an id).
- Events: `block` kind link → both items and the relationship in one proposal; prompt choices Confirm / Skip / Reject (Return, `s`, `n`; `y`, `q` also).
- First run may take minutes while a language model downloads (story 45): the app shows a calm "preparing" state with Stop when no event has arrived after the first second, and never a frozen window. **The download itself is an Ember/`relate` behaviour; the app only waits.**
- Messages: "no unrelated items" (story 46), no key (same path as Add, story 48), missing optional package (`RELATE-` code through the table with what to do).
- Summary of confirmed / skipped / rejected (story 47); gatekeeper rejections printed by `relate` as `relate rejected: CODE | detail` lines arrive as `message` events and are shown in plain words.

## 2. Tests
- **Embedder cannot be faked across a process (bridge L2 §10 D2).** With D2 = A, Link items end to end is "Not covered by tests" with one manual check using the real model; what IS tested is the UI against the JSON events (a scripted fake event stream feeding the screen: confirm / skip / reject / rejection message / empty pool / summary) and the bridge parsers. With D2 = B, the E2E uses the test-only embedder setting.
- Parity (D2 = B only): same input, terminal and app, identical `links` and `change_log` rows.
- Waiting-state test with a slow fake child (no event for 3 s): UI shows preparing + Stop; Stop ends the child cleanly (exit 2 path).
- Not covered: real model download; manual run once.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- link    -> pass, real numbers
```

## 4. Error codes raised
RELATE-xxx via the table (L2 §5.6); APP-001, 002, 008.

## 5. Rollback
A wrong link: Fix and close → Remove link (marks it Rejected; Undo also reverses it). Code: revert the commit.

## 6. Done when
E2E and parity pass; manual one-time real run recorded.

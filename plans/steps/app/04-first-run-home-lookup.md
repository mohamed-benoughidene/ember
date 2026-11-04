# L3 App Step 4: first run, Home, Look up

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §5.2. Spec user stories 1 to 15 and 30 to 41. Needs steps 02, 03 and bridge steps 01, 02.

## Constitution rules this step enforces
D3 (counts come from `list-items`, never recomputed), D4, P2, I8 (empty KB is a normal state), T2, T5.

## Deferred settings resolved by this step
- Search in the title bar and drag and drop (spec "Still open"): out of this step unless the founder decides first.

## 1. Boundary shapes (commands used, cite bridge L2 §5.3)
- First run: choose where the knowledge base file lives (default in the user-data folder). **Fact (read 2026-10-30, `open_database` in `ember/adapters/sqlite.py`):** `capture` and `capture-source` create the file on first use; `relate`, `maintain` and the query commands refuse a missing file (`MAINTAIN-007`, `QUERY-003`). No new command is needed. Until the first Add, the app knows the file does not exist and shows the empty state without calling any command.
- Home: `list-items` (counts per status and total), `history --limit N` (latest ledger lines), attention message (Challenged count, `maintain --dry-run` pending count).
- Look up: `topic-search` (query + filters), `list-items` (no query), `show-item` (detail: source, rationale, provenance), `history --item` with `--limit/--offset/--since` (Ledger tab).
- Key step on first run (stories 5 to 8): paste, plain explanation of what a key is and where text goes (6), skip allowed (7), clear messages for empty / too short (8). **Follows L2 §3 decision 5:** with A, "refused" is shown at the first Add and stories 5 and 8 are marked PARTIAL; with B, a `check-key` result is shown here.
- Story by story: 1 setup screen on first launch; 2 three steps and "about two minutes"; 3 file location with a default; 4 one sentence on what the file holds; 9 first action "Add your first text"; 10 Home leads with what needs attention; 11-12 counts match `list-items`; 13 latest ledger lines; 14 the main "Add text" button; 15 the button on the attention message goes to Fix or Clean up.
- Ledger tab words (story 122): `undone` and `redone` history kinds are shown as "Undone" and "Redone" in plain words through the sentence table; a test lists every history kind and fails on a kind with no label.

## 2. Tests
- Contract: Home counts equal `list-items` total and `current-state` Active+Challenged counts on a seeded KB (spec "counts match exactly").
- Each story above has one test line; the step 03 accessibility helper runs on every screen.
- E2E: empty KB shows "No items yet" with Add; loading and error states with Retry (a fake child that fails); filters + "Clear filters"; selecting an item shows source and provenance with the other item's heat mark; Ledger tab paging.
- Not covered: wording quality; founder reads each message.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- first-run home lookup   -> pass, real numbers
```

## 4. Error codes raised
APP-001, 002, 006, 008; QUERY-001, 003, 004, 006, 007 shown through the plain-sentence table (L2 §5.6, §6).

## 5. Rollback
Revert the commit. Read-only screens; no data written except settings.

## 6. Done when
E2E and contract tests pass; both Open items above answered and recorded.

# L3 App Step 4: first run, Home, Look up

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.2. Spec user stories 1 to 15 and 30 to 41. Needs steps 02, 03 and bridge steps 01, 02.

## Constitution rules this step enforces
D3 (counts come from `list-items`, never recomputed), D4, P2, I8 (empty KB is a normal state), T2, T5.

## Deferred settings resolved by this step
- Search in the title bar and drag and drop (spec "Still open"): out of this step unless the founder decides first.

## 1. Boundary shapes (commands used, cite bridge L2 §5.3)
- First run: choose where the knowledge base file lives (default in the user-data folder). **Fact (read 2026-10-30, `open_database` in `ember/adapters/sqlite.py`):** `capture` and `capture-source` create the file on first use; `relate`, `maintain` and the query commands refuse a missing file (`MAINTAIN-007`, `QUERY-003`). No new command is needed. Until the first Add, the app knows the file does not exist and shows the empty state without calling any command.
- Home: `list-items` (counts per status and total), `history --limit N` (latest ledger lines), attention message (Challenged count, `maintain --dry-run` pending count).
- Look up: `topic-search` (query + filters), `list-items` (no query), `show-item` (detail: source, rationale, provenance), `history --item` with `--limit/--offset/--since` (Ledger tab).
- Key step on first run: paste + test (a test call is a one-item `capture` dry connection? **Open:** there is no "test key" command. Candidates: the app only checks the key is non-empty and long enough and says the real test happens at first Add; or a bridge amendment. Decide at the review gate).

## 2. Tests
- Contract: Home counts equal `list-items` total and `current-state` Active+Challenged counts on a seeded KB (spec "counts match exactly").
- E2E: empty KB shows "No items yet" with Add; loading and error states with Retry (a fake child that fails); filters + "Clear filters"; selecting an item shows source and provenance with the other item's heat mark; Ledger tab paging.
- Not covered: wording quality; founder reads each message.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- first-run home lookup   -> pass, real numbers
```

## 4. Error codes raised
APP-001, 002, 006; QUERY-001, 003, 004, 006, 007 shown through the plain-sentence table.

## 5. Rollback
Revert the commit. Read-only screens; no data written except settings.

## 6. Done when
E2E and contract tests pass; both Open items above answered and recorded.

# L3 Undo Step 1: migration 013 and group stamping

Status: DRAFT 2, 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.1, §8. Phase: storage foundation.
**RISK step (AGENTS.md §2):** changes the database structure. Before any code, show the maintainer the then-current counts and ask A or B (see §7).

## Constitution rules this step enforces
D5 (additive column), D6 (numbered migration, version stored), D7 (safety copy), D1 (no row edited), B2 (Maintain and Capture share only the neutral `GroupIdPort`), I10 (additive), T4/T9.

## Deferred settings resolved by this step
- Where `GroupIdPort` lives (L2 §10). Contract: a one-method protocol `next_group_id() -> int` beside `ChangeLogEntry` (`ember/relate/rows.py`) or a new neutral module; the Capture store receives it by injection and gains one optional `group_id` keyword (default `None`), nothing else.
- Index on `group_id` (L2 §10): add only if a test shows a read that needs it. Default: none.

## 1. Boundary shapes (cite L2 §5.1)
- Migration file `ember/adapters/migrations/013_add_change_log_group_id.sql`: `ALTER TABLE change_log ADD COLUMN group_id INTEGER;` nullable, no default, no backfill, no table rebuild (pattern of migrations 010 and 012).
- Port growth, additive (L2 §5.1): the neutral `GroupIdPort.next_group_id() -> int` (`MAX(group_id)+1`, `1` when none); every human write method gains an optional `group_id: int | None = None` (I3: still ≤ 4 inputs). `None` keeps today's behaviour byte for byte.
- Entry points stamp: `run_close_item`, `run_set_status` (the same id on BOTH its transactions), `run_edit_item`, `run_remove_link`, `run_reverse_supersedes`, and the validated-flag path. `run_sweep` and `run_close_proposals` accepted closes: a proposal-accepted close rides `run_close_item` so it IS a human close and is stamped; the sweep is NOT stamped.
- Schema floors unchanged. Version becomes 13.

## 2. Tests
- Migration on a real v12 temp DB: all rows preserved, new column NULL on every old row, schema diff is exactly one column, FK check clean, `.bak-v12` written, failed migration rolls back (model: `tests/test_migration_012.py`).
- Each of the six actions leaves rows whose `group_id` is one shared non-NULL value; the sweep leaves `NULL`; a second action gets a different, larger id.
- `set-status` Challenged→Active: status row and `status_origin` row share the id.
- Existing suites stay green with no edits except schema-version expectations (list each one changed in Build Notes).
- **First commit of this step, before any change:** capture raw-stdout fixtures for `current-state` and `why` (today only `topic_search`, `history`, `history_item_1` are pinned in `tests/fixtures/query/no_flags_golden.json`). All five outputs must stay byte-identical afterwards.
- `ember history`, `export` and `db-check` on an untouched v12 file still succeed (they never migrate).

## 3. CLI check (S1)
```
$ ember close-item --item 1 --reason expired --db t.db        [exit 0, report line unchanged]
$ sqlite3 t.db "select id, field_changed, group_id from change_log order by id"
```
Expect: the close row and each `dependency_closed` row show the same group id; capture/relate rows show empty.

## 4. Error codes raised
MAINTAIN-007, 008, 009 (boot, unchanged), MAINTAIN-011, 012 (writes, unchanged). No new code (L2 §6).

## 5. Rollback
Migration is forward-only (L2 §8 risk 1) (as 010 and 012). Way back: the `<db>.bak-v12` safety copy written before upgrading. Stamping code: revert the commit; rows already stamped keep a harmless extra column value.

## 6. Done when
Full suite passes with the real count shown; the CLI check prints the shared id; the migration test passes on a copy of a v12 file.

## 7. Decision taken (2026-10-30, maintainer): **A — migration 013 approved.** Still show the counts in build notes (done: 0 tracked DB files, no `ember.db` on the machine).
- **A:** go with migration 013 now. Affects: 0 existing rows changed, 0 tracked database files, local files unknown (builder runs `sqlite3 <file> "select count(*) from change_log"` on the maintainer's real file and shows it). Undo: restore `.bak-v12`.
- **B (not taken):** use the spec's fallback (group rows by identical timestamp, no migration). Affects: 0 rows, no structure change; cost: special case in `set-status`, clock-tick risk, step 03 and 05 shrink.

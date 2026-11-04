# L3 Undo Step 5: history, db-check, export, E2E and closeout

Status: DRAFT 2, 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.6, §7. Phase: read side. Needs steps 01 to 04.

## Constitution rules this step enforces
D2, I10 (additive), T4 (one E2E), T9, S3, I17.

## Deferred settings resolved by this step
- The `group_id` field label in `export`: `group_id`, `-` when NULL or when the column does not exist, unless an existing label collides.

## 1. Boundary shapes (cite L2 §5.6)
- `history` (`ember/query/history.py`): for EVERY existing human pair add the same pair with causes `user_undo` and `user_redo`, mapped to the SAME kind as the original. That covers: `status`, `validated`, `link_removed`, `rationale`, `source`, `status_origin`, `link_reversed`. Add `("undo_of","user_undo") -> "undone"`, `("redo_of","user_redo") -> "redone"`, `("link_unreversed","user_undo") -> "link_unreversed"`. `close_reason` stays filled for undo/redo status rows (they stay kind `status_changed`).
- `db-check`: NO new floor entry (a floor of 13 would report every healthy v12 file as `DRIFT`). One new check only when version >= 13: every `undo_of`/`redo_of` marker names an existing group. On v12 print `group_id: not applicable (schema v12)`. Still read-only, no error codes.
- `export`: `gather_export` reads `group_id` only when `PRAGMA table_info(change_log)` shows the column; otherwise prints `-`. It never migrates (`open_query_database`). Render stays pure and deterministic. Regenerate the byte-for-byte expectations on purpose and list each changed expectation in Build Notes.

## 2. Tests
- `tests/query/test_history_unit.py`: loop over every existing human pair x `user_undo`/`user_redo`: none is `unknown`; new kinds; `unknown` fallback intact.
- `tests/test_db_check.py`: seeded drift (marker naming a missing group, v13) -> exit 1 `DRIFT`; healthy v13 exit 0; healthy **v12 exit 0**.
- `tests/test_export.py`: v13 prints group id; **v12 file exports successfully**; two exports byte-identical; read-only hash proof.
- E2E `tests/maintain/test_undo_e2e.py`: capture (fake) -> relate (fake) -> close-item -> undo -> redo -> history; invariants asserted; `db-check` exit 0.

## 3. CLI check (S1)
```
$ ember history --db t.db     -> undo and redo rows appear with kinds "undone"/"redone" and normal kinds for inverse rows
$ ember db-check --db t.db    -> exit 0 (also on a v12 file)
$ ember export --db t.db      -> every ledger row shows group_id (or "-")
```

## 4. Error codes raised (L2 §6)
None new.

## 5. Rollback
Revert the commit. Read side only.

## 6. Closeout (before the L2 is marked complete)
`PROJECT_MAP.md`: one line per new tracked file (every `.py`, every test, every fixture, `__init__.py`) and updated descriptions (`ember/cli.py`, `export.py`, `db_check.py`, the `change_log` table). `docs/commands.md` notes the changed `export` and `db-check` output. `plans/engine-maintain-plan.md` and `plans/engine-query-plan.md` get an Undo amendment note. Build Notes added to steps 01 to 05; full suite count recorded; `tests/test_docs_in_sync.py` green.

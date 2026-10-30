# L3 Undo Step 5: history kinds, db-check, export, E2E and closeout

Status: DRAFT 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.6, §7. Phase: read side. Needs steps 01 to 04.

## Constitution rules this step enforces
D2, I10 (additive), T4 (one E2E), T9, S3, I17.

## Deferred settings resolved by this step
- The `group_id` field label in `export` (L2 §10): `group_id`, with `-` when NULL, unless an existing label collides.

## 1. Boundary shapes (cite L2 §5.6)
- `history`: add pairs `("undo_of","user_undo") -> "undone"` and `("redo_of","user_redo") -> "redone"` to the classifier; inverse rows keep their normal kind with cause `user_undo` / `user_redo` (extend the status-cause set; a pair this build does not know stays `unknown`). History event gains no new required field.
- `db-check`: floor table gains `("undo", 13)`; new check "every `undo_of`/`redo_of` marker names an existing group"; replay check already covered by step 03. Still read-only, no error codes.
- `export`: one new aligned field line `group_id` on every ledger row. The render stays pure and deterministic. Regenerate the byte-for-byte expectations on purpose and list each changed expectation in Build Notes.

## 2. Tests
- `tests/query/test_history_unit.py`: new kinds, `unknown` fallback intact.
- `tests/test_db_check.py`: seeded drift (marker naming a missing group) → exit 1 `DRIFT`; healthy v13 exit 0; floor row shown.
- `tests/test_export.py`: group id printed; two exports byte-identical; read-only hash proof.
- E2E `tests/maintain/test_undo_e2e.py`: capture (fake) → relate (fake) → close-item → undo → redo → history; all invariants asserted; DB integrity and `db-check` exit 0.

## 3. CLI check (S1)
```
$ ember history --db t.db     -> the undo and redo rows appear with kinds "undone"/"redone"
$ ember db-check --db t.db    -> exit 0
$ ember export --db t.db      -> every ledger row shows group_id
```

## 4. Error codes raised
None new.

## 5. Rollback
Revert the commit. Read side only.

## 6. Closeout (before the L2 is marked complete)
`PROJECT_MAP.md` lines for every new file and the changed descriptions (`ember/cli.py`, `ember/adapters/export.py`, tables `change_log`); `plans/engine-maintain-plan.md` and `plans/engine-query-plan.md` get an Undo amendment note; Build Notes added to steps 01 to 05; the full suite count recorded.

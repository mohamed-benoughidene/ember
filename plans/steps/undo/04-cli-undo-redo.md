# L3 Undo Step 4: `ember undo` and `ember redo`

Status: DRAFT 2026-10-30. Parent: `plans/engine-undo-plan.md` §4. Phase: report and CLI edge. Needs steps 01 to 03.

## Constitution rules this step enforces
I12 (exit codes, stdout data, stderr errors), I2 (`--dry-run` is the existing pattern, no other flag), I7 (errors handled at the edge), S1, S2, I13 (`--db`), B3 (no rule in the CLI).

## Deferred settings resolved by this step
- Exact wording of the undo/redo report lines (L2 §10). Contract: one line per changed item or link, same shape as `format_report` lines, ending in `(dry-run)` for `--dry-run`; first line names the group undone and the new group.

## 1. Boundary shapes (cite L2 §4)
- `run_undo(ports, request) -> MaintainResult`-shaped result (named model), `run_redo` likewise. CLI bodies stay thin: open via `open_maintain_database`, call, print, map `EmberError` to `error: <log_line()>` exit 1.
- `--dry-run` loads and derives only; writes zero rows.
- `docs/commands.md` gains `undo` and `redo` (flags, reads, writes, no AI key, exit codes, error codes 023 to 027). `README.md` command table and `GLOSSARY.md` ("undo", "redo" in plain words) updated in the same commit; `tests/test_docs_in_sync.py` must pass.

## 2. Tests
- `tests/maintain/test_undo_cli.py` with `CliRunner` on real temp DBs: success exit 0 with the pinned lines; `--dry-run` DB hash unchanged; `MAINTAIN-023` and `-024` exit 1 with the older-changes note; `MAINTAIN-025` exit 1 after a sweep changed a touched item; unknown flag exit 2 (Click).
- Docs-sync test green.

## 3. CLI check (S1)
```
$ ember undo --dry-run --db t.db   -> planned lines, exit 0, DB hash unchanged
$ ember undo --db t.db             -> "undone group N as group M: ...", exit 0
$ ember redo --db t.db             -> "redone group N as group K: ...", exit 0
$ ember undo --db empty.db         -> "error: MAINTAIN-023 NothingToUndo | ..." exit 1
```

## 4. Error codes raised
MAINTAIN-023, 024, 025, 026, 027, plus the unchanged boot codes 007, 008, 009, 010.

## 5. Rollback
Revert the commit. Commands only; no data shape changes in this step.

## 6. Done when
CLI suite and docs-sync pass with real counts; the four samples above produce the stated exit codes.

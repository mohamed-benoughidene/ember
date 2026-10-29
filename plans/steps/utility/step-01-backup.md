# L3 Step 01: `ember backup PATH` (Engine E: Utility)

L2: `plans/engine-utility-plan.md` §4.1, §5.1, §6 (APPROVED, rotation ruling recorded in §9 finding 14)
Ticket: `.scratch/utility/issues/02-backup-command.md`

## Constitution rules this step enforces

B1 (one job: snapshot), B3 (rotate-not-destroy and verify rules in the adapter, not the CLI edge), D4 (target path validated at the edge), D6 (schema version read, never advanced), I2 (no behavior flags; rotation is a rule), I5/I6 (named EmberError subclasses), I7 (fail fast; broken output deleted, exit 1), I11/I21 (docstrings list raised codes), I17/I18/I19/I20 (stable codes, auto location, entity ids, one-line log_line), P2 (CLI -> adapter -> storage), P3 (fixed 5-phase pipeline), T3/T4 (real temp files, no mocks), T9 (sqlite3 only inside adapters), S1/S2/S4 (standalone CLI, isolated tests, page-copy transfer documented).

## Boundary shapes (L2 §5.1)

Public surface, exact:

- `ember/adapters/backup.py`: `create_backup(source_path: str, target_path: str) -> BackupReport`
- `BackupReport`: named model, fields `path: str`, `schema_version: int`, `item_count: int`, `rotated: str | None` (the `.old-<N>` path when rotation happened, else None)
- `ember/adapters/errors.py`: `BackupError(EmberError)` base (BACKUP-000, never raised directly) + leaves `TargetWriteFailed` (BACKUP-003), `SourceOpenFailed` (BACKUP-001), `SourceInvalid` (BACKUP-002), `VerifyFailed` (BACKUP-004)
- `ember/cli.py`: `@main.command("backup")`, argument `target_path` (one, required), option `--db` (default `ember.db`). One `except EmberError` mapping to `error: <log_line()>` on stderr, exit 1. Success: `backup written: <path> (schema v<N>, <count> items)` (+ ` (rotated to <path>)` on stderr when rotated).

Phase order fixed (L2 §5.1): precheck & rotate -> open source -> snapshot (`sqlite3.Connection.backup`, NEVER `shutil.copy`) -> verify (re-open, read schema_version + COUNT(items)) -> report. Partial file deleted on phase-3 AND phase-4 failure, then exit 1. Rotation: target exists -> rename into `.old-<N>` at the same directory, newest `.old-1`, keep 3, oldest deleted (mirrors `.bak-v` retention in `ember/adapters/sqlite.py:255-270`); target is a directory or rename impossible -> BACKUP-003. No engine floors on the source (L2 §5.1 ruling, verified safe).

## Error codes this step raises (L2 §6)

BACKUP-001 (source missing/not SQLite), BACKUP-002 (source unreadable), BACKUP-003 (target not preparable / snapshot write failed), BACKUP-004 (verify failed). No other codes; no reuse of QUERY codes here.

## Test targets (write first, red -> green)

In `tests/test_backup.py` (real temp SQLite files seeded through the real migration path, like `tests/test_db_check.py`):
1. Backup creates a usable copy: same schema_version and item count read back; exit report fields correct.
2. Rotation: second backup to the same target -> `.old-1` created, report says rotated; four backups -> `.old-2`, `.old-3` exist, oldest gone, still exit 0. Undo path: `mv .old-1` over target restores it (prose in build notes, not a test).
3. Hash proof: source file byte-identical before and after a backup.
4. Failure cleanup: snapshot failure (target made unwritable) -> partial file deleted, BACKUP-003, exit 1. Verify failure simulated -> BACKUP-004, copy deleted, exit 1.
5. Source failure: missing file -> BACKUP-001; garbage file -> BACKUP-001 or BACKUP-002 (assert code, T6/I21).
6. No floors: a v9-schema temp file backs up successfully (L2 §5.1).

## CLI check (run after green)

```
$ ember backup /tmp/opencode/b1.db --db <seeded temp db>
backup written: /tmp/opencode/b1.db (schema v12, N items)      [exit 0]
$ ember backup /tmp/opencode/b1.db --db <same seed>
backup written: /tmp/opencode/b1.db (schema v12, N items) rotated  [exit 0, .old-1 exists]
```

## Rollback

No rollback — the command writes nothing to the source; its only artifacts are the target file and rotation files, all removed by deleting the target directory contents. No schema change (v12 unchanged).

## Build Notes

*(post-implementation: what landed, suite numbers, deviations)*

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

What landed (2026-10-29, branch `feat/data-safety`, one commit):

- `ember/adapters/errors.py`: `BackupError` (`BACKUP-000`, never raised directly)
  plus the four leaves `SourceOpenFailed` (`BACKUP-001`), `SourceInvalid`
  (`BACKUP-002`), `TargetWriteFailed` (`BACKUP-003`), `VerifyFailed`
  (`BACKUP-004`), subclassing `ember.errors.EmberError` after the
  `ember/query/errors.py` base-class pattern.
- `ember/adapters/backup.py`: `create_backup(source_path, target_path) ->
  BackupReport` (frozen-shape dataclass: `path`, `schema_version`, `item_count`,
  `rotated`), five phases pinned as in §5.1. Snapshot uses
  `sqlite3.Connection.backup` only, source opened with the existing
  `_connect_readonly` (no engine floors). Verify re-opens the target read-only
  and reads the `schema_version` table (the `db_check` read pattern) plus
  `COUNT(*) FROM items`. Rotation mirrors `_prune_backups`: shift
  `.old-2 -> .old-3` after deleting the oldest, then `.old-1 -> .old-2`, then
  the old target becomes `.old-1`, keep newest 3.
- `ember/cli.py`: `ember backup TARGET_PATH --db PATH`, one
  `except EmberError` -> `error: <log_line()>` on stderr, exit 1. Success line
  `backup written: <path> (schema v12, N items)` on stdout, `rotated to
  <path>` on stderr when rotation happened. Help text ends with the restore
  warning verbatim.
- `tests/test_backup.py`: 16 tests over the 6 test targets, all seeded through
  the real migration runner and the shared `tests/fakes.py` helpers, no mocks.

TDD numbers: red run first (`ModuleNotFoundError: No module named
'ember.adapters.backup'`, 0 tests pass), then green: `tests/test_backup.py` +
`tests/test_architecture.py` = 22 passed. Full suite: **852 passed, 4
deselected** (baseline 836 + 16 new). CLI check on `/tmp/opencode/u2cli`:

```
$ ember backup /tmp/opencode/u2cli/b1.db --db /tmp/opencode/u2cli/seed.db
backup written: /tmp/opencode/u2cli/b1.db (schema v12, 3 items)      [exit 0]
$ ember backup /tmp/opencode/u2cli/b1.db --db /tmp/opencode/u2cli/seed.db
rotated to /tmp/opencode/u2cli/b1.db.old-1                (stderr)
backup written: /tmp/opencode/u2cli/b1.db (schema v12, 3 items)      [exit 0]
$ ember backup /tmp/opencode/u2cli/b1.db --db /tmp/opencode/u2cli/missing.db
error: BACKUP-001 SourceOpenFailed | ember.adapters.backup._open_source |
db file missing | db_path=/tmp/opencode/u2cli/missing.db             [exit 1]
$ ember backup /tmp/opencode/u2cli/dir --db /tmp/opencode/u2cli/seed.db
error: BACKUP-003 TargetWriteFailed | ... | target path is a directory [exit 1]
```

Undo path (prose, per the target list): after any rotation `mv
/tmp/opencode/u2cli/b1.db.old-1 /tmp/opencode/u2cli/b1.db` puts the previous
snapshot back in place of the newest one.

Deviations (each one line):

1. **Self-backup guard** (addition, D4/finding-9 spirit): the target
   normalizing to the source path is refused `BACKUP-003` *before* rotation,
   otherwise `ember backup ember.db --db ember.db` would first rename the live
   file to `.old-1` and then fail on the now-missing source.
2. **BACKUP-002 raise site**: the source gate reads the `schema_version`
   table after the open, so a valid-SQLite-but-not-Ember file (no
   `schema_version`) raises `BACKUP-002` at phase 2, and a source whose
   `items` table is unreadable surfaces at phase 4 as `BACKUP-004` on the
   target. This split keeps the verify-failure test constructible without
   mocks (a real file with a stamp but no `items` table).
3. **Rotation depth wording**: the target list says "four backups -> oldest
   gone". With keep-newest-3 on the `.old-` chain (mirroring `.bak-v`, which
   counts backup files, not the live file), the first snapshot is deleted by
   the *fifth* run, after the chain `target + .old-1..3` first overflows. The
   test asserts `.old-2`/`.old-3` exist after four backups and the oldest is
   gone after the fifth, all exit 0.
4. The §4 sample shows the rotation on stdout as a `(previous copy now at
   ...)` line. This step's contract phrase ("an extra stderr line `rotated to
   <path>`") was followed, which also matches the L2 §5.1 ruling that "the
   report names the rotation" on the error channel, keeping stdout one line.
   The ticket U1 bullet "refuses to overwrite" is superseded by the panel
   rotation ruling (L2 §9 finding 14, maintainer option A).

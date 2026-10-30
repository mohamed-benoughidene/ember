# L3 App Step 9: Keep safe (job 6)

Status: DRAFT 2026-10-30. Parent: `plans/interface-app-plan.md` §5.2. Spec stories 70 to 77. Needs steps 03, 04 and bridge step 01.

## Constitution rules this step enforces
D1, D7 (backup before touching), B3, I7, T5, S1.

## Deferred settings resolved by this step
- Open a different knowledge base file ("restore", story 76): the app changes its `--db` path in settings; no restore command exists by design (GLOSSARY). The window asks for one confirmation naming the file and says the current file is unchanged.

## 1. Boundary shapes (commands used)
- Back up: native save dialog → `backup <TARGET> --db <kb> --format json` → shows items count, schema version, location, "rotated to .old-N" when present (story 71). Refusing to overwrite the source file is the engine's rule (`BACKUP-` codes / path guard); the app shows the engine's refusal in plain words (story 72) and does not pre-judge it.
- Export: `export --out <file> --format json`; states in one line that an export cannot be restored into Ember (story 74); `EXPORT-002` refusal shown in plain words.
- Health check: `db-check --format json` → plain-word rows (version, floors, triggers, links, replay) with OK / DRIFT / UNREADABLE (story 75).
- Failures say the knowledge base file is unchanged (story 77); true because backup/export never write the live file (utility L2 §1).
- Open file: native open dialog; the chosen file must pass `db-check` (UNREADABLE → `APP-006` message) before the setting changes.

## 2. Tests
- Contract: backup through the app equals `ember backup` (file reads back, count equal); export file bytes equal `ember export --out` on the same KB; db-check rows equal the report.
- E2E: backup twice → `.old-1` shown; export to the DB path refused; open a backup file as the knowledge base then Look up works; corrupt file → clear message.
- Hash proof: live KB byte-identical after backup, export, db-check.

## 3. Check command (S1)
```
$ npm --prefix app run e2e -- keep-safe   -> pass, real numbers
```

## 4. Error codes raised
BACKUP-001 to 004, EXPORT-001, 002, QUERY-003, 004 via the table; APP-006.

## 5. Rollback
Backups and exports only create files. Open-file changes a setting; switch back in Settings or the menu. Code: revert the commit.

## 6. Done when
E2E and hash proofs pass with real counts.

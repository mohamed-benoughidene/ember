# Batch 4: data integrity and multi-writer safety

**Source:** `archive/Plan.md` Batch 4. Decisions D-03, D-23, D-25. Findings from `archive/Problems.md`. Checked facts in `archive/assumption-check.md`.
**Rules:** `Constitution.md`.
**Status:** draft. Checked against the code 2026-11-01 (see `archive/spec-check-batch4.md`). Not yet published.

## Problem Statement

The knowledge base can end up half-written, wrongly migrated, or silently wrong, and `db-check` still says OK.

- **Previews write.** `close-item`, `edit-item` and `remove-link` with `--dry-run` migrate the file and write a backup. (`maintain --dry-run` is already read-only.) [Fact: checked fact 1]
- **Typos create databases.** A mistyped `--db` creates a new empty knowledge base and writes into it.
- **One action, two commits.** An item and its "created" ledger row, or a status and its manual shield, are saved separately. A crash between them leaves a gap the app describes as "nothing was half-written".
- **Migration races.** Parallel openers of a new file crash 3 of 4 times. A missing migration script gives version 13 with a missing table. A database from before version tracking can never be opened. [Fact: checked fact 1]
- **`db-check` checks names, not rules.** A missing table, a no-op trigger with the right name, or version 99 all pass.
- **Backups and export can lie.** Backups copy a live file, rotate before the source is proven, and verify only counts. Export truncates in place and lets values forge section lines.
- **Two writers collide.** A coding agent and the app writing at once (D-03) can pick the same item id or merge two undo groups.

## Solution

- Previews open the file read-only and never migrate or back up.
- `ember init --db PATH` creates a knowledge base; on an existing, healthy, current knowledge base it succeeds without changing anything. Every other command refuses a missing file (D-25).
- Each user action is one transaction.
- Migration runs under an exclusive lock, re-reads the version inside it, and applies a pinned, complete script set.
- `db-check` checks tables, trigger rules and the version range.
- Backups use SQLite's backup function, rotate only after success, and run an integrity check. Export writes to a temp file then renames.
- Item ids are allocated, inserted and logged in one write transaction with a retry on id conflict, and undo group ids are assigned inside the write transaction, so two writers never collide. The id shown before saving stays the id saved.

## User Stories

1. As a user, I want a preview to change nothing, so that previewing is always safe.
2. As a user, I want a preview to say it is a preview, so that I never mistake it for the real change.
3. As a user, I want clicking Link items not to migrate my file without warning, so that only real writes change the format.
4. As an agent using the CLI, I want a typo in `--db` to fail, so that I never create a stray knowledge base.
5. As an agent, I want `ember init` to create a new knowledge base on purpose, so that creation is explicit.
6. As a user, I want my first Add to still create the knowledge base, so that first use stays simple.
7. As a user, I want an item and its history entry saved together or not at all, so that history always matches my items.
8. As a user, I want reopening a challenged item to save its status and its manual mark together, so that the next sweep doesn't re-challenge it.
9. As a user, I want "nothing was half-written" to be true whenever the app says it, so that I can trust that message.
10. As a user, I want a late failure in maintain to still report what changed, so that I know the real state.
11. As a user, I want two Adds at once on a new file to both succeed, so that a first-time race can't break my database.
12. As an agent, I want my CLI writes and the user's app writes to never collide, so that neither of us loses a confirmed item.
13. As a user, I want undo to always revert exactly one action, so that undo never mixes my change with someone else's.
14. As a user, I want Ember to refuse a database missing migration scripts, so that I never get a half-built schema.
15. As a user with an old database from before version tracking, I want a clear message, so that I know it can't be opened.
16. As a user, I want a version-0 file to get its own message, so that I'm not told to "upgrade" a file that never finished being created.
17. As a user, I want `db-check` to find missing tables, so that it means something when it says OK.
18. As a user, I want `db-check` to find a trigger whose rule was changed, so that a broken rule is visible.
19. As a user, I want `db-check` to flag a version newer than this Ember knows, so that I don't use the wrong app version on my file.
20. As a user, I want backups made with SQLite's backup function, so that a backup is always a complete snapshot.
21. As a user, I want my previous backup kept until the new one is proven good, so that a failed backup never costs me the last good one.
22. As a user, I want backups verified with an integrity check, so that "verified" means the file is sound.
23. As a user, I want "keep newest 3 backups" to mean three backups, so that retention does what it says.
24. As a user, I want a brand-new knowledge base not to make a pointless backup, so that retention slots go to real ones.
25. As a user, I want a failed export to leave my previous export intact, so that I never lose a good export.
26. As a user, I want item and history text in exports delimited like source text, so that no value can fake a section.
27. As a user, I want export to work on every version Ember can read, so that older files export too.
28. As a user, I want export's values aligned to the documented column, so that the file reads cleanly.
29. As a user, I want showing an item never to crash when a link appears mid-read, so that lookup always answers.
30. As a user, I want marking an already-validated item as validated not to add a fake history line, so that history only shows real changes.
31. As a user, I want two identical proposals in one note to be caught as duplicates, so that I don't accept the same item twice.
32. As a user, I want one edit to count each warning once, so that warning counts are true.
33. As the founder, I want edits not to burn item ids, so that ids stay readable.
34. As the founder, I want unreachable code removed, so that every branch is tested.
35. As the founder, I want each store's error path to roll back only its own work, so that one failure doesn't discard another's.
36. As the founder, I want undo pointer rows checked for the right group kind, so that undo never re-applies the wrong group.
37. As the founder, I want unknown fields in undo to fail loudly, so that a new field can't silently show the wrong value.
38. As the founder, I want time comparisons to use real timestamps, not text, so that imported dates sort correctly.
39. As the founder, I want a close proposal with a missing link id to be handled before it is compared, so that it can't crash.
40. As the founder, I want undo dry-run to use the right required version, so that it matches its documentation.
41. As the founder, I want table names in schema checks to come only from a fixed list, so that no name is ever pasted into SQL.
42. As the founder, I want path comparison to follow the file system's rules, so that two spellings of one file are treated as one.
43. As the founder, I want migration 011's backfill to account for reversed links, so that imported data stays consistent.
44. As a contributor, I want the "v10" test fixture to really be version 10, so that version tests test what they claim.
45. As the founder, I want history rows to carry their undo group id, so that the data matches the row type.
46. As a user, I want input checks to run before the database opens, so that a bad option gives the bad-option error.

## Implementation Decisions

### Opening and creating (D-25)
- New command `ember init --db PATH`: creates and migrates a new file. On an existing file it checks before touching anything: a healthy Ember database already at the pinned latest version gets a success with no changes (this is what makes the two-racing-first-Adds case of story 11 work); an existing non-Ember file and an existing Ember file older than the latest version are refused, each with its own house code. (N8)
- All other commands open an existing file only. Missing file gives a house code.
- The app runs `init` when the first Add targets a missing file (today Add creates it, per checked fact 1), then runs capture. Two first Adds racing both run this init+capture pair; the second init sees a healthy, current file and does nothing. The test harnesses that seed a knowledge base with `ember capture-source` (the launch check, `app/test/launch-check.js:10-12`) must also switch to `ember init` first in this same change, or the launch check fails once missing-file refusal lands.
- Read-only opener for the three remaining dry-runs and for relate's reads (universe, links, embedding-cache lookups). It never migrates or backs up. Relate opens one second, short-lived write connection only to save embedding-cache vectors (the upserts and the model-change wipe) and the raw AI reply; that connection never migrates either (N9). A file older than the command's required version is refused for preview with a "needs update" code instead of being migrated (the existing floor pattern: maintain 11, undo dry-run 13, query 10 — a healthy older file a command can read stays previewable).
- `close-item --dry-run` output ends with the same preview marker the other commands use.
- Command input is validated before the database is opened.

### One transaction per action
- The SQLite adapter offers a single "unit of work" entry point. A user action (create item with its ledger row, status change with its shield and origin row, maintain's write set) runs in one transaction. No store commits or rolls back on its own inside it.
- If maintain fails after some writes in one action, that action rolls back. If maintain completes several separate actions and a later one fails, it still prints the JSON document of what completed.
- The app's "nothing was half-written" sentence is only shown for codes where this is now true.

### Migration
- Read version and apply scripts inside one `BEGIN EXCLUSIVE` transaction per step, re-reading the version inside. Retry on busy within the existing busy timeout.
- The latest version is pinned in code. Startup asserts the script set is exactly 1..LATEST. Anything else is a house error before any change.
- A database with tables but no version table is refused with its own code (no adoption).
- Version 0 with no items table gets its own code and sentence.
- Migration 011 backfill accounts for reversed links.
- No backup is made when migrating a brand-new file.

### Multi-writer ids (D-03)
- Item ids are chosen by the app, as today (`MAX+1` computed inside the transaction), and are still shown to the user before the write; the id the confirm screen shows is the id the item gets (N10).
- Allocation, the item insert and its "created" ledger row run in one `BEGIN IMMEDIATE` transaction. If another writer took the id (unique-key conflict), the transaction re-reads `MAX+1` inside the lock and retries; inside `BEGIN IMMEDIATE` no other writer can insert between the re-read and the insert, so the retry suffices.
- Edits do not consume a new item id (the edit path stops asking for a fresh one; story 33).
- Source ids stay SQLite-assigned (unchanged from today). Undo group ids are assigned inside the write transaction.
- Source reuse is decided inside the transaction.

### `db-check`
- Checks the full expected table list, each trigger's SQL against the expected definition, and that the version is between 1 and LATEST.
- Any mismatch is one DRIFT line in the report (`result: DRIFT`, exit 1), never a crash and never a new error code: a check reports, it does not raise (the contract already pinned by `ember/adapters/db_check.py:5-7`).

### Backups and export
- Backups use SQLite's online backup function. The previous backup is renamed only after the new one passes `PRAGMA integrity_check`, and the file is synced to disk.
- Migration pre-backup names include a timestamp (today the name carries the source version, `.bak-v<version>`, so a repeated run overwrites the same name and only one old copy survives), so retention keeps three real backups. The `ember backup` rotation already keeps its last three (`.old-1..3`).
- Export writes to a temp file in the same folder, syncs, then renames over the target. All exported values are delimited the same way. Columns align to the documented width. `metadata` is selected only when the version has it.

### Smaller correctness fixes
- Show-item and why read items, links and sources in one read transaction, and a dangling target gives a house code.
- `set-validated` on an item already in that state is a no-op with no ledger line.
- The near-duplicate scan includes items accepted earlier in the same note.
- One edit counts each warning once. Unreachable dropped-proposal branch removed.
- Undo checks pointer rows for group kind, and fails loudly on unknown fields.
- Timestamps are parsed before comparing, in the manual-shield boundary and `--since`.
- Close proposer handles a missing link id before comparing.
- Undo dry-run uses the documented required version.
- Schema checks take table names from a fixed list.
- Path comparison uses the file system's real identity (same device and inode) when both paths exist (already true: `os.path.samefile`, `paths.py:14-16`); when one does not exist, the fallback compares symlink-resolved real paths instead of plain absolute strings.
- History rows select their group id.
- The "v10" test fixture is built without running migrations past 10.

## Testing Decisions

**Good tests here** use a real SQLite temp file and assert the observable result: file hash, schema version, rows present, error code.

**Seams (D-23):** the `ember` CLI on temp databases, plus the public database open function for thread races.
1. Dry-run: file hash and version unchanged, no `.bak` file.
2. `--db` on a missing path: refused. `init` then the same command: works. `init` on an existing healthy, current file: succeeds with no changes; `init` on a non-Ember file or an older-version file: refused (N8).
3. Forced ledger failure (trigger): no item row left. Forced shield failure: status unchanged.
4. 4 and 8 parallel openers on a new file: none crashes, version 13. 4 parallel captures on a new file: all succeed. Two init+capture pairs racing on a new file: both Adds succeed (story 11, via N8).
5. Two writers adding at once (100 rounds): distinct ids, separate undo groups, undo reverts exactly one. A forced id conflict (another writer takes `MAX+1` first): the retry saves the item with the next free id (N10).
6. Dropped migration script: refused before any change. Pre-version database: its code.
7. `db-check`: missing table, no-op trigger, version 99 each give a finding.
8. Backup: integrity check runs, previous backup kept on failure, three timestamped backups kept.
9. Export: a forced mid-write failure leaves the old export. A value containing a section line stays delimited.
10. Relate: the database version is unchanged after a run and no migration ran; a fresh cache vector and the raw AI reply are still saved by the short-lived write connection (N9).

**Prior art:** the review's own repros (report section 10). `tests/query/fakes.py` for building fixtures.

## Out of Scope

- The app screens that show these codes (Batches 5 and 6).
- Search and history speed (Batch 8).

## Further Notes

- Open questions for the code check (all answered 2026-11-01, evidence in `archive/spec-check-batch4.md`): item ids are app-chosen today (`MAX+1` computed in Python at Phase 3, `sqlite.py:1842-1857`); source ids are already SQLite-assigned (`lastrowid`, `sqlite.py:444-459`). Yes, a caller depends on the id before the insert: the confirm block prints `- id:` to the user before any write (`confirm_write.py:99`), and an edit revalidates with a new id. No timestamp column exists for backups and none is needed — backups are files, not rows; the timestamp goes in the file name.
- Decisions found by the code check were resolved 2026-11-01 by the founder (Plan.md decision table; options and costs in `archive/spec-check-batch4.md`): (1) relate's reads go through the read-only opener, and one short-lived write connection saves the cache vectors and the raw AI reply — relate never migrates (N9, option A); (2) item ids are still shown before saving, and allocation, insert and ledger row run in one `BEGIN IMMEDIATE` transaction with a retry on id conflict — edits stop taking a new id (N10, option A); (3) `ember init` succeeds on an existing, healthy, current Ember database and refuses a non-Ember file or an older version (N8, option A).

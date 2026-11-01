# Batch 4 implementation plan: data integrity and multi-writer safety
Spec: docs/Spec-Batch4.md
Branch: `batch-4` (D-29): each batch works on its own branch `batch-N`, cut from where the previous batch merged, and merges into `ember-interface` when its "Done when" passes — so `batch-4` is cut from the tip of `ember-interface` after `batch-3` merged there; if Batch 3 has not merged yet, this batch cannot start.
Needs first: Batches 0, 1, 2 and 3, in that order (archive/Plan.md section 3 order). Batch 2 especially: the new refusal codes here must be registered the same way (check report section 4). The `ember init` command and the app's first-Add change must ship in the same merge.
Size: 67 steps in 22 chunks (chunk 5 has 4 steps), about 42-52 hours.

## Before you start
- Run the Python tests this batch touches, exactly as typed (the venv is at `.venv/bin/pytest`, verified present):
  - `.venv/bin/pytest tests/test_batch4_init.py tests/test_batch4_transactions.py tests/test_batch4_writers.py tests/test_batch4_migrations.py -q` (all four of these files are NEW, created in this batch)
  - `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -q`
  - `.venv/bin/pytest tests/relate/test_relate_cli.py -q`
  - `.venv/bin/pytest tests/test_db_check.py tests/test_backup.py tests/test_export.py -q`
  - `.venv/bin/pytest tests/query/test_list_show_cli.py tests/query/test_history_integration.py tests/query/test_history_window_unit.py -q`
  - `.venv/bin/pytest tests/test_cli_validated.py tests/maintain/test_undo_core_unit.py tests/maintain/test_undo_cli.py tests/maintain/test_derive_unit.py tests/maintain/test_close_proposer_unit.py tests/test_item_gatekeeper_unit.py tests/test_confirm_write_unit.py -q`
  - App side: `npm test --prefix app` (plain node, no display needed)
  - App launch check (the only GUI command — xvfb is installed locally (I2), so this runs as typed, nothing to install): `xvfb-run --auto-servernum npm run check:launch --prefix app`
- Safety rules:
  - No AI keys: any command that could call the AI (capture, relate, maintain with proposals) runs as `env -u EMBER_AI_API_KEY -u OPENROUTER_API_KEY ...`. The Rust and JSON tests here use fake proposers, but keep the env unset anyway.
  - No real DB, no real `key.enc`: never touch `~/ember.db` or `~/.config/ember*`. Every test database lives in pytest's `tmp_path` or, for manual commands, under `/tmp/opencode/batch4/`.
  - GUI / Electron runs only under `xvfb-run` (here: the launch check only).
  - Temp files only under `/tmp/opencode/batch4/`.
  - No package installs or removals; nothing outside the listed files.

## Chunk 1 of 22: options are checked before the database opens
Covers: story 46; finding 4.7 #8.

1. Add a failing test `close_item_refuses_a_bad_reason_before_opening_the_database` to `tests/maintain/test_maintain_commands_cli.py` (file exists; the test is NEW). It calls the CLI (`ember.cli.main`) with `close-item --item 1 --reason typo --db <path that does not exist>` and asserts a Click usage error (exit 2, "Invalid value" for `--reason`) and that no file was created at `<path>`.
2. Run `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -k refuses_a_bad_reason -q`. Expect: 1 failed — today the database is opened first, so the test sees a MAINTAIN-007 house line instead of the usage error.
3. In `ember/cli.py`, functions `close_item`, `edit_item` and `remove_link`: run the option checks (close reason against `HUMAN_SETTABLE_REASONS` from `ember/maintain/human_actions.py`; the edit field whitelist; remove-link's link id) BEFORE `open_maintain_database` is called.

Proof it's real: temporarily move the new checks back behind the open call in `close_item`; the test goes red again (MAINTAIN-007 instead of the usage error). Undo the move.
Done when: `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -k refuses_a_bad_reason -q` prints "1 passed".
Commit message: B4-01: command input is validated before the database opens

## Chunk 2 of 22: the three dry-runs open read-only
Covers: story 1; findings 4.6 #2 and 4.10 #1 (same finding).

1. Add three failing tests to `tests/maintain/test_maintain_commands_cli.py` (file exists; the tests are NEW): `close_item_dry_run_leaves_an_older_file_byte_identical`, `edit_item_dry_run_leaves_an_older_file_byte_identical`, `remove_link_dry_run_leaves_an_older_file_byte_identical`. Each builds a real v12 file from scripts 001-012 (the same pattern as `_build_v12_db` in `tests/test_db_check.py:52-62`), records the sha256 and version, runs the command with `--dry-run`, and asserts: version still 12, hash unchanged, and no `*.bak-v*` file beside it.
2. Run `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -k dry_run_leaves_an_older_file -q`. Expect: 3 failed — today each command opens the writing database (`ember/cli.py:684`, `:852`, `:911`), migrates to 13, and writes `.bak-v12`.
3. In `ember/cli.py`, in `close_item`, `edit_item` and `remove_link`: the `--dry-run` branch opens the file with `open_maintain_database_readonly(output.db_path, required_version=11)` (the read-only opener that never migrates, `ember/adapters/sqlite.py:187`).

Proof it's real: switch one of the three dry-run branches back to `open_maintain_database` — that test fails again with version 13 and a `.bak-v12`. Undo.
Done when: the command from step 2 prints "3 passed"; `ls` on the temp dir shows no `.bak-v12`.
Commit message: B4-02: close-item, edit-item and remove-link --dry-run never migrate or back up

## Chunk 3 of 22: close-item's preview says it is a preview
Covers: story 2; finding 4.10 #5.

1. Add a failing test `close_item_dry_run_output_ends_with_the_preview_marker` to `tests/maintain/test_maintain_commands_cli.py` (file exists; the test is NEW). Run `close-item --item 1 --reason invalidated --dry-run` with `--format text` on a seeded file and assert every report line ends with ` (dry-run)` — the marker `edit-item` and `remove-link` already print (`ember/cli.py:885`, `:947`).
2. Run `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -k preview_marker -q`. Expect: 1 failed — `close-item` prints plain report lines with no marker.
3. In `ember/cli.py`, function `close_item`: in text format, append ` (dry-run)` to the printed report lines when `output.dry_run` (the `edit_item` render at `:880-886` is the pattern). The JSON document already carries `dry_run=true`.

Proof it's real: remove the marker suffix again; the test fails on the first report line. Undo.
Done when: the step-2 command prints "1 passed".
Commit message: B4-03: close-item --dry-run output marks itself a preview

## Chunk 4 of 22: relate reads read-only; its writes move to one short-lived connection
Covers: story 3; finding 4.8 #12 (decision N9).

1. Add a failing test `relate_never_migrates_and_still_saves_cache_reply_and_link` to `tests/relate/test_relate_cli.py` (file exists; the test is NEW). Seed a real v12 file (scripts 001-012 pattern) plus items with `tests/fakes.py` helpers, run the full `relate` command through `ember.cli.main` with the module's existing fakes (`_patch_phase2_ports`, `_patch_phase34_ports`, `_FakeLinkProposer`, `tests/relate/fakes.py: FakeEmbedder`), and assert: `schema_version` is still 12, no `.bak-v*` file exists, one `item_embeddings` row was written, one `ai_responses` row was written, and the accepted link is Confirmed.
2. Run `.venv/bin/pytest tests/relate/test_relate_cli.py -k never_migrates -q`. Expect: 1 failed — today `open_relate_database` (`ember/adapters/sqlite.py:110`) migrates the v12 file to 13.
3. Implement decision N9: in `ember/adapters/sqlite.py` add a NEW read-only relate opener (modelled on `open_maintain_database_readonly`, floor 12, never migrates, no backup); in `ember/cli.py` function `relate`: the reads (universe via `load_item_candidates`/`load_latest_candidates`, link and cache lookups, gatekeeper reads) go through the read-only connection; the writes (embedding-cache upserts and the model-change wipe in `ember/relate/candidate_pool.py:148`, the raw AI reply save, and the confirmed-link writes through `SqliteLinkStore`) open ONE short-lived write connection (never migrates) after the pool read. Note: the spec sentence names only the cache vectors and the raw reply, but the confirmed-link inserts also write — riding this same write connection is decided (I8: relate's write connection also saves confirmed links), not a founder question.

Proof it's real: point the short-lived write connection back at the read-only opener. The same test now fails on the saved-vector assertion (`RELATE-019` in the output). Undo.
Done when: the step-2 command prints "1 passed"; the seeded temp file still reports version 12.
Commit message: B4-04: relate reads read-only; cache, raw-reply and link writes on a short-lived write connection (N9)

## Chunk 5 of 22: `ember init` and the missing-file refusal
Covers: stories 4, 5, 6, 11; finding 4.10 #8 (decision N8).

1. Create `tests/test_batch4_init.py` (NEW) with four failing tests: `init_creates_and_migrates_a_new_knowledge_base`, `init_on_a_healthy_current_file_changes_nothing` (sha256 equal before and after, exit 0), `init_refuses_a_non_ember_file` (named house code, file unchanged), `init_refuses_an_older_version_file` (named house code, file unchanged).
2. Add two more failing tests to the same file: `list_items_refuses_a_missing_file` and `capture_source_refuses_a_missing_file` (both: named house code, no file created — today both create and migrate the file instead).
3. Add the test `two_init_capture_pairs_racing_on_a_new_file_both_succeed` to `tests/test_batch4_init.py` (test NEW): two threads each run `ember init` then `capture-source` on one fresh path (as the app's first Add will); both exit 0, one source row. Add the exact CLI invocation convention you use in the same file, then run `.venv/bin/pytest tests/test_batch4_init.py -q`. Expect: all 7 fail (`init`: "No such command"; the refusals: file created / wrong error).
4. Implement: in `ember/cli.py` add the NEW `init` command (`ember init --db PATH`): create and migrate a new file; on an existing file succeed only when it is a healthy Ember database already at the pinned latest version (N8), otherwise refuse. In `ember/adapters/sqlite.py`, the open paths get the missing-file refusal with a named house code (a NEW error class per family, next free number).

Done when (this step creates and overwrites database files — only ever in pytest `tmp_path` or `/tmp/opencode/batch4/`): the step-3 pytest run shows "7 passed" and no file outside the temp dir was touched.

Proof it's real: in the new `init`, replace the healthy-file success with a hard refusal (remove the N8 branch). `init_on_a_healthy_current_file_changes_nothing` and the race test go red. Undo.
Done when: `.venv/bin/pytest tests/test_batch4_init.py -q` prints "7 passed"; `.venv/bin/ember --help` now lists `init`.
Commit message: B4-05: ember init creates on purpose; every other command refuses a missing file (D-25, N8)

## Chunk 6 of 22: the docs name `init`
Covers: supports stories 4 and 5 (`tests/test_docs_in_sync.py` pins the README command table and `docs/commands.md` sections).

1. Add the ``| `init` |`` row to the command table in `README.md` (the table's own format: bare command name, no `ember` prefix — the row pinned by `test_readme_command_table_lists_every_command`) and an `### ember init --db PATH` section to `docs/commands.md` (what it creates, what it refuses, no API key).
2. Run `.venv/bin/pytest tests/test_docs_in_sync.py -q`. Expect: all pass (before this chunk, `test_readme_command_table_lists_every_command` would fail once `init` exists).
3. Run `.venv/bin/ember init --db /tmp/opencode/batch4/readme-demo.db` and `.venv/bin/ember init --db /tmp/opencode/batch4/readme-demo.db` (second run). Expect: first run creates; second run succeeds with "no changes" and the file hash is identical (visible with `sha256sum`).

Proof it's real: temporarily delete the README table row; `test_readme_command_table_lists_every_command` fails. Undo the deletion.
Done when: both runs above exit 0 and `sha256sum` prints the same digest twice.
Commit message: B4-06: document ember init in the README and the command inventory

## Chunk 7 of 22: the app's first Add runs init, the launch check seeds with init
Covers: stories 5 and 6 (the app side that must ship with chunk 5; check report section 4).

1. Add a failing test `the_first_add_runs_init_before_capture_when_the_file_is_missing` to `app/test/add-session.test.js` (file exists; the test is NEW): the fake engine asserts `ember init --db <path>` was spawned before `capture`.
2. Run `npm test --prefix app -- add-session`. Expect: 1 failed.
3. Wire it: in `app/main/add-session.js`, `startSession` runs `ember init` first when the knowledge-base file at `dbPath()` does not exist, then starts `capture` (today capture creates the file). `app/main/ipc.js` `validateAddTarget` (`:675-687`) keeps allowing a missing file (the file may be created by init) — no change needed there beyond the comment. In `app/test/launch-check.js`, change the seed call (`seedBaseArgs`, line 38, currently `capture-source`) to run `ember init` first, then `ember capture-source` — otherwise the launch check breaks once capture-source refuses a missing file (spec, "Opening and creating").

Proof it's real: remove the init call in `add-session.js` again; the new node test fails ("capture started without init"). Undo.
Done when: `npm test --prefix app -- add-session` is green, and `xvfb-run --auto-servernum npm run check:launch --prefix app` still passes (window starts, `items: N` printed, exit 0).
Commit message: B4-07: the app's first Add runs ember init, the launch check seeds with init

## Chunk 8 of 22: one user action is one transaction
Covers: stories 7, 8, 9, 10, 35; findings 4.3 #9 and 4.5 #2 (same finding), 4.6 #1, 4.4 #4, 4.6 #3, 4.3 #22.

1. Create `tests/test_batch4_transactions.py` (NEW) with the failing test `a_forced_ledger_failure_leaves_no_item_row`: seed a real v13 file with `tests/fakes.py` helpers, plant `CREATE TRIGGER force_fail BEFORE INSERT ON change_log WHEN NEW.field_changed = 'created' BEGIN SELECT RAISE(ABORT, 'forced'); END` on the same connection, run the capture accept write (`SqliteItemGatekeeper.insert_item` + `log_created`, `ember/adapters/sqlite.py:1859-1900`), and assert `items` is empty. Today red: the item insert commits first, so the item survives.
2. Add two more failing tests to the same file: `a_forced_shield_failure_leaves_the_status_unchanged` (trigger aborts `change_log` rows with `field_changed = 'status_origin'`; run `run_set_status` Challenged -> Active — today the status write commits and the shield is lost, `ember/maintain/run_maintain.py:214-222`) and `maintain_format_json_still_prints_the_document_when_a_later_action_fails` (seed a file whose sweep will change one item, run `maintain --format json` with no AI key so the close-proposal phase fails; assert the JSON document shows the sweep changes AND exit 1 — today only an error line prints, `ember/cli.py:618-620`).
3. Implement the unit of work: in `ember/adapters/sqlite.py` add a NEW `unit_of_work(conn)` context manager (one `BEGIN` ... one `COMMIT` / `ROLLBACK`); remove the per-store `commit()`/`rollback()` calls from inside the write methods it wraps (the capture `insert_item`/`log_created`, `apply_status_origin`); in `ember/capture/confirm_write.py` `accept` (`:164-173`) and in `run_set_status` (`ember/maintain/run_maintain.py:201-222`) wrap each action in it; in `ember/cli.py` `maintain`, on an `EmberError` after the sweep printed changes and `--format json` is set, print the document of what completed before exiting 1. Story 9's screen sentence itself is Batch 3/6 work (check report section 4) — here only the engine side becomes true.

Proof it's real: make `unit_of_work` commit after every store call again (a one-line change); both forced-failure tests go red. Undo.
Done when: `.venv/bin/pytest tests/test_batch4_transactions.py -q` prints "3 passed".

Done when (this step changes the write paths; data touched is only pytest temp files): the command above passes and `tests/test_batch4_writers.py` is still red (not yet written, so it cannot mask anything).
Commit message: B4-08: one user action is one transaction; maintain reports what completed (4.3 #9, 4.6 #1, 4.6 #3, 4.3 #22)

## Chunk 9 of 22: migration refusals, a pinned script set, no pointless first backup
Covers: stories 14, 15, 16, 24; findings 4.3 #2, 4.3 #5, 4.7 #1, 4.5 #17.

1. Create `tests/test_batch4_migrations.py` (NEW) with four failing tests: `a_dropped_migration_script_is_refused_before_any_change` (the NEW pinned-script-set guard refuses when the script numbers are not exactly 1..13; today `_migration_scripts` at `ember/adapters/sqlite.py:374-381` just sorts whatever it finds), `a_tables_but_no_version_table_file_is_refused_with_its_own_code` (no adoption, story 15), `a_version_0_file_with_no_items_table_gets_its_own_code` (story 16, distinct from the "needs update" sentence of 4.7 #1), `migrating_a_brand_new_file_makes_no_backup` (open a fresh path via `ember init`; assert no `*.bak*` file beside it — today a `.bak-v0` is written, `sqlite.py:344-345`).
2. Run `.venv/bin/pytest tests/test_batch4_migrations.py -k "dropped or no_version_table or version_0 or brand_new" -q`. Expect: 4 failed.
3. Implement in `ember/adapters/sqlite.py`: pin `_LATEST_VERSION = 13` (NEW constant) and assert `_migration_scripts()` returns exactly 1..`_LATEST_VERSION` before anything is touched (house error otherwise); refuse a file that has tables but no `schema_version` table with its own code; give version 0 with no `items` table its own code and sentence inputs; skip the pre-migration backup when the file is brand-new (nothing to back up).

Proof it's real: delete the pinned-set assertion; the dropped-script test passes the open again (red). For the backup: revert the brand-new skip; `migrating_a_brand_new_file_makes_no_backup` goes red with a `.bak-v0`. Undo both.
Done when: the step-2 command prints "4 passed" and `tests/test_migration_runner.py tests/test_migrations.py -q` stay green.
Commit message: B4-09: pinned script set 1..13, refusal codes for foreign and v0 files, no backup for a brand-new file

## Chunk 10 of 22: every connection sets an explicit busy timeout
Covers: decision I8 (Decisions from the implementation-plan check, 2026-11-01). This is the precondition for the busy retry in chunk 11 and for every parallel-writer test below.

1. Add a failing test `every_opened_connection_sets_busy_timeout_to_5000` to `tests/test_batch4_migrations.py` (file exists since chunk 9; the test is NEW): open one fresh file through `open_database` and a second through `open_maintain_database` (I8 says *every* connection), and assert `PRAGMA busy_timeout` returns 5000 on both connections.
2. Run `.venv/bin/pytest tests/test_batch4_migrations.py -k busy_timeout -q`. Expect: 1 failed — today no `PRAGMA busy_timeout` is set, so the pragma reads 0 (Python's sqlite3 5 s default is a library-side wait, not the pragma).
3. Implement: in `ember/adapters/sqlite.py`, `_connect` runs `PRAGMA busy_timeout = 5000` on every connection it opens (I8), so all openers — reads, writes, the migration retry (chunk 11) and the parallel-writer tests — share one visible limit.

Proof it's real: remove the pragma line from `_connect`; the test fails again (both connections read 0). Undo.
Done when: the step-2 command prints "1 passed" and `.venv/bin/pytest tests/test_batch4_migrations.py -q` stays green.
Commit message: B4-10: every connection sets PRAGMA busy_timeout to 5000 ms (I8)

## Chunk 11 of 22: the migration lock and the 011 backfill
Covers: story 43; findings 4.3 #1 and 4.3 #18. Also the opener half of story 11 (the two-Adds-at-once file stays healthy is chunk 5's init idempotence; the opener crash is fixed here).

1. Add two failing tests to `tests/test_batch4_migrations.py` (tests NEW): `migration_011_backfill_accounts_for_reversed_links` (build a real v10 file from scripts 001-010, insert a link and `change_log` rows `link_reversed` then `link_unreversed`, migrate to 13, assert `links.reversed_at IS NULL` — today the backfill at `ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql:12-19` reads only `link_reversed` and stamps it) and `four_parallel_openers_of_a_new_file_all_succeed` (4 threads call `open_database` on one fresh path; none raises, version ends 13 — today ~3 of 4 crash, the check report's confirmed fact).
2. Run `.venv/bin/pytest tests/test_batch4_migrations.py -k "backfill or parallel_openers" -q`. Expect: 2 failed.
3. Implement: in `ember/adapters/sqlite.py`, `_apply_migrations` runs each step inside one `BEGIN EXCLUSIVE` transaction and RE-READS the version inside it, retrying on busy within the 5000 ms busy timeout every connection sets (I8, chunk 10); edit `ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql` so the backfill's `EXISTS` also requires that no later `link_unreversed` row follows the last `link_reversed`.

Done when (migration script touched — own check): `.venv/bin/pytest tests/test_batch4_migrations.py tests/test_migration_011.py tests/test_migration_runner.py tests/test_migrations.py -q` all green, and a fresh full migration of an empty temp file under `/tmp/opencode/batch4/` still ends at version 13 (`SELECT version FROM schema_version`).

Proof it's real: revert the 011 `EXISTS` guard; the backfill test fails again (timestamp stamped on a link that was un-reversed). Undo.
Done when: the step-2 command prints "2 passed" (plus the migration files above stay green).
Commit message: B4-11: migrations run under an exclusive lock with a re-read version; 011 backfill honours link_unreversed

## Chunk 12 of 22: the capture races hold
Covers: story 11; finding 4.3 #1 (the write side).

1. Add a failing test `four_parallel_capture_sources_on_a_new_file_all_succeed` to `tests/test_batch4_init.py` (test NEW): 4 threads run `ember capture-source --db <fresh path>` with distinct texts; all exit 0, the file ends at version 13, healthy (this is the regression pin the spec's seam 4 asks for).
2. Run `.venv/bin/pytest tests/test_batch4_init.py -k parallel_capture -q`. Expect: 1 passed IF chunk 11's lock landed correctly (the check report measured this holding even today; if it fails, the lock above has a bug — fix `ember/adapters/sqlite.py` before moving on). This test is the guard, not the fix.
3. Run the whole migration suite once more: `.venv/bin/pytest tests/test_batch4_migrations.py tests/test_batch4_init.py -q`. Expect: all green.

Proof it's real: raise the parallelism to 8 threads in the step-1 test; if any run crashes or the version is not 13, the lock is incomplete (this is exactly the spec's seam 4 "4 and 8 openers" clause). Restore 4 threads after a green run.
Done when: the step-3 command prints "all passed" with no crash line in the output.
Commit message: B4-12: regression pins for parallel first opens and captures

## Chunk 13 of 22: two writers get distinct ids and separate undo groups
Covers: stories 12 and 13; findings 4.3 #19 and 4.6 #4 (same race), 4.3 #20, 4.5 #11.

1. Create `tests/test_batch4_writers.py` (NEW) with the failing test `two_writers_adding_at_once_get_distinct_ids_and_separate_undo_groups` (the spec's 100 rounds, seam 5): per round, two threads each write one item + its `created` row through the real store on one file; assert every round leaves distinct item ids, distinct `group_id`s, and `undo` reverts exactly one group.
2. Run `.venv/bin/pytest tests/test_batch4_writers.py -k distinct_ids -q`. Expect: 1 failed within 100 rounds (duplicate group ids merge two groups, or a lost write raises CAPTURE-013).
3. Implement: in `ember/adapters/sqlite.py`, the item-id allocation (`next_item_id`, `:1842-1857`), the item insert and its ledger row run in ONE `BEGIN IMMEDIATE` transaction (the chunk-8 unit of work begins IMMEDIATE on these paths); the undo group id is read inside the write transaction (`SqliteGroupIdPort.next_group_id`, `:404-409`, called from inside it); the source-reuse decision runs inside the same transaction (`insert_source`, `:444-459`).

Proof it's real: read the group id outside the transaction again (one-line revert in `run_maintain.py`'s `_next_group_id` call ordering); the test fails again with merged groups. Undo.
Done when: the step-2 command prints "1 passed" over the full 100 rounds.
Commit message: B4-13: allocation, insert, ledger row and group id run inside one BEGIN IMMEDIATE transaction (D-03)

## Chunk 14 of 22: the id shown is the id saved; edits stop burning ids
Covers: stories 12 (retry half) and 33; findings 4.3 #20 (retry) and 4.5 #13.

1. Add two failing tests to `tests/test_batch4_writers.py` (tests NEW): `a_forced_id_conflict_retries_with_the_next_free_id` (plant a one-shot trigger that aborts the first insert of item id N, simulating another writer taking `MAX+1`; the write path retries inside the lock and saves the item as N+1; the id from the confirm block is re-read and reported) and `an_edit_never_takes_a_new_item_id` (run two `edit-item` writes; `SELECT MAX(id) FROM items` is unchanged — today every edit consumes a fresh id via the revalidation call, `ember/capture/confirm_write.py:119` + `ember/cli.py:383`).
2. Run `.venv/bin/pytest tests/test_batch4_writers.py -k "conflict or edit_never" -q`. Expect: 2 failed.
3. Implement: the retry loop on the unique-key conflict inside the `BEGIN IMMEDIATE` transaction (N10); in the capture confirm path stop asking the gatekeeper's `next_item_id` for edited drafts (the edit keeps the draft's id, per N10 "edits stop taking a new id"); the id printed before the write stays the id saved (the retry re-allocates only on a real conflict).

Proof it's real: remove the retry (raise the stored error instead); the conflict test fails with CAPTURE-013 again. Undo.
Done when: the step-2 command prints "2 passed"; the confirm-block id equals the stored id in the race test output.
Commit message: B4-14: id-conflict retry inside the lock; edits stop burning item ids

## Chunk 15 of 22: db-check checks rules, not just names
Covers: stories 17, 18, 19, 41; findings 4.3 #7, 4.3 #8, 4.3 #12, 4.3 #21.

1. Add three failing tests to `tests/test_db_check.py` (file exists; tests NEW): `db_check_flags_a_missing_table` (DROP the `sources` table from a healthy copy -> `result: DRIFT`), `db_check_flags_a_no_op_trigger_with_the_right_name` (recreate one expected trigger as `BEGIN SELECT 1; END` -> DRIFT; today the check at `ember/adapters/db_check.py:121-129` compares names only), `db_check_flags_version_99` (stamp version 99 -> DRIFT; today only lower bounds exist).
2. Run `.venv/bin/pytest tests/test_db_check.py -k "missing_table or no_op_trigger or version_99" -q`. Expect: 3 failed (each reports OK today).
3. Implement in `ember/adapters/db_check.py`: check the full expected table list, each trigger's SQL against the expected definition, and that the version is between 1 and the pinned 13; every mismatch is ONE `result: DRIFT` line, exit 1, never a crash and never a new error code (the contract at `db_check.py:5-7`). In `ember/adapters/sqlite.py`, `column_exists` (`:1027-1037`) validates its table name against a fixed list and refuses anything else (finding 4.3 #21).

Proof it's real: temporarily let the trigger check accept any SQL body again; `db_check_flags_a_no_op_trigger_with_the_right_name` goes red (OK reported). Undo.
Done when: the step-2 command prints "3 passed"; the existing `tests/test_db_check.py` tests all still pass.
Commit message: B4-15: db-check checks tables, trigger SQL and the version range (4.3 #7, #8, #12, #21)

## Chunk 16 of 22: backups are proven before the old one moves
Covers: stories 20, 21, 22, 23; findings 4.3 #10, 4.3 #13, 4.3 #14, 4.3 #29.

1. Add three failing tests to `tests/test_backup.py` (file exists; tests NEW): `rotation_happens_only_after_the_new_snapshot_is_proven` (existing good target + a source that fails at open; assert the old backup still sits at the original target path — today `_precheck_and_rotate` at `ember/adapters/backup.py:57` runs first, so the old file has been moved aside), `the_migration_pre_backup_is_an_online_snapshot_with_a_timestamp_name` (seed a v10 file, open it so the pre-backup runs; assert the copy passes `PRAGMA integrity_check` and its name is NOT reusable, i.e. no `.bak-v<version>` collision — today `shutil.copy2` to `.bak-v<version>` at `ember/adapters/sqlite.py:301-312` overwrites the same name), `three_timestamped_migration_backups_are_kept` (two pre-backup runs leave two distinct names; the retention keeps at most 3).
2. Run `.venv/bin/pytest tests/test_backup.py -k "proven or online_snapshot or timestamped" -q`. Expect: 3 failed.
3. Implement: in `ember/adapters/backup.py` open and snapshot the source first and rename the old target only after the new copy passes `PRAGMA integrity_check`, with the file synced to disk (fsync); in `ember/adapters/sqlite.py` `_backup_database` uses `conn.backup` (SQLite's online backup function), names the copy `<db>.bak-<UTC timestamp>`, prunes to the newest 3, and syncs. `ember backup` already keeps its last three `.old-1..3` (story 23 is pinned by the existing retention test in `tests/test_backup.py`).

Done when (this step overwrites backup files — pytest temp only): the step-2 command prints "3 passed" and the existing `tests/test_backup.py` tests stay green.

Proof it's real: move `_precheck_and_rotate` back before `_open_source`; the rotation-order test fails again (old backup gone from its path). Undo.
Done when: the step-2 command prints "3 passed" and `.venv/bin/pytest tests/test_backup.py -q` is all green.
Commit message: B4-16: backups rotate only after proven; timestamped online migration snapshots (4.3 #10, #13, #14, #29)

## Chunk 17 of 22: export never lies and never destroys
Covers: stories 25, 26, 27, 28, 44; findings 4.3 #15, 4.3 #16, 4.3 #28, 4.3 #3, 4.7 #10.

1. Fix the v10 fixture first (it is the fixture the export tests below need): in `tests/query/fakes.py`, `make_v10` (`:152-154`) is rebuilt to run scripts 001-010 only, no migrations past 10 (today it calls `open_database` and lands at v13 — finding 4.7 #10, story 44).

Done when (test fixture build): `.venv/bin/pytest tests/query -q` — the tests using the fixture (`make_v10`, `make_v9`, e.g. `test_list_items_and_show_item_work_on_a_v10_file_never_migrating`) assert `version == 10` / `version == 9` as their names claim, and the whole `tests/query` suite stays green.
2. Add four failing tests to `tests/test_export.py` (file exists; tests NEW): `a_failed_export_leaves_the_previous_export_intact` (make the write fail after the old file exists — e.g. an unwritable sibling temp target; the old file's bytes are unchanged; today `write_export` overwrites in place with "w", `ember/adapters/export.py:241-244`), `a_value_containing_a_section_line_stays_delimited` (an item statement and a ledger value containing a forgeable line such as `== links (0) ==` render inside their field delimiter, never as a section — today only source text is delimited), `metadata_is_selected_only_when_the_version_has_it` (`--out` export of a real v10 file works; today `gather_export` selects `metadata` unconditionally at `:139` and the v10 file fails), `field_values_sit_at_the_documented_column_20` (assert the value column is 20 for a rendered field line; today the padding math lands at 22, `:374` with `_VALUE_COLUMN = 20`).
3. Run `.venv/bin/pytest tests/test_export.py -k "previous_export or section_line or metadata or column_20" -q`, expect 4 failed, then implement in `ember/adapters/export.py`: `write_export` writes to a temp file in the same folder, syncs, then renames over the target; all item/ledger values get the same delimiter treatment the source blocks use; `metadata` is selected only when `column_exists` says the v10+ column is there; the padding math lands the value at column 20.

Proof it's real: revert `write_export` to the truncate-in-place `"w"` open; the previous-export test fails again (old bytes destroyed). Undo.
Done when: the step-3 run prints "4 passed" and `tests/test_export.py tests/test_docs_in_sync.py -q` stay green.
Commit message: B4-17: export atomic write, delimited values, v10-compatible metadata read, column width (4.3 #3, #15, #16, #28)

## Chunk 18 of 22: query reads answer instead of crashing
Covers: stories 29, 38 (the `--since` half), 45; findings 4.7 #2, 4.7 #9, 4.7 #11.

1. Add three failing tests: `show_item_answers_with_a_house_code_when_a_links_other_end_is_gone` to `tests/query/test_list_show_cli.py`, `history_rows_carry_their_group_id` to `tests/query/test_history_integration.py` (run one real undo, call `SqliteQueryContext.list_change_log`, find the `undo_of` row, assert `group_id` is not None — today `list_change_log` at `ember/adapters/sqlite.py:1119-1146` never selects `group_id`), and `history_since_parses_timestamps_instead_of_comparing_text` to `tests/query/test_history_window_unit.py` (two rows whose TEXT order differs from their instant order, e.g. different UTC offsets; `--since` keeps the right rows — today `history.py:139` compares ISO strings). The show-item test seeds two items and a link, deletes the other item row directly (a dangling target), runs `ember show-item --item 1`, and asserts one house-code stderr line and exit 1, never a traceback (today `ember/query/show_item.py:37` raises raw `KeyError`).
2. Run `.venv/bin/pytest tests/query/test_list_show_cli.py tests/query/test_history_integration.py tests/query/test_history_window_unit.py -k "other_end or group_id or parses_timestamps" -q`. Expect: 3 failed.
3. Implement: `ember/query/show_item.py` returns a named error for a dangling other end (and the same guard covers `why`); `run_show_item` / `run_why` read items, links and source in one read transaction and map the dangling case to the house code; `ember/adapters/sqlite.py` `list_change_log` selects `group_id` (gated by `column_exists`, v12 files stay `None`) and `ember/adapters/db_check.py` `_ledger_rows` selects it too (the same 4.7 #11 spot it flagged at `db_check.py:221-237`); `ember/query/history.py` parses stored timestamps and compares instants for `--since`.

Proof it's real: revert the dangling-target guard to `by_id[other_id]`; the show-item test fails with a KeyError traceback again. Undo.
Done when: the step-2 command prints "3 passed" and the whole `tests/query` suite is green.
Commit message: B4-18: show/why survive a dangling link end, one read transaction; history parses since and carries group ids (4.7 #2, #9, #11)

## Chunk 19 of 22: the validated flag tells the truth; undo refuses wrong pointers loudly
Covers: stories 30, 36, 37, 40; findings 4.5 #18, 4.6 #5, 4.6 #6, 4.6 #11.

1. Add two failing tests: `set_validated_on_an_already_validated_item_writes_no_ledger_row` to `tests/test_cli_validated.py` (file exists; test NEW — run `set-validated` twice, assert exactly one `validated` ledger row; today a `true -> true` row is appended, `ember/adapters/sqlite.py:1919-1947`) and `undo_dry_run_on_a_v12_file_requires_version_13` to `tests/maintain/test_undo_cli.py` (file exists; test NEW — on a real v12 file, `ember undo --dry-run` raises the SchemaOutdated code with required 13; today `ember/cli.py:1010` passes 11, so the floor passes and the command answers MAINTAIN-023 instead).
2. Add two failing tests to `tests/maintain/test_undo_core_unit.py` (file exists; tests NEW): `undo_refuses_a_pointer_row_aimed_at_the_wrong_group_kind` (a crafted grouped ledger whose undo pointer names a group that is itself an undo — `derive_undo` refuses; today only ordering is checked, `ember/maintain/undo.py:109-149`) and `undo_fails_loudly_on_an_unknown_field` (a grouped row with a field the inversion does not know raises GroupRecordInvalid instead of silently comparing against `item.source` — today `_live_value` falls through at `ember/maintain/undo.py:286-313`).
3. Run `.venv/bin/pytest tests/test_cli_validated.py tests/maintain/test_undo_cli.py tests/maintain/test_undo_core_unit.py -k "already_validated or requires_version_13 or wrong_group_kind or unknown_field" -q`, expect 4 failed, then implement: the no-op check in the validated write path (`ember/capture/item_gatekeeper.py` `validate_set_validated` / `ember/cli.py` `_write_validated_flag`); `ember/cli.py` `_run_undo_or_redo` opens with `required_version=13`; `ember/maintain/undo.py` checks each pointer row's group kind and fails closed on unknown fields in `_live_value`.

Proof it's real: delete the kind check again; the wrong-pointer test goes red (the wrong group is re-applied). Undo.
Done when: the step-3 command prints "4 passed" and `tests/maintain/test_undo_core_unit.py tests/test_undo_e2e.py -q` stay green.
Commit message: B4-19: no fake validated history; undo checks group kind and fails loudly; undo dry-run needs 13 (4.5 #18, 4.6 #5, #6, #11)

## Chunk 20 of 22: capture honesty and the shield's clock
Covers: stories 31, 32, 34, 38 (the shield half), 39; findings 4.5 #7, 4.5 #12, 4.5 #14, 4.6 #7, 4.6 #8.

1. Add a failing test `two_identical_proposals_in_one_note_warn_on_the_second` to `tests/test_item_gatekeeper_unit.py` (file exists; test NEW — `validate_proposals` with two identical statements warns on the second; today the near-duplicate scan reads `existing` once before the loop, `ember/capture/item_gatekeeper.py:99-110`, so the second identical proposal is accepted silently).
2. Add three failing tests: `an_edit_counts_each_warning_once` to `tests/test_confirm_write_unit.py` (file exists; test NEW — edit an warned item; the warning is not counted twice; today `confirm_write.py:133-139` re-counts it after the edit); `the_shield_boundary_parses_timestamps` to `tests/maintain/test_derive_unit.py` (file exists; test NEW — a clear row and an evidence row whose TEXT sort order differs from their instant order compare correctly; today `derive.py:96-102` compares strings); `the_close_proposer_handles_a_missing_link_id_before_comparing` to `tests/maintain/test_close_proposer_unit.py` (file exists; test NEW — a Confirmed `answers` link with `id=None` is skipped, not a TypeError; today the comparison at `close_proposer.py:153` runs before the `:163` guard).
3. Run the four files with `-k "one_note or counts_each_warning or parses_timestamps or missing_link_id" -q`, expect 4 failed, then implement: the near-duplicate scan includes items accepted earlier in the same note (`item_gatekeeper.py`); the confirm loop counts each warning once (`confirm_write.py`); the shield sort key parses timestamps before comparing (`ember/maintain/derive.py`); `stale_close_candidates` guards `link.id` before the tuple comparison (`ember/maintain/close_proposer.py`); and remove the unreachable dropped-proposal branch in `confirm_write.py:194-197` (finding 4.5 #14, story 34) so every remaining branch is exercised by the existing confirm tests.

Done when (a code path is deleted — its own check): `.venv/bin/pytest tests/test_confirm_write_unit.py tests/bridge -q` is green with the branch gone, proving the tests that covered it never needed it (truly unreachable).

Proof it's real: reintroduce the read-once `existing` snapshot in the gatekeeper; the one-note test fails again ("accepted 2, warnings 0"). Undo.
Done when: the step-3 run prints "4 passed" and `tests/maintain tests/test_item_gatekeeper_unit.py -q` stay green.
Commit message: B4-20: same-note duplicates warn, warnings count once, shield parses time, close proposer guards link id, dead branch removed (4.5 #7, #12, #14; 4.6 #7, #8)

## Chunk 21 of 22: path identity follows the file system
Covers: story 42; finding 4.3 #30.

1. Add a failing test `same_path_treats_a_symlinked_spelling_as_one_file` to `tests/test_backup.py` (file exists; test NEW): create a real directory and a symlink to it, name one path through the symlink and the other through the real path, with the compared file NOT existing on either side; `ember/adapters/paths.py` `same_path` must return True. Today the fallback compares plain absolute strings (`paths.py:19`) and returns False.
2. Run `.venv/bin/pytest tests/test_backup.py -k symlinked_spelling -q`. Expect: 1 failed.
3. Implement in `ember/adapters/paths.py`: keep `os.path.samefile` when both paths exist (already true, `:14-16`); when one does not exist, compare symlink-resolved real paths (`os.path.realpath`) instead of plain `abspath`. Case sensitivity stays the file system's own (D-22, Linux only).

Proof it's real: revert the fallback to `abspath`; the test fails again with False. Undo.
Done when: the step-2 command prints "1 passed"; the backup and export self-guard tests (`tests/test_backup.py tests/test_export.py -q`) stay green.
Commit message: B4-21: same_path resolves symlinks in the missing-path fallback (4.3 #30)

## Chunk 22 of 22: the project map and the full suite
Covers: housekeeping for every NEW file this batch added (`tests/test_batch4_init.py`, `tests/test_batch4_transactions.py`, `tests/test_batch4_writers.py`, `tests/test_batch4_migrations.py`).

1. Add one PROJECT_MAP.md line per NEW file created in this batch (chunk 5, 8, 9, 13), under the Tests section, saying what each file is for. `tests/test_docs_in_sync.py` `test_every_tracked_file_has_a_project_map_line` fails until this is done.
2. Run `.venv/bin/pytest tests/test_docs_in_sync.py -q`. Expect: all pass.
3. Run the full suite: `.venv/bin/pytest -q`. Expect: 0 failed (write down the passed count). Then `npm test --prefix app`. Expect: 0 failed.

Proof it's real: temporarily remove one PROJECT_MAP line; `test_every_tracked_file_has_a_project_map_line` fails. Undo.
Done when: both full-suite commands finish with 0 failed.
Commit message: B4-22: project map covers the batch-4 test files; full suite green

## Final check
- Full suites, all green, run from the repo root:
  - `.venv/bin/pytest -q` — expect 0 failed (record the count).
  - `npm test --prefix app` — expect 0 failed.
  - `xvfb-run --auto-servernum npm run check:launch --prefix app` — expect: window started, `items: N` printed, exit 0 (this also proves the app's init+capture first-Add wiring, chunk 7). This command runs as typed: xvfb is installed locally (I2).
  - Decision I8 holds: `.venv/bin/pytest tests/test_batch4_migrations.py -k busy_timeout -q`, expect passed (`PRAGMA busy_timeout` reads 5000 on every opened connection).
- The batch's "Done when" from `archive/Plan.md` section 3 (Batch 4), each with the command that proves it:
  - "The report's own repros all fail safe" — covered chunk by chunk above; every repro test in `tests/test_batch4_*.py` drives the report's original trigger (planted triggers, dropped scripts, threads).
  - "Four and eight threads opening a new file all succeed, none crashes, version 13" — `.venv/bin/pytest tests/test_batch4_migrations.py -k parallel -q` (with the 8-thread variant from chunk 12's Proof), expect all passed.
  - "Four parallel capture runs on a fresh path also all succeed" — `.venv/bin/pytest tests/test_batch4_init.py -k parallel_capture -q`, expect passed.
  - "A dropped migration file makes db-check say not OK" — two commands: `.venv/bin/pytest tests/test_batch4_migrations.py -k dropped -q` (the pinned-set refusal on a fresh migrate) and `.venv/bin/pytest tests/test_db_check.py -k missing_table -q` (a file already migrated while the script was missing reads DRIFT). Both expect passed.
  - "A forced ledger failure leaves no item behind" — `.venv/bin/pytest tests/test_batch4_transactions.py -k forced_ledger -q`, expect passed. (Note: the test's `-k` name is the chunk-8 suite's `forced_ledger` selector; if the test landed under a different name, run the whole file.)
  - "Dry-run leaves the file hash unchanged" — `.venv/bin/pytest tests/maintain/test_maintain_commands_cli.py -k dry_run_leaves_an_older_file -q`, expect "3 passed".
  - "Two writers adding at once both succeed with different ids and separate undo groups" — `.venv/bin/pytest tests/test_batch4_writers.py -q`, expect all passed (100 rounds).
- Every user story 1-46 of `docs/Spec-Batch4.md` and every Batch-4 finding from `archive/Plan.md` section 3 (4.3 #1,2,3,5,7,8,9,10,12,13,14,15,16,18,19,20,21,22,28,29,30; 4.4 #4; 4.5 #2,7,11,12,13,14,17,18; 4.6 #1,2,3,4,5,6,7,8,11; 4.7 #1,2,8,9,10,11; 4.8 #12; 4.10 #1,5,8) appears in some chunk's Covers line above.

## Unknowns
- **House code numbers and names for the new refusals are not pinned.** The spec pins the cases (init refused, missing file, pre-version file, version-0 file, preview "needs update", dangling link target) but no code strings. The implementer picks the next free number in each family (I17: never reuse) and the Batch 6 sentence table gets them; nothing here invents wording.
- **Story 9's screen sentence "nothing was half-written"** (`app/main/add-session.js:125`, `app/renderer/screens/add.mjs:233`, `app/test/add-session.test.js:180`) is only made *true* by this batch (chunk 8); the pinned prose and its test are Batch 6's sentence table / Batch 3's add tests, not changed here (check report section 4).
- **`tests/test_ids_in_init.py` does not exist and should not be created** — if any earlier plan referenced "tests/test_measure_model_change.py", that file is Batch 0 scope, not Batch 4; nothing in this plan relies on it.

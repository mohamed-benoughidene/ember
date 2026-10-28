# L3 Hardening Step 1: Migration 011 Only (backup + guards + triggers + floors)

Implements L2 Hardening §5 (migration 011, pinned verbatim) + §5.0 (runner backup) + §8 (guards) + §11 (floors, churn points). This step ships the schema and nothing else — no reader, no replay, no db-check (steps 02–03).

## 0. Constitution rules this step enforces

- **D6** — one numbered migration, 011; the version bump is the runner's (L2 §5).
- **D5** — `ALTER TABLE links ADD COLUMN reversed_at TEXT`: new optional column, zero renames (L2 §4, §§Z D5).
- **D7** — the runner backs the DB up before the first above-version script; retention 3 (L2 §5.0).
- **L1 contract 1** — every pre-existing column keeps its exact type/CHECK/FK/UNIQUE/index; proven by diff tests, not by faith.
- **L1 contract 7** — no migration rewrites a `change_log` row; the backfill UPDATE touches only the new derived column (L2 §6).
- **I5 / I7** — the `_guard_011` CHECK kills the migration loudly at the DB; the runner's single transaction rolls it all back (L2 §8, §12).
- **I17 / I21** — zero new codes; existing codes re-raised at existing call sites (L2 §12).
- **B3** — enforcement lives in SQL triggers, the stable substrate; no engine core changes here (L2 §7).
- **T4** — acceptance on real temp DBs at observable boundaries (L2 §13).
- **P3** — this is Phase 1 of the L2 §3 pipeline only (boot: open → backup → apply 011 → floor check).

## 1. Job

Move the schema to version 11 and put the castle wall in: guards, the `reversed_at` column, backfill, `link_compat`, 4 triggers. After this step the DB rejects illegal pairs and reason-less closes by itself; readers still run as today.

## 2. Steps

1. **Backup step in `_apply_migrations`** (`ember/adapters/sqlite.py:227-241`, L2 §5.0): before the `number > current` loop, once per run, `shutil.copy2(db_path, f"{db_path}.bak-v{current}")`. Fresh install backs up once, not per script. Retention: keep the newest 3 `.bak-v*`, delete older. The copy call is wrapped so `OSError` re-raises as the caller's `DbMigrationFailed` (RELATE-013 via `open_relate_database`, MAINTAIN-008 via `open_maintain_database`; L2 §12).
2. **`ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql`** — paste the L2 §5 script **verbatim**. Plain SQL only: no `BEGIN`/`COMMIT`/`PRAGMA` — the runner owns them (`_apply_migration`, `sqlite.py:244-261`). Contents: the items `_guard_011` pre-assertion, `ADD COLUMN reversed_at`, the backfill UPDATE (§6 replay rule applied once), `link_compat` (16 rows), triggers `links_compat_insert`, `links_compat_update`, `items_closed_reason_insert`, `items_closed_reason_update`.
3. **Floor bumps** (L2 §11): `ensure_relate_schema` `required=9` → `11` (`sqlite.py:129`); `ensure_maintain_schema` `required=10` → `11` (`sqlite.py:176`). Query stays `required=10` (`sqlite.py:223`, never reads the column), capture stays none.
4. **6 declared version-pin test updates** (churn points, L2 §0 + §11): `tests/test_source_storage_integration.py:66`, `tests/test_relate_db_open.py:110`, `tests/maintain/test_maintain_boot.py:122`, `tests/test_migration_runner.py:83`, `tests/test_migrations.py:212` — `10` → `11`; plus `tests/test_migrations.py::test_links_table_has_expected_columns` (line 45) — column list gains `reversed_at`. Floor tests in `test_relate_db_open.py` and `tests/maintain/test_maintain_boot.py` assert `required == 11`.

## 3. Flag: L2 §8 links guard is declared but not in the §5 pinned script

L2 §8 declares a **symmetric pre-assertion for `links`** ("the same `_guard_011` technique … every existing links row satisfies TYPE_COMPAT (via the compat table) before the `links_compat_*` triggers land"), but the §5 script — marked "Pinned verbatim (L3 pastes it)" — contains only the items guard. Both readings are defensible; this plan does not invent. Decision needed (see §11).

## 4. Errors (codes only, per L2 §12)

- `RELATE-013` / `MAINTAIN-008` — migration or backup copy fails; re-raised by existing boot wrapping.
- `RELATE-012` / `MAINTAIN-007` — boot open/read failures (unchanged paths).
- `RELATE-014` / `MAINTAIN-009` — version below the new floor.
- `RELATE-029` / `MAINTAIN-011` — a legitimate port write hits a trigger abort; existing `sqlite3.Error` wrapping.

## 5. Test Targets (L2 §13 accept list; real temp DBs)

This step owns, in new `tests/test_migration_011.py`:
1. `test_migration_011_preserves_all_rows_and_values`
2. `test_migration_011_preserves_existing_schema`
3. `test_migration_011_foreign_key_check_empty`
4. `test_migration_011_preserves_sqlite_sequence`
5. `test_migration_011_backfills_reversed_at_from_ledger`
6. `test_migration_011_guard_rejects_closed_row_without_close_reason`
7. `test_fresh_install_applies_all_migrations_through_011`
8. `test_failed_migration_leaves_intact_prior_database`

This step owns, in new `tests/test_schema_enforcement.py` (#17/#23):
- `test_links_trigger_rejects_illegal_pair_insert`
- `test_links_compat_matches_compat_table`
- `test_links_trigger_allows_existing_writers`
- `test_items_trigger_rejects_closed_without_reason`
- `test_v10_rows_satisfy_closed_rule`

Churn edits (not new tests): the 6 sites in §2.4 plus the two floor-test extensions. Steps 02–03 own the replay/db-check and reader tests (L2 §13).

## 6. CLI check (Rule S1)

`ember db-check` does not exist yet (step 02). Interim inspectable check on a migrated temp DB:

```
python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); v=c.execute('SELECT version FROM schema_version').fetchone()[0]; t=c.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=''trigger'' AND name LIKE ''%011%'' OR name IN (''links_compat_insert'',''links_compat_update'',''items_closed_reason_insert'',''items_closed_reason_update'')').fetchone()[0]; n=c.execute('SELECT COUNT(*) FROM link_compat').fetchone()[0]; print(v, t, n)" <db>
```

Expected on a fresh install AND on a migrated v10 copy: `11 4 16` (version 11, 4 triggers, 16 compat rows). After step 02 lands, the standing check is `ember db-check --db <fixture>` → `result: OK`, exit 0 (L2 §2).

## 7. Pytest

```
python -m pytest tests/test_migration_011.py tests/test_schema_enforcement.py -q
python -m pytest -q            # full suite, must be green
```

## 8. Out of Scope

- **#15 / rule-9 relax stays OUT** — no rebuild, no migration 012 drafted; gated on the recorded ruling (L2 §10, L1 §2 Cluster 1).
- Reader deltas, replay, pairing, db-check (steps 02–03).

## 9. Rollback

In-DB rollback is **automatic**: the runner wraps each script in one transaction and rolls back on any failure, leaving the DB intact at v10 (`sqlite.py:251-261`; L2 §8, §12). File rollback: the runner's pre-migration backup — restore `<db>.bak-v10` (the file copied per L2 §5.0 before the first above-current script) after aborting with no script applied. No down-migration exists; the schema change is forward-only.

## 10. Step invariant

After this step: the module runs, `open_relate_database`/`open_maintain_database` boot at floor 11, and the full suite passes; migration 011 is applied on a fresh DB and on a migrated v10 DB.

## 11. Decision needed

Paste §5 verbatim (items guard only) or add the §8-declared links guard between the `link_compat` INSERT and the two `links_compat_*` triggers? Option A (verbatim) skips the pre-assertion §8 promises; option B inserts one extra guard table before the triggers live. Count either way: guarded rows touched = 0 (CHECK-only read, no row changes); undo = the runner's own rollback + the `.bak-v10` file.

## 12. Build Notes

(to be filled after implementation)

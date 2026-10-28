# L3 Hardening Step 1: Migration 011 Only (backup + guards + triggers + floors)

Implements L2 Hardening §5 (migration 011, as amended by this step's §11 decision) + §5.0 (runner backup) + §8 (guards) + §11 (floors, churn points). This step ships the schema and nothing else — no reader, no replay, no db-check (steps 02–03).

## 0. Constitution rules this step enforces

- **D6** — one numbered migration, 011; the version bump is the runner's (L2 §5).
- **D5** — `ALTER TABLE links ADD COLUMN reversed_at TEXT`: new optional column, zero renames (L2 §4, §§Z D5).
- **D7** — the runner backs the DB up before the first above-version script; retention 3 (L2 §5.0).
- **D2 / D3** — `links.reversed_at` is a derived copy: the 011 backfill UPDATE applies the replay rule (L2 §6) exactly once, writes only the new column, and `change_log` stays the single source (L2 §6, master plan rule 7).
- **L1 contract 1** — every pre-existing column keeps its exact type/CHECK/FK/UNIQUE/index; proven by diff tests, not by faith.
- **L1 contract 7** — no migration rewrites a `change_log` row; the backfill UPDATE touches only the new derived column (L2 §6).
- **I5 / I7** — the `_guard_011` CHECK kills the migration loudly at the DB; the runner's single transaction rolls it all back (L2 §8, §12).
- **I17 / I21** — zero new codes; existing codes re-raised at existing call sites (L2 §12).
- **B3** — enforcement lives in SQL triggers, the stable substrate; no engine core changes here (L2 §7).
- **T4** — acceptance on real temp DBs at observable boundaries (L2 §13).
- **S1** — the step is inspectable: the interim check in §6 runs standalone with printed output, until step 02's `ember db-check` becomes the standing check (L2 §2).
- **P3** — this is Phase 1 of the L2 §3 pipeline only (boot: open → backup → apply 011 → floor check).

## 1. Job

Move the schema to version 11 and put the castle wall in: guards, the `reversed_at` column, backfill, `link_compat`, 4 triggers. After this step the DB rejects illegal pairs and reason-less closes by itself; readers still run as today.

## 2. Steps

1. **Backup step in `_apply_migrations`** (`ember/adapters/sqlite.py:227-241`, L2 §5.0): compute the pending scripts first; **the backup runs only when the pending list is non-empty** — a no-op open on every command must not churn the 3-slot retention. Before the `number > current` loop, once per run, `shutil.copy2(db_path, f"{db_path}.bak-v{current}")`. Fresh install backs up once, not per script. Retention: keep the newest 3 `.bak-v*`, delete older. `_apply_migrations` is caller-agnostic — it knows no codes — so the `OSError` catch is added **at each per-engine boot call site**: `open_relate_database` → RELATE-013, `open_maintain_database` → MAINTAIN-008, `open_database` (capture) → **no code, the raw error propagates** (L2 §12).
2. **`ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql`** — paste the L2 §5 script **as amended by the §11 decision (option B)**. Plain SQL only: no `BEGIN`/`COMMIT`/`PRAGMA` — the runner owns them (`_apply_migration`, `sqlite.py:244-261`). Contents — option B, the §5 script as amended: the items `_guard_011` pre-assertion, the `_guard_011_links` pre-assertion (links/TYPE_COMPAT, added after the `link_compat` INSERT, before trigger creation), `ADD COLUMN reversed_at`, the backfill UPDATE (§6 replay rule applied once), `link_compat` (16 rows), triggers `links_compat_insert`, `links_compat_update`, `items_closed_reason_insert`, `items_closed_reason_update`.
3. **Floor bumps** (L2 §11): `ensure_relate_schema` `required=9` → `11` (`sqlite.py:129`); `ensure_maintain_schema` `required=10` → `11` (`sqlite.py:176`). Query stays `required=10` (`sqlite.py:223`, never reads the column), capture stays none.
4. **Version-pin + floor churn** (L2 §0 + §11). Recount by grepping `== 10` under `tests/` (done at review): **eight sites — seven `== 10` pins plus the column-list test.** The query floor stays 10, so `tests/query/test_query_db_open.py:87` (`required == 10`) is **not** touched.
   - Seven pins `10` → `11`: `tests/test_source_storage_integration.py:66`, `tests/test_relate_db_open.py:110`, `tests/maintain/test_maintain_boot.py:105` (`context["required"]`) and `tests/maintain/test_maintain_boot.py:122`, `tests/maintain/test_migration_010.py:43` (was missing from earlier lists — added), `tests/test_migration_runner.py:83`, `tests/test_migrations.py:212`.
   - `tests/test_migrations.py::test_links_table_has_expected_columns` (line 45) — column list gains `reversed_at`.
   - Floor tests (named sites): `tests/test_relate_db_open.py::test_ensure_relate_schema_accepts_version_9` — re-seed 9 → 11 and rename to `test_ensure_relate_schema_accepts_version_11`; `tests/test_relate_db_open.py::test_ensure_relate_schema_rejects_version_8` — its `context["required"]` assertion becomes `11` (name unchanged); `tests/maintain/test_maintain_boot.py::test_ensure_maintain_schema_accepts_version_10` — re-seed 10 → 11 and rename to `test_ensure_maintain_schema_accepts_version_11`.

   **Fixture churn (declared)** — the existing seeds violate the new triggers, so the full suite cannot pass without these diffs; the files are named here and are part of this step's diff:
   - `tests/relate/test_neighbors_integration.py` — the seeds contain Decision–`supports` and `answers`–Decision pairs, both absent from TYPE_COMPAT; convert the seeds to legal pairs.
   - `tests/relate/test_load_filter_integration.py` — the `supports` seeds between Questions and Decision→Question are not in TYPE_COMPAT (the `answers` Decision→Question seeds are legal); convert the illegal ones.
   - `tests/relate/test_relate_cli.py` — `_seed_item` with `status="Closed"` updates `status` only and leaves `close_reason` NULL; seeds must set `close_reason`; plus the seeded `supports` pairs whose types are not in TYPE_COMPAT.

## 3. Flag resolved: the links guard (option B) is now in the pinned script

L2 §8 declares a **symmetric pre-assertion for `links`**, and the §5 script originally contained only the items guard. The §11 decision closed as **option B**: the `_guard_011_links` pre-assertion is added to the pinned SQL (master plan §5) between the `link_compat` INSERT and the trigger creation. The flag is resolved — §2.2 pastes the amended script.

## 4. Errors (codes only, per L2 §12)

- `RELATE-013` / `MAINTAIN-008` — migration fails, or the backup copy's `OSError` — caught at each per-engine boot call site (`open_relate_database` / `open_maintain_database`) and re-raised as the caller's `DbMigrationFailed`.
- `open_database` (capture) — a backup copy failure surfaces as the **raw `OSError` / `sqlite3` error, no code** — capture has no migration codes; do not invent a code for this row (L2 §12).
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

Churn edits (not new tests): the §2.4 site list — seven `10`→`11` pins, the `reversed_at` column-list test, the three named floor-test updates, and the declared fixture churn. Steps 02–03 own the replay/db-check and reader tests (L2 §13).

## 6. CLI check (Rule S1)

`ember db-check` does not exist yet (step 02). Interim inspectable check on a migrated temp DB:

```
python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); v=c.execute('SELECT version FROM schema_version').fetchone()[0]; t=c.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=''trigger'' AND name IN (''links_compat_insert'',''links_compat_update'',''items_closed_reason_insert'',''items_closed_reason_update'')').fetchone()[0]; n=c.execute('SELECT COUNT(*) FROM link_compat').fetchone()[0]; print(v, t, n)" <db>
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

After this step: the module runs, `open_relate_database`/`open_maintain_database` boot at floor 11, migration 011 is applied on a fresh DB and on a migrated v10 DB, and **the full suite passes AFTER the fixture churn in §2.4 is applied; the churn files are named there and are part of this step's diff.**

## 11. Decision — CLOSED (option B chosen, recorded at review)

Option B is chosen: the links guard is in. The pinned §5 script is amended with a `_guard_011_links` pre-assertion between the `link_compat` INSERT and the trigger creation — same pattern as `_guard_011`: a throwaway `CREATE TABLE _guard_011_links (bad INTEGER NOT NULL CHECK (bad = 0))` whose INSERT counts `links` rows violating TYPE_COMPAT (via `link_compat`) and the CHECK kills the migration unless that count is 0. **Rationale:** under option A a pre-existing illegal pair migrates silently and nothing else detects it; L1's job is that the DATABASE guarantees what the gatekeepers enforce; cost is one read-only count and the same failure path (CHECK → IntegrityError → runner rollback). Either way: guarded rows touched = 0 (CHECK-only read, no row changes); undo = the runner's own rollback + the `.bak-v10` file.

## 12. Build Notes

(to be filled after implementation)

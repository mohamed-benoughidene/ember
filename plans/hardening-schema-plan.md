# L2 Hardening — Schema Enforcement Plan (Cluster 1)

Terse caveman style. Source: L1 `plans/hardening-plan.md` §2 Cluster 1 + master plan + Constitution. Issues #17, #15, #20, #21, #23. Name deviates from `engine-<name>` on purpose — cross-engine storage work, deviation recorded at L1 §7. No invention; every symbol below was read in the repo on 2026-10-28.

## 0. Status + Verified Inputs

- 4 engines shipped. Migrations 001..010 exist in `ember/adapters/migrations/`. Highest = 010 (`close_reason` + `status_origin`). Next = **011**.
- Runner: `_apply_migrations` + `_apply_migration` in `ember/adapters/sqlite.py` — one transaction per script, version bump inside it, plain SQL only (runner owns `BEGIN`/`COMMIT` + FK pragma). No backup step today — added here (§5.0).
- Boot floors today (verified `sqlite.py:117-224`): relate ≥ 9 (`ensure_relate_schema`), maintain ≥ 10, query ≥ 10 (read-only, never migrates), capture none (plain `open_database`).
- Tests pinning `version == 10` (churn points, verified): `tests/test_source_storage_integration.py:66`, `tests/test_relate_db_open.py:110`, `tests/maintain/test_maintain_boot.py:122`, `tests/test_migration_runner.py:83`. Also `tests/test_migrations.py:212`.
- Reversal today: `SqliteMaintainStore.apply_reversal` (`sqlite.py:842-908`) writes items restore + `status` row + `link_reversed` marker in one transaction. `links` row untouched. Sweep reads markers via `list_reversed_link_ids` (`maintain_lookup.py`, `sqlite.py:624-636`).
- Pairing precedent: `SqliteMaintainStore.apply_status_origin` (`sqlite.py:805-840`) — column UPDATE + ledger row, one commit, either failure rolls back.
- Gatekeeper: `validate_add_link` in `ember/relate/link_gatekeeper.py` — 9 pure rules, `RejectedLink(code)`. Query raises no `link_reversed` special cases; history renders it (`ember/query/history.py:29`).
- Compat: `ember/relate/compat.py` `TYPE_COMPAT` — 11 entries, **16 (source, target, type) pairs**. Single source.
- Error codes: highest used per family — RELATE-037, MAINTAIN-012, QUERY-005, CAPTURE-016. Removed RELATE 002-004, 015, 020, 034 stay removed. This plan introduces **zero new codes**.

## 1. Job (one job)

Make the DB guarantee what the gatekeepers already enforce: illegal link pairs rejected by the database, `Closed` implies `close_reason`, reversal state lives on the `links` row and is rebuildable from the ledger. No table rebuild by default; no writer bypasses a gatekeeper.

## 2. CLI (Rule S1) — `ember db-check`

This cluster ships storage, not an engine. Its inspectable artifact is one read-only command. It opens the DB `mode=ro`, never migrates, never writes.

This is the phase's S1 artifact — a storage cluster with no user-facing mutation still needs one runnable, inspectable command (S1), and db-check is where the D2 replay check lives.

```
$ ember db-check --db ember.db
version: 11
floors: relate 11 ok, maintain 11 ok, query 10 ok, capture none
triggers: links_compat_insert, links_compat_update, items_closed_reason_insert, items_closed_reason_update — present
link_compat: 16 rows, matches TYPE_COMPAT
foreign_key_check: 0 violations
reversal replay: 3 reversed links, column == ledger
result: OK
```
Exit 0.

```
$ ember db-check --db stale.db
version: 10
floors: unmet — relate needs 11, maintain needs 11
result: DRIFT
```
Exit 1. Missing file / unreadable DB: `result: UNREADABLE`, exit 1 (reported, no error code — a check reports, I12).

## 3. Internal Pipeline (5 phases, P3)

```
Phase 1 boot    : open DB → backup → apply 011 → floor check
   ↓
Phase 2 enforce : triggers own illegal writes (gatekeepers keep running first)
   ↓
Phase 3 pair    : reversal write path — column + marker in ONE transaction
   ↓
Phase 4 read    : relate rules 8/9 consult the column; RELATE-028/009 gain detail
   ↓
Phase 5 check   : ember db-check proves version, triggers, drift, replay
```

## 4. Data Shapes at Phase Boundaries

- After Phase 1: `schema_version = 11`; `links` columns = the 6 old + `reversed_at TEXT` (NULL default); `link_compat` = 16 rows; 4 triggers in `sqlite_master`; every pre-011 `link_reversed` marker backfilled into `reversed_at`. No existing column, CHECK, FK, UNIQUE, index changed.
- Phase 2 shape: an illegal INSERT/UPDATE raises `sqlite3.IntegrityError` before Pydantic or Python code sees the row.
- Phase 3 shape: after a reversal, `(links.reversed_at == newest marker timestamp)` and marker row exists — both or nothing (one transaction).
- Phase 4 shape: `Link` Pydantic model gains `reversed_at: str | None = None` (I10-safe optional field); rule 8's ancestor SQL filters `reversed_at IS NULL`; rule 9's report carries the duplicate's reversal state.
- Phase 5 shape: the db-check report above; `replay_reversals(ledger_rows) -> dict[int, str | None]` (pure mapping, §6).

## 5. Migration 011 — `ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql`

Plain SQL only. No `BEGIN`/`COMMIT`/`PRAGMA` in the script — the runner owns them. Pinned verbatim as amended (option B — includes the `_guard_011_links` links guard; L3 pastes it):

```sql
-- Guard (#23 pre-assertion): migration dies if any v10 row breaks the new rule.
CREATE TABLE _guard_011 (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _guard_011 (bad)
    SELECT COUNT(*) FROM items WHERE status = 'Closed' AND close_reason IS NULL;
DROP TABLE _guard_011;

-- #20: reversal state on the row. NULL = live. Derived data (D3), source stays
-- change_log (master plan rule 7). D5: new optional field, no rename.
ALTER TABLE links ADD COLUMN reversed_at TEXT;

-- Backfill = the replay rule (§6) applied once at migration time.
UPDATE links SET reversed_at = (
    SELECT cl.timestamp FROM change_log AS cl
    WHERE cl.link_id = links.id AND cl.field_changed = 'link_reversed'
    ORDER BY cl.id DESC LIMIT 1
) WHERE EXISTS (
    SELECT 1 FROM change_log AS cl
    WHERE cl.link_id = links.id AND cl.field_changed = 'link_reversed'
);

-- #17: pair table, 16 rows generated from compat.py TYPE_COMPAT (drift test §7).
CREATE TABLE link_compat (
    source_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    UNIQUE (source_type, target_type, link_type)
);
INSERT INTO link_compat (source_type, target_type, link_type) VALUES
    ('Decision', 'Assumption', 'depends_on'),
    ('Decision', 'Finding', 'depends_on'),
    ('Decision', 'Decision', 'depends_on'),
    ('Decision', 'Decision', 'supersedes'),
    ('Decision', 'Question', 'answers'),
    ('Assumption', 'Finding', 'depends_on'),
    ('Assumption', 'Assumption', 'depends_on'),
    ('Assumption', 'Assumption', 'supersedes'),
    ('Finding', 'Assumption', 'supports'),
    ('Finding', 'Assumption', 'contradicts'),
    ('Finding', 'Decision', 'supports'),
    ('Finding', 'Decision', 'contradicts'),
    ('Finding', 'Finding', 'contradicts'),
    ('Finding', 'Finding', 'supersedes'),
    ('Finding', 'Question', 'answers'),
    ('Question', 'Question', 'supersedes');

-- §8 symmetric pre-assertion for links (decision closed as option B): migration
-- dies if any existing links row violates TYPE_COMPAT — a pre-existing illegal
-- pair must not migrate silently. Same throwaway-guard pattern as above.
CREATE TABLE _guard_011_links (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _guard_011_links (bad)
    SELECT COUNT(*) FROM links AS l
    WHERE NOT EXISTS (
        SELECT 1 FROM link_compat
        WHERE source_type = (SELECT type FROM items WHERE id = l.source_item_id)
          AND target_type = (SELECT type FROM items WHERE id = l.target_item_id)
          AND link_type = l.link_type
    );
DROP TABLE _guard_011_links;

-- #17: DB-level pair enforcement. INSERT plus the three mutation columns on UPDATE
-- (the #20/#21 writes touch only reversed_at, which never fires this trigger).
CREATE TRIGGER links_compat_insert BEFORE INSERT ON links
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM link_compat
    WHERE source_type = (SELECT type FROM items WHERE id = NEW.source_item_id)
      AND target_type = (SELECT type FROM items WHERE id = NEW.target_item_id)
      AND link_type = NEW.link_type
)
BEGIN
    SELECT RAISE(ABORT, 'links: pair not in link_compat');
END;

CREATE TRIGGER links_compat_update BEFORE UPDATE OF source_item_id, target_item_id, link_type ON links
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM link_compat
    WHERE source_type = (SELECT type FROM items WHERE id = NEW.source_item_id)
      AND target_type = (SELECT type FROM items WHERE id = NEW.target_item_id)
      AND link_type = NEW.link_type
)
BEGIN
    SELECT RAISE(ABORT, 'links: pair not in link_compat');
END;

-- #23: Closed implies close_reason. items is NOT rebuilt.
CREATE TRIGGER items_closed_reason_insert BEFORE INSERT ON items
FOR EACH ROW
WHEN NEW.status = 'Closed' AND NEW.close_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'items: Closed requires close_reason');
END;

CREATE TRIGGER items_closed_reason_update BEFORE UPDATE OF status, close_reason ON items
FOR EACH ROW
WHEN NEW.status = 'Closed' AND NEW.close_reason IS NULL
BEGIN
    SELECT RAISE(ABORT, 'items: Closed requires close_reason');
END;
```

### 5.0 Runner backup step (D7 + L1 contract 2)

The backup runs ONCE per `_apply_migrations` run, before the first above-current-version script (a fresh install backs up once, not per script): `shutil.copy2(db_path, db_path + ".bak-v" + str(current))`. Failure to copy aborts before any script runs and surfaces through the caller's existing wrapping (§12): the backup call is wrapped at L3 — `OSError` is caught and re-raised as the caller's `DbMigrationFailed` (RELATE-013 / MAINTAIN-008). **Retention: keep the newest 3** `<name>.bak-v*` files, delete older — decided here at L2 per L1 contract 2. Backup counts a rehearsal procedure: copy prod DB → migrate the copy → run the §13 diff tests against the copy.

## 6. D3 Replay Contract (the column is derived)

- **Source of truth:** `change_log` rows `field_changed='link_reversed'` (master plan rule 7 unchanged). `links.reversed_at` is a labelled, rebuildable copy (D3).
- **Replay rule (named, pure):** a link's `reversed_at` = the `timestamp` of the **highest-id** `change_log` row with `field_changed='link_reversed'`, `link_id = links.id` (append order breaks any clock tie); no such row → `NULL`. Deterministic, no clock, no I/O.
- **Pure step:** `replay_reversals(entries: list[ChangeRow]) -> dict[int, str | None]` in `ember/adapters/link_replay.py` (adapters — engine cores never import it, T9/B3; input rows are already-validated shapes). The Monday-morning case: column corrupted or drift suspected → rerun `replay_reversals` on the ledger, compare with live column (db-check Phase 5 does exactly this). The backfill UPDATE in migration 011 applies the same rule for pre-011 markers.
- **Pairing rule (apply_status_origin pattern, `sqlite.py:805-840`):** `SqliteMaintainStore.apply_reversal` gains one statement inside its existing transaction — `UPDATE links SET reversed_at = ? WHERE id = ?` — before the marker INSERT, single `commit()` at the end; either failure rolls back the whole write and raises `MAINTAIN-011` / `MAINTAIN-012` (existing codes). No second port method — two methods would mean two commits, the exact smell step-03 ruled out. `reversed_at` receives the SAME single clock value stamped into the marker row — one `self._clock()` read shared by both halves of the transaction; a second clock read makes `column == ledger` false by construction and breaks db-check. Cross-plan note for the coordinator: this widens maintain's store to touch one `links` column; the maintain-plan "Maintain never writes links" amendment belongs to Cluster 2's amendment and must mention this too.
- The pairing UPDATE widens "Maintain never writes links" by one column; this L2 records that widening now (also mirrored in the relate §11 amendment) — it is not deferred to the cluster-2 amendment.

## 7. #17 — Compat Drift Contract

`ember/relate/compat.py` `TYPE_COMPAT` stays the single source. The 16-row `link_compat` table is generated from it at migration-authoring time, and two tests tie them (§13): a drift test expands `TYPE_COMPAT` in Python and asserts set equality with `SELECT ... FROM link_compat`, and a direct-INSERT test proves the DB rejects what the table forbids. Gatekeeper rules 5/6 unchanged — the trigger is the castle wall behind them, not a replacement (AI never writes raw; rule 1/2 unchanged).

## 8. #23 — items Trigger

Rule: `status='Closed'` implies `close_reason NOT NULL` — enforced by the two `items` triggers above. Pre-assertion: the `_guard_011` CHECK kills migration 011 (IntegrityError → runner rollback → per-engine migration code, §12) if any existing row breaks the rule. `items` never rebuilds — a rebuild would manufacture the "another reason" #23 says to wait for (L1). Existing writers are clean today (`apply_status_changes` always writes `close_reason` with status), but the guard tests the data, not the writers. Symmetric pre-assertion for `links`: a guard count with the same `_guard_011` technique asserts every existing `links` row satisfies `TYPE_COMPAT` (via the compat table) before the `links_compat_*` triggers land — "test the data, not the writers" holds for both tables. **Applied in §5 as amended (option B, recorded at L3 step-01 §11): the `_guard_011_links` table sits in the pinned script after the `link_compat` INSERT, before trigger creation; the script is no longer pasted "verbatim" but "as amended by this decision".**

## 9. #20 + #21 — Readers See the Reversal (relate deltas only)

Schema half of #20 = migration 011 (§5). Reader half, kept to the minimum the column makes free (relate reads its own table — no `change_log` read, so the boundary-crossing fix stays out, per L1):

- `ember/relate/rows.py` `Link`: add `reversed_at: str | None = None` (I10: optional field, safe).
- `SqliteLinkContext.find_existing` and `supersedes_ancestors` select/filter `reversed_at`. **Rule 8:** `supersedes_ancestors` walks `status='Confirmed' AND reversed_at IS NULL` — after a reversal, the corrective inverse no longer false-fires RELATE-028. **Rule 9:** `find_existing` still returns the row (the UNIQUE triple still stands — #15 pending), and the RELATE-009 rejection carries the duplicate's reversal state in `detail`.
- New port method `LinkLookupPort.supersedes_blocking_link(source_id, target_id) -> Link | None` (`ember/relate/link_lookup.py` protocol + `SqliteLinkContext` adapter): BFS in id order through live Confirmed supersedes edges; returns the first link row that connects the two sides, or `None`. Used **only** for message text — the cycle decision stays `supersedes_ancestors` (T5: decision logic untouched).
- `RejectedLink(code, detail: str | None = None)` (optional field, I10). RELATE-028 detail names the blocking link: `"blocked by link {id} ({source} -> {target})"`. RELATE-009 detail names the duplicate: `"link {id} exists"`, plus `" (reversed)"` when applicable. CLI prints `code` then `detail` on the rejection line; tests assert codes, not prose (I21).
- Query unchanged in this plan: history already renders reversals from the ledger; `current_state`/`why`/`topic_search` need no column.

## 10. Decision Gate — #15 UNIQUE Triple (both outcomes, honestly)

**Gate, not default.** No rebuild test is written, no migration 012 is drafted, until the maintainer records the #15 ruling (issue update + one-line record; ruling lands before any build, L1 §6). Outcomes:

- **Keep the block** = V1 spec 3.3 compliant ("no duplicate links"). No schema work. Issue #15 closes with the recorded trigger (a real re-supersede workflow demand). Rules 8/9 as in §9 already stand.
- **Relax** = live rows only. Mechanism: drop the table-level `UNIQUE` (a `links` table **rebuild** — SQLite cannot alter a constraint) and add `CREATE UNIQUE INDEX links_unique_triple_live ON links (source_item_id, target_item_id, link_type) WHERE status = 'Confirmed' AND reversed_at IS NULL`. Candidate predicate pinned here; the exact "live" definition (does a `Rejected` row stay blocking?) **is part of the #15 ruling** — open question below. Relax is a recorded spec 3.3 deviation (engine-relate-plan amendment gains one line at decision time).

Rebuild mechanics (only in the relax branch — the exact L1 recipe, nothing softer):
- Order: create `links_new` (merged CREATE TABLE below, pinned verbatim) → `INSERT INTO links_new (id, ...) SELECT id, ...` with **explicit ids** for every column → `DROP TABLE links` → `ALTER TABLE links_new RENAME TO links`. **Rename-first is forbidden:** on SQLite ≥ 3.26 a rename rewrites child FKs to the dead name, and `change_log.link_id REFERENCES links(id)` (migration 008) would silently repoint.
- Merged CREATE TABLE pinned (column order pinned — existing 6 columns exactly as migration 006, then `reversed_at` last, matching the ADD COLUMN order):

```sql
CREATE TABLE links_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_item_id INTEGER NOT NULL REFERENCES items(id),
    target_item_id INTEGER NOT NULL REFERENCES items(id),
    link_type TEXT NOT NULL CHECK (link_type IN ('supports', 'contradicts', 'depends_on', 'supersedes', 'answers')),
    status TEXT NOT NULL CHECK (status IN ('Confirmed', 'Rejected')),
    created_at TEXT NOT NULL,
    reversed_at TEXT,
    UNIQUE (source_item_id, target_item_id, link_type),  -- relax branch: replaced by the partial index
    CHECK (source_item_id != target_item_id)
);
```
- `sqlite_sequence` restored to `MAX(id)` for links after copy. `link_compat` + the two `links_compat_*` triggers recreated against `links` after the copy. Scripts stay plain SQL — no `BEGIN`/`COMMIT`/`PRAGMA` (runner owns them; a script-internal PRAGMA is a silent no-op).
- Rebuild tests (L1 §5 accept list, §13): value-level row equality, `change_log` join intact, `PRAGMA foreign_key_check` empty, sequence preserved, failed-build-mid-copy leaves an intact prior database, fresh install applies the whole sequence.
- This branch lands as migration 012 + its own L3 step + a second engine-relate-plan line; this plan only pins the recipe.

## 11. Boot Floors + Churn Points

- New floors set by this plan: **relate ≥ 11** (port reads `reversed_at`), **maintain ≥ 11** (store writes it). Query stays **≥ 10** (never reads the column; read-only boots already refuse to migrate). Capture stays none.
- Floors move in `ensure_relate_schema` (`required=9` → `11`) and `ensure_maintain_schema` (`10` → `11`), same change as migration 011. Higher versions rejected by nothing (unchanged behavior).
- Declared churn points (tests pinning `version == 10`, verified locations in §0): `tests/test_relate_db_open.py`, `tests/maintain/test_maintain_boot.py`, `tests/test_migration_runner.py`, `tests/test_source_storage_integration.py`, `tests/test_migrations.py`. Also `tests/test_migrations.py::test_links_table_has_expected_columns` (column list gains `reversed_at`).

## 12. Errors (I17, I21)

No new family, no new code. Call-site mapping (existing codes re-raised at existing sites):

| Failure | Surface | Code |
| --- | --- | --- |
| Migration 011/012 script dies (guard CHECK, bad trigger, copy failure mid-build) | `open_relate_database` / `open_maintain_database` wrapping | `RELATE-013` / `MAINTAIN-008` |
| DB unopenable / version read fails | existing boot paths | `RELATE-012` / `MAINTAIN-007` / `QUERY-003` |
| Version below floor after floor bump | `ensure_*_schema` | `RELATE-014` / `MAINTAIN-009` / `QUERY-004` |
| `apply_reversal` column UPDATE fails | `SqliteMaintainStore` | `MAINTAIN-011`; marker fail → `MAINTAIN-012` |
| Backup copy fails before any script runs | same try as migrations (`OSError` wrapped at L3, §5.0) | `RELATE-013` / `MAINTAIN-008` (capture: raw `sqlite3` error — capture has no migration codes, unchanged). Reuse of RELATE-013 justified: migration-phase failure, keeps zero-new-codes; RELATE-038 stays free |
| `db-check` anything | report + exit 1, no code (I12) | — |
| Runtime trigger abort on a legitimate port write (gatekeeper-passing `insert_link_with_log` hitting the compat trigger) | existing `sqlite3.Error` wrapping | `RELATE-029` / `MAINTAIN-011` — and a direct INSERT bypass outside the ports reaches no Ember code at all (raw IntegrityError, no family) |

`RELATE-038` is the next free relate code but is **not** introduced here — nothing in this plan needs it.

## 13. Test Targets (fakes per T3; cores pure; real temp DBs for migrations)

New files `tests/test_migration_011.py`, `tests/test_schema_enforcement.py`, `tests/test_link_replay.py`; extensions marked (churn). The six rebuild test names live in §10 and activate only if the #15 ruling selects "relax"; until then only the trigger/column/guard tests apply.

**Migration accept list (L1 §5, real temp DBs):**
1. `test_migration_011_preserves_all_rows_and_values` — full-row before/after equality for `items`, `links`, `change_log` (values, not counts).
2. `test_migration_011_preserves_existing_schema` — `sqlite_master` + `PRAGMA table_info/index_list/foreign_key_list` diff for every pre-011 object.
3. `test_migration_011_foreign_key_check_empty`.
4. `test_migration_011_preserves_sqlite_sequence`.
5. `test_migration_011_backfills_reversed_at_from_ledger` — seed markers at v10, column matches the §6 replay rule.
6. `test_migration_011_guard_rejects_closed_row_without_close_reason` — seed a `Closed`/NULL row via direct SQL at v10, apply dies, DB left intact at 10.
7. `test_fresh_install_applies_all_migrations_through_011`.
8. `test_failed_migration_leaves_intact_prior_database` (runner-level fault injection).

**Enforcement (#17, #23):**
- `test_links_trigger_rejects_illegal_pair_insert` — direct SQL `INSERT` of e.g. `Question supports Question` raises `sqlite3.IntegrityError` (the #17 direct-INSERT test).
- `test_links_compat_matches_compat_table` — drift test: 16 rows == `TYPE_COMPAT` expansion; fails when either side changes.
- `test_links_trigger_allows_existing_writers` — a real `insert_link_with_log` happy path still commits.
- `test_items_trigger_rejects_closed_without_reason` — direct SQL UPDATE to `Closed`/NULL raises.
- `test_v10_rows_satisfy_closed_rule` — a DB seeded only through real writer paths passes the §5 guard count.

**Replay / D2:**
- `test_replay_reversals_matches_live_column` — build a real DB, drive reversals through `reverse-supersedes`, run `replay_reversals` over the ledger, assert dict == live column for every link.
- `test_replay_last_marker_wins_on_clock_tie`.

**Relate readers (§9) — unit on the pure gatekeeper with an existing fake `LinkLookupPort` + integration:**
- `test_reversed_supersedes_not_cycle` — after reversal, inverse `supersedes` passes rule 8 (no RELATE-028).
- `test_relate_028_names_blocking_link` — genuine cycle → code `RELATE-028`; the test asserts the detail carries the link id + both endpoints (data), not prose wording.
- `test_relate_009_duplicate_reports_reversed_state`.
- Floors: extend `tests/test_relate_db_open.py`, `tests/maintain/test_maintain_boot.py` for 11.

**CLI:**
- `ember db-check --db <fixture>` — exit 0 report above; stale DB → exit 1 `DRIFT`; missing file → exit 1 `UNREADABLE`; read-only proof: file hash identical before/after.
- `test_db_check_rejects_unknown_flag` — `ember db-check --nope` exits 2 (Click usage error, no code), per the L1 CLI contract.

## 14. Deferred to L3

- Exact wording of CLI `db-check` lines beyond the pinned key-value rows.
- `supersedes_blocking_link` BFS tie-break order detail beyond "first edge in id order" (check appears in `detail` text only).
- No reader other than relate's `find_existing` populates the field in this plan; anything wider is a new L2 amendment.
- Whether `db-check` ever gains a `--repair` mode (today: report only; repair = restore from `.bak-v*` or re-run the §6 replay rule by hand).
- In the #15 relax branch: migration 012's L3 step plan and the engine-relate-plan one-liner — both blocked on the ruling (§10).

## §Z Constitution Compliance

- **B1** — this plan is storage + enforcement only; no engine behavior added beyond the named reader deltas.
- **B2** — engines read the column through their existing port surfaces (`LinkLookupPort` method), never by reaching into another module's tables.
- **B3** — `link_replay.py` is pure logic in adapters; core logic never depends on the DB tool; trigger logic lives in SQL, the stable substrate.
- **B5** — one migration + one replay module + one check command; no tiny chained layers (embedded schema work is deep, not shallow).
- **B6** — no new utils file, no circular imports; `link_replay.py` is named for its job, not `utils`.
- **D2** — `reversed_at` is rebuildable: named pure step `replay_reversals` + `test_replay_reversals_matches_live_column`.
- **D3** — `change_log` stays the single source; column is a labelled derived copy; pairing rule keeps both halves atomic.
- **D5** — `ALTER TABLE links ADD COLUMN reversed_at`: a new optional field, zero renames.
- **D6** — numbered migration 011 (branch: 012), version bumped by the runner, floors recorded (§11).
- **D7** — runner-owned `<name>.bak-v<N>` backup before any above-version migration; retention 3; rehearsal procedure named (§5.0).
- **D8** — untouched (no AI calls).
- **P3** — the 5-phase pipeline in §3 is a fixed sequence, no shared hidden state.
- **P4** — writes keep flowing through existing ports (`SqliteMaintainStore`, `LinkLookupPort`); no new port family for one column.
- **I2/I3** — `db-check` has no mode flags; one command, one job.
- **I5/I7** — migration guard fails loudly at the DB (CHECK), never silently skipped; caller wraps once at the boot edge.
- **I10** — all model changes are optional fields (`Link.reversed_at`, `RejectedLink.detail`); no renames.
- **I12** — db-check: stdout data, exit 0/1, missing DB reported not raised; all other behavior via existing CLIs.
- **I17/I21** — zero new codes; existing codes re-raised at call sites (table in §12); tests assert codes, not prose.
- **T1/T3** — `replay_reversals` is pure (rows in, dict out); fake `LinkLookupPort` reused for gatekeeper units, no mocks.
- **T4/T5** — migration acceptance on real temp DBs at observable boundaries; no private-helper tests.
- **T9** — no engine core imports `ember.adapters.link_replay`; architecture tests already enforce, extension not needed (no new core module). The L1's recursive-glob instruction for `tests/test_architecture.py` is part of this phase's test work (this plan adds no subpackage, so no coverage gap here).
- **T10** — tests reuse `db_path` fixtures + `tests/fakes.py` seed helpers, no new harness.
- **S1/S2/S3/S4** — db-check runs the cluster alone with inspectable output; new test files run in isolation; data shapes are §4; transfer mechanism = the SQLite file via documented SQL.
- **Untouched:** B4 (nothing hidden), D1/D4 (raw input + validation untouched), I1/I6/I8/I9/I11/I13-I20 (no new functions outside named deltas — I11/I20 satisfied by existing port docstrings gaining the reversal column), P1/P2 (no new pattern), T2/T6/T7/T8 (no AI, no adapters touched beyond the named store methods). If L3 adds a core module, I11/I20 re-check at that step.

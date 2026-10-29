# L3 Hardening Step 06: Timestamp-scoped manual shield (ticket 12, #14 option c)

Implements L2 maintain §13 ("V1.x Amendment: timestamp-scoped manual shield"), which rewrites §2.1 Gap B4 and adds one §4.6 vocabulary row. One pure rule change at the one choke point, one additive Phase-1 read, one additive write branch. No migration. Closes #14 (#18 untouched — plain-text export keeps its separate plan).

## 0. Constitution rules this step enforces

- **B4** — the volatile decision ("which evidence does a clear silence") hides inside one rule in `merge_and_filter`, the single Phase-2 boundary every command passes through (L2 §13.4).
- **T1 / I9** — the comparison is pure: snapshot in, decisions out, no clock, no second DB read during the sweep (L2 §13.5).
- **D5 / I10** — additive only: one snapshot field with a default, one bool field with a default, one port method, no renames, no schema (L2 §13.4/13.5).
- **D3** — the ledger is both the evidence and the boundary; the rule reads `change_log` rows, never a second truth (L2 §13.2/13.3).
- **I7 / B3** — the re-arm rides the existing all-or-nothing `apply_status_changes` batch: one transaction, same rollback contract (L2 §13.4).
- **I17 / I21** — zero new error codes (§4); tests assert codes and data, never prose.
- **T4 / T5** — acceptance on real temp DBs at the Phase 1 read boundary and the Phase 3 write boundary.
- **I4 / I12 / S1** — CLI contracts unchanged; exit codes 0/1/2 unchanged; report format untouched (L2 §13.9).
- **P1** — only the ruled scope: the timestamp rule, its one read, its one write pattern. Nothing else.

## 1. Job

After this step a manual clear silences only the evidence that predates it. A `contradicts`/`depends_on` confirmed after the clear re-flags the card; a `supersedes`/`answers` confirmed after the clear closes it; either way the card's `status_origin` returns to `derived`, and the next clear re-arms the shield. Evidence that existed when the human cleared stays silent, whether the human saw it or overlooked it.

## 2. The pin (all of it per L2 §13; do not re-decide here)

- **Rule (§13.4), at `merge_and_filter`'s shield skip (`ember/maintain/derive.py:68`):** for a non-exempt candidate on a `status_origin='manual'` item, apply iff `(evidence.timestamp, evidence.change_log.id) > (clear.timestamp, clear.change_log.id)` — strictly newer wins; equal timestamps go to the higher `change_log.id`; a tie lost, or any fail-closed gap, skips exactly as today. Fail-closed gaps: no clear row for the item, or no `link_confirmed` row for the candidate's `link_id`.
- **Evidence timestamp (§13.2), one source for every cause family** (`contradicts_confirmed`, `dependency_closed`, `supersedes_confirmed`, `answers_confirmed`): the triggering link's `change_log` row with `field_changed='link_confirmed'`, `link_id` = that link. NOT `links.created_at` (value-equal by construction — one clock read at `link_gatekeeper.py:137-156`, pair-written at `sqlite.py:1401-1454` — but the ledger row carries the `id` the tie rule needs).
- **Clear timestamp (§13.3):** the latest `change_log` row for the item with `field_changed='status_origin'` AND `trigger_cause='user_set_status'` AND `new_value='manual'` (exact stored spellings verified at `sqlite.py:970-971`). Latest = max `(timestamp, change_log.id)`.
- **Re-arm (§13.4), on an applied change that passed the shield:**
  - `ember/maintain/rows.py`: `StatusChange.rearm: bool = False` (additive; `exempt` matching unaffected — never stamped on exempt changes); `MaintainSnapshot.shield_log: list[ChangeLogEntry] = []` (reuse `ember.relate.rows.ChangeLogEntry`; additive default keeps every constructor valid).
  - `merge_and_filter` stamps `rearm=True` (model copy) on the winning candidate of a shielded item whose evidence passed.
  - `SqliteMaintainStore.apply_status_changes` (`ember/adapters/sqlite.py`, branch in the existing loop): for a `rearm` change the same batch UPDATE also sets `status_origin='derived'`, and one extra ledger row is appended — `(item_id, link_id=<causing link id>, 'status_origin', 'manual', 'derived', <same ONE clock read>, 'sweep_rearm')` — inside the same transaction (MAINTAIN-011/012 rollback contract unchanged). Writing `'derived'` is legal: migration 010 CHECK is `('derived','manual')` (verified).
  - Rejected (L2 §13.4, do not "simplify" to it): `apply_status_origin(item_id, 'derived')` after the batch — that writer hardcodes `trigger_cause='user_set_status'`, which both mislabels a sweep write as a human act AND reads back as a clear under the boundary rule, poisoning it.
- **The Phase-1 read (§13.5):** new `MaintainLookupPort.list_shield_log() -> list[ChangeLogEntry]` (`ember/maintain/maintain_lookup.py` + `SqliteMaintainContext` next to `list_reversed_link_ids`, `sqlite.py:763`), failure raises `MAINTAIN-010`; `_load` (`ember/maintain/run_maintain.py:69`) folds it in as the fourth read. One query, pinned:

```sql
SELECT id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause
FROM change_log
WHERE (field_changed = 'status_origin' AND trigger_cause = 'user_set_status' AND new_value = 'manual')
   OR field_changed = 'link_confirmed'
ORDER BY id
```

- **History rendering:** `ember/query/history.py::_KIND_BY_PAIR` gains `("status_origin", "sweep_rearm") -> "status_origin_changed"` (one additive dict line).

## 3. Steps

1. `ember/maintain/rows.py`: the two additive fields (`StatusChange.rearm`, `MaintainSnapshot.shield_log`) with docstring sentences naming their job (I10/I11).
2. `ember/maintain/maintain_lookup.py` + `SqliteMaintainContext`: the new port method and its adapter (docstring names the read failure = `MAINTAIN-010`).
3. `ember/maintain/run_maintain.py`: `_load` passes `shield_log=ports.list_shield_log()`; docstring "three port reads" becomes four.
4. `ember/maintain/derive.py`: `_shield_passes` (pure helper: latest clear per §2, evidence by `link_id`, tuple compare, fail-closed) called from the shield skip in `merge_and_filter`; re-arm stamping on the winning candidate; docstrings updated (skip bullet + module header).
5. `ember/maintain/apply_status.py` port docstring: `apply_status_changes` documents the `rearm` branch. `ember/adapters/sqlite.py::SqliteMaintainStore.apply_status_changes`: the branch (UPDATE variant setting `status_origin='derived'`, extra ledger row, same clock read, same commit/rollback).
6. `ember/query/history.py`: the `_KIND_BY_PAIR` line.
7. `tests/maintain/fakes.py`: `FakeMaintainLookup.list_shield_log()` returns `[]` (the Protocol now names it). `tests/fakes.py`: new additive seeding helper `insert_link_with_confirmation(conn, source_item_id, target_item_id, link_type, created_at=FIXED_TIME) -> int` — inserts the `links` row AND the production-shaped `link_confirmed` ledger row (`item_id`=source, `link_id`=<new id>, `NULL`, `f"{link_type}:{target}"`, `created_at`, `'user_confirmed'`), mirroring `SqliteLinkStore.insert_link_with_log`. Existing callers untouched (`insert_link` stays as-is).

## 4. Errors (codes only, per L2 §6 / §13.7)

**Zero new codes.** `MAINTAIN-010 ItemsReadFailed` — the new Phase-1 read. `MAINTAIN-011` / `MAINTAIN-012` — the batch write, including the re-arm branch. Nothing else changes.

## 5. Test targets

Owned (names checked against `tests/` for collisions — none exist today):

- Pure, `tests/maintain/test_derive_unit.py` (drive the rule through `shield_log` rows with explicit `id`s; synthetic `ChangeLogEntry`s; timestamps `T1 < T2 < T3`, all UTC `+00:00`):
  - `test_newer_contradicts_passes_manual_shield`
  - `test_older_contradicts_stays_silent` (evidence predates the clear: the pre-clear link, seen or overlooked)
  - `test_newer_supersedes_closes_shielded_item` (full-scope close fires)
  - `test_newer_answers_closes_shielded_question`
  - `test_same_timestamp_tie_older_evidence_id_stays_silent`
  - `test_same_timestamp_tie_newer_evidence_id_passes`
  - `test_newest_clear_sets_the_boundary` (clear T1, evidence T2, clear T3 → silent; newest clear wins)
  - `test_newest_clear_wins_on_equal_timestamps` (two clears same timestamp → higher id is the boundary)
  - `test_rearm_is_stamped_on_passing_shield_changes` (winning change carries `rearm=True`; all other fields intact)
  - `test_exempt_change_does_not_rearm`
  - `test_links_created_at_is_not_the_evidence_clock` (flipping `links.created_at` does NOT flip the decision — pins §13.2's source)
- Store, `tests/maintain/test_maintain_store_integration.py` (real temp DB):
  - `test_apply_status_changes_rearm_writes_origin_and_log_row` (row contents per §2; `link_id` = causing link; same batch timestamp; `status_origin='derived'` after), all-or-nothing kept
  - `test_apply_status_changes_without_rearm_leaves_origin` (derived items untouched, one ledger row as today)
- Pipeline, `tests/maintain/test_maintain_commands_integration.py` (real temp DB, `run_sweep` end-to-end):
  - `test_sweep_reflags_shielded_item_on_newer_evidence` (clear at T2, newer `contradicts` + `link_confirmed` at T3 via the §3.7 helper → `applied == 1`, item `Challenged`, `status_origin='derived'`, both ledger rows present)
  - `test_sweep_stays_silent_on_preclear_evidence` (the ticket's pre-clear-link proof, WITH the ledgered pair — proves the timestamp compare, not fail-closed)
  - `test_sweep_tie_resolved_by_change_log_id` (same-timestamp evidence and clear, evidence row inserted first → lower id → silent)
  - `test_second_clear_silences_passed_evidence_again` (rule 6: re-flag, human clears at T4, sweep silent, origin `manual` again)
- CLI, `tests/maintain/test_maintain_commands_cli.py` (CliRunner on real temp DB, SQL-seeded):
  - `test_maintain_cli_reflags_shielded_item`
  - `test_maintain_cli_silent_on_preclear_evidence`

Declared churn (part of this step's diff; the tests that pin the OLD blanket-shield behavior, with their behavior under the new rule):

| Test | New expected behavior | Edit needed? |
|---|---|---|
| `tests/maintain/test_derive_unit.py::test_manual_shield_skips_derived_change` | Still passes byte-for-byte: its snapshot has no `shield_log` (default `[]`), so silence is now the fail-closed branch, not the blanket veto. One comment line added saying so. | No assertions change |
| `tests/maintain/test_derive_unit.py::test_exempt_change_bypasses_ladder_and_manual_shield` | Unchanged: exempt matching is value equality; rearm stamping never applies (§13.4) | No |
| `tests/maintain/test_maintain_commands_integration.py::test_set_status_active_clears_challenge_shields_and_blocks_resweep` | Still passes: its seed helper `insert_link` writes NO `link_confirmed` row, so evidence is fail-closed silent; even with the pair, evidence (inserted before the clear, same `FIXED_TIME`) loses the id tie. Meaning narrows from "blocks resweep forever" to "pre-clear evidence stays silent" | No assertions change |
| `tests/maintain/test_maintain_commands_integration.py::test_set_status_challenged_does_not_shield`, `test_set_status_noop_writes_nothing`, `tests/maintain/test_human_actions_unit.py::test_ladder_set_status_challenged_manual_shield_not_dropped`, `tests/maintain/test_maintain_store_integration.py::test_apply_status_origin_*` | Validator/store/human-path tests; the timestamp rule never reaches them | No |
| `tests/maintain/fakes.py::FakeMaintainLookup` | Gains `list_shield_log()` returning `[]` | Additive (owned, §3.7) |
| `tests/query/test_history_unit.py` pair-parametrize table (line ~22) | Gains `(("status_origin", "sweep_rearm"), "status_origin_changed")` | One row; grep for any `len(_KIND_BY_PAIR)`-style count pin before editing |
| Docstrings: `derive.py` (shield bullet, header), `apply_status.py`, `rows.py` (two new fields), `run_maintain._load` | Updated with the code | No test impact |

## 6. CLI check (Rule S1)

Real `.venv/bin/ember` commands on real temp DBs (migrations apply on open). Seed with the production-shaped pair (`links` row + `link_confirmed` ledger row, `SqliteLinkStore.insert_link_with_log`'s exact rows) because no CLI writes links outside the AI `relate` session. `T_OLD = 2026-01-01T00:00:00+00:00`, `T_NEW = 2031-01-01T00:00:00+00:00` — deterministic whether the check runs today or next year.

**Silent case.** Seed: source 1, item 1 `Finding` "Source", item 2 `Finding` "Contradicted" (`status='Challenged'`), link `contradicts` 1→2 at `T_OLD` + its `link_confirmed` row at `T_OLD` (the pair is REQUIRED — without the ledger row this case would pass fail-closed for the wrong reason).

```
$ ember set-status --item 2 --to Active --db /tmp/silent.db
item 2: Challenged -> Active
closed: 0, challenged: 0, reopened: 1, unchanged: 1
$ ember maintain --db /tmp/silent.db
closed: 0, challenged: 0, reopened: 0, unchanged: 2
```

Both exit 0. `SELECT status_origin FROM items WHERE id = 2` → `manual` (boundary held).

**Re-flag case (fresh DB).** Same seed, then:

```
$ ember set-status --item 2 --to Active --db /tmp/rearm.db          # clear at real now
item 2: Challenged -> Active
closed: 0, challenged: 0, reopened: 1, unchanged: 1
$ sqlite3 /tmp/rearm.db  # insert link id 2 contradicts 1->2 at T_NEW + its link_confirmed row at T_NEW
$ ember maintain --db /tmp/rearm.db
item 2: Active -> Challenged
closed: 0, challenged: 1, reopened: 0, unchanged: 1
```

Exit 0. After the run: `items` row 2 is `Challenged` with `status_origin='derived'`; `change_log` gained the `status` row (`link_id=2`, `contradicts_confirmed`) and the re-arm row (`status_origin`, `manual`→`derived`, `sweep_rearm`, `link_id=2`). `ember history --item 2 --db /tmp/rearm.db` renders both, the re-arm row as `status_origin_changed` (not `unknown`). `--dry-run` on the re-flag DB (item back to Active/manual in a copy) shows the same `item 2: Active -> Challenged` line and writes nothing.

## 7. Rollback

Code revert only — no schema, no down-migration, nothing to un-backfill (L2 §13.8). The rule only READS timestamps, and this is the migration-free semantics change stated honestly: every shield already on disk (each `items.status_origin='manual'` plus its ledger clear row) gains the new behavior automatically the moment the code runs, and loses it again on revert. Rows a re-arm wrote in between are clean state under BOTH builds: under the old binary the item is simply unshielded (`derived`) with an inert `unknown`-kind ledger row — the old rule checks only the column. Undo procedure: revert the commits; zero DB steps.

## 8. Step invariant

After this step: the module runs, the pure rule is total (never raises on empty/unknown-id snapshots), all four derived cause families share the one evidence source and the one rule, re-arm is one transaction inside the existing batch, every owned test passes, the declared churn is applied, the full suite is green with real numbers recorded in Build Notes. `ember db-check` still says `floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none` (L2 §13.6 — nobody bumps a floor for ticket 12).

## 9. Out of scope

No blanket veto command, no per-cause acknowledgment state, no new column, no UI, no report-format change, no touching of `run_set_status` / `validate_set_status` / `apply_status_origin` (the human clear path keeps its `user_set_status` row and second-transaction shape), no `history` command change beyond the one dict line.

## 10. Build Notes

Landed § by §: rows.py (`StatusChange.rearm: bool = False`, `MaintainSnapshot.shield_log: list[ChangeLogEntry] = []`) / maintain_lookup.py + `SqliteMaintainContext.list_shield_log` (the pinned SELECT, `MAINTAIN-010` on failure) / `run_maintain._load` (four port reads) / derive.py (`_shield_passes` + `_latest_clear` + `_evidence_row` + `_maybe_rearm`, the shield skip made per-candidate and timestamped at the one choke point) / apply_status.py port docstring + `SqliteMaintainStore.apply_status_changes` re-arm branch (observed `old_value` read before the batch UPDATE sets `status_origin='derived'`, one extra ledger row from the same ONE clock read, same transaction and MAINTAIN-011/012 rollback) / history.py `_KIND_BY_PAIR` line / tests/maintain/fakes.py (`shield_log` param + `list_shield_log()`) and tests/fakes.py (`insert_link_with_confirmation`).

TDD: red first on all 21 owned test items, then green.

- Before: **772 passed, 4 deselected** in 3.75s (baseline re-run, real numbers).
- After: **793 passed, 4 deselected** in 3.83s. The +21 = 11 pure + 2 store + 4 pipeline + 2 CLI + 1 history param row + 1 read-failure param row.
- No existing test needed an assertion edit. Declared churn applied exactly as the plan predicted: one comment line on `test_manual_shield_skips_derived_change`, one additive param row in `tests/query/test_history_unit.py`, additive fake updates. Grep found no `len(_KIND_BY_PAIR)`-style count pins.

§6 CLI checks, run for real with `.venv/bin/ember` on `/tmp` DBs (`T_OLD = 2026-01-01`, `T_NEW = 2031-01-01`, clear at the real clock 2026-10-29):

- Silent case: `set-status` → `item 2: Challenged -> Active` / `closed: 0, challenged: 0, reopened: 1, unchanged: 1`, exit 0. `maintain` → `closed: 0, challenged: 0, reopened: 0, unchanged: 2`, exit 0. `items.status_origin` for item 2 = `manual` (boundary held).
- Re-flag case: `set-status` exit 0, then a newer `contradicts` pair at `T_NEW`, `--dry-run` → `item 2: Active -> Challenged` / `closed: 0, challenged: 1, reopened: 0, unchanged: 2`, exit 0, and the row count is unchanged (4 rows before, 4 after). `maintain` → `item 2: Active -> Challenged` / `closed: 0, challenged: 1, reopened: 0, unchanged: 2`, exit 0. After: item 2 `Challenged`, `status_origin='derived'`; ledger rows 5 and 6 = the `status` / `contradicts_confirmed` row (`link_id=2`) and the re-arm row (`status_origin`, `manual` -> `derived`, `sweep_rearm`, `link_id=2`), both stamped from the same clock read (`12:21:05.255623+00:00`).
- `db-check` on the temp DB: `floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none`, `result: OK` (no floor moved, §13.6).
- `ember history --item 2` renders the re-arm row as `kind: "status_origin_changed"`, `cause: "sweep_rearm"` (not `unknown`).

Deviations from the pin (none touches the rule, the read, or the write pattern):

1. §6's re-flag seed says "insert link id 2 contradicts 1→2 at T_NEW". That is impossible: migration 006 has `UNIQUE (source_item_id, target_item_id, link_type)`, so a second `contradicts` link between the same pair can never exist (I hit the real `IntegrityError` doing it). The legal shape used instead: a new source item 3, link 3→2 `contradicts` at `T_NEW`. Identical rule coverage (newer evidence from a different source).
2. One test beyond the owned list: `tests/maintain/test_maintain_read_failures.py` gains a one-row param for `list_shield_log` (same additive shape as the history param row). That file's docstring promises `MAINTAIN-010` coverage for **every** `SqliteMaintainContext` read, and the new read would have made the promise stale.
3. `_shield_sort_key` maps a missing `change_log.id` (none in the store, possible on synthetic snapshots) to 0, so the tuple compare never raises: the step invariant "the rule is total" holds, and the fail-closed gaps are unchanged.

Minor red-phase note for honesty: the first red run reported a `UNIQUE constraint` error inside the re-flag CLI test, caused by deviation 1's original seed shape. It was a test-seed bug (fixed by deviation 1), not a product bug, and it never masked a green.

## 11. Issue closure

- Closes #14 (sticky manual clear) via ticket 12; comment with the §6 evidence and the tied number of new tests. The #14 trigger line in `plans/hardening-decisions.md` goes stale: the decision line (option c) is the record, and §13.1's B4 rewrite is the spec sentence.
- #18 untouched: plain-text export stays with its separate plan.
- Update `PROJECT_MAP.md` rows for `ember/maintain/derive.py`, `ember/maintain/rows.py`, `ember/maintain/maintain_lookup.py` (one line each, per AGENTS.md) at closure.

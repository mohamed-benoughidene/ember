# L3 Maintain Step 5: remove-link (hardening cluster 2 — issue #19 half 2)

Adds the human `remove_link` write to the Maintain engine: a pure validator, one store method running the ONE `UPDATE links SET status='Confirmed'→'Rejected'` + its ledger row in one transaction, and the `ember remove-link` command. Never INSERT a `links` row, never DELETE one, never flip back (§12.2's amended-clause scope).

## Gates

| Gate | Artifact | Rule |
|---|---|---|
| **Gate 2 — the #15 ruling** | The ruling recorded per `plans/hardening-schema-plan.md` **§10**: the issue #15 update (either outcome), plus the engine-relate-plan one-liner only if the relax branch is chosen. **"Keep the block" is a valid closed state.** | **This step must not start until the gate artifact exists.** §12.1: a removed link becomes indistinguishable from a human-rejected proposal; gatekeeper rule 9 + the UNIQUE triple (migration 006) then block the pair forever — whether removal freezes the triple for good or a partial live-only index frees it is **#15's ruling, not this step's**. |
| **Gate 1 — the rule-7 ADR (conditional)** | The filled `Decision:` line in engine-maintain-plan §12.0. | As drafted the ADR touches only item text ("edit_item never writes links") and does **not** gate this step. It gates here **only if** the maintainer's filled text reaches the links clause (e.g. it rewords the §12.2 amendment). Check the filled line before building. |

The plan is written now; the build waits. §12.1: "Until that ruling lands, `remove_link` is unbuildable, and the §12.6 store method must not exist."

## 0. Constitution rules this step enforces

- **B1** — `validate_remove_link` lives in `ember/maintain/human_actions.py` beside its peers (§12.6); the B6 watch is recorded in §12.8, not split.
- **B2** — reads through `MaintainLookupPort`, writes through `MaintainStorePort`.
- **B3 / T1** — the validator is pure; `old_status` comes from the Phase-1 snapshot.
- **D1** — the `links` row is **updated, never deleted** — `change_log.link_id REFERENCES links(id)`; a DELETE is refused outright by the `change_log.link_id` foreign key (migration 008) with `PRAGMA foreign_keys ON` (§12.5). The one status flip is the removal; it is recorded in the ledger, never rewritten.
- **D2 / D3** — the UPDATE and its `link_removed` ledger row land in **one transaction** (the `apply_status_origin` pattern, `ember/adapters/sqlite.py:805-840`); the removed state is rebuildable from the `link_removed` rows (§12.10a D2).
- **I1** — named by job (`validate_remove_link`, `apply_remove_link`).
- **I2** — no boolean flags; `--dry-run` omits the store call.
- **I3** — `validate_remove_link(snapshot, link_id)` = 2 inputs; `run_remove_link(ports, request)` = 2 inputs (§12.6).
- **I5 / I17** — `MAINTAIN-015` covers missing-or-not-Confirmed as ONE failure (Phase 1's Confirmed-only read cannot split them — same conflation as `MAINTAIN-005`, §12.5); the `MAINTAIN-017` UPDATE code and the `MAINTAIN-012` INSERT code are separate failures.
- **I8 — knowingly deviated (§12.10c):** removing a non-Confirmed link is an **error, not a silent no-op** — the `MAINTAIN-004` precedent; a wrong `--link` must not read as success.
- **I9 / D4** — `--link` is outside data; validated at the CLI edge (non-integer → exit 2), domain check in the command body.
- **I12** — exit 0 success, 1 on a `MAINTAIN-*` code, 2 on Click usage errors.
- **I19** — `MAINTAIN-015`/`017` carry `link_id` (§12.7).
- **I21** — every code fired here has a test asserting the code.
- **T3 / T5 / T9 / S1** — fakes; DB-state assertions; no new modules; `ember remove-link` runs alone.
- **P3 / P4** — the shared §4 four-phase pipeline; SQLite behind the port.

## 1. Job

Let a human remove one confirmed relationship edge — all five link types in scope (#19 has no type limit, §12.5) — without deleting history. The removal is a status flip plus one ledger row; nothing derived re-fires and nothing derived unwinds. Step invariant: **step finish → every module in `ember/maintain/` imports and runs; the full `tests/maintain/` suite passes.**

## 2. Inputs / boundaries (shapes per §12.6, cites)

- **`validate_remove_link(snapshot: MaintainSnapshot, link_id: int) -> list[LinkChange]`** — pure, joins `ember/maintain/human_actions.py` (§12.6). Checks:
  1. the link is a `status='Confirmed'` row in the snapshot → else `MAINTAIN-015`. One code for "no such row" and "not Confirmed" — Phase 1's Confirmed-only read (L2 §4 Phase 1) cannot distinguish them (§12.5 last bullet);
  2. a **reversed-but-Confirmed link is ACCEPTED** (§12.5, orthogonal-to-reversal): it is still a Confirmed row; the ledger then ends with both a `link_reversed` and a `link_removed` row;
  3. otherwise one `LinkChange(link_id, old_status='Confirmed' <observed>, new_status='Rejected', trigger_cause='user_remove_link', item_id=<the link's source_item_id>)`.
- **`LinkChange(link_id: int, old_status: str, new_status: str, trigger_cause: str, item_id: int)`** — pydantic, in `ember/maintain/rows.py` next to `StatusChange` (§12.6). `item_id` = the link's **source** — Relate's convention, stated so Query guesses nothing (engine-query-plan §4.6, cited by §12.5).
- **Query's `HistoryPage` — stated here so the two plans do not drift:** HistoryPage carries limit/offset/since only; the raw item_id parameter governs (Amendment §D as amended at review: item_id removed from the shape). The SHAPE edit to `plans/engine-query-plan.md` §D is NOT this step's edit.
- **`MaintainStorePort.apply_remove_link(change: LinkChange) -> int`** — int = 1 or raise; joins `ember/maintain/apply_status.py` (§12.6). One transaction: `UPDATE links SET status='Rejected' WHERE id=?` + `INSERT INTO change_log (item_id=<source>, link_id=<id>, field_changed='link_removed', old_value='Confirmed', new_value='Rejected', timestamp, trigger_cause='user_remove_link')`, the `insert_link_with_log` discipline — one `commit()`, `rollback()` in every `except` (§12.5 Phase 3). Raises `MAINTAIN-017` on the UPDATE, `MAINTAIN-012` on the INSERT (§12.6).
- **`run_remove_link(ports, request) -> list[LinkChange]`** — joins `ember/maintain/run_maintain.py` (§12.6): `_load(ports.lookup)` (the SAME Phase-1 snapshot the sweep uses, §12.4) → `validate_remove_link` → store. Reads `request.link_id` (already on `MaintainRequest` — no new field). Returns `list[LinkChange]`; it always holds exactly 1 element or raises — a no-op is impossible by design (MAINTAIN-015 eats it, §12.5 / §12.10c). Return type = the L2 gap recorded in step 04's §10 and folded into the L2.
- **CLI** — `ember remove-link --link <id> [--dry-run] [--db <path>]` (§12.3). `--link` is plain `type=int`; non-integer → Click exit 2. No confirm loop — the human invoking IS the confirmation (§12.3). Same `open_maintain_database` boot (I13; no new migration — §12 preamble).

## 3. Outputs

- `list[LinkChange]` (exactly 1) from validator and entry point; `1` (or raise) from the store.
- STDOUT, one line (§12.3's sample is the final wording — §12.9 item 1 resolved):
  `link 7: supersedes 2 -> 5 removed (Confirmed -> Rejected)`
  The line needs the link's type/source/target from the snapshot — display only (§12.9 item 3: the derived state left standing is **not** named on stdout; the per-type table below lives in the tests, not the report).
- `--dry-run` STDOUT, one line, pinned: `link 7: Confirmed -> Rejected (dry-run)` — §12.3's final-run wording style; writes zero rows, exit 0.

## 4. Steps

1. Gate-2 artifact exists (see Gates); Gate-1 check per the conditional.
2. Add `LinkChange`, `validate_remove_link`, `apply_remove_link`, `run_remove_link`, the CLI command.
3. Error-code audit before numbering: verify nothing beyond the numbers step 04 took (`013`/`014`/`016` per §12.7's ordering; `errors.py` today ends at `012` — re-check `git log -p ember/maintain/errors.py` at write time, §12.7). The family is contiguous (I17) once both steps have landed; landing order between 04 and 05 follows whichever gate closes first — numbers are never reused either way.
4. Apply the plan amendments listed in §10 in the same commit.

### 4.1 The one write, and what it must never be

- The ONLY `links` write this step makes: `UPDATE links SET status='Rejected' WHERE id=?` (§12.5). Never INSERT, never DELETE, never flip `Rejected` back (§12.2).
- **Interaction with cluster 1's `reversed_at` column** (hardening-schema-plan §5/§6 — verified NOT landed on this branch: migrations stop at 010, `sqlite.py` has no `reversed_at`):
  - When it lands, the §1 amended clause (§12.2) names exactly TWO link writes: this step's status UPDATE and `apply_reversal`'s `UPDATE links SET reversed_at` (schema-plan §6 pairing rule) — **this step's removal must not touch `reversed_at`**; it writes `status` only.
  - **db-check after a removal:** cluster 1's `ember db-check` replay (`replay_reversals`, schema-plan §2/§6) rebuilds `reversed_at` from `link_reversed` rows only — a removal writes no such marker, so a removed link must never drift the replay. Pinned by `test_remove_link_db_check_replay_still_matches`.
  - **Rule 9 after a removal (the Gate-2 substance):** under "keep the block", `find_existing` returns the row of any status and rule 9 blocks the pair forever (accepted; spec 3.3). Under the relax branch, the partial live index is `WHERE status='Confirmed' AND reversed_at IS NULL` (schema-plan §10) — a removed row leaves it, but whether a `Rejected` row stays blocking is part of the ruling. This step implements whatever the ruling says; it does not pre-decide.
- **Reverse after removal is dead, by design:** `validate_reverse_supersedes` requires a Confirmed link (`human_actions.py:241`), so re-reversing a removed link exits `MAINTAIN-005` — correct per §12.5.

### 4.2 Per-type consequences (§12.5 table — recorded, not hidden; tested, not promised)

| removed link type | immediate effect | does NOT happen |
|---|---|---|
| `supersedes` | nothing derived re-fires | the superseded item is **NOT reopened** (§8 carry-forward, verbatim) |
| `answers` | nothing derived re-fires | the answered `Question` is **NOT reopened** (same ruling) |
| `contradicts` | nothing derived re-fires | the challenged target is **NOT un-challenged** — single-step, no unwind |
| `depends_on` | nothing derived re-fires | the dependent is **NOT un-challenged** — same |
| `supports` | none | nothing |

The sweep needs no new rule: Phase 1 loads `status='Confirmed'` only, so a `Rejected` link is invisible to all four triggers (§12.5) — the parameterized test pins it.

## 5. Errors (codes only, cross-ref L2 §12.7)

- `MAINTAIN-015` — `RemoveLinkNotConfirmed` — no link with that id, or it is not `Confirmed`.
- `MAINTAIN-017` — `RemoveLinkWriteFailed` — the `links` UPDATE failed; rolled back.
- `MAINTAIN-012` — `ChangeLogWriteFailed` — reused, the ledger INSERT (§12.6).
- Boot path unchanged: `MAINTAIN-007` / `008` / `009` / `010` (I13).

`MAINTAIN-001` is **not** used here (edit-item only, §12.7). Context (I19): 015/017 carry `link_id`.

## 6. Test targets (names owned by this step, per L2 §12.8)

Unit — `tests/maintain/test_remove_link.py` (FakeMaintainLookup, pure):
- `test_validate_remove_link_confirmed_link_returns_link_change` — §12.8 unit, remove happy path.
- `test_validate_remove_link_missing_or_rejected_link_raises_015` — §12.8 unit bullet (both shapes, one code).
- `test_validate_remove_link_reversed_but_confirmed_link_passes` — §12.8 unit bullet (a `LinkChange` for a reversed-but-Confirmed link).

Integration — `tests/maintain/test_remove_link_integration.py` (real temp DB, `open_maintain_database`):
- `test_apply_remove_link_flip_and_ledger_row_one_transaction` — §12.8 integration bullet 2.
- `test_apply_remove_link_sqlite_error_injection_raises_017_and_rolls_back` — the I21 named row for 017. **Vehicle (precisely): a test-local delegating connection proxy that raises `sqlite3.Error` only when the SQL matches the `links` UPDATE under test; it delegates everything else — including `rollback()` — to the real connection. A fake per T3, not a mock: there is no in-repo write-side precedent (`BrokenConnection` is read-side all-or-nothing; real-constraint routes cannot fire for these columns). The MAINTAIN-017 assertions stay as written.** Real store, not a fake (the step-02 T10 trap applies).
- `test_apply_remove_link_insert_failure_raises_012_and_rolls_back` — the I21 named row for the reused 012.
- `test_sweep_ignores_removed_link[supersedes|answers|contradicts|depends_on|supports]` — **the ONE parameterized sweep-interplay test over all five types** (§12.8 integration bullet): after removing each, the next sweep writes zero rows and no derived state unwinds — the §4.2 table, row by row.
  - per-param item-type fixtures required — legal seeds per TYPE_COMPAT: supersedes same-type pairs; answers (Decision|Finding)->Question; contradicts (Finding, Assumption|Decision); depends_on (Decision|Assumption)->(Assumption|Finding|Decision); supports (Finding)->(Assumption|Decision). supports feeds no trigger even Confirmed, so its param pins a trivially-true case.
- `test_removed_supersedes_does_not_reopen_the_closed_item` — **named regression 1** (§12.8 bullet; engine-maintain-plan §8, verbatim).
- `test_reversed_then_removed_link_has_both_marker_rows_sweep_unaffected` — **named regression 2** (§12.8 bullet; §12.5 orthogonal-to-reversal).
- `test_change_log_still_joins_links_after_removal` — the **migration-008 reason proven**: no DELETE ever ran; the ledger's FK still joins (§12.8 integration bullet).
- `test_remove_link_db_check_replay_still_matches` — the §4.1 db-check interaction (conditional on cluster 1 having landed; else marked skipped-churn).

CLI — `tests/maintain/test_remove_link_cli.py` (§12.8 CLI bullets):
- `test_remove_link_cli_unknown_link_exits_1_maintain_015` — bullet 4.
- `test_remove_link_cli_already_rejected_exits_1_maintain_015` — bullet 5 (a rejected proposal).
- `test_remove_link_cli_success_exits_0_one_line` — bullet 6.
- `test_remove_link_cli_dry_run_writes_zero_rows` — bullet 8.
- `test_remove_link_cli_non_integer_link_exits_2` — bullet 9 (Click, exit code not error code).

E2E — `tests/maintain/test_remove_link.py` (this step's file; the ONE combined test lives here):
- `test_e2e_edit_item_then_remove_link_then_history_renders_unknown_kind` — §12.8's single both-CLIs E2E, owned by this step as ONE combined test: `ember edit-item` → `ember remove-link` → `ember history --item <id>` asserts **all** new rows render `kind='unknown'` with raw values visible and nothing crashing (caveat: holds until §12.9 item 4 — Engine D work, not ours). Step 04 keeps only its step-local half-assertions in its own file; see §10.

## 7. CLI check (Rule S1)

```
$ ember remove-link --link 7 --db research.db
link 7: supersedes 2 -> 5 removed (Confirmed -> Rejected)   # exit 0
$ ember remove-link --link 99 --db research.db
error: MAINTAIN-015 ...                                     # exit 1
$ ember remove-link --link 7 --db research.db               # again
error: MAINTAIN-015 ...                                     # exit 1 — an error, not a no-op (§12.10c I8)
```

`--dry-run` prints the pinned one line `link 7: Confirmed -> Rejected (dry-run)` (§12.3's final-run wording style), writes zero rows, exit 0; missing DB → exit 1 `MAINTAIN-007`; non-integer `--link` → exit 2 (§12.3).

## 8. Out of scope (this step)

- `edit_item` — step 04.
- Re-creating a removed link — gatekeeper rule 9 / Relate's write path, per the #15 ruling; not this step's write.
- Any `links` write beyond the one UPDATE (no INSERT, no DELETE, no flip-back, no `reversed_at` write — §12.2, §4.1).
- The Query classifier extension (`kind` for `link_removed`) — §12.9 item 4, Engine D work.
- Migration — none (§12 preamble); `status='Rejected'` is migration 006's existing CHECK value.

## 9. Next

Cluster 2 is complete; both #19 halves and #1's writer have shipped. Engine-query-plan §4.6 still renders `unknown` for the new rows — correct, per §12.4, until §12.9 item 4.

## 10. Deferred settings + L2 amendment log

- (§12.9 item 1) Report wording — **resolved**: §12.3's sample line verbatim.
- (§12.9 item 3) Naming the derived state left standing — **resolved: no.** One line per §12.3; the consequence table is realized as the §6 tests, not stdout.
- Plan amendments this step applies (same commit as `apply_remove_link`, per §12.2 item 1): the **engine-maintain-plan §1 clause edit** — "Maintain never writes `links`" gains the two named writes (this step's status UPDATE; `apply_reversal`'s `UPDATE links SET reversed_at` per schema-plan §6's cross-plan note — apply the `reversed_at` mention only if cluster 1 has landed at build time; otherwise amend the removal half alone); the **`link_removed` writer-side row appended to the frozen L2 §4.6 vocabulary table** (§12.4's table, its last row). Until this commit the frozen §1 text stays — this file is the amendment of record (§12.2).
- **L2 §12.9 amendment recorded:** the singular `04-edit-and-remove.md` is split into `04-edit-item.md` + `05-remove-link.md` — mirrored in step 04 §10; fold into the L2 when amended.
- **L2 §12.8 amendment recorded (§12.8 as amended at review):** §12.8's single both-CLIs E2E is owned by step 05 as one combined test; step 04 owns only step-local assertions (mirrored in step 04 §10; fold into the L2 when amended).
- **L2 §12.9 amendment recorded:** §12.9's both-gates-before-authoring rule is superseded by the split: 04 proceeds on Gate 1 alone, 05 on Gate 2 alone (plus Gate 1 only if the ADR touches links) (mirrored in step 04 §10; fold into the L2 when amended).
- **Test-file ownership:** step 04's tests land in `tests/maintain/test_edit_item.py` / `test_edit_item_integration.py` / `test_edit_item_cli.py` (all new files); step 05's in `tests/maintain/test_remove_link.py` / `test_remove_link_integration.py` / `test_remove_link_cli.py` (all new files); the combined E2E lives in step 05's file — identical test names can never shadow one file.
- **Amendment §D as amended at review recorded:** HistoryPage carries limit/offset/since only; the raw item_id parameter governs — item_id removed from the shape. The SHAPE edit to `plans/engine-query-plan.md` §D is not this step's; stated in §2 so the two plans do not drift (fold into the L2 when amended).

## 11. Rollback

One in-place `links.status` UPDATE + one append-only `change_log` INSERT, one transaction, rollback in every `except` (I7). No down-migration; no data rollback — and **the product has no un-remove**: the amended §1 clause forbids flipping `Rejected` back (§12.2). A mistaken removal is auditable forever in the `link_removed` row; re-creating the pair is ruled by #15, not by this command. Undo before the first removal on an existing DB: `cp ember.db ember.db.bak`.

## 12. Build Notes (post-implementation)

Built 2026-10-29 on `feat/hardening`. **Gate 2 was CLOSED before any code:** the #15 ruling is "keep the block" (recorded per `plans/hardening-schema-plan.md` §10, GitHub #15 closed). Consequence implemented: a removed pair stays reserved forever (`find_existing` reads any status, gatekeeper rule 9 keeps blocking), and the removal is the ONE `UPDATE links SET status='Confirmed' -> 'Rejected'`. INSERT, DELETE, flip-back, and any `reversed_at` write are all absent by construction. The Gate-1 check was done: the filled ADR text touches only item text and never reaches the links clause, so no extra Gate-1 constraint applied.

**Cluster-1 dependency resolved:** `reversed_at` HAS landed on this branch (migration 010-era work, `apply_reversal` in `ember/adapters/sqlite.py:958`), so the §1 clause amendment applies **in full** (both named writes) and the db-check replay test was authored, not skipped.

**What landed** (one commit):

- `ember/maintain/human_actions.py` — `validate_remove_link(snapshot, link_id) -> list[LinkChange]`, 2 inputs. One Confirmed-row lookup; a reversed-but-Confirmed link passes (orthogonal to reversal); missing-or-not-Confirmed is ONE code, `MAINTAIN-015` with `link_id` in context (the Phase-1 Confirmed-only read cannot split the shapes, same conflation as `MAINTAIN-005`). A no-op is impossible by design (the recorded §12.10c I8 deviation: error, not silent success).
- `ember/maintain/rows.py` — `LinkChange(link_id, old_status, new_status, trigger_cause, item_id)`, the exact §12.6 shape, `item_id` = the link's source.
- `ember/maintain/run_maintain.py` — `run_remove_link(ports, request) -> list[LinkChange]` (always exactly 1 or raise; `request.link_id` already on `MaintainRequest`).
- `ember/maintain/apply_status.py` — `MaintainStorePort` gains `apply_remove_link(change) -> int`.
- `ember/adapters/sqlite.py` — `SqliteMaintainStore.apply_remove_link`: the ONE `UPDATE links SET status = ? WHERE id = ?` + one `change_log` INSERT (`field_changed='link_removed'`, `old_value` = the observed `Confirmed`, `item_id` = the link's source, `trigger_cause='user_remove_link'`, `link_id` = the id), one `commit()`, `rollback()` in every `except`. `MAINTAIN-017` on the UPDATE (carries `link_id`), `MAINTAIN-012` on the INSERT.
- `ember/maintain/errors.py` — `RemoveLinkNotConfirmed` (`MAINTAIN-015`), `RemoveLinkWriteFailed` (`MAINTAIN-017`). The family is contiguous again: 012, 013, 014, 015, 016, 017. Error-code audit receipt: `git log -p ember/maintain/errors.py` at build time ended at 016, with 015/017 held free by step 04.
- `ember/cli.py` — `ember remove-link --link N [--dry-run] [--db P]`. Success prints the §12.3 sample line verbatim, e.g. `link 1: supersedes 2 -> 1 removed (Confirmed -> Rejected)`. `--dry-run` prints the pinned `link N: Confirmed -> Rejected (dry-run)` and writes nothing, exit 0. Non-integer `--link` is Click exit 2; `MAINTAIN-*` is exit 1; boot path unchanged (`MAINTAIN-007`/`008`/`009`/`010`).

**How the LinkChange display fields were resolved (§10's review amendment):** `LinkChange` keeps the 5-field §12.6 shape — no display fields added. The success line's `link_type source -> target` are read at the CLI edge from the SAME Phase-1 snapshot the command validates against, BEFORE the flip (step plan §3: "display only"; a removed link leaves the Confirmed-only read, so no post-flip read is possible). Cost stated: in the real-run path the CLI loads the snapshot once for display and `run_remove_link` loads it again inside; two Phase-1 reads per removal, accepted for shape honesty over cleverness. The dry-run path uses one load.

**Deviations / deltas recorded:**

- Combined-E2E file location: the orchestrating ticket summary said "the CLI test file"; the step plan (source of truth) pins it in §6 and §10 to `tests/maintain/test_remove_link.py` ("the ONE combined test lives here"). The plan was followed; the E2E lives in `test_remove_link.py`.
- The reversed-then-removed marker assertion had to match reality: `apply_reversal` writes THREE rows carrying the link id (the item `status` restore, then the `link_reversed` marker), so the ledger for that link id is `["status", "link_reversed", "link_removed"]` — both markers present, order proven.
- The §4.2 parameterized test asserts per-type seeded states are EXACTLY preserved after removal + sweep (zero rows written, `applied == 0`, `changed == []`), one param per link type with legal TYPE_COMPAT seeds, `supports` trivially true as planned.

**Plan amendments applied in this commit (per §10):** `plans/engine-maintain-plan.md` §1's "Maintain never writes `links`" clause now names the TWO writes (this step's status UPDATE, and — cluster 1 having landed — `apply_reversal`'s `reversed_at` UPDATE); the `link_removed` writer-side row was appended to the frozen §4.6 vocabulary table, and the §4.6 note that held the seat for it was updated. The §12.9/§12.8 recorded L2 amendments (step split, E2E ownership, return types) stay recorded in §10 here until an L2 amendment pass folds them in, as in step 04.

**Test counts:** before 668 passed / 4 deselected. After: **690 passed / 4 deselected** in ~3s — 22 named tests added, all watched red at collection (`ImportError: cannot import name 'RemoveLinkWriteFailed'`) then green: 4 in `tests/maintain/test_remove_link.py` (3 unit + the ONE combined E2E), 12 in `tests/maintain/test_remove_link_integration.py` (3 store tests, the 5-param sweep sweep, 2 named regressions, the FK-join proof, the db-check replay), 6 in `tests/maintain/test_remove_link_cli.py` (unknown, already-rejected, success, second removal, dry-run, non-integer). Injection vehicle exactly as §6 dictates: a test-local `DelegatingConnection` delegating proxy; both injection tests assert the full rollback (link still `Confirmed`, zero ledger rows) plus the code (`017`, `012`). `tests/test_architecture.py` passes unchanged (no new modules, T9).

**CLI check (Rule S1, real run, real temp DB, items 1/2/3 = Decision/Decision/Question, link 1 = supersedes 2 -> 1 Confirmed, link 2 = answers 2 -> 3 Rejected):**

```
$ ember remove-link --link 1 --db cli-check.db
link 1: supersedes 2 -> 1 removed (Confirmed -> Rejected)                  exit 0
$ ember remove-link --link 1 --db cli-check.db        # again
error: MAINTAIN-015 RemoveLinkNotConfirmed | ... | link_id=1               exit 1  (error, not no-op)
$ ember remove-link --link 99 --db cli-check.db
error: MAINTAIN-015 RemoveLinkNotConfirmed | ... | link_id=99              exit 1
$ ember remove-link --link 2 --db cli-check.db        # a Rejected proposal
error: MAINTAIN-015 RemoveLinkNotConfirmed | ... | link_id=2               exit 1
$ ember remove-link --link abc --db cli-check.db
Error: Invalid value for '--link': 'abc' is not a valid integer.           exit 2
$ ember remove-link --link 1 --dry-run --db fresh.db
link 1: Confirmed -> Rejected (dry-run)                                    exit 0; links unchanged (1 row, still Confirmed), change_log 0 rows
$ ember db-check --db fresh.db         # after a REAL removal of link 1
result: OK                                                                 exit 0 (0 FK violations, replay column == ledger)
```

**Combined E2E proof (real CLIs, one fresh DB):** `ember edit-item --item 1 --field rationale --value "chosen for the ceiling"` (exit 0) -> `ember remove-link --link 1` printing `link 1: depends_on 1 -> 2 removed (Confirmed -> Rejected)` (exit 0) -> `ember history --item 1` renders BOTH new rows `kind='unknown'` with raw values visible (`rationale: null -> chosen for the ceiling`; `link_removed: Confirmed -> Rejected`, `item 1`, `link 1`), then `ember db-check` exits 0. The same sequence is pinned as the ONE combined test `test_e2e_edit_item_then_remove_link_then_history_renders_unknown_kind`.

**Not done here:** any link INSERT/DELETE path, any rule change to the relate gatekeeper (rule 9 stays "keep the block" per #15), any migration, any query change (the `link_removed` row renders `unknown` by design until the Engine D classifier work), `edit_item` rework. No linter exists in this repo (CI runs pytest only, which includes the architecture test and passed).

**Implementation review (ticket 08, 2026-10-29):** APPLIED — `_confirmed_link` in `cli.py` gains full type hints (`MaintainSnapshot` in, `Link | None` out), closing the I1 gap. ADJUDICATED (kept): the CLI's Confirmed-link pre-read duplicates a scan the validator also does; it stays because the report line needs the actual row (type, endpoints) BEFORE the flip, and the validator returns changes, not rows. ADJUDICATED (kept): the pre-existing cross-module private import pattern (`_load`, `_connect_readonly`) is consistent houses style; widening it is out of scope here (recorded on step 02's note as well).

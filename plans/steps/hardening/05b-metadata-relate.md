# L3 Hardening Step 5b: Relate Metadata Signal Reads items.metadata (ticket 11, #5)

Implements L2 relate §13 ("V1.x Amendment: metadata signal reads items.metadata"). Ships the reader only. Builds on `05a-metadata-capture.md` (column and capture writer exist, schema at version 12). Closes #5 together with 05a.

## 0. Constitution rules this step enforces

- **B1 / B2** — the label is read through the existing ports; `candidate_pool.py` stays driver-free, no SQL in the core.
- **D2 / D3** — the column is written once by capture, read here, never rewritten. No backfill, no derived copy.
- **D4** — a stored label is compared deterministically (strip + casefold), never guessed at.
- **D5 / I10** — `NewItem.metadata` is additive (`str | None = None`); every existing caller and test compiles unchanged.
- **B3** — no new trigger, no migration in this step; SQL triggers stay where 011 put them.
- **I17 / I21** — zero new error codes; RELATE-023 stays a timestamp error only (§4).
- **T1 / T4 / T5** — pure-core unit tests on the matrix, one integration test on a real temp DB with a mixed corpus.
- **P1** — this read path is the #5 decision. No fuzzy matching, no relabel command.

## 1. Job

Make the metadata signal prefer the project label and keep the time proxy for unlabeled items, exactly per the §13 matrix.

## 2. The pin (L2 relate §13)

- `NewItem` (`ember/relate/rows.py`) gains `metadata: str | None = None`.
- `LinkLookupPort` grows its 13th method `item_metadata(item_id: int) -> str | None` (§11 precedent). `SqliteLinkContext` implements it, and `list_other_items` / `find_latest_unlinked_active` add the column to their SELECTs. Read failures raise `RELATE-016` like sibling reads.
- `load_filter._read_item` reads the label into the new item's `NewItem`. None is legal (unlabeled) and never trips the "row missing" check.
- `_metadata_signal(items, new_item)` rewritten to the frozen matrix:
  - normalize: `value.strip().casefold()` on both sides at signal time.
  - new labeled: keep candidates that are labeled and casefold-equal. The window does not apply.
  - new unlabeled: keep unlabeled candidates within `METADATA_WINDOW` (today's proxy, restricted to the both-NULL subset).
  - labeled-new vs unlabeled-candidate: excluded. unlabeled-new vs labeled-candidate: excluded. No partial matches.
- `METADATA_WINDOW`, `FLAT_COSINE`, `Signals`, `_merge`, counts key `metadata`, `Pool`, CLI JSON: all unchanged (§12 guarantees stand).

## 3. Steps

1. `ember/relate/rows.py`: add the field.
2. `ember/relate/link_lookup.py` + `ember/adapters/sqlite.py`: the 13th port method, the three SELECTs, error wrapping.
3. `ember/relate/load_filter.py`: `_read_item` reads metadata.
4. `ember/relate/candidate_pool.py`: rewrite `_metadata_signal` to the matrix. Nothing else in the module moves.
5. Floor: `ensure_relate_schema` `required=11` -> `12` (`RELATE-014`), docstring updated. `ember/adapters/db_check.py` FLOORS gains `("relate", 12)` in the same step. Maintain stays 11, query stays 10 (neither reads the column). (Review fix 2.)
6. Fakes: `tests/relate/fakes.py` lookup gains `item_metadata`; `tests/fakes.py::insert_item` gains an optional `metadata` kwarg (additive, default None).

## 4. Errors (codes only)

**Zero new error codes.** `RELATE-016` wraps label reads like every other item read. `MetadataReadFailed` (RELATE-023) stays timestamp-only: despite the name it is never raised for `items.metadata` (NULL is legal, never a malformed value). All other Phase 2 codes unchanged: RELATE-017, 018, 019, 021, 022, 023, 037.

## 5. Test targets

Owned (names checked against `tests/`, no collisions):

- `tests/relate/test_candidate_pool_unit.py`: `test_labeled_new_item_matches_only_casefolded_equal_labels`, `test_same_label_matches_outside_the_thirty_day_window`, `test_unlabeled_new_item_keeps_the_time_proxy_against_unlabeled_candidates`, `test_labeled_candidates_are_excluded_from_the_unlabeled_time_proxy`, `test_metadata_signal_normalizes_case_and_padding`, `test_blank_metadata_is_unlabeled`.
- `tests/relate/test_candidate_pool_integration.py`: `test_seeded_mixed_corpus_routes_labels_and_the_time_proxy` (labeled new item with: an equal-label candidate far outside the window, an equal-label candidate inside it, a different-label candidate, an unlabeled same-day candidate; plus the unlabeled-new mirror).

Declared churn (part of this step's diff): `tests/test_relate_db_open.py::test_ensure_relate_schema_accepts_version_11` re-seeded to 12 and renamed `_accepts_version_12`; `test_ensure_relate_schema_rejects_version_8` `required` assertion 11 -> 12 (name unchanged); the two fake additions in §3.6.

Must pass untouched: every pre-existing unit function in `test_candidate_pool_unit.py` (recount at build time; today's seeds are all unlabeled, so the proxy branch reproduces them exactly), every pre-existing integration test in `test_candidate_pool_integration.py`, `tests/relate/test_relate_cli.py` (it builds `Pool` directly, §12 accept list), `test_relate_core_does_not_import_adapters`, and the empty-pool golden byte test. If a pre-existing test needs an edit, stop: that is a bug against the §13 pin.

Declared churn (part of this step's diff): the two relate floor tests in `tests/test_relate_db_open.py` (rename `accepts_version_11` -> `accepts_version_12`, `rejects_version_8` context `required` 11 -> 12), `tests/test_db_check.py::test_db_check_healthy` (`floors: relate 11 ok` -> `relate 12 ok`), and `tests/test_db_check.py::test_db_check_drift_stale_version` (`relate needs 11` -> `relate needs 12`). Also `tests/relate/test_load_filter_unit.py::_VanishingLookup` gains the additive `item_metadata` (returning None) so `test_vanishing_row_raises_items_read_failed` keeps exercising the missing-row path, not an AttributeError (review fixes 2 and 3).

## 6. CLI check (Rule S1)

- `ember relate --item 1 --db <single-item fixture>`: exit 0, stdout byte-identical to `tests/fixtures/relate/empty_pool_golden.json`. The label read happens on the path (cli.py:290 loads candidates first) but produces no output, so `Pool.empty` prints the same JSON as the golden (review fix 10).
- Signal behavior on the seeded mixed corpus is asserted on `Pool.counts` through the integration route with `FakeEmbedder` (a labeled new item whose only equal-label partner sits outside the 30-day window yields `counts["metadata"] >= 1`). The counts JSON is only printable in the empty-pool branch (cli.py:305-310), so a size-1 pool has no CLI JSON to pin: its observable is the full-run summary, which stays `accepted: N, rejected: 0, skipped: 0, aborted: false` byte-for-byte per §12 (review fix 5).

## 7. Rollback

No migration in this step: nothing to restore. The signal change writes no rows (embedding upserts follow today's rules only). Code undo: drop the commits. The column and stored labels stay in the DB, harmless and unread until this step is reapplied.

## 8. Step invariant

After this step: the module runs, `open_relate_database` boots at floor 12, the §13 matrix is proven by unit and mixed-corpus integration tests, and the full suite is green with real numbers recorded in Build Notes.

## 9. Out of Scope

- No capture changes (05a owns the writer). No Maintain relabel, no `edit-item` metadata path, no bulk labeling, no fuzzy matching, no BM25, no 4th signal.

## 10. Build Notes

Landed exactly per §3, in §3 order: (1) `NewItem.metadata: str | None = None` in `ember/relate/rows.py`. (2) The 13th port method `item_metadata` on `LinkLookupPort` (`ember/relate/link_lookup.py`) + `SqliteLinkContext.item_metadata` wrapping failures as `RELATE-016`, with `metadata` added to the `list_other_items` and `find_latest_unlinked_active` SELECTs and their `NewItem` builds (`ember/adapters/sqlite.py`). (3) `load_filter._read_item` reads the label after the missing-row check, so None (unlabeled) never trips it. (4) `_metadata_signal` rewritten to the frozen §13 matrix (`strip().casefold()` both sides, labeled branch window-free, both-NULL keeps `METADATA_WINDOW`, mixed pairs never match, `_parse_created_at`/`_within_window` still run for every row so RELATE-023 surface is unchanged). (5) `ensure_relate_schema` floor 11 -> 12 (`RELATE-014` `required=12`, docstring updated) and `db_check.py` FLOORS `("relate", 12)` (maintain 11 and query 10 untouched). (6) `tests/relate/fakes.py::FakeLinkLookup.item_metadata` (mirrors the adapter, None on missing) and the `_VanishingLookup` additive method (returning None) per review fixes 2 and 3. `tests/fakes.py::insert_item` already had the `metadata` kwarg from 05a, used as-is.

TDD red first: the 6 named matrix unit tests + the mixed-corpus integration test were written and run before any implementation: 7 failed for the right reasons (unit: old code saw every item as unlabeled, so the labeled branch kept 0 or the wrong count; integration: labeled run counted `metadata: 4` under the old proxy vs the expected 2). The extra parse-surface test (`test_labeled_new_item_still_parses_every_created_at`, review fix 9) was green from the start, as expected, since the old code also parsed every row; it now guards the surface against regression.

Test churn, all declared or explained: `tests/test_relate_db_open.py` rename `accepts_version_11` -> `accepts_version_12` (version 12 seeded) and `rejects_version_8` `required` assertion 11 -> 12. `tests/test_db_check.py` `relate 11 ok` -> `relate 12 ok` and `relate needs 11` -> `relate needs 12`. No pre-existing test needed any other edit (the §5 must-pass list holds: all 34 prior unit functions and 4 prior integration tests untouched and green, `test_relate_cli.py` green untouched, architecture test green, empty-pool golden test green untouched).

Deviations from the pin (both documentation/observable-fidelity only, no behavior change):
1. The `candidate_pool.py` module docstring's one-line description of the metadata signal was updated ("project labels from `items.metadata`, with the frozen 30-day time proxy for unlabeled items") because the old text described only the proxy branch and would have been false after this step. No code outside `_metadata_signal` + the new `_normalize_label` helper moved.
2. During the red phase, per-candidate `source is SignalKind.metadata` assertions in the new tests were replaced by exact `Pool.counts` assertions. Reason, observed: with a universe of at most ten and equal default vectors, every metadata member is also a dense member, and `_merge` keeps the dense source (`setdefault`, §12 frozen), so per-id source attribution is impossible through the public function by design. Exact counts (the §6-declared observable) discriminate the matrix: the corpus shapes are built so each wrong branch produces a different `metadata` count, and the integration run's labeled/new and unlabeled/mirror runs pin 2 and 1 respectively.

Suite: before 764 passed, 4 deselected (baseline, verified at session start); after 772 passed, 4 deselected in 3.95s (8 new tests: 7 unit incl. the parse guard, 1 integration). No package changes, no new error codes, no capture file touched (git diff confirms scope).

§6 evidence (real CLI, `.venv/bin/ember`, `EMBER_AI_API_KEY=dummy`): fresh single-item v12 temp DB, `ember relate --item 1` exit 0, stderr empty, stdout byte-identical to `tests/fixtures/relate/empty_pool_golden.json` (python byte comparison: True). `ember db-check --db <fresh v12 temp DB>`: exit 0, `version: 12` / `floors: relate 12 ok, maintain 11 ok, query 10 ok, capture none` / triggers present / `link_compat: 16 rows, matches TYPE_COMPAT` / `foreign_key_check: 0 violations` / `reversal replay: 0 reversed links, column == ledger` / `result: OK`. The full-run summary observable (`accepted: N, rejected: 0, skipped: 0, aborted: false`) needs the live relate AI, so it is proven by the CLI tests, which keep passing untouched: `tests/relate/test_relate_cli.py` 19 passed, including `test_empty_pool_stdout_byte_identical_to_pre_amendment` and `test_relate_item_runs_phases_3_and_4`.

## 11. Issue closure

- Closes #5 via ticket 11 together with 05a: migration + capture writer + relate reader. Comment with §6 evidence and the §5 accept list.
- #18 left alone: plain-text export stays with its separate plan.

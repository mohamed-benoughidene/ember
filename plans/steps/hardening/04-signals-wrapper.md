# L3 Hardening Step 4: Signals Wrapper (ticket 10, #8)

Implements the L2 amendment `plans/engine-relate-plan.md` §12 ("V1.x Amendment: Signals wrapper, ticket 10, #8 ruling") at one boundary: `build_candidate_pool` in `ember/relate/candidate_pool.py`. Pure restructure, zero output change, closes #8. Builds on steps 01–03; no migration, no port change, no CLI change.

## 0. Constitution rules this step enforces

- **I4 / I3** — the external contract stays the named `Pool(ranked, counts, warning)`; `build_candidate_pool` keeps its 4 inputs (amendment §12 guarantees).
- **I10 / D5** — pure restructure: no rename, no removal, no field change; every existing caller and test compiles and passes unchanged (amendment §12 accept list).
- **B1** — `Signals` lives and dies inside `candidate_pool.py`, the module with the one Phase 2 job; zero new imports anywhere else (amendment §12 pin).
- **I17 / I21** — zero new error codes; the step must raise nothing new; tests assert codes and data, never prose (amendment §12).
- **T1 / T5 / T6** — `Signals` is a pure data bundle inside the pure core; tests assert the returned `Pool` and the wrapper's contract, not private call counts.
- **T9** — the architecture test gains one line: no module outside `candidate_pool.py` names `Signals` (amendment §12 boundary).
- **S1 / I12** — relate still runs alone; flags, exit codes 0/1/2, stdout/stderr split untouched; §6 proves it byte-identical.
- **P1, stated honestly** — the maintainer ruled build against the defer recommendation (`hardening-decisions.md` #8). The step buys structure, zero behavior; it must not buy anything else (out-of-scope line, §8 here).

## 1. Job

Bundle the three Phase 2 signal results into one `Signals` object inside `build_candidate_pool`, so a future 4th signal (only if ever approved by an L1 amendment) has one place to join. The pool ranks identically. `Pool`, the CLI output, the warning, and every error stay byte-for-byte as today.

## 2. The pin (amendment §12 — cited for every boundary)

- `class Signals(BaseModel)` in `ember/relate/candidate_pool.py`: exactly `content: dict[int, float]`, `graph: set[int]`, `metadata: set[int]` (§12 field list). Not in `rows.py`; no re-export.
- Built in `build_candidate_pool` after the three signal calls return; consumed in the same function by `_merge` and the `counts` dict (§12 boundary).
- Counts keys stay `dense`/`graph`/`metadata` while the content field stays `content` (§12 naming trap).

## 3. Steps

1. `ember/relate/candidate_pool.py`: add `Signals` above `build_candidate_pool`, three fields per §2. Docstring states the boundary: built at Phase 2, single consumer `_merge` plus the counts.
2. `build_candidate_pool`: after the `_content_signal` / `_graph_signal` / `_metadata_signal` calls, build `Signals(content=content, graph=graph, metadata=metadata)`; `_merge(items, signals)` replaces the three keyword arguments (private helper, I10-conformant); `counts` derives from `len()` of the wrapper's fields under the frozen keys. The empty-universe early return (`Pool.empty(warning=warning)`, `candidate_pool.py:64-65`) stays unchanged and before all of this — no `Signals` built there (§12 boundary).
3. Nothing else moves: `_content_signal`, `_graph_signal`, `_metadata_signal`, `_model_change_warning`, `_resolve_vector`, `_parse_created_at`, `_within_window`, `_cosine` bodies unchanged. No `rows.py`, `errors.py`, `cli.py`, adapter, or port edit.
4. `tests/test_architecture.py`: add `test_signals_wrapper_stays_inside_candidate_pool` — assert no `ember/*.py` file except `candidate_pool.py` mentions `Signals`.

## 4. Errors (codes only)

**Zero new error codes — this step must raise nothing new.** `build_candidate_pool` raises exactly today's set from exactly today's sites, unchanged: `RELATE-017`, `RELATE-018`, `RELATE-019`, `RELATE-021`, `RELATE-022`, `RELATE-023`, `RELATE-037` (verified against the `candidate_pool.py` docstring and L2 §4.6).

## 5. Test targets

Owned tests (names checked against `tests/relate/` and `tests/test_architecture.py` — no collisions):

- `test_signals_holds_exactly_three_fields` (`tests/relate/test_candidate_pool_unit.py`) — the type has exactly `content`/`graph`/`metadata`, nothing more (§2 pin).
- `test_signals_wrapper_stays_inside_candidate_pool` (`tests/test_architecture.py`) — step 3.4.
- `test_empty_pool_stdout_byte_identical_to_pre_amendment` (`tests/relate/test_relate_cli.py`) — raw stdout bytes equal a pre-code capture. Capture (query step 04 precedent): before any wrapper code, run the empty-pool case through `CliRunner` on a single-item temp DB and store raw stdout into `tests/fixtures/relate/empty_pool_golden.json`. No fakes needed — the empty-universe path never loads a model and never calls the AI (proven by `test_relate_cli.py:318`).

Must pass unmodified (amendment §12 accept list): all 34 unit functions in `test_candidate_pool_unit.py`, all 4 integration tests in `test_candidate_pool_integration.py`, `test_relate_cli.py` untouched (its exact-string summary asserts are themselves byte pins), `test_relate_core_does_not_import_adapters` green. If any existing test needs an edit, stop: that is a bug in the restructure, not churn.

## 6. CLI check (Rule S1)

```
$ ember relate --item 1 --db <single-item fixture>    # universe empty after the Phase 1 filter
{"phase": 2, "pool_size": 0, "signals": {"dense": 0, "graph": 0, "metadata": 0}}
(exit 0; no embedder load, no AI call, nothing on STDERR — byte-identical to the §5 capture)
```

Full-run summary via the existing CLI-test patching route (`_patch_phase2_ports` + `_patch_phase34_ports`, `test_relate_cli.py:304-305`), `y` on one proposal:

```
accepted: 1, rejected: 0, skipped: 0, aborted: false
(exit 0; the accepted link's YAML block unchanged)
```

Both outputs byte-identical to the pre-amendment build (§5 capture plus the existing exact-string asserts).

## 7. Rollback

No rollback — the step writes no rows. Pure in-memory restructure: no migration, no schema, no cache-write change, no DB touch. Code undo: drop the commits.

## 8. Step invariant

After this step: the module runs, every pre-existing relate test passes unmodified, the new tests are green, and the full suite is green with real numbers recorded in Build Notes.

## 9. Build Notes

Built 2026-10-29 on `feat/hardening`. Zero deviations from the §12 pin.

- **What landed vs §3.** `ember/relate/candidate_pool.py` gained `class Signals(BaseModel)` above `build_candidate_pool`, exactly the three pinned fields (`content: dict[int, float]`, `graph: set[int]`, `metadata: set[int]`). The class docstring states the boundary: built at Phase 2 inside `build_candidate_pool`, single consumer `_merge` plus the `counts` dict. One new import (`from pydantic import BaseModel`, same base as `Pool`). `build_candidate_pool` builds `Signals(content=content, graph=graph, metadata=metadata)` right after the three signal calls, passes it as `_merge(items, signals)` (private helper, signature free to change per §3), and derives `counts` from `len()` of the wrapper's fields under the frozen keys `dense`/`graph`/`metadata` (§12 naming trap kept). The empty-universe early return stays unchanged and before all of this, no `Signals` is built there. Every other helper body is untouched. No `rows.py`, `errors.py`, `cli.py`, adapter, or port edit.
- **TDD red first.** `test_signals_holds_exactly_three_fields` failed with `ImportError: cannot import name 'Signals'` before the code landed, then went green. The architecture test is a guard, green from birth (nothing outside `candidate_pool.py` named `Signals` before or after). The CLI byte test pins the capture so it was green before the code by construction.
- **Capture-first proof.** Commit `a3b2090` stores `tests/fixtures/relate/empty_pool_golden.json`, captured through `CliRunner` on a single-item temp DB (source 1, item 1, `relate --item 1`) from the pre-wrapper tree (base commit `a9a5b06`). Captured stdout: `{"phase": 2, "pool_size": 0, "signals": {"dense": 0, "graph": 0, "metadata": 0}}\n`, stderr empty, exit 0. The wrapper code plus the two red-first tests land in the second commit of this pair (hash in the ticket reply).
- **Suite numbers (real).** Before: `742 passed, 4 deselected in 3.83s`. After: `745 passed, 4 deselected in 3.46s` (the +3 are exactly the three owned tests). The `tests/relate` tree after: `206 passed`.
- **§6 CLI check (real).** Real binary `.venv/bin/ember relate --item 1 --db <single-item temp DB>`: exit 0, stderr 0 bytes, stdout byte-identical to the golden (`byte identical: True`). Full-run summary via the existing `_patch_phase2_ports` plus `_patch_phase34_ports` route on the six-item seed: exit 0, three `link_id` blocks, `accepted: 3, rejected: 0, skipped: 0, aborted: false`. §6 quotes `accepted: 1` as an example, the repo's own exact-string pin in `test_relate_item_runs_phases_3_and_4` has always been `accepted: 3`, and that assert passed untouched.
- **Accept-list proof.** `git diff --numstat a9a5b06..HEAD -- tests/`: additions only. The single removed line in the whole diff is the one-line import in `test_candidate_pool_unit.py`, widened to also import `Signals` for the new test. Zero existing test functions modified or deleted. All 34 unit functions, all 4 integration tests, the CLI file, and `test_relate_core_does_not_import_adapters` passed unmodified. The stop clause stayed unused.
- **Deviation from §5's capture note (not from the pin).** §5 said the empty-pool capture needs no fakes, and indeed the path never loads a model and never calls the AI. But `ember/cli.py:285` builds `build_link_proposer(os.environ)` before the empty check and the real builder raises RELATE-035 without a key. Capture and test both set a dummy `EMBER_AI_API_KEY` so the real builder constructs its client offline. No port is replaced by a fake in either run.
- **Environment note.** No linter is installed in `.venv` (no ruff, flake8, or mypy), so the syntax check was `python -m compileall` on the changed module (clean) plus the suite. New code and test prose contain no em dashes and no semicolons.
- **Rollback (§7).** Drop the two commits. No rows were written.

## 10. Issue closure

- **Closes #8** via ticket 10 (`Signals` wrapper, decision: build, 2026-10-29) — comment with the §6 evidence and the §5 accept list.
- **#18 left alone** — plain-text export stays with its separate utility plan; this step does not absorb it.

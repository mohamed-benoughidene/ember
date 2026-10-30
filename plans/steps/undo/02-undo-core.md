# L3 Undo Step 2: the pure undo core

Status: DRAFT 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.2, §5.3. Phase: derive. Needs step 01 done.

## Constitution rules this step enforces
T1 (pure, no I/O, no clock), T9 (imports no adapter), B1/B5, I1, I3 (snapshot wrapper), I4, I5, I11/I21, D3 (pointer is a marker row).

## Deferred settings resolved by this step
None.

## 1. Boundary shapes (cite L2 §5.3)
- In: `UndoSnapshot { groups: list[LedgerGroup], items: list[ItemState], links: list[Link] }`. `LedgerGroup { group_id, rows: list[ChangeLogEntry] }`. Built in Phase 1 by a new lookup read `list_grouped_ledger()` (port `MaintainLookupPort` grows by this one read; it returns only rows with a non-NULL `group_id`).
- Out: `UndoPlan { source_group_id, direction: "undo"|"redo", changes: list[InverseChange], marker: MarkerRow }`. `InverseChange` is a named model (never a tuple, I4) with the target (item or link), the expected current value, the value to write, and the ledger row to append.
- Functions (names at implementer's discretion, contract fixed): `derive_undo(snapshot)`, `derive_redo(snapshot)`, both pure.

## 2. Tests (unit, fakes only, tests/maintain/test_undo_core_unit.py)
One test per spec 12.2 row: close (+ dependents), set-status (Challenged→Active with shield, Active→Challenged), set-validated, clear-validated, edit-item (rationale and source), remove-link, reverse-supersedes. Plus: stack order (undo twice steps back); redo only after undo; a new original action clears redo; refusal for each kind of mismatch with the right entity ids; sweep re-arm between clear and undo refuses; unknown row shape raises `MAINTAIN-027`; pre-013 rows (no group) are invisible and `MAINTAIN-023` says so.

## 3. CLI check (S1)
None yet: the core has no command until step 04. Standalone check: `pytest tests/maintain/test_undo_core_unit.py -q` passes in isolation (S2) with the real count shown.

## 4. Error codes raised
MAINTAIN-023, 024, 025, 027 (L2 §6).

## 5. Rollback
No rollback needed: pure code, writes nothing. Revert the commit.

## 6. Done when
New unit file passes; `tests/test_architecture.py` still passes (core imports no adapter).

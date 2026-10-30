# L3 Undo Step 3: the atomic store write and the replay amendment

Status: DRAFT 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.4, §5.5. Phase: apply. Needs steps 01 and 02.
**RISK step (AGENTS.md §2):** amends two written design rules (confirmed by the maintainer 2026-10-30) and writes `links.status` upward for the first time.

## Constitution rules this step enforces
D1 (append only), D2 (`reversed_at` rebuildable), D6, P4 (DB behind the port), T2/T3, I5, I7, I17/I18/I19.

## Deferred settings resolved by this step
- Whether the `links` triggers fire on a `Rejected -> Confirmed` UPDATE. Contract: the builder tests it on a real v13 DB first. If a trigger blocks it, stop and report; do not weaken a trigger.

## 1. Boundary shapes (cite L2 §5.4, §5.5)
- `MaintainStorePort.apply_undo(plan: UndoPlan) -> int`: ONE transaction, ONE clock read; item/link UPDATEs, inverse `change_log` rows stamped with the new group id, the marker row. Returns the number of rows changed. Raises `MAINTAIN-026` (UPDATE) or `MAINTAIN-012` (ledger INSERT); either rolls everything back.
- `replay_reversals`: highest-id `link_reversed` marker per link wins; `new_value == 'Reversed'` → its timestamp, else `None`. Existing callers and tests keep passing; two new cases added.
- Record the rule 7 amendments (spec 12.3 rules 1 and 2) in `plans/engine-maintain-plan.md` §12 and the `apply_remove_link` docstring ("never flip back" gets "except as an undo, step 03").

## 2. Tests
- Real temp DB: undo then redo for each undoable action returns the exact prior state (items, links, `reversed_at`, `status_origin`); ledger row count only grows.
- Delegating-connection injection: UPDATE failure → `MAINTAIN-026` and zero rows changed; INSERT failure → `MAINTAIN-012` and zero rows changed.
- Replay: reversal, undo of reversal → `None`, redo → timestamp. `check_database` reports OK for all three.
- Shield: after undo of a clear, `status_origin='manual'`; the next sweep behaves as before the clear (compare sweep output with a control DB).
- Relate interplay: a removed link restored by undo is `Confirmed`; relate rules 8 and 9 see it as live again (one test using the real gatekeeper).

## 3. CLI check (S1)
Python-level, no command yet: `pytest tests/maintain/test_undo_store_integration.py -q`.

## 4. Error codes raised
MAINTAIN-026, MAINTAIN-012 (reused).

## 5. Rollback
Revert the commit. Data written by a real undo is ordinary ledger rows plus restored item/link values; to reverse one in practice, run `ember redo`.

## 6. Done when
Integration suite passes with real counts; `ember db-check` exit 0 on a DB after every undo kind.

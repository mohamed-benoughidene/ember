# L3 Undo Step 3: the atomic store write and the reader changes

Status: DRAFT 2, 2026-10-30. Parent: `plans/engine-undo-plan.md` §5.4, §5.5. Phase: apply. Needs steps 01 and 02.
**RISK step (AGENTS.md §2):** amends written rules (confirmed by the maintainer 2026-10-30), writes `links.status` upward for the first time, and changes what two existing readers mean.

## Constitution rules this step enforces
D1 (append only), D2 (`reversed_at` rebuildable), D5/I10 (a NEW marker field, no old meaning changed), D6, P4 (DB behind the port), T2/T3, I5, I7, I17/I18/I19, B2 (the one cross-module write is declared and tested).

## Deferred settings resolved by this step
- None left open: migration 011 triggers were read on 2026-10-30. An UPDATE of `links.status` is not blocked; the builder still proves it on a real v13 DB in the first test (if it fails, stop and report, never weaken a trigger).

## 1. Boundary shapes (cite L2 §5.4, §5.5)
- `MaintainStorePort.apply_inverse_group(plan: UndoResult) -> int`: ONE transaction, ONE clock read; item/link UPDATEs (a redo of a close sets `status` and `close_reason` in one UPDATE), inverse `change_log` rows stamped with the new group id, the marker row. Raises `MAINTAIN-026` (UPDATE) or `MAINTAIN-012` (INSERT); either rolls back everything.
- **Reversal readers (both, one rule):** a link is reversed when its highest-id marker among `link_reversed` and `link_unreversed` is `link_reversed`. Apply in `replay_reversals` (`ember/adapters/link_replay.py`) AND `SqliteMaintainContext.list_reversed_link_ids` (feeds `derive.py`). Without the second change the sweep keeps skipping an un-reversed link.
- **Shield readers (both):** a clear is `status_origin` with `new_value='manual'` and cause `user_set_status` OR `user_redo`: `derive._latest_clear` and `SqliteMaintainContext.list_shield_log`.
- Record the rule amendments in `plans/engine-maintain-plan.md` §1 and §12 and in the `apply_remove_link` docstring ("never flip back" gains "except as an undo").
- Existing tests are not edited: `tests/test_link_replay.py` builds markers with `new_value=None` and still sees them as reversed.

## 2. Tests
- Real temp DB: undo then redo for each undoable action returns the exact prior state (items, links, `reversed_at`, `status_origin`); ledger row count only grows.
- Delegating-connection injection: UPDATE failure -> `MAINTAIN-026`, zero rows changed; INSERT failure -> `MAINTAIN-012`, zero rows changed.
- **Reverse -> undo -> sweep:** the sweep treats the link as live again. Reverse again by redo: skipped again.
- **Shield:** clear -> undo: status back to `Challenged`, origin back to the recorded OLD value (normally `derived`). Clear -> undo -> relate confirms a new link -> redo -> sweep: the item stays shielded (the redo is a clear).
- `check_database` reports OK after each case. One test: undo of `validated` writes `items.validated` (the declared B2 exception).
- Relate interplay: a removed link restored by undo is `Confirmed`; relate rules 8 and 9 see it live (real gatekeeper).

## 3. Standalone check (S1; no CLI yet)
```
$ python -m pytest tests/maintain/test_undo_store_integration.py -q   -> "N passed", real N shown
```

## 4. Error codes raised (L2 §6)
MAINTAIN-026, MAINTAIN-012 (reused).

## 5. Rollback
Revert the commit. Data written by a real undo is ordinary ledger rows plus restored values; to reverse one in practice run `ember redo`.

## 6. Done when
Integration suite passes with real counts; `ember db-check` exit 0 after every undo kind; `tests/test_link_replay.py` unchanged and green.

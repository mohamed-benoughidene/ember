# Planning Framework

Terse AI caveman style. Single source truth for plan structure.

Goal: break work into small, testable, standalone chunks. Never code without plan.

---

## 1. Plan Hierarchy (3 Levels)

```
Level 1: System Master Plan
  └── Level 2: Engine Master Plan (x4: Capture, Relate, Maintain, Query)
        └── Level 3: Step Plans (per pipeline phase)
```

### Level 1: System Master Plan (L1)
- Scope: whole system. 4 engines. Data flow between engines.
- Length: 1 to 2 pages (~100-150 lines).
- Contents:
  - 4 engine definitions (job, boundary).
  - Inter-engine data contracts (what Engine A hands Engine B).
  - Shared storage rules (SQLite DB, ledger, foreign keys).
  - Global invariants (no direct DB write by AI, immutable history).
- Excluded: functions, files, algorithms, internal steps.
- Location: `plans/master-plan.md`.

### Level 2: Engine Master Plan (L2)
- Scope: single engine. One plan per engine.
- Length: 1 to 2 pages each.
- Contents:
  - Engine purpose (one job).
  - Standalone CLI interface (Rule S1: single command, sample input, inspectable output).
  - Internal pipeline sequence (Rule P3: phase 1 -> phase 2 -> phase N).
  - Data shape at each phase boundary (typed input/output).
  - Test targets and fake adapters (Rule T1-T4).
- Excluded: function code, internal helper logic.
- Location: `plans/engine-<name>-plan.md` (`capture`, `relate`, `maintain`, `query`).

### Level 3: Step Plan (L3)
- Scope: single phase inside single engine pipeline.
- Length: short, specific, actionable.
- Contents:
  - Exact file paths to create/edit.
  - Functions with strict type hints (input, output, errors raised) (Rule I1, I3).
  - Boundary test case with fixture (Rule T7).
  - CLI check command with expected result (Rule S1).
  - Rollback note: how undo step safely.
- Invariant: step finish -> module must still run, tests must pass.
- Location: `plans/steps/<engine>/step-<XX>-<name>.md`.

---

## 2. Invariants Across All Levels

1. **Top-down authoring**: L1 approved before any L2. L2 approved before child L3s.
2. **Bottom-up execution**: build L3 step-by-step. Engine works standalone before wiring to next engine.
3. **Run alone rule**: each level must define inspectable artifact (doc or running CLI).
4. **Data contracts explicit**: no step starts without input/output shape defined in parent plan.
5. **Phase testing gate**: step plan not marked done without passing test and CLI check.

---

## 3. Plan Review Gate

Before coding any step:
1. Agent write step plan.
2. Human approve.
3. Code written.
4. Test run, CLI check run. Numbers shown.
5. `PROJECT_MAP.md` updated.
6. Next step plan start.

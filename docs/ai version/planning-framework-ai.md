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
- Included: stack decisions (language, libraries, env var names, model names), test strategy, global invariants. L1 is the right place to lock the stack because L2 and L3 inherit it.
- Location: `plans/master-plan.md`.

### Level 2: Engine Master Plan (L2)
- Scope: single engine. One plan per engine.
- Length: 1 to 4 pages, ~100-500 lines. Longer is acceptable when the engine has stable error codes (e.g. 30+), multiple migrations (e.g. 3+), or more than 3 new ports. If a plan exceeds 300 lines, consider an appendix split: §A migrations, §B error codes, §C port catalog — keep the prose design section short.
- Contents:
  - Engine purpose (one job).
  - Standalone CLI interface (Rule S1: single command, sample input, inspectable output).
  - Internal pipeline sequence (Rule P3: phase 1 -> phase 2 -> phase N).
  - Data shape at each phase boundary (typed input/output).
  - Test targets and fake adapters (Rule T1-T4).
  - Deferred to L3 section: list every L1-deferred item this L2 did not resolve, plus any new settings L3 must pick. L3 step plans that resolve these items open with a "Deferred settings resolved by this step" subsection. Deferred items that survive to V1 build complete become GitHub issues labeled `deferred`.
- Excluded: function code, internal helper logic.
- Location: `plans/engine-<name>-plan.md` (`capture`, `relate`, `maintain`, `query`).

### Level 3: Step Plan (L3)
- Scope: single phase inside single engine pipeline.
- Length: short, specific, actionable.
- Contents:
  - Exact port names + boundary shapes (cite the L2 §X that defines the port).
  - Test targets: integration test on real DB at the phase boundary; for AI parser steps, named fixture files under `tests/fixtures/`.
  - CLI check command with expected result (Rule S1): `ember <cmd> --<flag> ...` and the expected output / exit code.
  - List of error codes this step raises (codes only, not prose), cross-referenced to L2 §X.
  - Module file paths and function signatures are at the implementer's discretion, constrained by the L2 port contracts. The L3 plan is a contract, not an implementation hint.
  - Rollback: state "No rollback — append-only by L1 §4 rule 7" for steps that write immutable rows, or describe the reversal procedure for steps that don't.
  - Build Notes (optional, post-implementation): a §Y "Build Notes" section may be added AFTER the code is written, recording what actually happened, what tests passed, what deferred items got resolved, and any Constitution alignment pass. This is an audit trail, not a planning input.
- Invariant: step finish -> module must still run, tests must pass.
- Location: `plans/steps/<engine>/step-<XX>-<name>.md`.

---

## 2. Invariants Across All Levels

1. **Top-down authoring**: L1 approved before any L2. L2 approved before child L3s. Approval can be in-memory; git commit of a plan is separate from approval. Multiple L2 plans may be approved before any of their L3 step plans start. Bottom-up execution of engines is preferred over parallel.
2. **Bottom-up execution**: build L3 step-by-step. Engine works standalone before wiring to next engine.
3. **Run alone rule**: each level must define inspectable artifact (doc or running CLI).
4. **Data contracts explicit**: no step starts without input/output shape defined in parent plan.
5. **Phase testing gate**: step plan not marked done without passing test and CLI check.
6. **Constitution cross-reference**: every L2 plan ends with a "§Z Constitution compliance" section listing every Constitution rule (B/D/I/P/S/T families) the plan touches. Every L3 step plan opens with a "Constitution rules this step enforces" subsection. Constitution compliance is systematic, not accidental.

---

## 3. Plan Review Gate

Before coding any step:

1. **Dispatch sub-agents in parallel.** The "agent" in this gate is a coordinator, not a single author. Dispatch 2-6 sub-agents in parallel for: spec-compliance review (does the plan match L1 + L2 contracts?), Constitution-alignment review (which rules does it touch?), error-code audit (every error path has a code?), over-engineering audit (is the plan doing more than it needs to?), and any engine-specific concern. Each sub-agent returns findings; the coordinator integrates them.

2. **Coordinator integrates findings into one plan.** Present the integrated plan to the human with a `Done / Checked / Not checked / Could break / Decision needed` summary (per AGENTS.md).

3. **Human reviews and signals clean or requests changes.** The human is a reviewer, not the author. The human may request fixes; the coordinator applies them; loop on 1-3.

4. **Loop on 1-3 until human signals clean.** Budget 2-4 cycles per plan. Iteration is normal; "approve first try" is the exception, not the rule.

5. **Code written.** Step-by-step per L3 plan. Each L3 step commits separately.

6. **Test run, CLI check run. Numbers shown.** Pass/fail, line counts, exit codes. Real numbers, not "should work."

7. **`PROJECT_MAP.md` updated.** Can be batched at milestone end, but must happen before the L2 plan that introduced the files is marked complete.

8. **Next step plan starts.**

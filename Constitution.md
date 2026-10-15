# Constitution

Goal: System built from standalone modules. Each module run alone. Build piece by piece, test alone, connect.

## Principle 1: Module Boundaries
Split code. Change one part, no break other parts.

Rules:
- B1. One module, one job. All inside serve that job.
- B2. Public calls only. Never reach into internal variables, file formats, or DB tables of other module.
- B3. Depend on stable things. Business logic never depend on volatile external tools (AI provider, DB). Tools depend on logic shape.
- B4. Hide volatile decision. Module hide nothing -> module should not exist.
- B5. Deep module beat shallow. Small interface, large inside work. No split into many tiny chained pieces.
- B6. Warning signs: circular import, growing utils/helpers file, multi-file edits for single change, feared module, long import list, passing same 6 variables through 4 functions. Fix boundary immediately.

## Principle 2: Data Modeling
Rules:
- D1. Raw data immutable. Store original input and external response untouched.
- D2. Derived data rebuildable from raw data. Bug fix -> rerun step on raw input.
- D3. Single source of truth. One fact, one place. Reference by ID. Copy allowed only for speed if labeled derived and rebuildable.
- D4. Outside data untrusted (files, APIs, AI output, user input). Validate once at boundary, trust inside.
- D5. Prefer new optional fields over renames. Renames break legacy data.
- D6. Schema migrations: numbered scripts in repo. Store schema version number.
- D7. Production data manual edits forbidden without backup.
- D8. AI projects: save raw model response verbatim.

## Principle 3: Core Patterns
Rules:
- P1. Pattern must solve concrete project problem. No decorative architecture.
- P2. Layered: top talk only to immediate bottom (UI -> logic -> data). Use for standard app. Avoid for one-way flows. Never add passthrough-only layer.
- P3. Pipeline: data flow through fixed sequence of steps (input -> transform -> output). Use for documents, data transforms, AI pipelines. Avoid if bidirectional chatter needed. No hidden shared state.
- P4. Ports & Adapters: core define small interface (port); adapter fit external tool (AI, DB, disk). Use for slow, volatile, expensive, or unreliable tools. Skip for simple scripts.

## Principle 4: Interfaces
Rules:
- I1. Name function by job, not mechanism. Strict type hints for input and output.
- I2. No boolean behavior flags. Split into two functions.
- I3. Maximum 4 inputs per function. More -> function too broad or inputs need object wrapper.
- I4. Consistent return type. Empty list instead of None. Named object instead of tuple.
- I5. Split failure modes: expected failure (missing file, timeout) get explicit named error; code bugs crash loudly.
- I6. Custom error hierarchy with single project base error.
- I7. Fail fast. Validate inputs at start. Never swallow error (`bare except: pass` banned). Add context. Handle at edge (CLI, web), not core.
- I8. Design error away when possible (e.g., delete non-existent resource = success).
- I9. Validate at edge, trust inside core.
- I10. Stable interface contract. Add optional field safe; remove/rename break callers. Mark private code with leading underscore.
- I11. Public function contract doc: input, output, raised errors, side effects. Mismatch = bug.
- I12. CLI: explicit flags (`--output file.md`), exit code 0 success, non-zero fail, stdout data, stderr errors.
- I13. Config: load once at boot, validate, pass down. Fail fast at startup if missing.
- I14. Web API: clear resource nouns (`/contracts/123/clauses`), standard HTTP status codes, idempotent write operations, version path (`/v1/`).
- I15. External services: enforce timeout, retry limit with backoff, hide behind port interface.
- I16. AI calls: structured output schema validation, log raw response.
- I17. Error codes: stable code + name (e.g. `SPLIT-002 UnreadablePdf`). Never reuse.
- I18. Module and function name injected into error automatically, never hardcoded string.
- I19. Error must carry target entity IDs (contract ID, clause ID). Zero secrets in errors.
- I20. One line error logging: code, module.function, entity IDs.
- I21. Function contract note list error codes. Tests assert error code, not message prose.

## Principle 5: Testability
Rules:
- T1. Pure core: deterministic input -> output. Zero I/O, disk, network, clock, or UI in core logic.
- T2. Push side effects to thin edge adapters. Inject dependencies (DB, clock, clients).
- T3. Prefer fakes (working stand-ins) over mocks (call-recording stand-ins).
- T4. Test pyramid: many unit tests on pure core, few integration tests with real SQLite temp file, 1-2 E2E tests with fake outside tools.
- T5. Test boundaries and observable behavior, not internal implementation details.
- T6. Good targets: contract promises, edge cases, expected error codes, regression bugs. Poor targets: private helpers, call counts, pure glue code.
- T7. AI testing: test parser/validation/retries with saved fixtures. Assert output schema/types, never exact prose words.
- T8. AI evaluation: small benchmark set with known answers run periodically to measure drift/quality.
- T9. Architecture tests: assert core never imports adapters. Run in CI.
- T10. Painful test setup = design smell. Fix architecture, do not bloat test harness.

## Principle 6: Standalone Modules
Rules:
- S1. Module must run alone via single CLI command on sample input, produce inspectable output.
- S2. Module has dedicated test suite runnable in isolation.
- S3. Module explicitly document input shape and output shape.
- S4. Modules define explicit data transfer mechanism (files, calls, API) and document choice.

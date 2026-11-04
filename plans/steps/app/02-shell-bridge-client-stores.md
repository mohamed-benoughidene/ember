# L3 App Step 2: shell, bridge client, settings and key stores

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-app-plan.md` §4, §5.1, §5.3, §5.4. Needs step 01 passed (A) and the bridge L2 built.
**RISK step (AGENTS.md §2):** adds packages (Electron and dev tools). Show exact names, versions and the changelog check, and ask A or B, before `npm install`.

## Constitution rules this step enforces
P2, P4 (stores and bridge client are adapters with fakes), B2, D4 (validate child output once), D5/D6 (settings schema versioned), I5-I7, I13, I15 (timeouts, retry limit), I17-I20, T1-T3, T9.

## Deferred settings resolved by this step
- Exact Electron version and package list (L2 §9), checked against each package's changelog.
- Where the app finds the bundled `ember` (the method chosen in step 01).
- Key storage backend (L2 §3 decision 4) and the test packages (decision 7): confirmed here with exact names and versions.

## 1. Boundary shapes (cite L2 §5.1, §5.3, §5.4, §6)
- `runCommand(name, args)` and `runConfirmSession(name, args)` exactly as L2 §5.1. The error-line parser comes from `app/shared/`, and is the SAME regexp pinned by `tests/bridge/test_error_line_contract.py` (copy the pattern into a shared fixture file read by both test suites so they cannot drift).
- Settings store: `load() -> Settings`, `save(patch) -> Settings`; schema number 1; atomic write.
- Key store: `get() -> string | null`, `set(key)`, `remove()`; session-only fallback; the value never leaves the main process except into the child's environment.
- Preload list: the named calls only. A node test asserts the renderer cannot reach `fs`, `child_process`.
- An empty window that shows "Ember is starting", then the result of one read command (the knowledge base item count) — the smallest end-to-end proof.

## 2. Tests
- Unit: error-line parser table; event-line parser (garbage lines → `APP-002`); settings round trip, corrupt file → defaults + `APP-004`; key store fake paths.
- Contract: bridge client against a temp knowledge base made by the Python test helpers: item count equals `ember list-items` total.
- Timeout: a hung fake child is killed at the limit and returns `APP-008` (never `APP-001`/`APP-002`). A hung READ retries once; a hung WRITE never retries and the app re-reads state before offering Retry (L2 §5.1).
- Walking skeleton: if platform decision 2 = B, the three-system launch check (build, open a temp knowledge base, run one read command, print `items: N`) is added to CI in THIS step instead of waiting for step 13.

## 3. Check commands (S1)
```
$ npm --prefix app test                -> all pass, real count shown
$ npm --prefix app run check:launch    -> window starts, shows the item count, exits 0 (headless where available)
```

## 4. Error codes raised
APP-001, 002, 003, 004, 006, 007, 008 (L2 §6).

## 5. Rollback
Revert the commit; remove `app/`. No Python or data change.

## 6. Done when
Tests and launch check pass with real numbers; A/B on packages recorded; `PROJECT_MAP.md` lines drafted.

# L3 Bridge Step 4: contract suite and closeout

Status: DRAFT 2, 2026-10-30. Parent: `plans/interface-bridge-plan.md` §7. Phase: closeout. Needs steps 01 to 03.

## Constitution rules this step enforces
S1, S2, S3, T4, T9 (architecture test extended), I17 (codes never reused), D3.

## Deferred settings resolved by this step
None.

## 1. Boundary shapes
- `tests/bridge/test_contract_table.py`: a table with one row per command (22 at close of this L2). Columns: command name, a sample argument list, JSON top-level keys, whether `--format` and `--confirm` apply, exit codes. A test lists `main.commands` and fails if a command has no row or a row names a missing command.
- `tests/bridge/test_error_line_contract.py`: for one real error per code family, plus one case whose value contains a newline and a `|`, the FIRST stderr line matches the pattern of L2 §5.2 (`\Aerror: (?P<code>[A-Z]+-\d{3}) (?P<name>\w+) \| (?P<where>[^|\n]+) \| (?P<rest>.*)\Z`, `re.S`). The pattern is stored in one fixture file that the app tests also read.
- `tests/test_architecture.py`: new `test_bridge_core_does_not_import_adapters` over `ember/bridge/*.py` (forbidden tokens as for the other cores). The directories there are listed by hand, so the new package is NOT covered until this test is added.
- `docs/commands.md`: new section "Machine use" (the `--format`, `--confirm`, event lines, stdin answers, error-line shape). `README.md` and `GLOSSARY.md` touched only where a new command or word appears.

## 2. Tests
The three files above plus the full suite.

## 3. CLI check (S1)
```
$ python -m pytest tests/bridge -q    -> all pass, real count shown
$ ember --help                        -> lists 22 commands
```

## 4. Error codes raised
None new.

## 5. Rollback
Revert the commit. Tests and docs only.

## 6. Closeout (before the L2 is marked complete)
`PROJECT_MAP.md`: one line per tracked file (the test suite fails otherwise), including every `__init__.py`, every fixture (the "before" goldens, the shared error-pattern fixture), `ember/adapters/json_confirm.py` and every file under `ember/bridge/` and `tests/bridge/`; Build Notes added to steps 01 to 04; the full suite count recorded; `tests/test_docs_in_sync.py` green.

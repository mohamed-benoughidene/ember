# L3 Query Step 1: Load + Current State (Phases 1+3+4 for mode 1, plus the full read seam)

Implements L2 Query plan §3 (boot), §4.5 (port + models), §4.7 (gatekeeper, orchestration), §4 Phase 3 (render), §5 (CLI) for `current_state`, plus L2 §10 step-01 deliverables. Ships the whole read seam — the full `QueryLookupPort`, all six error codes, and every row model — so steps 02 and 03 consume it without amending the L2.

## 0. Constitution rules this step enforces

- **B1** — one job per module: `errors`, `rows`, `lookup`, `tokenize`, `query_gatekeeper`, `current_state` (pure core), `render`, `run_query` are separate files.
- **B2** — the core reads `items` / `links` / `change_log` only through `QueryLookupPort` (L2 §4.5); no direct table access.
- **B3** — the core depends on the port and on Pydantic row models, never on SQLite.
- **B5** — one deep port (`QueryLookupPort`, all four methods from day one) so steps 02–03 never churn the seam.
- **B6** — per L2 §Z(c): the adapter grows a 4th context class (`SqliteQueryContext`) + boot pair inside `ember/adapters/sqlite.py`; the file is not split.
- **D1** — the engine writes nothing, not even at boot (L2 §2.6): read-only open, no `_apply_migrations`.
- **I2** — the mode is the entry point: `run_current_state` exists; no `run_query(mode=...)` and no boolean flag.
- **I4** — every return is a named Pydantic model or a list of them; empty result is an empty list.
- **I6** — all codes subclass `QueryError(EmberError)` (L2 §6).
- **I9** — the gatekeeper owns QUERY-001/002; the pure core never re-raises them.
- **I12** — the CLI contract: flags, 0/1/2 exits, JSON on stdout.
- **I17 / I21** — stable codes 000–005; tests assert the code, not the message.
- **I18** — no `__init__` on any error subclass; `EmberError._caller_location()` injects raising site for free.
- **I20** — errors reach stderr as one line: `error: {exc.log_line()}`.
- **P3 / P4** — Load → Derive (pure) → Render → CLI; `QueryLookupPort` is the port, `SqliteQueryContext` the adapter.
- **S1 / S3** — CLI check in §7; input/output shapes in §2/§3.
- **T1 / T2 / T3 / T9** — the core is pure (no I/O, no clock); `FakeQueryLookup` ships here (§4.11); architecture test ships with this step (first `ember/query/` modules land here).

## 1. Job

Open the user's database read-only and refuse instead of migrate; read the `items` table through the port; keep `Active` + `Challenged` rows; render one JSON document with `Challenged` first. After this step, `ember current-state --db <path>` works end to end.

## 2. Inputs

From the CLI:
- `--db PATH` (default: `DEFAULT_DB_PATH` in `ember/cli.py`, used directly — no module imports it from `ember.cli`, per L2 §5 B6 warning).

Boot, per L2 §3 (`open_query_database(db_path)` in `ember/adapters/sqlite.py`):
1. missing file → `QUERY-003`, message `db file missing`, context `db_path`; the file is never created (`open_database` is NOT used).
2. `sqlite3.connect(f"file:{urllib.parse.quote(str(db_path))}?mode=ro", uri=True)` — **`uri=True` is part of the contract**; the path is quoted (SQLite parses `?`, `#`, `%` as URI syntax).
3. Probe `SELECT COUNT(*) FROM sqlite_master` inside the try — makes "file is not a database" land on `QUERY-003`.
4. `ensure_query_schema(conn)`: `SELECT version FROM schema_version`; read failure → `QUERY-003` (`schema version read fail`); `version < 10` → `QUERY-004` (`version`, `required=10`). **Never migrates** (L2 §2.6).
5. `PRAGMA foreign_keys = ON`.

Known limitation (recorded, L2 §3): a hot journal cannot be rolled back read-only → `QUERY-003`; the message tells the user to run another `ember` command once.

From the port (`QueryLookupPort`, L2 §4.5, `ember/query/lookup.py`) — **all four methods land in this step**:
- `list_items() -> list[QueryItem]` — every item, `ORDER BY id`: `id, type, statement, status, close_reason, status_origin, rationale, created_at, source_id`.
- `list_links() -> list[Link]` — `Link` **imported** from `ember.relate.rows` (D3).
- `list_change_log() -> list[ChangeRow]` — `id, item_id, link_id, field_changed, old_value, new_value, timestamp, trigger_cause`; `ChangeRow` is the nullable-`item_id` **read** model (L2 §4.5; §Z(c) D3).
- `item_exists(item_id: int) -> bool` — house precedent: `LinkLookupPort.item_exists`.

Each read raises `QUERY-005` on failure.

## 3. Outputs

Row models (`ember/query/rows.py`, L2 §4.5):
- `QueryItem(id, type, statement, status, close_reason, status_origin, rationale, created_at, source_id)` — the input row.
- `CurrentStateRow(id, type, statement, status, created_at, source_id, status_origin, challenged)` — the output projection; `challenged` is the explicit warning flag (AI spec 3.8:137). `close_reason` / `rationale` do **not** leak.

Envelope (L2 §4 Phase 3): `{"mode": "current_state", "count": N, "items": [CurrentStateRow, …]}` — each row's keys are exactly its model's fields, in field order. `run_current_state(lookup) -> str` returns the rendered JSON; the CLI echoes it (maintain/relate house shape).

## 4. Steps

1. `ember/query/errors.py`: `QueryError` (QUERY-000) + the five subclasses per L2 §6. **No `__init__`** on any subclass (I18 injection is free).
2. `ember/query/rows.py`: `QueryItem`, `CurrentStateRow`, `ChangeRow`; import `Link` from `ember.relate.rows`.
3. `ember/query/tokenize.py`: lowercase, split on runs of non-(unicode letter|digit) characters. No stemming, no stopword list. Shared with the gatekeeper (step 01) and the scorer (step 02). Its four unit tests land in §6 of this step, where the module lands.
4. `ember/query/lookup.py`: the `QueryLookupPort` ABC, four methods.
5. `ember/query/query_gatekeeper.py`: `validate_query_text(text) -> str` (pure; QUERY-002 if no tokens; carries `query_length`, never the text) and `validate_query_item(lookup, item_id)` (QUERY-001, context `item_id`, if missing). Both land now; QUERY-001's CLI exposure comes in steps 02–03.
6. `ember/adapters/sqlite.py`: `open_query_database` + `ensure_query_schema` + `SqliteQueryContext` per L2 §3; import alias `from ember.query.errors import DbOpenFailed as QueryDbOpenFailed` (house style, L2 §6).
7. `ember/query/current_state.py` (pure core): `current_state(items) -> list[CurrentStateRow]` — L2 §4 Phase 2's name; keep `status in ("Active", "Challenged")`; **no sorting here** (Phase 3 owns order); returns rows in input order. (`run_current_state` stays the orchestrator's name in step 9 — one name, one module.)
8. `ember/query/render.py` (pure): `json.dumps` only, no click/print. Sort: `(status_rank, id)` with Challenged→0, Active→1; build the envelope.
9. `ember/query/run_query.py`: `run_current_state(lookup) -> str` — gatekeeper not needed for this mode (no text, no item); load → derive → render.
10. `ember/cli.py`: `ember current-state [--db PATH]`, flat on the root group; exit 0 on success (empty result included), 1 on `QUERY-*`, 2 on Click usage errors; errors on stderr as `error: {exc.log_line()}`.
11. `tests/query/fakes.py`: `FakeQueryLookup` (in-memory port, L2 §10).
12. `tests/test_architecture.py`: `test_query_core_does_not_import_adapters` — glob `ember/query/*.py`, raw substring scan for `sqlite3`, `openai`, `anthropic`, `sentence_transformers`, `numpy`, `ember.adapters`. Docstring trap: core docstrings say *the storage adapter*, never a module path.

## 5. Errors (codes only, per L2 §6)

- `QUERY-000` — base, never raised. **L2 §6.**
- `QUERY-001` `QueryItemNotFound` — raised by `validate_query_item`; context `item_id` (code lands this step; CLI paths in steps 02–03). **L2 §6 / §4.7.**
- `QUERY-002` `QueryTextEmpty` — raised by `validate_query_text`; context `query_length`. **L2 §4.7.**
- `QUERY-003` `DbOpenFailed` — the file is missing, is not a readable SQLite database, the version read failed, or the database has a hot journal; context `db_path`. Raised by `open_query_database` (missing file, open fail, probe fail) and `ensure_query_schema` (version read fail). **L2 §3.**
- `QUERY-004` `SchemaOutdated` — `version < 10`; context `version`, `required`. **L2 §3.**
- `QUERY-005` `ItemsReadFailed` — any port read failure; context `table`. **L2 §4.5.**

All six exist after this step. No code is reused from another namespace (I17).

## 6. Test Targets

Unit (pure core + fakes, no DB):
- `current_state`: Active+Challenged kept, Closed dropped; `challenged` true/false; `close_reason`/`rationale` absent from the row; **output order equals a deliberately scrambled input order** (the real "core returns unsorted" contract).
- Gatekeeper: an **empty** query and a punctuation-only query each raise QUERY-002; a token-bearing query passes; missing id → QUERY-001; existing id passes; a valid request returns without touching the core.
- Tokenizer (the module this step ships): mixed case folds; punctuation splits; a unicode letter is a token character; digits are tokens.
- Renderer: Challenged first, then Active, each group by `item_id`, from scrambled input; JSON round-trips through `json.loads`; keys match the models; empty list is `count: 0`, not an error.
- Error codes: stable values; `name` equals the class name.

Integration (real temp DB, migrations 001–010 applied):
- Missing file → QUERY-003 and the file is **not created**; non-SQLite file → QUERY-003.
- A real v9 database → QUERY-004 with `version=9`, `required=10` — no monkeypatch needed; read-only never migrates.
- **DB file byte-identical before/after a query** (hash it) and a write attempt raises `sqlite3.OperationalError` — the read-only proof (L2 §7.2).
- Each port method on a seeded DB returns rows in `id` order with the right columns; a dropped-table read failure → QUERY-005.
- Mode end-to-end on one item per status: two rows, Closed omitted, Challenged first.

CLI (smoke, L2 §7.4):
- `ember current-state --db <fixture>` → exit 0, one JSON document, Challenged item first (assert via `json.loads`, not strings).
- `ember current-state --item abc` → exit 2 (Click usage error).
- stdout carries nothing but the JSON document.

## 7. CLI check (Rule S1)

`ember current-state --db tests/fixtures/query/current_state.db` → one JSON document, `{"mode": "current_state", "count": 2, "items": [...]}` with the Challenged item at `items[0]`, exit 0. (Fixture DB is a copy of a temp DB built by the integration tests; it is never written to.)

**As built:** no binary DB is committed — `*.db` is gitignored, so the check is run against a temp DB built by the same seed helpers (`tests/query/fakes.py`). See Build Notes below.

## 8. Out of Scope (this step)

- `topic_search` / `why` / `history` cores and commands (steps 02–03).
- The golden BM25 fixture (step 02); the change_log classifier (step 03).
- README / PROJECT_MAP updates and issue closures (step 03).
- Any write path, `--limit`, filters, pagination (L2 §8, step-02/03 deferred settings).

## 9. Next

Step 02 adds the BM25 scorer and the `why` traversal on top of this seam, plus the `ember topic-search` and `ember why` commands.

## 10. Deferred Settings (from L2 §9)

- None resolved here. Step 02 resolves §9 #1–#3 (BM25 constants, result cap, filters); step 03 resolves §9 #4–#5 (history limit, `unknown` kind).

## 11. Rollback

No rollback — Engine D writes no rows and ships no migration (L2 §2.6); the database is never touched. Undo of the code itself: drop the commits.

## 12. Build Notes (post-implementation)

Landed on `feat/query-engine`.

**Code**
- `ember/query/errors.py`: `QueryError` + the five subclasses (000–005), no `__init__` anywhere (I18).
- `ember/query/rows.py`: `QueryItem`, `CurrentStateRow`, `ChangeRow`; `Link` imported from `ember.relate.rows`.
- `ember/query/tokenize.py`: `tokenize(text) -> list[str]`, lowercase + `str.isalnum` split.
- `ember/query/lookup.py`: `QueryLookupPort` (4 methods).
- `ember/query/query_gatekeeper.py`: `validate_query_text` (QUERY-002, `query_length`), `validate_query_item` (QUERY-001, `item_id`).
- `ember/query/current_state.py`: `current_state(items) -> list[CurrentStateRow]`, input order preserved.
- `ember/query/render.py`: `render_current_state(rows) -> str`; sort `(challenged first, id)`.
- `ember/query/run_query.py`: `run_current_state(lookup) -> str`.
- `ember/adapters/sqlite.py`: `_connect_readonly` (URI `mode=ro`, quoted path, `uri=True`), `open_query_database` (no migration), `ensure_query_schema` (required 10), `SqliteQueryContext` (4 reads, `table=` context, `QUERY-005`).
- `ember/cli.py`: `ember current-state [--db PATH]`.

**Deviations recorded**
- **No fixture DB is committed.** Step §7 named `tests/fixtures/query/current_state.db`; `*.db` is gitignored in this repo, and a binary fixture adds nothing a seed helper does not. The CLI check ran against a temp DB built by the same helpers (`tests/query/fakes.py::make_v10` + `tests/fakes.py`). Revisit only if a human wants a hand-inspectable file in the repo.
- `ensure_query_schema`'s version-read failure raises QUERY-003 **without** `db_path` context: the function receives only the connection, and the house's `ensure_relate_schema` / `ensure_maintain_schema` do the same. The path *is* carried on the missing-file and open-fail paths.
- `validate_query_text` returns the **stripped** text (L2 §4.7 says "normalises the text"); the core tokenizes it anyway, so stripping is the whole normalisation.
- The `v9` integration test lowers `schema_version` after a real migration run, so the file is a genuine v10 database with a v9 stamp — the read-only boot refuses it for real, with no monkeypatch.

**Tests (49 new; suite 468 → 518 passed, 4 deselected, 3.02s)**
- `tests/query/test_current_state_unit.py` (5): status filter, `challenged` flag, no `close_reason`/`rationale` leak, **input order preserved**, empty input.
- `tests/query/test_query_gatekeeper_unit.py` (9): empty/blank/punctuation QUERY-002 (parametrized), `query_length` not the text, strip, no lookup on the text path, QUERY-001 + `item_id`, one lookup on the item path.
- `tests/query/test_render_unit.py` (3): Challenged-first from a scrambled list, JSON round-trip + key match, empty → `count: 0`.
- `tests/query/test_query_errors_unit.py` (18, parametrized ×3): codes/names stable, every class subclasses `QueryError`/`EmberError`, no subclass defines `__init__`.
- `tests/query/test_query_db_open.py` (11): missing file (not created), non-SQLite file, **real v9 → QUERY-004 with `version=9`/`required=10` and the version unchanged afterwards**, `ensure_query_schema` accepts 10, **DB byte-identical (sha256) across a query**, a write on the handle raises `sqlite3.OperationalError`, port reads ordered by id incl. the NULL-`item_id` row, and QUERY-005 for all four reads on a closed connection (parametrized).
- `tests/query/test_query_cli.py` (3): happy path Challenged-first, unknown flag → exit 2, stdout is JSON only.
- `tests/test_architecture.py`: `test_query_core_does_not_import_adapters` (the 4th arch test).

**Manual CLI check (real output)**
- `ember current-state --db <temp v10>` → `{"mode": "current_state", "count": 2, "items": [{... "id": 2, "status": "Challenged", "challenged": true}, {... "id": 1, "status": "Active", "challenged": false}]}`, exit 0.
- Same DB with `version = 9` → `error: QUERY-004 SchemaOutdated | ember.adapters.sqlite.ensure_query_schema | schema version too old | version=9 required=10`, exit 1.
- Missing file → `error: QUERY-003 DbOpenFailed | ember.adapters.sqlite.open_query_database | db file missing | db_path=…`, exit 1.

**Linter:** the repo has none configured (`.github/workflows/test.yml` runs `pytest` only), so there was nothing to run.

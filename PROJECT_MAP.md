# Project Map

This file lists every file and its purpose in the repository. Update it when files or folders are added or removed.

## Root Files
- `.gitignore`: Ignore rules for Python build files and local database files.
- `AGENTS.md`: Rules for AI coding agents working in this repository.
- `Constitution.md`: Core build rules for modules, data, interfaces and tests (AI caveman version).
- `Personal guidelines.md`: Rules for tone, accuracy and review style (AI caveman version).
- `PROJECT_MAP.md`: This file. Index of files and their purpose.
- `README.md`: Overview of the Ember project, its core purpose, and repository layout.
- `SECURITY.md`: Security vulnerability reporting instructions and policy.

## GitHub Config (`.github/`)
- `.github/workflows/test.yml`: CI job. Installs the package and runs pytest on push and pull requests (rule T9, architecture test included).
- `.github/CODEOWNERS`: Defines code and documentation ownership for pull requests.
- `.github/dependabot.yml`: Dependabot settings. Watches GitHub Actions versions each week.
- `.github/pull_request_template.md`: Default checklist and summary template for pull requests.
- `.github/ISSUE_TEMPLATE/bug_report.md`: Issue template for reporting bugs.
- `.github/ISSUE_TEMPLATE/feature_request.md`: Issue template for suggesting improvements.

## Documentation (`docs/`)
- `docs/brand-philosophy.md`: Brand meaning behind the name Ember, the logo, and the Lantern Keeper character.
- `docs/pain statment.md`: The problem the product solves, written as a pain statement.

### AI Versions (`docs/ai version/`)
- `docs/ai version/brand-philosophy-ai.md`: Brand philosophy, terse caveman style for AI readers.
- `docs/ai version/planning-framework-ai.md`: 3-level planning framework (L1 System, L2 Engine, L3 Step), terse caveman style for AI readers.
- `docs/ai version/project-context-system-v1-ai.md`: Project Context System V1 spec, terse caveman style for AI readers.

### Human Versions (`docs/humen version/`)
- `docs/humen version/brand-philosophy-humen.md`: Brand philosophy, plain English for human readers.
- `docs/humen version/Constitution-humen.md`: Core build rules, plain English for human readers.
- `docs/humen version/Personal guidelines-humen.md`: Tone, accuracy and review rules, plain English for human readers.
- `docs/humen version/project-context-system-v1-human.md`: Project Context System V1 spec, plain English for human readers.

### Diagrams and Examples (`docs/Graphs/`)
- `docs/Graphs/V1 Master Diagram Project Context Management System – Master diagram.html`: Visual diagram of the system architecture.
- `docs/Graphs/V1 Master Diagram Project Context Management System-1.pdf`: PDF export of the master diagram.
- `docs/Graphs/V1 Example Run the blue button story – Example run.html`: Worked example showing the system in use.
- `docs/Graphs/V1 Example Run the blue button story-4.pdf`: PDF export of the worked example.

## Active Brand Assets (`assets/`)
- `assets/logo.svg`: Main Ember logo, vertical format.
- `assets/logo-horizontal.svg`: Ember logo, horizontal format for wide spaces.
- `assets/icon.svg`: Small square Ember icon.

## Archived Assets (`archive/assets/`)
Earlier logo and character images, kept for history.
- `archive/assets/ChatGPT Image Oct 14, 2026, 09_11_14 PM.jpg`
- `archive/assets/Charred Ember Emblem Logo.png`
- `archive/assets/Ember_ Lantern Keeper Concept Sheet.png`
- `archive/assets/Ember Logo with Glowing Rock Icon.png`
- `archive/assets/Ember Preserve_ Illustrated Rockscape.png`
- `archive/assets/Ember Rock Logo on Cream Background.png`
- `archive/assets/Molten Ember Shard Emblem.png`

## Planning Documents (`plans/`)
- `plans/master-plan.md`: L1 System Master Plan. 4 engines (Capture, Relate, Maintain, Query), shared SQLite storage, global rules, test strategy, L1 §0 stack decisions.
- `plans/engine-capture-plan.md`: L2 Capture engine master plan. Pipeline phases 1-4 (source storage, AI proposal, gatekeeper, user confirm + write).
- `plans/engine-relate-plan.md`: L2 Relate engine master plan. Pipeline phases 1-4 (load + filter, candidate pool, AI proposal, confirm + write).
- `plans/steps/capture/01-source-storage.md`: L3 Step 1 plan. Phase 1, source dedup by content hash.
- `plans/steps/capture/02-ai-port-call.md`: L3 Step 2 plan. Phase 2, AI proposal via `ItemProposerPort`.
- `plans/steps/capture/03-user-confirm-write.md`: L3 Step 3 plan. Phases 3+4, gatekeeper + user confirm + write.
- `plans/steps/relate/01-load-and-filter.md`: L3 Relate Step 1 plan. Phase 1, load the item and filter type-compatible candidates.
- `plans/steps/relate/02-candidate-pool.md`: L3 Relate Step 2 plan. Phase 2, the 3 signals and merge.
- `plans/steps/relate/03-ai-propose-and-confirm-write.md`: L3 Relate Step 3 plan. Phases 3+4, AI proposal, confirm, and write.

## Python Implementation (`ember/`)
- `pyproject.toml`: Package metadata, locked stack deps (click, openai, pydantic; pytest is a dev dep), the optional `relate` extra (`sentence-transformers`), pytest config.
- `ember/__init__.py`: Package version.
- `ember/__main__.py`: Runs the CLI via `python -m ember`.
- `ember/cli.py`: Click CLI. `capture` runs the full 4-phase pipeline; `capture-source` is the Phase 1 standalone command; `relate` runs all 4 Relate phases (Phase 3 AI propose, Phase 3.5 raw-answer save, Phase 4 gatekeeper + confirm + atomic write) and defines `RelateTerminalConfirm` (raises the relate `UserAbort` on end of input); `set-validated` / `clear-validated` write the Assumption flag.
- `ember/errors.py`: Base `EmberError`. Carries a stable code and the raising module.function, no secrets.
- `ember/capture/__init__.py`: Marks the capture engine folder as a package.
- `ember/capture/errors.py`: Capture error codes `CAPTURE-001` to `CAPTURE-016`.
- `ember/capture/source_storage.py`: Phase 1 core. SHA-256 dedup behind `SourceStorePort`, returns `{source_id, raw_text, content_hash}`.
- `ember/capture/input_reader.py`: Edge reader for STDIN or file, 5 MiB file limit, UTF-8 decode.
- `ember/capture/item_proposal.py`: Phase 2 core. The 4 item types, the AI port `ItemProposerPort`, the item-context port, context mode A/B, the AI system prompt, parse + validate the AI answer, retry once.
- `ember/capture/item_gatekeeper.py`: Phase 3 core plus the human flag check. The 4 checks (type, statement, quote, near-dup warning), id/timestamp/Active generation, the source-text read port, and `validate_set_validated` for the Assumption flag.
- `ember/capture/confirm_write.py`: Phase 4 core. The `y/n/e/q` confirm loop and the confirm/commit ports.
- `ember/relate/__init__.py`: Marks the relate engine folder as a package.
- `ember/relate/errors.py`: Relate error codes `RELATE-001` to `RELATE-037` (with the documented gaps).
- `ember/relate/rows.py`: Pydantic row models `NewItem`, `CandidateUniverse`, `Link`, `SignalKind`, `RankedCandidate`, `ChangeLogEntry`, and `Pool`.
- `ember/relate/link_lookup.py`: The `LinkLookupPort` protocol (item reads, per-triple and batch link reads, 1-hop neighbors, and Step 3 status/cycle reads).
- `ember/relate/compat.py`: The 5 link types and the V1 spec 3.3 type-compatibility table.
- `ember/relate/load_filter.py`: Relate Phase 1 core. Loads by id (`load_item_candidates`) or latest (`load_latest_candidates`) and builds the candidate universe.
- `ember/relate/embedder.py`: The `EmbedderPort` protocol (embed, dim, model name).
- `ember/relate/embedding_store.py`: The `EmbeddingStorePort` protocol for the `item_embeddings` cache (read, upsert, model name, wipe); reads raise `RELATE-037`, writes `RELATE-019`.
- `ember/relate/candidate_pool.py`: Relate Phase 2 core. Runs the content, graph, and metadata signals, merges them by highest cosine, and returns a ranked `Pool` with counts and the model-change warning.
- `ember/relate/ai_response_store.py`: The `AiResponseStorePort` protocol for the Phase 3.5 raw-answer save.
- `ember/relate/link_proposal.py`: Relate Phase 3 core. The AI port, the strict-JSON boundary parser, the transport-only retry, and the target/source checks.
- `ember/relate/link_gatekeeper.py`: Relate Phase 4 pure gatekeeper. `validate_add_link` runs the 9 rules and returns `ValidatedLink` or `RejectedLink`.
- `ember/relate/confirm_write.py`: Relate Phase 4 core. The `y/n/s/q` confirm loop, `format_link_block`, and `ConfirmResult`.
- `ember/relate/run_relate.py`: Relate engine-core entry point. `RelatePorts`, `RelateRequest`, `run_relate` tie Phases 3 + 3.5 + 4 together behind ports.
- `ember/adapters/__init__.py`: Marks the adapters layer folder as a package.
- `ember/adapters/sqlite.py`: SQLite connection, numbered migrations, `SqliteSourceStore` and `SqliteItemGatekeeper` (writes are the gatekeeper boundary), `SqliteItemContext` (item reads), `SqliteAiResponseStore` (raw AI answers) and `build_ai_response_store`, `SqliteLinkContext` (relate item/link reads plus 1-hop neighbors, and the `item_status` / `supersedes_ancestors` reads), `SqliteLinkStore` (atomic `insert_link_with_log`), `SqliteEmbedderStore` (packed-vector cache; reads `RELATE-037`, writes `RELATE-019`), `build_embedding_store`, `open_relate_database` / `ensure_relate_schema` (relate boot checks).
- `ember/adapters/llm.py`: `OpenAiItemProposer` (`ItemProposerPort` on the OpenAI SDK, OpenRouter base URL) and the env-driven factory; `OpenAiLinkProposer` (`LinkProposerPort`) and the `build_link_proposer` factory.
- `ember/adapters/embedder.py`: `SentenceTransformerEmbedder` (`EmbedderPort` on the optional `sentence-transformers` extra), the env-driven `build_embedder` factory, and `validate_embedder_config` (boot check for the timeout and optional packages).
- `ember/adapters/migrations/__init__.py`: Marks the migrations folder as a package.
- `ember/adapters/migrations/001_create_sources.sql`: Creates the `sources` table.
- `ember/adapters/migrations/002_create_items.sql`: Creates the `items` table.
- `ember/adapters/migrations/003_create_change_log.sql`: Creates the `change_log` table.
- `ember/adapters/migrations/004_add_item_detail_columns.sql`: Adds the `items.rationale` and `items.source` columns.
- `ember/adapters/migrations/005_create_ai_responses.sql`: Creates the `ai_responses` table.
- `ember/adapters/migrations/006_create_links.sql`: Creates the `links` table (typed edges, any status, no self-links).
- `ember/adapters/migrations/007_create_item_embeddings.sql`: Creates the `item_embeddings` cache table.
- `ember/adapters/migrations/008_add_change_log_link_fk.sql`: Rebuilds `change_log` with the `link_id` foreign key.
- `ember/adapters/migrations/009_drop_source_id_not_null_and_add_item_id.sql`: Makes `ai_responses.source_id` nullable and adds `item_id`.

## Tests (`tests/`)
- `tests/__init__.py`: Marks the tests folder as a package.
- `tests/conftest.py`: `db_path` temp-file fixture.
- `tests/fakes.py`: Shared test helpers: the port stand-ins (`FakeSourceStore`, `FakeItemProposer`, `FakeItemContext`, `FakeConfirm`, `FakeItemCommit`), `FIXED_TIME`, and the row-seed helpers `insert_source`, `insert_item`, `make_item`.
- `tests/test_source_storage_unit.py`: Phase 1 unit tests on a fake store, no DB.
- `tests/test_source_storage_integration.py`: Phase 1 tests on a real SQLite temp DB.
- `tests/test_item_proposal_unit.py`: Phase 2 unit tests on a fake AI and fake item reader, no network.
- `tests/test_item_proposal_fixtures.py`: Phase 2 parser tests on saved AI answers.
- `tests/test_llm_adapter_unit.py`: LLM adapter tests on a fake client, no network.
- `tests/test_item_gatekeeper_unit.py`: Phase 3 unit tests on a fake source and item list, no DB.
- `tests/test_confirm_write_unit.py`: Phase 4 unit tests on a fake user and fake commit, no DB.
- `tests/test_item_store_integration.py`: SQLite item reader and gatekeeper-write tests on a real temp DB.
- `tests/test_ai_response_store.py`: SQLite raw AI-answer store tests on a real temp DB: save by `source_id`, save by `item_id`, and the exactly-one-owner rule.
- `tests/test_capture_pipeline_integration.py`: Phases 3 + 4 end to end on a real temp DB.
- `tests/test_migrations.py`: Asserts the `items` and `change_log` schema after migrations.
- `tests/test_cli.py`: CLI checks for the Phase 1 command, file/stdin modes and exit codes.
- `tests/test_cli_capture.py`: CLI checks for the `capture` command with a fake AI.
- `tests/test_cli_validated.py`: CLI checks for `set-validated` / `clear-validated` and the Assumption-only rule.
- `tests/test_capture_live.py`: Live AI round trip. Marked `live`, so a plain pytest run never calls the API; run it with `./.venv/bin/python -m pytest -m live`.
- `tests/test_relate_live.py`: Live AI round trip for the relate link proposer. Marked `live`, so a plain pytest run never calls the API; run it with `./.venv/bin/python -m pytest -m live`.
- `tests/test_architecture.py`: Asserts the capture and relate engine cores never import an adapter.
- `tests/test_relate_db_open.py`: Relate DB open checks: missing/corrupt file, migration fail, schema version 5/8/9 gate, and all migrations applied.
- `tests/test_relate_read_failures.py`: Every `SqliteLinkContext` read maps a `sqlite3` failure to `RELATE-016`; also covers `item_status` and `supersedes_ancestors`.
- `tests/test_migration_runner.py`: Each migration and its version bump are one transaction; failures roll back.

### Relate Tests (`tests/relate/`)
- `tests/relate/__init__.py`: Marks the relate tests folder as a package.
- `tests/relate/fakes.py`: In-memory port fakes: `FakeLinkLookup`, `FakeEmbedder`, `FakeEmbeddingStore`.
- `tests/relate/test_load_filter_unit.py`: Phase 1 unit tests on the fake port, no DB.
- `tests/relate/test_load_filter_integration.py`: Phase 1 tests on a real SQLite temp DB.
- `tests/relate/test_candidate_pool_unit.py`: Phase 2 unit tests on fakes: signals, merge, ranking, pre-flight, cosine behavior through the public function, error codes.
- `tests/relate/test_candidate_pool_integration.py`: Phase 2 tests on a real SQLite temp DB: seeded ranking, cache reuse (`embedded_at`/blobs unchanged), pre-flight wipe, graph read failure.
- `tests/relate/test_embedding_store_integration.py`: `SqliteEmbedderStore` tests on a real temp DB: float32 round-trip, model names, wipe, read (`RELATE-037`) / write (`RELATE-019`) failures.
- `tests/relate/test_neighbors_integration.py`: `SqliteLinkContext.neighbors_of` tests: Confirmed both directions, Rejected excluded, 1-hop, failure code.
- `tests/relate/test_embedder_adapter_unit.py`: `SentenceTransformerEmbedder` and `validate_embedder_config` tests with a fake model module; no network, no real model.
- `tests/relate/test_relate_cli.py`: `ember relate` CLI checks (boot validation, Phase 2 output, warning to stderr) and exit codes.
- `tests/relate/test_link_gatekeeper_unit.py`: Phase 4 unit tests for the 9 gatekeeper rules.
- `tests/relate/test_link_proposal_unit.py`: Phase 3 unit tests for parse, retry and the target/source checks.
- `tests/relate/test_run_relate_unit.py`: `run_relate` unit tests on fake ports.
- `tests/relate/test_confirm_write_unit.py`: Phase 4 confirm-loop unit tests.
- `tests/relate/test_relate_integration.py`: Phases 3 + 3.5 + 4 end-to-end on a real SQLite temp DB.
- `tests/relate/test_link_proposer_adapter_unit.py`: `OpenAiLinkProposer` adapter tests on a fake client, no network.

### AI Answer Fixtures (`tests/fixtures/ai_responses/`)
Saved AI answers for parser tests. Each pair is `case_NN.raw_text.txt` (the source text) + `case_NN.response.json` (the AI's answer).
- `tests/fixtures/ai_responses/case_01.raw_text.txt`: Source text for case 1.
- `tests/fixtures/ai_responses/case_01.response.json`: Case 1 answer, all entries valid.
- `tests/fixtures/ai_responses/case_02.raw_text.txt`: Source text for case 2.
- `tests/fixtures/ai_responses/case_02.response.json`: Case 2 answer, 1 valid + 3 bad entries.

## Database Tables (SQLite)
- `schema_version`: Holds the applied migration number.
- `sources`: Immutable raw input texts. Columns `id`, `title`, `full_text`, `timestamp`, `content_hash` (unique, the dedup key).
- `items`: Confirmed typed items. Columns `id`, `type`, `statement`, `source_id` (foreign key to `sources.id`), `status`, `created_at`, `validated` (set only on Assumption rows), `rationale` (Decision text), `source` (Finding evidence text).
- `change_log`: Append-only ledger. Columns `id`, `item_id`, `link_id` (foreign key to `links.id`), `field_changed`, `old_value`, `new_value`, `timestamp`, `trigger_cause`.
- `ai_responses`: Raw AI answers, stored verbatim. Columns `id`, `source_id` (nullable foreign key to `sources.id`), `item_id` (nullable foreign key to `items.id`), `response_text`, `timestamp`.
- `links`: Typed directional edges. Columns `id`, `source_item_id`, `target_item_id`, `link_type`, `status` (`Confirmed` or `Rejected`), `created_at`. Unique per source/target/type.
- `item_embeddings`: Rebuildable vector cache. Columns `item_id`, `vector`, `model_name`, `embedded_at`.

## Empty Folders
These folders exist but hold no files yet.
- `draft/`: Working drafts.
- `reports/`: Generated reports.
- `research/`: Research notes.

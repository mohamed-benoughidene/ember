# Project Map

This file lists every file and its purpose in the repository. Update it when files or folders are added or removed.

## Root Files
- `.gitignore`: Ignore rules for Python build files and local database files.
- `AGENTS.md`: Rules for AI coding agents working in this repository.
- `CLA.md`: Contributor License Agreement (license-grant style): contributors keep copyright, grant the project a permanent license, signed with a `Signed-off-by:` commit line.
- `Constitution.md`: Core build rules for modules, data, interfaces and tests (AI caveman version).
- `LICENSE`: Business Source License 1.1 (source-available): free for personal and internal use, commercial license required only for offering Ember to third parties; each version becomes MIT two years after its first publication.
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
- `plans/master-plan.md`: L1 System Master Plan. 4 engines (Capture, Relate, Maintain, Query), shared SQLite storage, global rules, test strategy, L1 §0 stack decisions. §8 now also holds the approved Engine E amendment (Utility: backup, export).
- `plans/engine-capture-plan.md`: L2 Capture engine master plan. Pipeline phases 1-4 (source storage, AI proposal, gatekeeper, user confirm + write).
- `plans/engine-utility-plan.md`: L2 Engine E (Utility) master plan, APPROVED 2026-10-29 after a 4-axis review panel. `ember backup` (online-API snapshot, `.old` rotation, verified read-back) and `ember export` (deterministic readable text, not restorable). §9 holds the 16-finding review log.
- `plans/steps/utility/step-01-backup.md`: L3 Utility Step 1 plan. Backup: precheck+rotate, open read-only, snapshot, verify, report.
- `plans/steps/utility/step-02-export.md`: L3 Utility Step 2 plan. Export: gather, pure render, guarded emit (EXPORT-002 self-overwrite refusal).
- `plans/engine-relate-plan.md`: L2 Relate engine master plan. Pipeline phases 1-4 (load + filter, candidate pool, AI proposal, confirm + write).
- `plans/steps/capture/01-source-storage.md`: L3 Step 1 plan. Phase 1, source dedup by content hash.
- `plans/steps/capture/02-ai-port-call.md`: L3 Step 2 plan. Phase 2, AI proposal via `ItemProposerPort`.
- `plans/steps/capture/03-user-confirm-write.md`: L3 Step 3 plan. Phases 3+4, gatekeeper + user confirm + write.
- `plans/steps/relate/01-load-and-filter.md`: L3 Relate Step 1 plan. Phase 1, load the item and filter type-compatible candidates.
- `plans/steps/relate/02-candidate-pool.md`: L3 Relate Step 2 plan. Phase 2, the 3 signals and merge.
- `plans/steps/relate/03-ai-propose-and-confirm-write.md`: L3 Relate Step 3 plan. Phases 3+4, AI proposal, confirm, and write.
- `plans/engine-query-plan.md`: L2 Query engine master plan. The four read modes (`current_state`, `topic_search`, `why`, `history`), the read-only boot path, the BM25 formula, and the `change_log` vocabulary contract.
- `plans/engine-maintain-plan.md`: L2 Maintain engine master plan. Pipeline phases 1-4 (load, derive, apply, report), migration 010, the four deterministic zero-AI rules, and the change_log vocabulary.
- `plans/steps/maintain/01-load-and-derive.md`: L3 Maintain Step 1 plan. Phases 1+2, migration 010, the pure derive core, and a runnable `ember maintain --dry-run`.
- `plans/steps/maintain/02-apply-and-cli.md`: L3 Maintain Step 2 plan. Phases 3+4, the atomic status + `change_log` write path, and the `ember maintain` command.
- `plans/steps/maintain/03-human-actions.md`: L3 Maintain Step 3 plan. The three human commands (`close-item`, `set-status`, `reverse-supersedes`), the `status_origin` shield and the `link_reversed` reversal marker, and the cross-plan amendments that close out the engine.
- `plans/steps/maintain/04-edit-item.md`: L3 hardening Step 4 plan. `ember edit-item` under ADR Option A (rationale/source only, statement forbidden), with post-implementation Build Notes.
- `plans/steps/maintain/05-remove-link.md`: L3 hardening Step 5 plan. `ember remove-link`: the ONE `links` status UPDATE (Gate 2, "keep the block"), the per-type sweep-interplay table, and the combined E2E, with post-implementation Build Notes.

## Python Implementation (`ember/`)
- `pyproject.toml`: Package metadata, locked stack deps (click, openai, pydantic; pytest is a dev dep), the optional `relate` extra (`sentence-transformers`), pytest config.
- `ember/__init__.py`: Package version.
- `ember/__main__.py`: Runs the CLI via `python -m ember`.
- `ember/cli.py`: Click CLI. `capture` runs the full 4-phase pipeline; `capture-source` is the Phase 1 standalone command; `relate` runs all 4 Relate phases (Phase 3 AI propose, Phase 3.5 raw-answer save, Phase 4 gatekeeper + confirm + atomic write, printing one `relate rejected: CODE | detail` line per gatekeeper rejection before the summary) and defines `RelateTerminalConfirm` (raises the relate `UserAbort` on end of input); `set-validated` / `clear-validated` write the Assumption flag; `maintain` runs the Maintain sweep (load + derive + atomic write + report) and then the Phase-5 close proposals on a fresh post-apply snapshot (the free `stale_close_candidates` pre-filter: an empty shortlist prints the `stale:` outcome line and builds no AI adapter, no key needed; a non-empty shortlist prints one pinned proposal block per stale Question and confirms with `[y]es / [n]o / [q]uit` via `MaintainTerminalConfirm`, an accepted close written through the human `validate_close_item` path, raw answers stored in `ai_responses` keyed by `item_id`; `--dry-run` lists the pre-apply shortlist as `item <id>: stale <type> (...) (dry-run)` lines and builds no proposer; `stale shortlist capped at 10 items (list truncated)` before the loop; exit 2 on abort); `close-item` / `set-status` / `reverse-supersedes` are the Maintain human-only mutations (close an item by hand, move it between `Active` and `Challenged`, and undo a `supersedes`); `edit-item` is the Maintain human write for `items.rationale` / `items.source` (`--dry-run` prints the planned old -> new line and writes nothing); `remove-link` is the Maintain human removal of one confirmed link (ONE `Confirmed -> Rejected` status flip plus its `link_removed` ledger row in one transaction, the row never deleted, `--dry-run` prints the pinned flip line and writes nothing, a second removal of the same link exits 1 `MAINTAIN-015`); `db-check` prints the read-only database health report (exit 0 healthy, 1 on `DRIFT` / `UNREADABLE`); `backup` is the thin CLI edge over `create_backup` (argument `target_path`, option `--db`; success prints `backup written: <path> (schema v<N>, <count> items)` with `rotated to <path>` on stderr when an existing target was rotated aside, any `EmberError` prints `error: <log_line()>` on stderr and exits 1, the help text ends with the restore warning); `export` is the thin CLI edge over the export pipeline (option `--out` optional, option `--db`; the DB is opened by `open_query_database` read-only, then gather -> render -> emit, `--out` prints `exported <N> items, <M> links, <K> ledger rows, <S> sources -> <path>`, no `--out` prints the whole rendered text to stdout, the self-overwrite guard runs before any open-for-write and `--out` naming the DB file itself exits 1 `EXPORT-002` with the DB byte-identical, any `EmberError` prints `error: <log_line()>` on stderr and exits 1, the help text ends with the not-restorable warning); `topic-search` takes `--status` `--type` `--limit` on top of `--query` (bad values exit 1 `QUERY-006` with `field`, non-integer limits and unknown flags exit 2 via Click); `history` takes `--limit` / `--offset` / `--since` on top of `--item` (the window composes on both views, a naive or unparseable `--since` exits 1 `QUERY-007` with `since_length`, negative limit/offset exit 1 `QUERY-006` with `field`, non-integer values and unknown flags exit 2 via Click).
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
- `ember/relate/rows.py`: Pydantic row models `NewItem` (carries the nullable `metadata` project label, read by the relate metadata signal), `CandidateUniverse`, `Link` (carries the optional `reversed_at` reversal timestamp from migration 011), `SignalKind`, `RankedCandidate`, `ChangeLogEntry`, and `Pool`.
- `ember/relate/link_lookup.py`: The `LinkLookupPort` protocol (13 reads: item reads including the `item_metadata` project label, per-triple and batch link reads, 1-hop neighbors, Step 3 status/cycle reads, and `supersedes_blocking_link` for cycle-rejection detail, raising `RELATE-021`).
- `ember/relate/compat.py`: The 5 link types and the V1 spec 3.3 type-compatibility table.
- `ember/relate/load_filter.py`: Relate Phase 1 core. Loads by id (`load_item_candidates`) or latest (`load_latest_candidates`) and builds the candidate universe.
- `ember/relate/embedder.py`: The `EmbedderPort` protocol (embed, dim, model name).
- `ember/relate/embedding_store.py`: The `EmbeddingStorePort` protocol for the `item_embeddings` cache (read, upsert, model name, wipe); reads raise `RELATE-037`, writes `RELATE-019`.
- `ember/relate/candidate_pool.py`: Relate Phase 2 core. Runs the content, graph, and metadata signals (metadata compares `items.metadata` labels casefold-equal at any age, falling back to the frozen 30-day time proxy for unlabeled items, per L2 §13), bundles the three results into the in-module `Signals` wrapper (L2 §12, ticket 10, no other module may name it), merges them by highest cosine, and returns a ranked `Pool` with counts and the model-change warning.
- `ember/relate/ai_response_store.py`: The `AiResponseStorePort` protocol for the Phase 3.5 raw-answer save.
- `ember/relate/link_proposal.py`: Relate Phase 3 core. The AI port, the strict-JSON boundary parser, the transport-only retry, and the target/source checks.
- `ember/relate/link_gatekeeper.py`: Relate Phase 4 pure gatekeeper. `validate_add_link` runs the 9 rules and returns `ValidatedLink` or `RejectedLink` (rules 8/9 carry a `detail` naming the blocking link id plus endpoints, and the duplicate's reversal state).
- `ember/relate/confirm_write.py`: Relate Phase 4 core. The `y/n/s/q` confirm loop, `format_link_block`, and `ConfirmResult` (which also carries the gatekeeper `RejectedLink`s for the CLI to print, in `gatekeeper_rejections`).
- `ember/relate/run_relate.py`: Relate engine-core entry point. `RelatePorts`, `RelateRequest`, `run_relate` tie Phases 3 + 3.5 + 4 together behind ports.
- `ember/maintain/__init__.py`: Marks the maintain engine folder as a package.
- `ember/maintain/errors.py`: Maintain error codes `MAINTAIN-000` to `MAINTAIN-022` (contiguous, none reused; 018-022 are the Phase-5 close-proposal codes: `CloseAiCallFailed`, `CloseAiSchemaInvalid`, `CloseAiConfigMissing`, `CloseAiStoreFailed`, `UserAbort`).
- `ember/maintain/rows.py`: Pydantic row models `ItemState` (carries the `rationale` / `source` authorial columns, nullable, from migration 004, plus the additive `statement` display column the Phase-5 proposal reads), `MaintainSnapshot` (with the additive `shield_log` ledger slice the timestamp-scoped shield reads, default `[]`), `StatusChange` (with the additive `rearm` bool the merge stamps on a shielded item's winning change and the adapter executes), `EditChange`, `LinkChange` (the removal's `Confirmed -> Rejected` change, `item_id` = the link's source; `Link` / `ChangeLogEntry` are imported from `ember.relate.rows`).
- `ember/maintain/maintain_lookup.py`: The `MaintainLookupPort` protocol (4 reads: items, confirmed links, reversed link ids, shield log).
- `ember/maintain/derive.py`: Maintain Phase 2 pure core. `derive_status_changes` (the four rules) and `merge_and_filter` (one change per item, escalation-only, the timestamp-scoped manual shield: a `status_origin='manual'` item skips only candidates whose `link_confirmed` evidence `(timestamp, id)` beats the item's latest manual clear `(timestamp, id)`, fail-closed on any gap, and the winner is stamped `rearm=True` so the adapter re-arms it, `sweep_rearm` in the ledger).
- `ember/maintain/report.py`: `format_report`, the shared run/dry-run report formatter.
- `ember/maintain/run_maintain.py`: Maintain Phase 1 loader `_load(ports)`, the `index_items` by-id index, and the engine-core orchestration: `MaintainPorts`, `MaintainRequest`, `MaintainResult` (carries `total_items`), `_apply_and_report(ports, snapshot, changes)`, `run_sweep`, the three human sweep entry points `run_close_item` / `run_set_status` / `run_reverse_supersedes`, `run_edit_item` (returns the `list[EditChange]` directly, `[]` on a no-op), `run_remove_link` (returns the single-element `list[LinkChange]`; a no-op is impossible, `MAINTAIN-015`), and the separate Phase-5 entry point `run_close_proposals(ports, now)` with `CloseProposalPorts` — fresh post-apply snapshot, one AI call plus a verbatim D8 save per stale candidate, the y/n/q confirm loop, an accepted close riding `run_close_item` unchanged, rejections and declines writing nothing.
- `ember/maintain/human_actions.py`: The pure validators for the five human commands — `validate_close_item`, `validate_set_status`, `validate_reverse_supersedes`, `validate_edit_item` (Option-A rule: `rationale` writable on a `Decision`, `source` on a `Finding`, `statement` known-but-rejected, same-value edit returns `[]`), and `validate_remove_link` (one Confirmed row -> one `LinkChange`; missing-or-not-Confirmed is one code `MAINTAIN-015`; a reversed-but-Confirmed link passes). Each reads a `MaintainSnapshot` (no DB).
- `ember/maintain/apply_status.py`: The `MaintainStorePort` protocol — the atomic write port (`apply_status_changes`, `apply_status_origin`, `apply_reversal`, `apply_item_edit`, `apply_remove_link`).
- `ember/maintain/close_proposer.py`: The Phase-5 pure core. `stale_close_candidates` — the one deterministic pre-filter (Active Questions whose newest Confirmed `answers` link is at least `STALE_DAYS = 30` days old, capped at `MAX_CLOSE_PROPOSALS = 10` with `truncated`, fail-closed on any malformed or naive timestamp), returning `StaleShortlist` of `StaleCandidate`; `parse_close_proposal` — the boundary parser (strict JSON object, boolean `close`, `false` declines, `true` requires reason in `HUMAN_SETTABLE_REASONS`, confidence in [0.0, 1.0], rationale string-or-null, any deviation raises `MAINTAIN-019`); `propose_close_with_retry` (retry ONCE on `MAINTAIN-018` or `MAINTAIN-019`, the second failure propagates); `format_proposal_block` (the pinned confirmation block, a decline printing `no close proposed`); the `CloseProposerPort` / `ConfirmPort` protocols, `CloseProposal` / `CloseProposalResponse` / `ProposalOutcome` models, the pinned `SYSTEM_PROMPT`, and `PROMPT = "[y]es / [n]o / [q]uit"` — stdlib + pydantic only.
- `ember/query/__init__.py`: Marks the query engine folder as a package.
- `ember/query/errors.py`: Query error codes `QUERY-000` to `QUERY-007` (`QueryError` base, item-not-found, empty text, DB open, schema outdated, items read, filter invalid, since invalid).
- `ember/query/rows.py`: Pydantic row models `QueryItem`, `CurrentStateRow`, `ChangeRow` (nullable `item_id` read shape), `TopicFilter` (the `--status` / `--type` / `--limit` filter shape for topic-search), `HistoryPage` (the `--limit` / `--offset` / `--since` page shape for history, `since` normalised to UTC by the validator, the item scope never lives here), `SearchHit`, `WhyReason`, `WhyResult`, `HistoryEvent` (`Link` is imported from `ember.relate.rows`).
- `ember/query/tokenize.py`: The one tokenizer shared by the query gate and the BM25 scorer (lowercase, split on non-alphanumerics).
- `ember/query/lookup.py`: The `QueryLookupPort` protocol (4 reads: items, links, change_log, item_exists).
- `ember/query/query_gatekeeper.py`: The read gate: `validate_query_text` (`QUERY-002`), `validate_query_item` (`QUERY-001`), `validate_topic_filter` (`QUERY-006`, exact-case status/type sets plus the shared module-private `_require_non_negative` raising site for negative limit/offset), and `validate_history_page` (`QUERY-006` via the same shared helper, `QUERY-007` for a `--since` that does not parse or parses as naive, returning the page with `since` normalised to UTC).
- `ember/query/current_state.py`: `current_state` pure core. Keeps `Active` + `Challenged` and returns the input order.
- `ember/query/topic_search.py`: BM25 pure core (`k1 = 1.2`, `b = 0.75`, `ln(1 + …)` IDF, score-then-`item_id` tie-break). Takes an optional `TopicFilter`: status/type narrow the corpus before scoring (counts recompute over the subset), `limit` crops behind the final sort, `0` = explicit empty, the default filter restricts nothing.
- `ember/query/why.py`: The `why` pure core: `depends_on` to its target, `supports` to its source, Confirmed only, transitive and cycle-safe.
- `ember/query/history.py`: The `change_log` classifier (ten kinds from the `(field_changed, trigger_cause)` pair, including the sweep's `sweep_rearm` re-arm row rendered as `status_origin_changed`, `unknown` fallback) and the `history` union derivation, which takes the `HistoryPage` window strictly after the union and the `(timestamp, id)` sort (since cut as opaque ISO text, then offset skips, then limit caps, `None` = no cut).
- `ember/query/render.py`: The display layer: `render_current_state` (Challenged first), `render_topic_search`, `render_why`, `render_history`, all `json.dumps` only.
- `ember/query/run_query.py`: The four engine entry points `run_current_state`, `run_topic_search`, `run_why`, `run_history` (validate, load, derive, render).
- `ember/adapters/__init__.py`: Marks the adapters layer folder as a package.
- `ember/adapters/sqlite.py`: SQLite connection, numbered migrations with a pre-migration file backup (`<db>.bak-v<N>` taken once per run when scripts are pending, newest 3 kept; boot call sites wrap a failed copy as RELATE-013 / MAINTAIN-008), `SqliteSourceStore` and `SqliteItemGatekeeper` (writes are the gatekeeper boundary), `SqliteItemContext` (item reads), `SqliteAiResponseStore` (raw AI answers) and `build_ai_response_store`, `SqliteLinkContext` (relate item/link reads plus 1-hop neighbors, the `item_status` / `supersedes_ancestors` reads (rules 8 see `reversed_at IS NULL` so a reversed supersedes no longer blocks), and `supersedes_blocking_link` for the cycle-rejection detail (RELATE-021 on read failure)), `SqliteLinkStore` (atomic `insert_link_with_log`), `SqliteEmbedderStore` (packed-vector cache; reads `RELATE-037`, writes `RELATE-019`), `build_embedding_store`, `open_relate_database` / `ensure_relate_schema` (relate boot checks, required version 12), `SqliteMaintainContext` (maintain item/link/reversed-link/shield-log reads, the item read growing the `rationale` / `source` columns), `SqliteMaintainStore` (maintain atomic status + `change_log` writes, the re-arm branch of `apply_status_changes` (a `rearm` change sets `status_origin='derived'` in the batch UPDATE and appends its `status_origin` / `sweep_rearm` ledger row from the same ONE clock read), plus the reversal pairing write of `links.reversed_at` + the `link_reversed` marker in one transaction from one clock read, plus `apply_item_edit` — one `items` column UPDATE + one ledger row in one transaction behind the `_EDIT_COLUMNS` whitelist, plus `apply_remove_link` — the ONE `links` status UPDATE `Confirmed -> Rejected` + its `link_removed` ledger row in one transaction, never an INSERT, DELETE, or `reversed_at` write), `open_maintain_database` / `ensure_maintain_schema` (maintain boot checks, required version 11), and `SqliteQueryContext` (the four query reads) with `open_query_database` / `ensure_query_schema` (read-only boot, required version 10, never migrates).
- `ember/adapters/link_replay.py`: `replay_reversals`, the pure D3 replay step (hardening 02): ledger rows in, `dict[int, str | None]` out, highest-id `link_reversed` marker wins, no clock, no I/O. Adapters-only by T9: no engine core imports it.
- `ember/adapters/errors.py`: Adapter-layer error namespaces: `BackupError` (`BACKUP-000` base, never raised directly) and its leaves `SourceOpenFailed` (`BACKUP-001`), `SourceInvalid` (`BACKUP-002`), `TargetWriteFailed` (`BACKUP-003`), `VerifyFailed` (`BACKUP-004`), plus `ExportError` (`EXPORT-000` base, never raised directly) and its leaves `OutputWriteFailed` (`EXPORT-001`, the `--out` file cannot be written) and `OverwriteRefused` (`EXPORT-002`, the `--out` path is the knowledge base file itself), all `EmberError` subclasses after the `ember/query/errors.py` pattern.
- `ember/adapters/backup.py`: `create_backup(source_path, target_path) -> BackupReport`, the five-phase backup pipeline (precheck + rotate, read-only source open, snapshot via the sqlite3 online backup API, verify by re-opening the copy and reading `schema_version` + item count, report). An existing target rotates into `.old-<N>` files (newest `.old-1`, newest 3 kept, older deleted, the `.bak-v` convention); a partial copy is deleted on snapshot or verify failure. No engine floors on the source.
- `ember/adapters/export.py`: the `ember export` pipeline behind `gather_export(conn) -> ExportData` (fixed-order SELECTs: items by id, links by id, sources by id, ledger by `(timestamp, id)`, schema version read never advanced, `item_embeddings` / `ai_responses` never read), the row models `ExportItem` / `ExportSource` / `ExportData` (links are the shared `ember.relate.rows.Link`, ledger rows the shared `ember.query.rows.ChangeRow`), the PURE `render_export(data) -> str` (no I/O, no clock, deterministic: header lines include counts and "as of" = max ledger timestamp, sections `== items ==` / `== links ==` / `== sources ==` / `== ledger ==`, one aligned `  label: value` field block per row, removed links labelled `(removed)` and reversed ones `(reversed)`, ledger values never truncated), and the emitter: `refuse_self_overwrite(db_path, out_path)` (raises `EXPORT-002` before any open-for-write when both paths name one file: `os.path.samefile` where both exist, resolved absolute paths otherwise) and `write_export(text, out_path)` (UTF-8, LF endings, raises `EXPORT-001`). Raw source text is D1-verbatim between pinned marker lines, the end marker carrying the source id, byte count and sha256 so no source can ever carry its own end marker.
- `ember/adapters/db_check.py`: `check_database`, the read-only health check behind `ember db-check` (hardening 02): reads version, floors (relate 12, maintain 11, query 10, capture none), the four enforcement triggers, `link_compat` vs `TYPE_COMPAT`, `PRAGMA foreign_key_check`, and the reversal replay against the live `reversed_at` column. Reports `OK` / `DRIFT` / `UNREADABLE`, never migrates, never writes, no error codes.
- `ember/adapters/llm.py`: `OpenAiItemProposer` (`ItemProposerPort` on the OpenAI SDK, OpenRouter base URL) and the env-driven factory; `OpenAiLinkProposer` (`LinkProposerPort`) and the `build_link_proposer` factory; `OpenAiCloseProposer` (`CloseProposerPort`, the maintain-third section: parses the raw close answer at the boundary with `parse_close_proposal`, key missing fails fast `MAINTAIN-020`) and the `build_close_proposer` factory.
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
- `ember/adapters/migrations/010_add_item_close_reason.sql`: Adds the `items.close_reason` and `items.status_origin` columns.
- `ember/adapters/migrations/011_add_links_reversed_at_and_enforcement_triggers.sql`: Adds `links.reversed_at`, the `link_compat` pair table (16 rows), the items/links guard pre-assertions, and the four enforcement triggers (compat pairs on `links`, `Closed` implies `close_reason` on `items`).
- `ember/adapters/migrations/012_add_items_metadata.sql`: Adds the `items.metadata` column (nullable TEXT, no default, no rebuild, no backfill). NULL means unlabeled. Written by capture (ticket 11, step 05a), read by relate (step 05b).

## Tests (`tests/`)
- `tests/__init__.py`: Marks the tests folder as a package.
- `tests/conftest.py`: `db_path` temp-file fixture.
- `tests/fakes.py`: Shared test helpers: the port stand-ins (`FakeSourceStore`, `FakeItemProposer`, `FakeItemContext`, `FakeConfirm`, `FakeItemCommit`), `FIXED_TIME`, and the row-seed helpers `insert_source`, `insert_item` (with `status` / `close_reason` / `status_origin` / `metadata` / `rationale` / `source` params), `insert_link`, `insert_link_with_confirmation` (the production-shaped `links` row + `link_confirmed` ledger pair, `created_at` sets both), `insert_link_reversed`, and `make_item`.
- `tests/test_backup.py`: `ember backup` tests (utility step 01): a usable v12 copy read back with the same schema version and count, rotation to `.old-1` with depth-3 retention and the oldest deleted, the CLI success and rotation-stderr lines, the source-hash proof (source byte-identical), the directory-target and unwritable-snapshot failures deleting any partial copy (`BACKUP-003`), the verify failure deleting the copy (`BACKUP-004`), source failures with pinned codes (missing/garbage `BACKUP-001`, no-schema-version `BACKUP-002`), the missing-DB CLI exit 1, a v9 file backing up without floors, and the help text ending with the restore warning.
- `tests/test_export.py`: `ember export` tests (utility step 02): the pure render (render twice byte-identical, pinned header and section order, as-of = max ledger timestamp with no real date anywhere, the verbatim fixture round-tripping exactly between the sha256-stamped end markers with the spoof lines inside the block, `(removed)` / `(reversed)` link states, an untruncated 400-char ledger value, an empty `ExportData` header, gather matching the CLI shape), the seeded coverage proof (one item per type, kept/removed/reversed links, `(timestamp, id)` ledger order, every field line and value asserted in the text), the read-only hash proofs (DB byte-identical across an export and across a refused `EXPORT-002` attempt), the CLI surface (`--out` file bytes equal to stdout, the summary line, unwritable path exit 1 `EXPORT-001`, `--out <the-db>` exit 1 `EXPORT-002`, an empty DB exporting 0-count exit 0 I8), and floors (a v9 file refused `QUERY-004`, DB untouched).
- `tests/fixtures/export_source_verbatim.txt`: The verbatim-round-trip fixture for the export tests: blank lines, two- and four-space leading indentation, a trailing-space line, emoji and other non-ASCII, a bare marker-look-alike line, the full sha256-stamped end marker of a DIFFERENT source id, and no trailing newline (both ending modes are exercised with and without one added newline).
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
- `tests/test_migration_011.py`: Migration 011 on real v10 temp DBs: full-row preservation, schema diff, foreign-key check, `sqlite_sequence`, ledger backfill of `reversed_at`, both guard pre-assertions, backup-when-pending with retention 3, fresh install, and failed-migration rollback.
- `tests/test_migration_012.py`: Migration 012 on real v11 temp DBs: the nullable `metadata` column, full-row preservation (values intact, new column NULL), schema diff, 011's Closed trigger still active and metadata writes not firing the status/close_reason trigger, fresh install through 012, and failed-migration rollback with the `.bak-v11` backup.
- `tests/test_schema_enforcement.py`: The migration 011 triggers: direct illegal pair INSERT rejected, `link_compat` matches `TYPE_COMPAT` (16 rows), real writers still commit, and `Closed` without `close_reason` rejected.
- `tests/test_link_replay.py`: The D3 replay tests (hardening 02): `replay_reversals` over a real ledger matches the live `links.reversed_at` column, highest-id marker wins on a clock tie, and pure-unit cases (no marker gives `None`, link-less rows skipped).
- `tests/test_db_check.py`: `ember db-check` CLI checks (hardening 02): healthy DB exits 0 with the pinned report, seeded drifts (zeroed column, dropped `link_compat` row, stale v10 DB) exit 1 `DRIFT`, missing and corrupt files exit 1 `UNREADABLE`, the read-only hash proof (identical sha256 before and after), and unknown flags exit 2.
- `tests/test_cli.py`: CLI checks for the Phase 1 command, file/stdin modes and exit codes.
- `tests/test_cli_capture.py`: CLI checks for the `capture` command with a fake AI.
- `tests/test_cli_validated.py`: CLI checks for `set-validated` / `clear-validated` and the Assumption-only rule.
- `tests/test_capture_live.py`: Live AI round trip. Marked `live`, so a plain pytest run never calls the API; run it with `./.venv/bin/python -m pytest -m live`.
- `tests/test_relate_live.py`: Live AI round trip for the relate link proposer. Marked `live`, so a plain pytest run never calls the API; run it with `./.venv/bin/python -m pytest -m live`.
- `tests/test_architecture.py`: Asserts the capture, relate, maintain, and query engine cores never import an adapter, and that no engine core module references the `link_replay` replay step (hardening 03).
- `tests/test_relate_db_open.py`: Relate DB open checks: missing/corrupt file, migration fail, schema version 5/8/12 gate, and all migrations applied.
- `tests/test_relate_read_failures.py`: Every `SqliteLinkContext` read maps a `sqlite3` failure to `RELATE-016`; also covers `item_status` and `supersedes_ancestors`.
- `tests/test_migration_runner.py`: Each migration and its version bump are one transaction; failures roll back.

### Maintain Tests (`tests/maintain/`)
- `tests/maintain/__init__.py`: Marks the maintain tests folder as a package.
- `tests/maintain/fakes.py`: In-memory port fakes `FakeMaintainLookup` (with the `shield_log` list and its `list_shield_log()` read), `FakeMaintainStore`, `FakeCloseProposer` (a canned close AI whose `calls` list records one `StaleCandidate` per propose call), and `AiResponseStoreStub` (records D8 saves, or always fails for the `MAINTAIN-021` path).
- `tests/maintain/test_derive_unit.py`: Phase 2 unit tests: the four rules, tie-breaks, one-change-per-item, escalation-only, the manual shield (fail-closed silence, newer-evidence pass, the `(timestamp, id)` tie and boundary rules, and the `rearm` stamp) on the fake lookup.
- `tests/maintain/test_report_unit.py`: `format_report` line, ordering, and summary-bucket tests.
- `tests/maintain/test_apply_unit.py`: `run_sweep` / `_apply_and_report` unit tests on a fake store: the write path calls `apply_status_changes` once and counts `reopened`.
- `tests/maintain/test_human_actions_unit.py`: Unit tests for the three pure human-action validators (`validate_close_item`, `validate_set_status`, `validate_reverse_supersedes`): error codes, the no-op path, and the ladder regression (a human may move an item down) on the fake lookup.
- `tests/maintain/test_migration_010.py`: Migration 010 on a non-empty DB: rows survive, the new columns default correctly.
- `tests/maintain/test_maintain_boot.py`: `open_maintain_database` missing / corrupt / migration-fail / schema-version checks (`MAINTAIN-007` / `008` / `009`).
- `tests/maintain/test_maintain_read_failures.py`: Every `SqliteMaintainContext` read maps a `sqlite3` failure to `MAINTAIN-010`.
- `tests/maintain/test_maintain_store_integration.py`: `SqliteMaintainStore` on a real temp DB: exact log rows, the `MAINTAIN-011` / `012` codes, real FK atomicity rollback, and the injected clock.
- `tests/maintain/test_maintain_integration.py`: `_load` + `derive_status_changes` on a real temp DB: the exact `StatusChange` list.
- `tests/maintain/test_maintain_run_integration.py`: `run_sweep` end to end on a real temp DB: exact `items` + `change_log` state and idempotence.
- `tests/maintain/test_maintain_cli.py`: `ember maintain` CLI checks: dry-run writes nothing, a plain run applies, idempotence, and `MAINTAIN-007` on a missing DB.
- `tests/maintain/test_maintain_commands_cli.py`: CLI checks for `ember close-item` / `set-status` / `reverse-supersedes`: exit codes and the `MAINTAIN-001`–`006` codes.
- `tests/maintain/test_maintain_commands_integration.py`: The three human commands end to end on a real temp DB: the `status_origin` shield row, the close fan-out, and the no-op path.
- `tests/maintain/test_maintain_reversal_integration.py`: `reverse-supersedes` end to end on a real temp DB: the item is restored, two `change_log` rows exist (`status` + `link_reversed`), the `links` row is unchanged, and a later supersedes still closes the item.
- `tests/maintain/test_edit_item.py`: `validate_edit_item` unit tests on the fake lookup (013/014 codes, the Option-A `statement` rejection, the same-value `[]` no-op, the observed `old_value`) plus the step-local E2E: `ember edit-item` then `ember history --item N` renders the new ledger row as `kind='unknown'` with raw values visible.
- `tests/maintain/test_edit_item_integration.py`: `apply_item_edit` on a real temp DB: UPDATE + ledger row in one transaction, the delegating-connection injection tests (`MAINTAIN-016` / `MAINTAIN-012`, each asserting full rollback), the grown Phase-1 item read, and the sweep leaving `rationale` / `source` untouched.
- `tests/maintain/test_edit_item_cli.py`: `ember edit-item` CLI checks: exit 0 on success and on the same-value no-op (zero rows), exit 1 with `MAINTAIN-001` / `013` / `014`, `--dry-run` writes zero rows and prints the pinned line, and Click usage errors exit 2.
- `tests/maintain/test_remove_link.py`: `validate_remove_link` unit tests on the fake lookup (the happy `LinkChange`, one code `MAINTAIN-015` for missing or not-Confirmed, the reversed-but-Confirmed pass) plus the step's ONE combined E2E: `ember edit-item` -> `ember remove-link` -> `ember history --item` renders both new ledger rows `kind='unknown'` and `ember db-check` stays exit 0.
- `tests/maintain/test_remove_link_integration.py`: `apply_remove_link` on a real temp DB: the ONE flip + `link_removed` row in one transaction, the delegating-connection injection tests (`MAINTAIN-017` / `MAINTAIN-012`, each asserting full rollback), the 5-param per-type sweep-interplay test (removed links feed no trigger; nothing un-closes or un-challenges), the supersedes-no-reopen and reversed-then-removed regressions, the ledger-to-link FK join proof, and the db-check replay still matching.
- `tests/maintain/test_remove_link_cli.py`: `ember remove-link` CLI checks: success exit 0 with the one report line, unknown link / already-rejected / second removal each exit 1 `MAINTAIN-015`, `--dry-run` writes zero rows and prints the pinned flip line, and a non-integer `--link` exits 2.
- `tests/maintain/test_close_proposer_unit.py`: The Phase-5 pure core (20 tests): the pre-filter (the one staleness rule, the exact-30-day boundary, newest-link selection, Challenged/Closed and non-Question invisibility, Rejected links, the 10-cap + `truncated`, the statement slice, malformed and naive `created_at` fail-closed), the boundary parser on T7 fixtures (valid, decline, bad reason, not an object, empty, confidence out of range, each raising `MAINTAIN-019`), the one engine retry (both failure kinds retried once, the second propagating `MAINTAIN-018`), and the decline block shape.
- `tests/maintain/test_close_proposer_adapter.py`: The `OpenAiCloseProposer` adapter, no network: missing key raises `MAINTAIN-020`, env overrides reach the client (`base_url`, timeout 60, `max_retries=0`), `OpenAIError` maps to `MAINTAIN-018` carrying `item_id` with the key redacted, and the request passes `temperature=0.0`.
- `tests/maintain/test_close_proposals_integration.py`: `run_close_proposals` on real temp DBs with `FakeCloseProposer` and a scripted confirm fake: an empty shortlist never calls the proposer, the accept path writes exactly one `user_closed` row via `run_close_item` (including the `invalidated` fan-out written through the same validator, and the accepted close leaving `status_origin='manual'` on a shielded item), reject/decline count without writing, `q` aborts with leftovers uncalled, the raw answers stored verbatim keyed by `item_id`, a store failure raising `MAINTAIN-021`, an error mid-loop keeping earlier accepts, and the 10-cap on a 12-question shortlist.
- `tests/maintain/test_close_proposals_cli.py`: `ember maintain` Phase 5 CLI checks on real temp DBs, the proposer faked at the `ember.cli.build_close_proposer` seam, no API key anywhere: the empty shortlist builds no proposer, the pinned accept/reject/quit outcome lines and blocks, a decline printing `no close proposed` and no prompt, the dry-run shortlist lines without a key, a missing key on a stale shortlist exiting 1 `MAINTAIN-020`, and the truncation note with exactly 10 AI calls.

### Maintain Close-Proposal Fixtures (`tests/fixtures/maintain/`)
- `tests/fixtures/maintain/close_proposal_valid.json`: Recorded valid proposal (`close=true`, `expired`, confidence 0.8, rationale) — T7.
- `tests/fixtures/maintain/close_proposal_decline.json`: Recorded decline (`close=false`, other keys ignored).
- `tests/fixtures/maintain/close_proposal_bad_reason.json`: Recorded bad reason (`superseded` outside `HUMAN_SETTABLE_REASONS`).
- `tests/fixtures/maintain/close_proposal_not_object.json`: Recorded answer that parses as JSON but is not an object.
- `tests/fixtures/maintain/close_proposal_empty.txt`: Recorded empty answer.

### Relate Tests (`tests/relate/`)
- `tests/relate/__init__.py`: Marks the relate tests folder as a package.
- `tests/relate/fakes.py`: In-memory port fakes: `FakeLinkLookup`, `FakeEmbedder`, `FakeEmbeddingStore`.
- `tests/relate/test_load_filter_unit.py`: Phase 1 unit tests on the fake port, no DB.
- `tests/relate/test_load_filter_integration.py`: Phase 1 tests on a real SQLite temp DB.
- `tests/relate/test_candidate_pool_unit.py`: Phase 2 unit tests on fakes: signals, merge, ranking, pre-flight, cosine behavior through the public function, the L2 §13 metadata matrix (label equality, no-window labeled branch, both-NULL proxy, mixed-pair exclusion, normalization, blank-as-NULL), and error codes.
- `tests/relate/test_candidate_pool_integration.py`: Phase 2 tests on a real SQLite temp DB: seeded ranking, cache reuse (`embedded_at`/blobs unchanged), pre-flight wipe, graph read failure, and the seeded mixed-corpus §13 matrix (labeled new item with equal-label partners in and far outside the window, a different label, an unlabeled same-day item, plus the unlabeled-new mirror).
- `tests/relate/test_embedding_store_integration.py`: `SqliteEmbedderStore` tests on a real temp DB: float32 round-trip, model names, wipe, read (`RELATE-037`) / write (`RELATE-019`) failures.
- `tests/relate/test_neighbors_integration.py`: `SqliteLinkContext.neighbors_of` tests: Confirmed both directions, Rejected excluded, 1-hop, failure code.
- `tests/relate/test_embedder_adapter_unit.py`: `SentenceTransformerEmbedder` and `validate_embedder_config` tests with a fake model module; no network, no real model.
- `tests/relate/test_relate_cli.py`: `ember relate` CLI checks (boot validation, Phase 2 output, warning to stderr, one `relate rejected: CODE | detail` line per gatekeeper rejection, accepted corrective inverse after a reversal) and exit codes.
- `tests/relate/test_link_gatekeeper_unit.py`: Phase 4 unit tests for the 9 gatekeeper rules, including the rules 8/9 rejection details (blocking link id + endpoints, reversed-duplicate state) on the fake port.
- `tests/relate/test_blocking_link_integration.py`: `SqliteLinkContext.supersedes_blocking_link` tests (hardening 03) on a real temp DB: first connecting edge in id order, both walk directions, reversed and Rejected rows never block, no-path `None`, and `RELATE-021` on a read failure.
- `tests/relate/test_link_proposal_unit.py`: Phase 3 unit tests for parse, retry and the target/source checks.
- `tests/relate/test_run_relate_unit.py`: `run_relate` unit tests on fake ports.
- `tests/relate/test_confirm_write_unit.py`: Phase 4 confirm-loop unit tests.
- `tests/relate/test_relate_integration.py`: Phases 3 + 3.5 + 4 end-to-end on a real SQLite temp DB, plus the corrective-inverse test (hardening 03): after `apply_reversal`, the inverse supersedes passes rule 8 and commits, and the reversed triple stays blocked as `RELATE-009` naming its reversed state.
- `tests/relate/test_link_proposer_adapter_unit.py`: `OpenAiLinkProposer` adapter tests on a fake client, no network.

### AI Answer Fixtures (`tests/fixtures/ai_responses/`)
Saved AI answers for parser tests. Each pair is `case_NN.raw_text.txt` (the source text) + `case_NN.response.json` (the AI's answer).
- `tests/fixtures/ai_responses/case_01.raw_text.txt`: Source text for case 1.
- `tests/fixtures/ai_responses/case_01.response.json`: Case 1 answer, all entries valid.
- `tests/fixtures/ai_responses/case_02.raw_text.txt`: Source text for case 2.
- `tests/fixtures/ai_responses/case_02.response.json`: Case 2 answer, 1 valid + 3 bad entries.

### Query Tests (`tests/query/`)
- `tests/query/__init__.py`: Marks the query tests folder as a package.
- `tests/query/fakes.py`: In-memory port fake `FakeQueryLookup` (records every call) plus the row builders `make_item`, `make_row`, `make_change_row`, `make_link`, and the DB builders `make_v10` / `make_v9`.
- `tests/query/test_current_state_unit.py`: The `current_state` pure core: the status filter, the `challenged` flag, no field leak, and input-order preservation.
- `tests/query/test_tokenize_unit.py`: The shared tokenizer: case folding, punctuation and underscore splitting, unicode letters, digits.
- `tests/query/test_topic_search_unit.py`: BM25 against the hand-computed golden fixture (6 decimal places), the positive-IDF property, the zero-token corpus guard, the tie-break, and the hit fields.
- `tests/query/test_why_unit.py`: Both link directions, Rejected links, a terminating cycle, transitivity with depth, rationale, and the empty case.
- `tests/query/test_history_unit.py`: All 14 documented `(field_changed, trigger_cause)` pairs, the seven status causes, the `unknown` fallback, the `Closed:*` / `Closed:None` splitter, the union and dedup rules, the NULL-subject row, and the `(timestamp, id)` order.
- `tests/query/test_render_unit.py`: The four envelopes: ordering, JSON round-trip, and keys matching the row models.
- `tests/query/test_run_query_unit.py`: The four entry points: the gate runs before any read, the global history view makes no item lookup, and each path reads through the port in the expected order.
- `tests/query/test_query_errors_unit.py`: Codes and names are stable, every class subclasses `QueryError`, and none defines `__init__`.
- `tests/query/test_query_db_open.py`: The read-only boot: missing file not created, non-SQLite file, a real v9 database refused without migrating, the file byte-identical across a query, a write rejected by the handle, and `QUERY-005` on a closed connection.
- `tests/query/test_topic_filter_unit.py`: The topic-search filters in the pure core: the default `TopicFilter` scores every item identically to the no-argument call, status/type narrow the corpus and recompute the scores, and `limit` crops behind the ranking with `0` empty.
- `tests/query/test_topic_filter_cli.py`: The topic-search filter CLI on real temp DBs: the no-flags stdout byte-identical to the pre-amendment golden fixture, the DB hash unchanged across every flag set, the crop-then-count case, and the exit 1 (QUERY-006 `field=`) / exit 2 (Click, no house error line) paths.
- `tests/query/test_history_window_unit.py`: The history window in the pure core (hardening 07): the window applies after the union rule and the sort (a both-branches row appears once, NULL-subject rows stay global-only), `--since` keeps the boundary row and the `+02:00` spelling normalises to the same instant, the accepted spellings are pinned (space separator, fractional seconds, date-only rejected as naive), offset/limit edges (`limit 0` empty, offset past the end `[]`), and `validate_history_page` raising QUERY-007 (`since_length`, never the raw text) and QUERY-006 via the shared helper.
- `tests/query/test_history_window_cli.py`: The history window CLI on real temp DBs: the no-flags stdout byte-identical to the pre-amendment golden fixture for `history` and `history --item 1`, the DB hash unchanged across every flag set including failure paths, the 5-row ledger cases (`--limit 2` count 2, `--offset 4` one row, `--offset 99` empty, `--limit 0` explicit empty, `--since` windows with the boundary kept, the two TZ spellings printed identically) on both views, the both-branches-once CLI case, and the exit 1 (QUERY-007 `since_length=19` naive / `=9` garbage, QUERY-006 `field=`, QUERY-001 unchanged) / exit 2 (Click, no house error line) paths.
- `tests/query/test_search_and_why_integration.py`: `topic-search` and `why` end to end on a real temp DB.
- `tests/query/test_history_integration.py`: `history` over a ledger written by the real Relate and Maintain writers.
- `tests/query/test_query_cli.py`: CLI checks for all four commands: exit codes, `QUERY-001` / `QUERY-002`, and JSON-only stdout.
- `tests/query/test_query_e2e.py`: The one end-to-end chain: capture → relate → maintain → query on a single temp DB with every outside tool faked, all four query documents asserted, and the database hash unchanged by the query phase.

### Query Fixtures (`tests/fixtures/query/`)
- `tests/fixtures/query/bm25_golden.json`: The hand-computed BM25 corpus, query and expected scores, with the derivation notes.
- `tests/fixtures/query/no_flags_golden.json`: Raw stdout captured from the pre-amendment build (item filtering), for the three no-flag commands (`topic-search --query sqlite`, `history`, `history --item 1`) on a temp v10 DB seeded with fixed clock stamps and named ids. The history lines are asserted by `tests/query/test_history_window_cli.py` (hardening 07), the topic-search line by `tests/query/test_topic_filter_cli.py` (hardening 06).

## Scripts (`scripts/`)
- `scripts/measure_model_change.py`: Throwaway measurement asset for issue #12 (not product code). Seeds a synthetic database through the real schema and `tests/fakes.py` helpers, builds the real `bge-base-en-v1.5` embedder, warms the relate Phase-2 vector cache, re-points the cached model name at `all-MiniLM-L6-v2`, then times the real wipe + re-encode + total Phase-2 wall clock with `time.perf_counter`. Args `--items N` (default 500), `--db PATH` (default under `/tmp/opencode/measure14/`). Prints a dated number block the maintainer records on the issue; asserts `MODEL_CHANGED_LINE` on stderr; deletes its throwaway database on the measured paths (the abort paths before the run leave the file for the next run to reset).
- `scripts/ember-key-wizard.sh`: interactive key setup. Walks the human through openrouter.ai and writes `/tmp/opencode/ember.env` (mode 600, outside the repo, deleted after real runs). Run it whenever a real-key command needs the key.

## Database Tables (SQLite)
- `schema_version`: Holds the applied migration number.
- `sources`: Immutable raw input texts. Columns `id`, `title`, `full_text`, `timestamp`, `content_hash` (unique, the dedup key).
- `items`: Confirmed typed items. Columns `id`, `type`, `statement`, `source_id` (foreign key to `sources.id`), `status`, `created_at`, `validated` (set only on Assumption rows), `rationale` (Decision text), `source` (Finding evidence text), `close_reason` (why closed; one of 5 reasons, NULL when open), `status_origin` (`derived` or `manual`), and `metadata` (nullable project label from migration 012, written by capture, read by relate's metadata signal, NULL means unlabeled).
- `change_log`: Append-only ledger. Columns `id`, `item_id`, `link_id` (foreign key to `links.id`), `field_changed`, `old_value`, `new_value`, `timestamp`, `trigger_cause`. Maintain writes `field_changed` values `status`, `status_origin`, `link_reversed`, `rationale` / `source` (`edit-item`), and `link_removed` (`remove-link`).
- `ai_responses`: Raw AI answers, stored verbatim. Columns `id`, `source_id` (nullable foreign key to `sources.id`), `item_id` (nullable foreign key to `items.id`), `response_text`, `timestamp`.
- `links`: Typed directional edges. Columns `id`, `source_item_id`, `target_item_id`, `link_type`, `status` (`Confirmed` or `Rejected`), `created_at`, and `reversed_at` (NULL live, non-NULL reversal timestamp, migration 011; written only by maintain's paired reversal write). Unique per source/target/type.
- `item_embeddings`: Rebuildable vector cache. Columns `item_id`, `vector`, `model_name`, `embedded_at`.

## Empty Folders
These folders exist but hold no files yet.
- `draft/`: Working drafts.
- `reports/`: Generated reports.
- `research/`: Research notes.

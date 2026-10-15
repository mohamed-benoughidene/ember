# Project Context Management System — V1 Specification (AI Version)

Target reader: AI system. Style: compressed, dense, unambiguous. Zero fluff.

## 1. System Definition

System store project context. Context = persistent knowledge altering project understanding or decisions.
System not store project artifacts (code, binaries, design files, raw datasets).
System store durable knowledge *about* project artifacts and actions.

Boundary exclusions:
1. Outputs (code, design files, builds, documents).
2. Execution (tasks, tickets, sprint backlogs, timelines).
3. Operational data (runtime logs, telemetry, metrics).
4. Raw source corpora (full PDFs, audio recordings). Store only extracted knowledge plus source text reference.
5. Transient chatter (brainstorming, temporary chats).
6. Secrets (API keys, passwords, credentials).

## 2. Full Architecture (Target Vision)

Nine context item categories:
- Decision: Choice project made.
- Assumption: Premise project currently believes, unproven.
- Finding: Fact discovered via work, test, observation.
- Question: Unknown project needs resolved.
- Constraint: Boundary or limitation governing project.
- Issue: Problem or defect requiring attention.
- Evidence: Data supporting or contradicting claim.
- Rationale: Justification for decision.
- Reasoning: Explanatory logic behind conclusions.

Four core operations:
1. Capture: Filter input, classify category, extract meaning, record provenance, initialize state.
2. Relate: Detect candidates, evaluate relationship, store typed directional edge.
3. Maintain: Trace consequences, flag invalidations, keep graph coherent, preserve history.
4. Query: Retrieve relevant items, traverse graph, filter by state, return context view.

---

## 3. V1 Specification (Active Operational Rules)

Section 3 supersedes Section 2 wherever conflicts exist for V1.

### 3.1 Item Types (4 Active)
V1 active types:
1. `Decision`
2. `Assumption`
3. `Finding`
4. `Question`

Field mappings for deferred types:
- `Rationale` stored as text field on `Decision`.
- `Evidence` stored as source field on `Finding`.
- Deferred from V1: `Constraint`, `Issue`, `Evidence` (as standalone type), `Rationale` (standalone type), `Reasoning` (standalone type).

### 3.2 Status Model
Single shared status field for all 4 types:
- `Active`: Current valid knowledge.
- `Challenged`: Shaky knowledge needing recheck. Triggered by Maintain rules or set manually by human.
- `Closed`: Concluded item. Requires close reason: `answered`, `invalidated`, `superseded`, `reversed`, `expired`.

Deletion forbidden. Historical items immutable.

### 3.3 Relationships (5 Active Types)
Typed, directional links between item pairs:
1. `supports`: Source `Finding` -> Target `Assumption` or `Decision`.
2. `contradicts`: Source `Finding` -> Target `Assumption`, `Decision`, or `Finding`.
3. `depends_on`:
   - Source `Decision` -> Target `Assumption`, `Finding`, or `Decision`.
   - Source `Assumption` -> Target `Finding` or `Assumption`.
4. `supersedes`: Source item -> Target item of identical type. Target must not be `Closed`. Loops forbidden.
5. `answers`: Source `Finding` or `Decision` -> Target `Question`.

Global link rules:
- No self-links (`source_id != target_id`).
- No duplicate links (`source_id`, `target_id`, `type` must be unique).
- Both items must exist in store.
- Premise rule: Decision or Assumption resting on premise MUST use `depends_on`. `supports` from `Assumption` rejected.

Relationship status & approval:
- AI proposes candidate pair at save time.
- Script infers relationship type via compatibility table. User picks if multiple valid types exist.
- User accepts or rejects on spot.
- Accepted = status `Confirmed`.
- Rejected = status `Rejected` (stored permanently to prevent repeat suggestions).
- No stored `Proposed` state in DB.

Deferred links: `informs`, `constrained_by`, `invalidates`, `raises`, `derived_from`.
("invalidates" handled via `contradicts` link plus closing target as `invalidated`).

### 3.4 Candidate Discovery (Scripted, Zero AI)
Trigger: New item save.
Discovery pipeline:
1. Content signal: Dense vector embedding via local `bge-base-en-v1.5`. Top 10 by cosine similarity form initial candidate pool. BM25 keyword matching excluded from candidate selection.
2. Graph signal: Traverse existing graph links from neighbor items.
3. Metadata signal: Filter by project area, temporal proximity, type compatibility table.

AI role: Read candidate pool, propose pairs only. AI never selects candidates, never invents link types.

### 3.5 Maintain Rules (Deterministic, Zero AI)
Four fixed event triggers:
1. `supersedes` confirmed -> Target old item marked `Closed` with reason `superseded`.
2. Item `Closed` with reason `invalidated`, `superseded`, or `reversed` -> All items directly having `depends_on` link pointing to closed item set to `Challenged`.
3. `contradicts` confirmed -> Target item set to `Challenged`. Link direction chosen by user during accept.
4. `answers` confirmed -> Target `Question` closed with reason `answered`.

Flag spreading limit: Single-step only. Challenged items do NOT cascade Challenged status to secondary dependents.
Human actions:
- User manually resolves Challenged items via `set_status`.
- User sets/clears `validated` flag on `Assumption`. Validated assumption remains `Active`.
- Reversing `supersedes` link: Target old item returns to `Active`. Dependents flagged Challenged remain Challenged until human clears.

### 3.6 Storage Architecture
- Engine: Local single-file SQLite DB. Foreign key enforcement ON (`PRAGMA foreign_keys = ON;`).
- Schema integrity: Constraints / triggers enforce compatibility table rules.
- Change log: Append-only ledger table (`item_id`, `field_changed`, `old_value`, `new_value`, `timestamp`, `trigger_cause`). Immutable, append-only.
- Source storage: Separate table for full source texts (`id`, `title`, `full_text`, `timestamp`). Items link to source ID.
- Plain text export: Read-only CLI export script dumps DB to formatted text file.

### 3.7 AI Boundary & Gatekeeper Scripts
AI direct DB write access: PROHIBITED. All mutations pass gatekeeper validation scripts.

AI-callable proposals (Require user confirmation):
1. `add_item`: Validates 4 allowed types. Checks source quote existence in stored source text. Scans near-duplicates via text similarity warning. Generates ID, timestamp, default `Active` status.
2. `add_link`: Validates pair against compatibility table. Checks both IDs exist. Requires user accept/reject.
3. `close_item`: Executes deterministic Maintain cascade. User confirms.
4. `query`: Read-only. Returns raw stored items/links. No data mutation.

Human-only operations:
1. `edit_item`: Modify wording or source link.
2. `set_status`: Manual state change (`Active` <-> `Challenged`).
3. `set_validated`: Set/clear `validated` flag on Assumption.
4. `remove_link`: Remove confirmed relationship edge.

### 3.8 Query Operations
Four read-only query modes:
1. `current_state`: Returns items with status `Active` + `Challenged`. `Challenged` items displayed first with explicit warning flags. `Closed` omitted.
2. `topic_search`: BM25 keyword search over item statements. Returns ranked list of item IDs.
3. `why`: Traverses backward dependency links (`depends_on`, `supports`, rationale) from item ID.
4. `history`: Reads append-only change log. Displays chronological field mutations and causes.

Query output format: Structured lists of stored items and relationships. Zero AI-written prose summaries in V1.
Live AI chat access: Read-only query execution permitted during interactive sessions.

### 3.9 Post-Build Live Measures
Four metrics evaluated during live deployment:
1. Capture quality on raw/messy chat transcripts (evaluate prompt v3 extraction yield).
2. Human approval prompt fatigue rate (batch prompts if frequency excessive).
3. Dense vector candidate recall scale test (500–5000 items).
4. Author ground-truth data provision for initial 20 benchmark items.

# Project Context Management System (V1 Specification)

This document describes how our project stores and manages its knowledge over time. It is written for human builders and contributors.

---

## 1. What This System Does

When a team works on a project, people make decisions, discover facts, test assumptions, and ask questions. Over time, that knowledge gets lost in chat logs or memory. 

This system stores that durable knowledge so anyone—human or AI—can understand what the project knows, why decisions were made, and what is currently uncertain.

### What Stays In
We store durable knowledge that changes how the project is understood or what decisions should be made:
- Choices we decided on.
- Premises we believe but have not yet proven.
- Facts discovered from tests or research.
- Unresolved questions.

### What Stays Out
We do not store project artifacts or temporary chatter:
1. **Project Outputs:** Raw code, image designs, binaries, and built documents. Context records knowledge *about* code, not the code files.
2. **Task Execution:** To-do lists, sprint tickets, assignees, and deadlines. These answer "what are we doing today?", not "what do we know?".
3. **Operational Telemetry:** Server logs, CPU metrics, and traffic monitors.
4. **Mass Source Corpora:** Gigabyte datasets or full video recordings. We store the extracted insight and keep a reference copy of the text.
5. **Temporary Chat:** Casual banter, brainstorming spitballs, and side talk.
6. **Secrets:** API keys, passwords, and private tokens.

---

## 2. The Full System Architecture (Long-Term Vision)

The complete vision for the system contains nine knowledge categories and four major operations.

### Nine Long-Term Knowledge Categories
- **Decision:** A deliberate choice made for the project.
- **Assumption:** A belief we rely on that is not yet proven true.
- **Finding:** A verified discovery from tests, data, or real observation.
- **Question:** An important unknown that must be answered.
- **Constraint:** A boundary or limitation we must obey.
- **Issue:** A defect, conflict, or problem needing resolution.
- **Evidence:** Concrete material that supports or disputes a statement.
- **Rationale:** The specific reason behind an accepted choice.
- **Reasoning:** The explanatory thinking connecting several conclusions.

### Four Core Operating Engines
1. **Capture:** Receives raw information, filters out noise, classifies the idea, and creates an official context item.
2. **Relate:** Discovers links between items and records directional relationships (such as "supports" or "contradicts").
3. **Maintain:** Watches for changes and updates statuses when older items are invalidated, superseded, or questioned.
4. **Query:** Retrieves items and relationships to give the user a clear picture of any topic or past choice.

---

## 3. The V1 Operating System (Active Rules)

To keep V1 rock-solid, predictable, and simple to build, we streamline the system down to fixed rules. Wherever this section differs from the long-term vision above, **this section wins for V1**.

### 3.1 Four Active Knowledge Types
In V1, we track only four categories:
1. **Decision:** A choice the project adopted. Rationale is stored directly inside the Decision as an explanation field.
2. **Assumption:** A premise we are acting on without complete proof.
3. **Finding:** A concrete discovery from real testing or observation. Evidence is stored as a source reference on the Finding.
4. **Question:** An unresolved question that blocks or informs a path.

*Deferred:* Standalone Constraints, Issues, Evidence, Rationales, and Reasoning are deferred to later versions.

### 3.2 Single Shared Status Model
Every item uses one shared status field:
- **Active:** Current, accepted project knowledge.
- **Challenged:** Shaky knowledge. An item becomes Challenged when an item it depends on is closed, when a confirmed contradiction points at it, or when a human marks it by hand.
- **Closed:** Retired or concluded knowledge. A closed item must have one of five reasons: `answered`, `invalidated`, `superseded`, `reversed`, or `expired`.

**Rule:** Items are never erased or deleted from the database. History is kept forever.

### 3.3 Five Allowed Relationships
Items connect to each other through five strict, directional links:

| Link Name | Source Type | Target Type | Meaning |
|---|---|---|---|
| `supports` | Finding | Assumption or Decision | Evidence backs up an assumption or choice |
| `contradicts` | Finding | Assumption, Decision, or Finding | Evidence conflicts with an existing statement |
| `depends_on` | Decision or Assumption | Assumption, Finding, or Decision | One choice or premise rests upon another item |
| `supersedes` | Same type as target | Same type as source | A new item replaces an older active item |
| `answers` | Finding or Decision | Question | A finding or choice resolves an open question |

#### Link Rules
- No item can link to itself.
- Duplicate links between the same two items are blocked.
- If a Decision or Assumption rests on another item as its premise, you must use `depends_on` (not `supports`).
- A `supersedes` link is only valid if the target item is currently active (not already closed), and circular replacement chains are rejected.

### 3.4 Candidate Discovery Without AI Guesswork
When a new note is being saved, the system searches existing notes to see what might be related:
1. **Embeddings:** A local mathematical text matcher (`bge-base-en-v1.5`) finds the top 10 most semantically similar notes.
2. **Graph Signals:** The script checks neighbors already connected in the database.
3. **Field Matching:** The script checks project topic and allowed link types from our table.

**Safety Rule:** Finding candidate items uses deterministic code, never AI imagination. The AI only reviews the top 10 candidates found by the script and suggests pairs. The human approves or rejects each pair on the spot.

### 3.5 Maintain Engine: Four Deterministic Rules
When notes change, status updates happen by code, not by AI discretion:
1. **When a `supersedes` link is confirmed:** The old note is automatically Closed with the reason `superseded`.
2. **When an item is Closed as `invalidated`, `superseded`, or `reversed`:** Every item that directly uses `depends_on` pointing to that item automatically switches to `Challenged`.
3. **When a `contradicts` link is confirmed:** The target note becomes `Challenged`. The human selects the direction when accepting the link.
4. **When an `answers` link is confirmed:** The Question note is automatically Closed with the reason `answered`.

#### Safety Limits on Flag Spreading
In V1, the `Challenged` flag spreads only **one step**. If note B becomes Challenged because note A was closed, note C (which depends on B) is not automatically changed. This keeps ripple effects small and predictable. The user inspects the Challenged list to resolve items.

### 3.6 Storage in SQLite, Change Log, and Source Copies
- **Local SQLite Database:** All notes, relationships, sources, and changes live in a single SQLite database file on your local machine. No external database server is needed.
- **Foreign Key Enforcement:** SQLite foreign key checks are turned ON on every connection to prevent orphaned or broken links. Database constraints prevent impossible link combinations.
- **Append-Only Change Log:** Every change to a note or link adds a row to an audit ledger (`item_id`, what changed, old value, new value, date, and cause). Nothing in this log is ever edited or deleted.
- **Stored Copies of Sources:** The system saves the full text of source documents or chat conversations in a dedicated table. Findings point to their source record. An optional quote check verifies that cited quotes actually exist verbatim in the stored source text. A secret scanner flags passwords, tokens, or private keys before a source is saved.
- **Plain-Text Export:** A read-only export script dumps the database into a clean text file so you can read your project context without opening a database tool.

### 3.7 AI Boundaries and Gatekeeper Scripts
To prevent AI hallucinations from corrupting project memory:
- **AI never writes directly to the database.**
- All changes must pass through gatekeeper scripts that check inputs, verify IDs, and enforce rules.

#### AI Proposal Actions (Must be confirmed by the human)
- `add_item`: Proposes a new note. The script checks for near-duplicate wording and verifies that any cited quotes exist in the stored source text.
- `add_link`: Proposes a relationship between two notes. The script checks the compatibility table and asks the user to accept or reject. Rejected suggestions are recorded permanently so you are never asked about them again.
- `close_item`: Proposes retiring an item. Triggers the maintain rules upon human confirmation.
- `query`: Runs a read-only search and returns stored notes.

#### Human-Only Actions
Only a human can:
- Edit the text or source reference of an existing note (`edit_item`).
- Manually change status between Active and Challenged (`set_status`).
- Mark an Assumption as validated (`set_validated`).
- Delete a confirmed relationship link (`remove_link`).

### 3.8 Querying Project Context
Users and AI sessions can inspect context through four read-only modes:
1. **Current State:** Lists all Active and Challenged items. Challenged items appear first at the top with warning badges so you immediately see uncertain areas.
2. **Topic Search:** Keyword search (BM25) over note text to find matching notes.
3. **Why:** Walks backward through `depends_on` and `supports` links to explain why a decision was reached.
4. **History:** Reads the change log to show what changed, what it was before, when it changed, and what caused the change.

**Rule:** Query outputs in V1 are returned as clean, structured lists of items and links. The AI does not generate freeform prose summaries for queries in V1.

---

### 3.9 Four Measures to Track in Live Project Use
Four specific behaviors cannot be measured in a lab and must be evaluated during real project work:
1. **Real-Chat Capture Quality:** Test the capture prompt on a messy conversation to verify it extracts real reasons and findings.
2. **Confirmation Fatigue:** Track how many times the system asks the human to accept or reject links in a session. If too high, batch the review questions.
3. **Candidate Search at Scale:** Test embedding search accuracy once the store reaches 500 to 5,000 notes.
4. **Author Input on Benchmark Notes:** Fill in missing real reasons and sources on the initial 20 test notes when the author provides them.

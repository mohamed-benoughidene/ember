# Ember

Ember preserves the evolving state of what a project knows, believes, decides, and learns. This glossary holds the shared language of the project. Terms that only one engine uses are explained in that engine's plan in `plans/`.

## Language

### The knowledge and its containers

**Knowledge base**:
Everything a project knows in Ember: the items, the links between them, and the ledger of every change. It is kept in one local file.
_Avoid_: the database, the DB (say "the knowledge base file" when the file itself is meant). Command and flag names such as `--db` and `db-check` keep the word "database", because those names are fixed.

**Ledger (the change log)**:
The append-only record of every change ever made to the knowledge base. The ledger is the source of truth: what Ember shows about an item's current state is derived from it.
_Avoid_: audit log, history table

**Item**:
One unit of what the project knows: a Decision, Assumption, Finding, or Question, tied to a source.
_Avoid_: card, record, entry, note

**Link**:
One confirmed relationship between two items (supports, contradicts, supersedes, answers, depends_on). Removed links keep their ledger history and are marked, never deleted.
_Avoid_: edge, relation

**Source**:
The raw text given to Ember, such as a chat or a document, kept word for word. Every item points back to the source it came from.
_Avoid_: input

### Where an item stands

**Status**:
Where an item stands: Active (still counts), Challenged (needs a second look), or Closed (finished, with a close reason).
_Avoid_: state

**Close reason**:
Why an item was Closed: answered, invalidated, superseded, reversed, or expired.
_Avoid_: resolution

**Validated**:
A mark that a person has verified an Assumption. Only an Assumption can carry it.
_Avoid_: confirmed (confirming is for proposals)

### How knowledge gets in and stays true

**Proposal**:
An item or link that the AI suggests. Nothing is saved until you confirm it.
_Avoid_: suggestion, draft

**Confirm**:
Your yes to one proposal. Only confirmed proposals are saved.
_Avoid_: approve

**Gatekeeper**:
The fixed checks, with no AI, that every proposal and every change must pass before it is saved.
_Avoid_: validator, filter

**Sweep**:
One run of the fixed rules that updates item statuses from the confirmed links.
_Avoid_: refresh, recompute

**Engine**:
One of Ember's five parts, each with one job: Capture, Relate, Maintain, Query, and Utility.
_Avoid_: module, service

### Keeping the knowledge safe (ruled 2026-10-29, issue #18 discussion)

**Backup**:
A file copy of the knowledge base, taken at a chosen moment, restorable by pointing Ember back at it. Answers the fear "I broke or lost my working Ember."
_Avoid_: export (an export is for reading, not restoring)

**Restore**:
Pointing Ember at a backup file again (by copying it back or with `--db`). Ember deliberately has no restore command: restore must never silently overwrite live knowledge.
_Avoid_: import, load backup

**Export**:
A human-readable rendering of the whole knowledge base into a plain text file, readable without Ember, forever. Answers the fear "Ember died and nothing can read my knowledge." Cannot be restored into Ember. That is the Backup's job.
_Avoid_: dump (ambiguous between this and Backup)

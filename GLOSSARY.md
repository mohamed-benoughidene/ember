# Ember

Ember preserves the evolving state of what a project knows, believes, decides, and learns. This glossary holds the project's language, in two places: here (shared terms) and each engine's amendment tables for engine-specific vocabulary.

## Language

### The knowledge and its containers

**Knowledge base**:
Everything a project knows in Ember: the items, the links between them, and the ledger of every change. It lives in one SQLite file.
_Avoid_: the database, the DB (say "the knowledge base file" when the file itself is meant)

**Ledger (the change log)**:
The append-only record of every change ever made to the knowledge base. The ledger, not any column, is the source of truth; columns are derived from it.
_Avoid_: audit log, history table

**Item**:
One unit of what the project knows: a Decision, Finding, Assumption, Question, or Metric, tied to a raw source.
_Avoid_: card, record, entry

**Link**:
One confirmed relationship between two items (supports, contradicts, supersedes, answers, depends_on). Removed links keep their ledger history and are marked, never deleted.
_Avoid_: edge, relation

### Keeping the knowledge safe (ruled 2026-10-29, issue #18 discussion)

**Backup**:
A file copy of the knowledge base, taken at a chosen moment, restorable by pointing Ember back at it. Answers the fear "I broke or lost my working Ember."
_Avoid_: export (an export is for reading, not restoring)

**Restore**:
Pointing Ember at a backup file again (by copying it back or with `--db`). Ember deliberately has no restore command: restore must never silently overwrite live knowledge.
_Avoid_: import, load backup

**Export**:
A human-readable rendering of the whole knowledge base into a plain text file, readable without Ember, forever. Answers the fear "Ember died and nothing can read my knowledge." Cannot be restored into Ember; that is the Backup's job.
_Avoid_: dump (ambiguous between this and Backup)

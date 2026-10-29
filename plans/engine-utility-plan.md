# Engine E L2 Plan: Utility (backup, export)

Status: APPROVED (maintainer gate passed 2026-10-29: rotation chosen (option A), L1 amendment approved); L3 steps start next
Origin: maintainer decision, working session 2026-10-29 (backup-vs-export discussion; vocabulary provisionally recorded in GLOSSARY.md)
Glossary: `GLOSSARY.md`, section "Keeping the knowledge safe" (Backup / Export / Restore)
Branch: `feat/data-safety` (from `main` at `de245d0`)

## §1 Purpose (one job)

Keep the knowledge base safe and portable: **Backup** answers "I broke my working
Ember" (restorable file copy), **Export** answers "Ember died and nothing reads my
files anymore" (human-readable text, readable forever, not restorable by design).
Neither command writes to the live database, ever. Both are **human-only commands**:
neither joins the L1 AI-callable list, and export stays AI-safe only in the sense
that query already has (read-only); backup is for humans at a keyboard, full stop.

## §2 L1 amendment (governance)

L1 defines four engines (Capture, Relate, Maintain, Query) connected by data flow
through the pipeline. Utility is not a phase of that pipeline: it has no inter-engine
contract and calls no AI. Proposed single-line L1 amendment, subject to maintainer
approval at this plan's review gate:

> **Amendment (2026-10-29, APPROVED by maintainer; applied to plans/master-plan.md §8):** A fifth standalone module, Engine E: Utility, holds
> commands outside the capture→relate→maintain→query pipeline, human-only, implemented
> in the adapters layer following the `ember/adapters/db_check.py` precedent (a
> self-contained store-adjacent tool that opens the database itself). It shares the
> storage engine (SQLite, ledger) and inherits L1's read-write invariants; boot engine
> floors apply at normal engine opens, not at the backup snapshot path (§4.1). It
> defines no inter-engine data flow; its two commands are leaves on the CLI, layered
> UI → logic → data (Constitution P2), and they never mutate the live database
> (backup snapshots it read-only, export reads it read-only).

Stack: unchanged (Python, stdlib `sqlite3`, Click). No new dependency. No schema
change, schema stays v12, floors stay relate 12 / maintain 11 / query 10.

## §3 Module layout (Constitution T9 conformance, adjudicated)

No new `ember/utility/` package. Draft v1 typed `sqlite3.Connection` inside a core
package, which would fail the architecture test (`tests/test_architecture.py` forbids
sqlite3 outside adapters) and inverted the repo's real layering (CLI bodies open the
database, core receives data). The controlling precedent is `ember/adapters/db_check.py`:
a self-contained tool whose whole job IS SQLite, living in adapters, opening by path.
Both commands are exactly that shape:

```
ember/adapters/errors.py      (new per-package errors home: BackupError BACKUP-000,
                               ExportError EXPORT-000, plus their leaves)
ember/adapters/backup.py      (create_backup(source_path, target_path) -> BackupReport)
ember/adapters/export.py      (gather_export(conn) -> ExportData, render_export(data) -> str)
tests/test_backup.py          (mirrors test_db_check.py's flat style)
tests/test_export.py
```

`render_export` is filed in adapters (like db_check's report assembly) but is a pure
function: `ExportData` in, fixed text out, no I/O, no clock — unit-testable in
isolation (T1). The CLI bodies in `ember/cli.py` stay thin: backup is one call;
export opens via the existing `open_query_database` (QUERY-003/004 semantics) and
then calls gather → render → emit.

## §4 CLI surface (Rule S1 samples)

```
$ ember backup /tmp/opencode/ember-backup.db --db ember.db
backup written: /tmp/opencode/ember-backup.db (schema v12, 42 items)      [exit 0]

$ ember backup /tmp/opencode/ember-backup.db --db ember.db   # again, next week
backup written: /tmp/opencode/ember-backup.db (schema v12, 43 items)      [exit 0]
      (previous copy now at /tmp/opencode/ember-backup.db.old-1 — rotation, see §5.1)

$ ember export --db ember.db --out /tmp/opencode/ember.txt
exported 42 items, 17 links, 310 ledger rows, 12 sources -> /tmp/opencode/ember.txt      [exit 0]

$ ember export --db ember.db --out ember.db
error: EXPORT-002 OverwriteRefused | ember.adapters.export.refuse_self_overwrite | output path is the knowledge base file | db_path=ember.db out=ember.db      [exit 1]

$ ember export --db ember.db | head -8        # default is stdout
# Ember knowledge base export
# schema version: 12
# as of (latest ledger event): 2026-10-29T11:04:55Z
# counts: 42 items, 17 links, 310 ledger rows, 12 sources
# embeddings and AI responses are derived, rebuildable data (D2) and are not exported.
...
```

Both commands are standalone (S1): single command, sample input, inspectable output.
`backup --help` ends with: "Restore: copy the file back, or point Ember at it with
`--db`. There is deliberately no restore command (GLOSSARY)." `export --help` ends
with: "This file is for reading without Ember. It is not restorable into Ember;
that is the backup's job (GLOSSARY)."

## §5 Internal pipelines

### §5.1 Backup (`ember/adapters/backup.py`)

```
phase 1: precheck & rotate -> phase 2: open source -> phase 3: snapshot -> phase 4: verify -> phase 5: report
```

| Phase | In (typed) | Out (typed) | Failure |
|---|---|---|---|
| 1 precheck & rotate | `source_path, target_path: str` | rotation performed or refused | BACKUP-003 (target not preparable: rename failed, target is a directory, ...) |
| 2 open source | `source_path: str` | read-only `sqlite3.Connection` (adapter layer; db_check precedent) | BACKUP-001 (missing/not SQLite), BACKUP-002 (opens but unreadable schema/items) |
| 3 snapshot | open source conn, target path | new file at target path | BACKUP-003 (write failed; the partial copy is deleted) |
| 4 verify | target path | `(schema_version: int, item_count: int)` | BACKUP-004 (does not read back; the copy is deleted, exit 1) |
| 5 report | verify result | `BackupReport(path, schema_version, item_count, rotated)` | — |

**Rotation (adjudicated, replaces draft v1's refuse-overwrite).** The review panel
showed refuse-with-`--force`-absent means a weekly `ember backup ~/backups/ember.db`
needs a manual `mv` every single week, forever (the migration runner's `.bak-v`
retention only fires at schema upgrades, so it provides no history here). New rule,
no flags (I2): if the target exists, it is renamed into a `.old-<N>` rotation beside
it (newest `.old-1`, keeping the newest 3, oldest deleted), mirroring the product's
existing `.bak-v` retention convention. The live/previous backup is moved, never
silently destroyed beyond the declared depth-3 policy, and the report line names
the rotation when it happened. Undo for any rotation: `mv <target>.old-1 <target>`.
Refusal stays only where rotation cannot make the target safe (BACKUP-003).

**Verification kept, delete-on-fail kept.** A dedicated backup command's whole value
is "you will trust this file when things break", so one cheap read-back (open,
schema_version, item count) earns its ~10 lines; and on failure the broken copy is
deleted so a false backup never sits where safety is expected. The command then
exits 1 with BACKUP-004.

Design rules: the snapshot must use the sqlite3 online backup API
(`Connection.backup`), never `shutil.copy`: the online API copies a consistent page
image even if a writer was mid-transaction. The source is opened read-only and only
`schema_version` / item-count readability is checked — **no engine floors**
[deliberate asymmetry, verified safe by the panel: backup of an older-schema file
stays restorable because boot auto-upgrades on restore; refusing to back up an old
file would leave the user with nothing. Export enforces floors; backup does not.]

### §5.2 Export (`ember/adapters/export.py`)

```
phase 1: gather -> phase 2: render -> phase 3: emit (with self-overwrite guard)
```

| Phase | In (typed) | Out (typed) | Failure |
|---|---|---|---|
| 1 gather | `sqlite3.Connection` (opened by the CLI via `open_query_database`: read-only, floors QUERY-003/004) | `ExportData` (named model: items, links, sources, ledger, schema_version) | reuses QUERY-003/QUERY-004 |
| 2 render | `ExportData` | `str` (pure, deterministic, no clock) | — |
| 3 emit | text, optional `--out` path | stdout or file | EXPORT-001 (cannot write), EXPORT-002 (out path is the DB itself) |

**EXPORT-002 (found severe by the error audit):** `open(path, "w")` truncates before
refusing, so `--out <the-db>` would erase the live knowledge base with exit 0. The
emit phase therefore refuses, before opening anything, when the output path
normalizes to the database path (resolved-path compare plus `os.path.samefile` when
the target exists). Exit 1, database untouched.

Render is pure core: its only input is `ExportData`, so two exports of one database
are byte-identical by construction. No wall clock anywhere in the output: the
header's "as of" is the max ledger timestamp. Section order fixed: header, items
(id order), links (id order), sources (id order), ledger (timestamp, then id). All
fields exported for every row, including removed/reversed links, close_reason,
status_origin, metadata, validated. Raw source text verbatim between explicit
BEGIN/END markers (indentation would destroy leading whitespace). Full ledger
values, no truncation: the export is the record; a truncated record is a lossy
summary. Deliberately excluded: `item_embeddings` and `ai_responses` (derived and
rebuildable per D2; the header states the exclusion). Source blocks also carry the
source's own timestamp (the review panel's "grieving reader" check).

## §6 Error codes (new namespace, following I17: stable, never reused)

| Code | Name | Raised at |
|---|---|---|
| BACKUP-000 | BackupError | namespace base, never raised directly |
| BACKUP-001 | SourceOpenFailed | §5.1 phase 2 (missing or not a SQLite file) |
| BACKUP-002 | SourceInvalid | §5.1 phase 2 (opens but schema/items unreadable) |
| BACKUP-003 | TargetWriteFailed | §5.1 phases 1+3 (target not preparable or snapshot write failed; partial file deleted) |
| BACKUP-004 | VerifyFailed | §5.1 phase 4 (copy does not read back; copy deleted) |
| EXPORT-000 | ExportError | namespace base, never raised directly |
| EXPORT-001 | OutputWriteFailed | §5.2 phase 3 (`--out` path not writable) |
| EXPORT-002 | OverwriteRefused | §5.2 phase 3 (`--out` is the knowledge base file itself) |

Existing codes reused for the same meanings (I17 forbids reusing a code for a
*different* meaning): QUERY-003 (db missing), QUERY-004 (schema below floor) on
export, raised by the existing `open_query_database`; the CLI-wide `EmberError`
handling prints them identically. Splitting open-fail from invalid-source follows
the audit finding that one code for two different fixes violates I17's spirit.

## §7 Test targets (T1-T4 pyramid; all offline, no keys)

1. Unit on pure render: given a constructed `ExportData`, assert section order,
   determinism (render twice, byte-identical), verbatim source block with leading
   whitespace and non-ASCII preserved, removed/reversed links labelled, full
   (untruncated) ledger values, header counts correct.
2. Integration on real temp SQLite files: backup creates a usable copy (same
   schema_version, same item count read back); second backup to the same target
   rotates to `.old-1` and reports it; third and fourth to depth 3, oldest gone,
   still exit 0; source file byte-identical before/after a backup (hash proof);
   verify-failure and snapshot-failure delete the partial copy (BACKUP-003/004);
   export leaves the DB byte-identical (hash proof); every seeded row of items,
   links, sources, change_log appears in the export text; EXPORT-002 refuses
   `--out <the-db>` leaving the DB byte-identical; QUERY-004 on a below-floor file;
   backup of a v9 file succeeds (no floors, by design).
3. CLI checks (S1): the §4 samples asserted with exit codes; tests per T3 with real
   temp files (no mocks); isolation per S2 (`tests/test_backup.py`, `tests/test_export.py`,
   mirroring `test_db_check.py`).
4. E2E: ticket U5 (restore round trip on real data, human-executed proof closing #18).

## §8 Deferred to L3

- Exact helper names below the two public functions (L3's discretion, bounded by §5
  contracts). L3 steps: `plans/steps/utility/step-01-backup.md`,
  `step-02-export.md`, each committing separately.
- Fixture file names for the verbatim-source test (`tests/fixtures/`).
- README wording and PROJECT_MAP lines (drafted at build time, reviewed in U4).
- Deferred items inherited from L1 that this L2 does **not** resolve: external vector
  DB at scale (#4, excluded by maintainer), embedder model swap (measured, deferred,
  master-plan §9). This L2 resolves neither and introduces no new L1-deferred item.

## §9 Findings and adjudications (review log, ticket U0)

| # | Axis | Finding | Disposition |
|---|---|---|---|
| 1 | spec | Origin line cited #18 as if ruled on GitHub; #18 has no comment; the ruling was in-session | Applied: origin line reworded (session + GLOSSARY) |
| 2 | spec | §2 said "inherits schema floors" while §4.1 skips floors for backup | Applied: amendment reworded (read-write invariants inherited; floors at normal opens) |
| 3 | spec | Floors asymmetry breaks no documented invariant; backup of v9 restorable | Confirmed as designed; test added (§7.2 backup of a v9 file) |
| 4 | spec | Commands must be explicitly human-only vs the L1 AI-callable list | Applied: stated in §1 |
| 5 | spec | "Machine-only per D2" overstates D2 | Applied: reworded "derived and rebuildable per D2" |
| 6 | const | sqlite3 typed inside a core `ember/utility/` package would fail T9 / invert layering | Applied: §3 rewritten — modules live in `ember/adapters/` after the `db_check.py` precedent; no new package |
| 7 | const | Opening the DB inside a core runner inverts CLI→logic→data | Applied: export's CLI opens via `open_query_database`; backup opens inside the adapter, as db_check does |
| 8 | const | §Z claimed all expected failures live in utility/errors.py, false for reused QUERY codes; D7 called "the D7 mechanism" overstated | Applied: §6 wording and D7 line corrected ("D7 enabled") |
| 9 | errors | Severe: `--out ember.db` truncates the live DB with exit 0 | Applied: EXPORT-002 OverwriteRefused + samefile/normalized-path guard + test |
| 10 | errors | Disk-full mid-snapshot mislabeled as source failure and leaked a partial file | Applied: BACKUP-003 TargetWriteFailed covers both target phases; partial file deleted |
| 11 | errors | BACKUP-002 was one code for two different fixes (open-fail vs unreadable) | Applied: split into BACKUP-001/BACKUP-002 |
| 12 | errors | Namespace lacked the base-class pattern every other engine has | Applied: BACKUP-000 / EXPORT-000 bases |
| 13 | errors | Sample error line didn't match real `log_line()` shape | Applied: §4 sample fixed |
| 14 | over | Refuse-overwrite guarantees weekly manual `mv` friction (`--force` absent, I2 forbids a flag) | Adjudicated: rotation replaces refusal (§5.1), consistent with the `.bak-v` depth-3 convention; undo is one `mv`. **MAINTAINER RULING 2026-10-29: option A, rotation approved** |
| 15 | over | Verify's delete-on-fail choreography over-promises | Adjudicated: kept, deliberately — a false backup must never sit where safety is expected; failure exits 1 (BACKUP-004) |
| 16 | over | L1 amendment, named models, export field completeness | Adjudicated: all kept as written (one honest sentence, I4 returns, "export is the record") |

## §Z Constitution compliance

- **B1** one job per module: `backup.py` snapshots, `export.py` renders/gathers. **B2** both commands touch storage only through established public openers and their own adapter modules, never other engines' internals. **B3** business rules (rotate-not-destroy, determinism, section order, self-overwrite refusal) sit in the adapter logic, not the volatile CLI edge. **B5** deep modules: one entry point per command, thin CLI bodies; no chained mini-modules (the db_check precedent is one file doing one whole job).
- **D1** raw data untouched: statement and source raw text written verbatim; backup is a byte-faithful page image. **D2** derived data (embeddings, AI responses) deliberately excluded from export because it is rebuildable. **D3** export references items by id; no copying of facts into new truths. **D4** target/out paths are outside data — validated once at phase 1. **D5** no renames, no schema change. **D6** schema version read and reported, never advanced. **D7** enabled: these commands make the backup-before-touch discipline D7 presumes available as a product verb (the rule itself defines no mechanism; wording corrected per finding 8).
- **P1** no decorative architecture: two files, no port layer, P4 skipped for simple store-adjacent scripts, declared here and matched to the db_check precedent. **P2** layered CLI → adapter → storage (finding 7 applied). **P3** pipelines fixed: precheck→open→snapshot→verify→report and gather→render→emit, no hidden shared state.
- **I1** names by job (`create_backup`, `gather_export`, `render_export`). **I2** no behavior flags; rotation is a rule, not a mode; `--out` is data (I12's own example). **I3** every function ≤ 4 inputs (`ExportData` is the wrapper where gathering would exceed). **I4** named returns (`BackupReport`, `ExportData`), never bare tuples across boundaries. **I5/I6** expected failures are named `EmberError` subclasses: new codes in `ember/adapters/errors.py`, reused QUERY codes from `ember/query/errors.py` (finding 8). **I7** fail fast at phase 1; broken output deleted, exit 1; no swallowed errors. **I8** designed-away: exporting an empty database succeeds (0-count file); rotation makes the safe path the zero-flag path. **I9** validation at the edge, trust inside render. **I10** additive only; nothing existing renamed. **I11/I21** public functions' docstrings list inputs, output, side effects, raised codes. **I12** explicit flags, exit 0/1, stdout data, stderr errors. **I17** new stable codes, never reused; QUERY codes reused only for their existing meaning; open-fail split from invalid-source (finding 11). **I18/I19/I20** auto-injected locations, entity ids (`path`, `db_path`, `out`) carried, one-line `log_line()`. **I13** `--db` follows the existing boot config pattern.
- **T1** render pure; backup's snapshot/verify are thin edges. **T2** I/O pushed to the CLI and adapters. **T3/T4** real temp files as fakes-by-construction, no mocks; pyramid §7. **T5/T6** tests assert observable outputs and codes, not internals. **T9** conformed: sqlite3 appears only in adapters (finding 6).
- **S1** §4 samples run standalone. **S2** `tests/test_backup.py` / `tests/test_export.py` isolated. **S3** §5 shapes document input and output. **S4** transfer mechanism = SQLite page copy (backup) and a UTF-8 text file (export), documented.

"""Adapter-layer error namespaces. Codes are stable and never reused (I17)."""

from __future__ import annotations

from ember.errors import EmberError


class BackupError(EmberError):
    """Base error for every backup failure. Never raised directly."""

    code = "BACKUP-000"
    name = "BackupError"


class SourceOpenFailed(BackupError):
    """The source could not be read: missing, or not a SQLite file."""

    code = "BACKUP-001"
    name = "SourceOpenFailed"


class SourceInvalid(BackupError):
    """The source opens but its `schema_version` table is unreadable."""

    code = "BACKUP-002"
    name = "SourceInvalid"


class TargetWriteFailed(BackupError):
    """The target could not be made safe, or the snapshot write failed."""

    code = "BACKUP-003"
    name = "TargetWriteFailed"


class VerifyFailed(BackupError):
    """The written copy does not read back as a whole store."""

    code = "BACKUP-004"
    name = "VerifyFailed"


class ExportError(EmberError):
    """Base error for every export failure. Never raised directly."""

    code = "EXPORT-000"
    name = "ExportError"


class OutputWriteFailed(ExportError):
    """The `--out` file could not be written."""

    code = "EXPORT-001"
    name = "OutputWriteFailed"


class OverwriteRefused(ExportError):
    """The `--out` path is the knowledge base file itself."""

    code = "EXPORT-002"
    name = "OverwriteRefused"


class BridgeError(EmberError):
    """Base error for every bridge failure. Never raised directly."""

    code = "BRIDGE-000"
    name = "BridgeError"


class MigrationError(EmberError):
    """Base error for every migration-refusal failure. Never raised directly.

    The numbered migration runner (`ember/adapters/sqlite.py`) is shared by
    the capture, relate and maintain open paths, so its refusals cannot
    name any one engine's family — they get their own (Batch 4 chunk 9).
    """

    code = "MIGRATION-000"
    name = "MigrationError"


class ScriptSetInvalid(MigrationError):
    """The migration scripts on disk are not exactly 1..13 (story 14).

    The script set is pinned: every number from 1 to the latest version
    must be present before ANY open migrates anything, so a dropped or
    renamed `.sql` refuses up front instead of building a half schema.
    """

    code = "MIGRATION-001"
    name = "ScriptSetInvalid"


class VersionTableMissing(MigrationError):
    """The file has tables but no `schema_version` table (story 15).

    A database from before version tracking is never adopted: opening it
    must not stamp a version onto it and try to migrate — it refuses with
    this code and the file is left byte-identical.
    """

    code = "MIGRATION-002"
    name = "VersionTableMissing"


class HalfCreatedDatabase(MigrationError):
    """A version-0 file with no `items` table never finished being created
    (story 16).

    The user is not told to "upgrade" a file that never got its tables:
    this is its own code, distinct from the "schema version too old"
    (`SchemaOutdated`) sentence. The file is refused, never adopted.
    """

    code = "MIGRATION-003"
    name = "HalfCreatedDatabase"


class AnswerLineInvalid(BridgeError):
    """A stdin answer line is not `{"answer": <string>}` (L2 §6).

    Declared here in step 01; raised from step 03's JSON confirm adapter,
    which re-asks once and aborts with the engine `UserAbort` on a second
    bad line.
    """

    code = "BRIDGE-001"
    name = "AnswerLineInvalid"

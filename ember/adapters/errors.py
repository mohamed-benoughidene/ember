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


class AnswerLineInvalid(BridgeError):
    """A stdin answer line is not `{"answer": <string>}` (L2 §6).

    Declared here in step 01; raised from step 03's JSON confirm adapter,
    which re-asks once and aborts with the engine `UserAbort` on a second
    bad line.
    """

    code = "BRIDGE-001"
    name = "AnswerLineInvalid"

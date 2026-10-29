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

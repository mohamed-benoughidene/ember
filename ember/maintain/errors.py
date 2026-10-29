"""Maintain engine errors. Codes are stable and never reused."""

from __future__ import annotations

from ember.errors import EmberError


class MaintainError(EmberError):
    code = "MAINTAIN-000"
    name = "MaintainError"


class MaintainItemNotFound(MaintainError):
    code = "MAINTAIN-001"
    name = "MaintainItemNotFound"


class CloseReasonInvalid(MaintainError):
    code = "MAINTAIN-002"
    name = "CloseReasonInvalid"


class CloseReasonMismatch(MaintainError):
    code = "MAINTAIN-003"
    name = "CloseReasonMismatch"


class ItemAlreadyClosed(MaintainError):
    code = "MAINTAIN-004"
    name = "ItemAlreadyClosed"


class ReversalPreconditionFailed(MaintainError):
    code = "MAINTAIN-005"
    name = "ReversalPreconditionFailed"


class StatusTransitionInvalid(MaintainError):
    code = "MAINTAIN-006"
    name = "StatusTransitionInvalid"


class DbOpenFailed(MaintainError):
    code = "MAINTAIN-007"
    name = "DbOpenFailed"


class DbMigrationFailed(MaintainError):
    code = "MAINTAIN-008"
    name = "DbMigrationFailed"


class SchemaOutdated(MaintainError):
    code = "MAINTAIN-009"
    name = "SchemaOutdated"


class ItemsReadFailed(MaintainError):
    code = "MAINTAIN-010"
    name = "ItemsReadFailed"


class StatusWriteFailed(MaintainError):
    code = "MAINTAIN-011"
    name = "StatusWriteFailed"


class ChangeLogWriteFailed(MaintainError):
    code = "MAINTAIN-012"
    name = "ChangeLogWriteFailed"


class EditFieldUnknown(MaintainError):
    code = "MAINTAIN-013"
    name = "EditFieldUnknown"


class EditTargetMismatch(MaintainError):
    code = "MAINTAIN-014"
    name = "EditTargetMismatch"


class RemoveLinkNotConfirmed(MaintainError):
    code = "MAINTAIN-015"
    name = "RemoveLinkNotConfirmed"


class ItemEditWriteFailed(MaintainError):
    code = "MAINTAIN-016"
    name = "ItemEditWriteFailed"


class RemoveLinkWriteFailed(MaintainError):
    code = "MAINTAIN-017"
    name = "RemoveLinkWriteFailed"


class CloseAiCallFailed(MaintainError):
    code = "MAINTAIN-018"
    name = "CloseAiCallFailed"


class CloseAiSchemaInvalid(MaintainError):
    code = "MAINTAIN-019"
    name = "CloseAiSchemaInvalid"


class CloseAiConfigMissing(MaintainError):
    code = "MAINTAIN-020"
    name = "CloseAiConfigMissing"


class CloseAiStoreFailed(MaintainError):
    code = "MAINTAIN-021"
    name = "CloseAiStoreFailed"


class UserAbort(MaintainError):
    code = "MAINTAIN-022"
    name = "UserAbort"

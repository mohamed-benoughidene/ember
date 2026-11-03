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


class NothingToUndo(MaintainError):
    code = "MAINTAIN-023"
    name = "NothingToUndo"


class NothingToRedo(MaintainError):
    code = "MAINTAIN-024"
    name = "NothingToRedo"


class UndoRefused(MaintainError):
    code = "MAINTAIN-025"
    name = "UndoRefused"


class UndoWriteFailed(MaintainError):
    code = "MAINTAIN-026"
    name = "UndoWriteFailed"


class GroupRecordInvalid(MaintainError):
    code = "MAINTAIN-027"
    name = "GroupRecordInvalid"


class InverseTargetMoved(MaintainError):
    code = "MAINTAIN-028"
    name = "InverseTargetMoved"


class CloseAiRateLimited(CloseAiCallFailed):
    """The AI service refused the close-suggestion request with a 429 reply
    (Batch 7, Chunk 3 — `OpenAiCloseProposer`'s own retry policy).

    Its own dedicated code MAINTAIN-029: the fix is waiting and retrying,
    different advice from the shared MAINTAIN-018 call-failure code the
    failure previously carried. Carries `item_id` like its base (I19).
    Subclasses `CloseAiCallFailed`, so only the base ever needs catching.
    """

    code = "MAINTAIN-029"
    name = "CloseAiRateLimited"


class CloseAiCallTimedOut(CloseAiCallFailed):
    """The close-suggestion request timed out waiting for the AI service
    (Batch 7, Chunk 3 — `OpenAiCloseProposer`'s own retry policy).

    Its own dedicated code MAINTAIN-030: the fix is retrying after a pause,
    different advice from the shared MAINTAIN-018 call-failure code. Carries
    `item_id` like its base (I19). Subclasses `CloseAiCallFailed`, so only
    the base ever needs catching.
    """

    code = "MAINTAIN-030"
    name = "CloseAiCallTimedOut"

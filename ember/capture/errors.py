"""Capture engine errors. Codes are stable and never reused."""

from __future__ import annotations

from ember.errors import EmberError


class CaptureError(EmberError):
    code = "CAPTURE-000"
    name = "CaptureError"


class SourceFileNotFound(CaptureError):
    code = "CAPTURE-001"
    name = "SourceFileNotFound"


class SourceFileTooLarge(CaptureError):
    code = "CAPTURE-002"
    name = "SourceFileTooLarge"


class StdinReadError(CaptureError):
    code = "CAPTURE-003"
    name = "StdinReadError"


class InvalidUtf8Error(CaptureError):
    code = "CAPTURE-004"
    name = "InvalidUtf8Error"


class SourceDbReadError(CaptureError):
    code = "CAPTURE-005"
    name = "SourceDbReadError"


class SourceDbWriteError(CaptureError):
    code = "CAPTURE-006"
    name = "SourceDbWriteError"


class AiError(CaptureError):
    """Base for AI failures. The retry loop catches this, nothing wider."""

    code = "CAPTURE-007"
    name = "AiError"


class AiCallError(AiError):
    code = "CAPTURE-008"
    name = "AiCallError"


class AiSchemaError(AiError):
    code = "CAPTURE-009"
    name = "AiSchemaError"


class ContextModeInvalid(CaptureError):
    code = "CAPTURE-010"
    name = "ContextModeInvalid"


class ItemDbReadError(CaptureError):
    code = "CAPTURE-011"
    name = "ItemDbReadError"


class ItemSourceMissing(CaptureError):
    code = "CAPTURE-012"
    name = "ItemSourceMissing"


class ItemDbWriteError(CaptureError):
    code = "CAPTURE-013"
    name = "ItemDbWriteError"


class UserAbort(CaptureError):
    """User quit the confirm prompt, or input ended mid-prompt. Exit 2."""

    code = "CAPTURE-014"
    name = "UserAbort"


class ItemNotFound(CaptureError):
    code = "CAPTURE-015"
    name = "ItemNotFound"


class NotAnAssumption(CaptureError):
    """Only Assumption rows carry the `validated` flag (spec 3.5)."""

    code = "CAPTURE-016"
    name = "NotAnAssumption"


class DbOpenFailed(CaptureError):
    """The capture database cannot be opened or migrated (decision I1)."""

    code = "CAPTURE-017"
    name = "DbOpenFailed"


class BaseUrlInvalid(CaptureError):
    """`EMBER_AI_BASE_URL` is not a usable URL (decision I1)."""

    code = "CAPTURE-019"
    name = "BaseUrlInvalid"

"""Capture engine errors. Codes are stable and never reused."""

from __future__ import annotations

from ember.errors import EmberError


class CaptureError(EmberError):
    code = "CAPTURE-000"
    name = "CaptureError"


class SourceFileNotFound(CaptureError):
    code = "CAPTURE-001"
    name = "FileNotFound"


class SourceFileTooLarge(CaptureError):
    code = "CAPTURE-002"
    name = "FileTooLarge"


class StdinReadError(CaptureError):
    code = "CAPTURE-003"
    name = "StdinReadFail"


class InvalidUtf8Error(CaptureError):
    code = "CAPTURE-004"
    name = "InvalidUtf8"


class SourceDbReadError(CaptureError):
    code = "CAPTURE-005"
    name = "DbReadFail"


class SourceDbWriteError(CaptureError):
    code = "CAPTURE-006"
    name = "DbWriteFail"


class AiError(CaptureError):
    """Base for AI failures. The retry loop catches this, nothing wider."""

    code = "CAPTURE-007"
    name = "AiFail"


class AiCallError(AiError):
    code = "CAPTURE-008"
    name = "AiCallFail"


class AiSchemaError(AiError):
    code = "CAPTURE-009"
    name = "AiSchemaFail"


class ContextModeInvalid(CaptureError):
    code = "CAPTURE-010"
    name = "ContextModeInvalid"


class ItemDbReadError(CaptureError):
    code = "CAPTURE-011"
    name = "ItemDbReadFail"


class ItemSourceMissing(CaptureError):
    code = "CAPTURE-012"
    name = "ItemSourceMissing"


class ItemDbWriteError(CaptureError):
    code = "CAPTURE-013"
    name = "ItemDbWriteFail"


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

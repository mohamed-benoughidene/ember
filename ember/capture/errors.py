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


class TextNotEncodable(CaptureError):
    """Text (an edited field) cannot be written as UTF-8 (decision I1)."""

    code = "CAPTURE-018"
    name = "TextNotEncodable"


class BaseUrlInvalid(CaptureError):
    """`EMBER_AI_BASE_URL` is not a usable URL (decision I1)."""

    code = "CAPTURE-019"
    name = "BaseUrlInvalid"


class DbFileMissing(CaptureError):
    """The database file of a user command does not exist (D-25, N8).

    Only `ember init` creates the knowledge base, on purpose; every other
    capture-side command refuses here BEFORE the open can create the file
    implicitly (SQLite connects with create semantics).
    """

    code = "CAPTURE-020"
    name = "DbFileMissing"


class InitRefused(CaptureError):
    """`ember init` found a file that is not a healthy current knowledge base (N8).

    The one healthy shape `ember init` accepts is an Ember database with the
    `schema_version` table at the pinned latest version and the expected
    tables intact. Anything else — a non-Ember file, no version table, an
    older or newer version, missing tables — is refused, never adopted.
    """

    code = "CAPTURE-021"
    name = "InitRefused"


class ApiKeyMissing(CaptureError):
    """No AI API key is configured (`EMBER_AI_API_KEY` / `OPENROUTER_API_KEY`).

    Its own dedicated code (Batch 6 D-08/I17): the missing-key refusal is a
    setup problem with different advice from the call-failure code
    CAPTURE-008 it previously shared.
    """

    code = "CAPTURE-022"
    name = "ApiKeyMissing"

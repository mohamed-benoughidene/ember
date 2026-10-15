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

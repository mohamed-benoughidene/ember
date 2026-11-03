"""Edge adapter: read raw bytes from STDIN or a file, decode as UTF-8."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from ember.capture.errors import (
    InvalidUtf8Error,
    SourceEmpty,
    SourceFileNotFound,
    SourceFileTooLarge,
    StdinReadError,
)

MAX_SOURCE_BYTES = 5 * 1024 * 1024


class InputMode(str, Enum):
    STDIN = "stdin"
    FILE = "file"


def read_raw_text(
    *,
    mode: InputMode,
    path: str | None = None,
) -> str:
    """Read input, enforce the size limit for ALL inputs, decode as UTF-8.

    Empty (whitespace-only) text is refused here, before the source is
    stored and before any AI call is made (Batch 7 chunk 6).
    """
    if mode is InputMode.FILE:
        raw_bytes = _read_file_bytes(path)
    else:
        raw_bytes = _read_stdin_bytes()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidUtf8Error("invalid utf-8") from exc
    if not text.strip():
        raise SourceEmpty("captured text is empty")
    return text


def _read_file_bytes(path: str | None) -> bytes:
    if not path:
        raise SourceFileNotFound("file not found: <empty path>")
    file_path = Path(path)
    if not file_path.is_file():
        raise SourceFileNotFound(f"file not found: {path}", path=path)
    size = file_path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise SourceFileTooLarge(
            "file too large", path=path, size=size, max_bytes=MAX_SOURCE_BYTES
        )
    return file_path.read_bytes()


def _read_stdin_bytes() -> bytes:
    try:
        raw_bytes = sys.stdin.buffer.read()
    except OSError as exc:
        raise StdinReadError("stdin read fail") from exc
    # Same cap as files; a pasted note must never sneak past it (story 4).
    if len(raw_bytes) > MAX_SOURCE_BYTES:
        raise SourceFileTooLarge(
            "stdin over the source size limit",
            path="<stdin>",
            size=len(raw_bytes),
            max_bytes=MAX_SOURCE_BYTES,
        )
    return raw_bytes

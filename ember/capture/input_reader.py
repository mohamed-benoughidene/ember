"""Edge adapter: read raw bytes from STDIN or a file, decode as UTF-8."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from ember.capture.errors import (
    InvalidUtf8Error,
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
    max_bytes: int = MAX_SOURCE_BYTES,
) -> str:
    """Read input, enforce the size limit for files, decode as UTF-8."""
    if mode is InputMode.FILE:
        raw_bytes = _read_file_bytes(path, max_bytes)
    else:
        raw_bytes = _read_stdin_bytes()
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidUtf8Error("invalid utf-8") from exc


def _read_file_bytes(path: str | None, max_bytes: int) -> bytes:
    if not path:
        raise SourceFileNotFound("file not found: <empty path>")
    file_path = Path(path)
    if not file_path.is_file():
        raise SourceFileNotFound(f"file not found: {path}", path=path)
    size = file_path.stat().st_size
    if size > max_bytes:
        raise SourceFileTooLarge(
            "file too large", path=path, size=size, max_bytes=max_bytes
        )
    return file_path.read_bytes()


def _read_stdin_bytes() -> bytes:
    try:
        return sys.stdin.buffer.read()
    except OSError as exc:
        raise StdinReadError("stdin read fail") from exc

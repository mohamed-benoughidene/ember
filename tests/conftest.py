"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")

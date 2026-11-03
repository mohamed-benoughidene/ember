"""Pins the numbers the AI-limit policy rests on (Batch 7, Chunk 18).

The engine's capture budget is only safe because it sits BELOW the app's
session idle limit, and the retry cap plus one request timeout fit inside
the budget — so the budget's refusal logic stays decisive. These tests
parse the real files every run, so a drift on either side fails fast.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (REPO.joinpath(*parts)).read_text(encoding="utf-8")


def test_capture_budget_below_app_session_idle_limit() -> None:
    """90 s budget < 120_000 ms (120 s) app idle limit, parsed from source."""
    from ember.adapters.llm import TOTAL_CALL_BUDGET_SECONDS

    js = _read("app", "main", "bridge-client.js")
    match = re.search(r"sessionIdleMs\s*=\s*([0-9_]+)", js)
    assert match, "sessionIdleMs default not found in app/main/bridge-client.js"
    session_idle_ms = int(match.group(1).replace("_", ""))
    session_idle_seconds = session_idle_ms / 1000
    assert TOTAL_CALL_BUDGET_SECONDS < session_idle_seconds, (
        f"capture budget {TOTAL_CALL_BUDGET_SECONDS}s must stay below the "
        f"app's session idle limit {session_idle_ms}ms "
        f"({session_idle_seconds}s), or the app's idle timeout would fire first"
    )


def test_budget_covers_wait_plus_one_request_timeout() -> None:
    """The budget covers a capped wait plus one full request, so the
    budget's refusal logic is decisive for the whole next attempt."""
    from ember.adapters.llm import (
        REQUEST_TIMEOUT_SECONDS,
        RETRY_AFTER_CAP_SECONDS,
        TOTAL_CALL_BUDGET_SECONDS,
    )

    assert TOTAL_CALL_BUDGET_SECONDS >= RETRY_AFTER_CAP_SECONDS + REQUEST_TIMEOUT_SECONDS, (
        f"budget {TOTAL_CALL_BUDGET_SECONDS}s must cover a capped retry wait "
        f"({RETRY_AFTER_CAP_SECONDS}s) plus one request timeout "
        f"({REQUEST_TIMEOUT_SECONDS}s), else the budget could refuse mid-attempt"
    )


def test_marker_run_rules() -> None:
    """pyproject addopts excludes live and slow; CI runs 'not live' so the
    slow test runs there. The slow marker must stay declared."""
    pyproject = _read("pyproject.toml")
    addopts = re.search(r'^addopts\s*=\s*"([^"]*)"', pyproject, re.MULTILINE)
    assert addopts, "addopts line not found in pyproject.toml"
    assert "not live" in addopts.group(1), "addopts must exclude the live marker"
    assert "not slow" in addopts.group(1), "addopts must exclude the slow marker"
    assert re.search(r'"slow:', pyproject), "slow marker must stay declared"

    workflow = _read(".github", "workflows", "test.yml")
    run_lines = re.findall(r"run:\s*(\S.*)", workflow)
    assert any(
        "pytest" in line and 'not live' in line and "not slow" not in line
        for line in run_lines
    ), f"CI must run pytest -m \"not live\" (so the slow test runs); found: {run_lines}"

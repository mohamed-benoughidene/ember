"""I2 guard: a format/mode choice is a parameter of NO non-CLI function.

The `--format` branch lives only in `ember/cli.py` (I2). This greps every
ember function definition via the AST: outside `cli.py` no parameter may be
named `fmt`, and a parameter named `mode` exists only in the one
pre-bridge, maintainer-locked I2 exception (capture's input-source reader).
"""

from __future__ import annotations

import ast
from pathlib import Path

EMBER = Path(__file__).resolve().parents[2] / "ember"
# The two PRE-BRIDGE `mode` parameters (both maintainer-locked I2-style
# exceptions predating the bridge): capture's input-source choice and
# capture's context mode A/B. Recorded in the deviation ledger.
ALLOWED_MODE = {("input_reader", "read_raw_text"), ("item_proposal", "build_context")}


def _parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    arguments = node.args
    names = [p.arg for p in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]
    for extra in (arguments.vararg, arguments.kwarg):
        if extra is not None:
            names.append(extra.arg)
    return names


def _offending(wanted: str) -> list[str]:
    failures: list[str] = []
    for path in sorted(EMBER.rglob("*.py")):
        if path.name == "cli.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if wanted in _parameter_names(node):
                if wanted == "mode" and (path.stem, node.name) in ALLOWED_MODE:
                    continue
                failures.append(f"{path.relative_to(EMBER.parent)}:{node.name}")
    return failures


def test_no_fmt_parameter_outside_cli() -> None:
    assert _offending("fmt") == []


def test_no_mode_parameter_outside_cli_beyond_the_locked_exception() -> None:
    assert _offending("mode") == []

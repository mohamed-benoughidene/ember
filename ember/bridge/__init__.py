"""Marks the bridge layer folder as a package.

The bridge is the structured door between the app and Python (the
interface-bridge plan, sections 1 and 4). Everything here is PURE code only
(T1): no I/O, no stdin/stdout, no clock. The bridge imports NO adapter (T9):
`ember/cli.py` (the composition root) converts adapter reports to plain
dicts before anything crosses this boundary. The one adapter of the bridge
(the JSON-lines confirm port) lives in `ember/adapters/`.
"""

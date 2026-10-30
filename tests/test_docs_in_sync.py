"""Docs stay in sync with the code.

The README, the command inventory, the diagrams, the glossary, and the project
map all name things that exist in the code: commands, flags, settings, item
kinds, link kinds, and files. These tests fail when a doc names something that
is gone, or when the code gains something the docs do not list.
"""

from __future__ import annotations

import re
import subprocess
import urllib.parse
from pathlib import Path

import pytest

from ember.capture.item_proposal import ItemType
from ember.cli import main
from ember.relate.compat import LINK_TYPES

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
COMMANDS_DOC = ROOT / "docs" / "commands.md"
GLOSSARY = ROOT / "GLOSSARY.md"
PROJECT_MAP = ROOT / "PROJECT_MAP.md"
DIAGRAMS = sorted((ROOT / "docs" / "Graphs").glob("*.html"))
MASTER_DIAGRAM = next(path for path in DIAGRAMS if "Master" in path.name)
LINKED_DOCS = [README, ROOT / "plans" / "README.md", ROOT / "docs" / "index.html"]

STATUSES = ("Active", "Challenged", "Closed")
FILE_EXTENSION = re.compile(r"\.[A-Za-z0-9]+$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_code_blocks(markdown: str) -> str:
    """Drop fenced blocks, so `# comment` lines are not read as headings."""
    kept, inside = [], False
    for line in markdown.splitlines():
        if line.startswith("```"):
            inside = not inside
        elif not inside:
            kept.append(line)
    return "\n".join(kept)


def _html_text(html: str) -> str:
    html = re.sub(r"<(style|script).*?</\1>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def _code_source() -> str:
    return "\n".join(_read(p) for p in sorted((ROOT / "ember").rglob("*.py")))


def _all_flags() -> set[str]:
    flags = {"--help"}
    for command in main.commands.values():
        for param in command.params:
            flags.update(opt for opt in param.opts if opt.startswith("--"))
    return flags


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "ls-files", "-z"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available here")
    return [p for p in out.split("\0") if p and not p.endswith(".pyc")]


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading (lowercase, no punctuation, dashes)."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


# --- commands ---------------------------------------------------------------


def test_readme_command_table_lists_every_command() -> None:
    rows = set(re.findall(r"^\| `([a-z][a-z-]*)` \|", _read(README), flags=re.M))
    assert rows == set(main.commands)


def test_command_inventory_has_a_section_for_every_command() -> None:
    headings = [l for l in _read(COMMANDS_DOC).splitlines() if l.startswith("### ")]
    documented = {name for l in headings for name in re.findall(r"`ember ([a-z-]+)", l)}
    assert set(main.commands) <= documented


def test_docs_name_only_real_commands() -> None:
    named: dict[str, set[str]] = {}
    for path in (README, COMMANDS_DOC):
        named[path.name] = set(re.findall(r"`ember ([a-z][a-z-]*)", _read(path)))
    for path in DIAGRAMS:
        html = _read(path)
        names = set(re.findall(r"<code>ember ([a-z][a-z-]*)", html))
        for cmd_line in re.findall(r'<p class="cmd">(.*?)</p>', html, flags=re.S):
            names.update(re.findall(r"<code>(?:ember )?([a-z][a-z-]*)", cmd_line))
        named[path.name] = names
    unknown = {doc: sorted(n - set(main.commands)) for doc, n in named.items()}
    assert {doc: n for doc, n in unknown.items() if n} == {}


def test_flags_named_in_docs_exist() -> None:
    texts = [_read(README), _read(COMMANDS_DOC)] + [_html_text(_read(p)) for p in DIAGRAMS]
    named = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", "\n".join(texts)))
    assert sorted(named - _all_flags()) == []


# --- settings ----------------------------------------------------------------


def test_settings_table_names_and_defaults_exist_in_code() -> None:
    code = _code_source()
    rows = re.findall(r"^\| `((?:EMBER|OPENROUTER)_[A-Z_]+)`.*\| (.+?) \|$", _read(README), flags=re.M)
    assert rows, "the Settings table was not found in the README"
    missing = []
    for name, default in rows:
        if name not in code:
            missing.append(name)
        value = default.strip("` ")
        if len(value) >= 4 and value != "none" and value not in code:
            missing.append(f"{name} default {value}")
    assert missing == []


# --- words the docs share with the code --------------------------------------


def test_item_kinds_are_the_four_the_code_allows() -> None:
    glossary = _read(GLOSSARY)
    item_entry = re.search(r"\*\*Item\*\*:\n(.+)", glossary).group(1)
    assert all(kind.value in item_entry for kind in ItemType)
    for path in (README, GLOSSARY, *DIAGRAMS):
        assert "Metric" not in _read(path), f"{path.name} names an item kind the code does not have"


def test_link_kinds_and_statuses_match_the_code() -> None:
    glossary = _read(GLOSSARY)
    diagram = _html_text(_read(MASTER_DIAGRAM))
    for kind in LINK_TYPES:
        assert kind in glossary, f"glossary misses link kind {kind}"
        assert kind.replace("_", " ") in diagram, f"master diagram misses link kind {kind}"
    for status in STATUSES:
        assert status in glossary and status in diagram


# --- files and links ----------------------------------------------------------


def test_every_tracked_file_has_a_project_map_line() -> None:
    mapped = set(re.findall(r"^- `([^`]+)`:", _read(PROJECT_MAP), flags=re.M))
    missing = [p for p in _tracked_files() if p not in mapped]
    assert missing == []


def test_project_map_lines_point_at_real_files() -> None:
    mapped = re.findall(r"^- `([^`]+)`:", _read(PROJECT_MAP), flags=re.M)
    candidates = [p for p in mapped if not p.endswith("/") and ("/" in p or FILE_EXTENSION.search(p))]
    assert [p for p in candidates if not (ROOT / p).exists()] == []


@pytest.mark.parametrize("doc", LINKED_DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(doc: Path) -> None:
    text = _read(doc)
    targets = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'href="([^"]+)"', text)
    broken = []
    for target in targets:
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = urllib.parse.unquote(target.split("#")[0])
        if not (doc.parent / path).exists():
            broken.append(target)
    assert broken == []


def test_readme_anchor_links_match_headings() -> None:
    prose = _without_code_blocks(_read(README))
    headings = {_slug(h) for h in re.findall(r"^#{1,6}\s+(.*)$", prose, flags=re.M)}
    broken = [a for a in re.findall(r"\]\(#([^)]+)\)", prose) if a not in headings]
    assert broken == []

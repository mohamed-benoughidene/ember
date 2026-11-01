"""A bad `EMBER_AI_BASE_URL` fails at the config point, before any request.

Plan Chunk 9 (stories 10, 24; findings 4.5 #4, 4.3 #24): today the invalid
URL dies inside the SDK with a raw `httpx.InvalidURL` traceback. After the
chunk it is one house line — CAPTURE-019 on the CLI, and the owning family's
config code when the link and close proposers are built.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from ember.cli import main

BAD_URL = "::::nope"


def test_capture_bad_base_url_is_one_capture_019_line(
    tmp_path, monkeypatch
) -> None:
    """`capture` with an unusable base URL: one house line, exit 1, no crash."""
    fake_key = "sk-fake"  # fake only — never a real key
    monkeypatch.setenv("EMBER_AI_API_KEY", fake_key)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("EMBER_AI_BASE_URL", BAD_URL)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    note = tmp_path / "note.txt"
    note.write_text("a note", encoding="utf-8")
    db = str(tmp_path / "c.db")

    result = CliRunner().invoke(main, ["capture", "--file", str(note), "--db", db])

    lines = (result.stderr or "").splitlines()
    assert result.exit_code == 1
    assert len(lines) == 1
    assert lines[0].startswith("error: CAPTURE-019 BaseUrlInvalid |")
    assert "ai base url" in lines[0]
    assert "Traceback" not in (result.stderr or "")


def test_relate_bad_base_url_raises_config_missing() -> None:
    """The link proposer rejects a bad base URL with RELATE-035."""
    from ember.adapters.llm import build_link_proposer
    from ember.relate.errors import ConfigMissing

    with pytest.raises(ConfigMissing) as excinfo:
        build_link_proposer(
            {"EMBER_AI_API_KEY": "sk-fake", "EMBER_AI_BASE_URL": BAD_URL}
        )

    assert excinfo.value.code == "RELATE-035"
    assert "ai base url" in str(excinfo.value.message)


def test_maintain_bad_base_url_raises_close_ai_config_missing() -> None:
    """The close proposer rejects a bad base URL with MAINTAIN-020."""
    import pytest

    from ember.adapters.llm import build_close_proposer
    from ember.maintain.errors import CloseAiConfigMissing

    with pytest.raises(CloseAiConfigMissing) as excinfo:
        build_close_proposer(
            {"EMBER_AI_API_KEY": "sk-fake", "EMBER_AI_BASE_URL": BAD_URL}
        )

    assert excinfo.value.code == "MAINTAIN-020"
    assert "ai base url" in str(excinfo.value.message)

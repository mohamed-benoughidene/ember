"""The scripted interactive sessions behind the confirm tests (bridge step 03).

Each `*_session` function runs one full command against a fresh temp database
with the AI and embedder faked at the exact seams the existing CLI tests use
(`ember.cli.build_item_proposer`, `ember.cli.build_link_proposer`,
`ember.cli.build_close_proposer`, `ember.cli.build_embedder`, ...), and
returns the `CliRunner` result.

Two uses, one source of truth:
- `tests/bridge/test_confirm_terminal_golden.py` replays the three terminal
  sessions byte for byte against the goldens captured BEFORE step 03 changed
  `ember/cli.py` (`fixtures/bridge/confirm_goldens/`).
- `tests/bridge/test_confirm_json_cli.py` runs the same seeds under
  `--confirm json` and asserts the event stream.

Recapture the goldens (only pre-change, after editing the sessions here):
`.venv/bin/python -m tests.bridge.confirm_scenarios`
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest.mock as mock
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from click.testing import CliRunner

from ember.adapters.sqlite import SqliteEmbedderStore, open_database
from ember.capture.item_proposal import (
    DroppedProposal,
    ItemProposal,
    ItemType,
    ProposalBatch,
    ProposalResponse,
)
from ember.cli import main
from tests.fakes import insert_item, insert_link, insert_source
from tests.maintain.fakes import FakeCloseProposer
from tests.relate.fakes import FakeEmbedder

SAMPLE_NOTE = "We decided to use SQLite. We assume the team ships weekly."

T_ANSWER = "2026-01-01T00:00:00+00:00"
T_CLEAR = "2026-01-02T00:00:00+00:00"

GOLDEN_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "bridge"
    / "confirm_goldens"
)


# --- capture fakes -----------------------------------------------------------


def capture_proposals() -> ProposalResponse:
    """One dropped proposal plus two valid ones (a Decision and an Assumption)."""
    batch = ProposalBatch(
        proposals=[
            ItemProposal(
                type=ItemType.DECISION,
                statement="Use SQLite",
                source_quote="use SQLite",
                confidence=0.9,
                metadata="auth-network",
            ),
            ItemProposal(
                type=ItemType.ASSUMPTION,
                statement="Team ships weekly",
                source_quote="ships weekly",
                confidence=0.8,
                metadata=None,
            ),
        ],
        dropped=[DroppedProposal(rule="type")],
    )
    return ProposalResponse(raw_response="RAW-AI-ANSWER", batch=batch)


@contextmanager
def capture_ai(response: ProposalResponse) -> Iterator[None]:
    """Fake the capture AI at the `ember.cli.build_item_proposer` seam."""
    from tests.fakes import FakeItemProposer

    with mock.patch(
        "ember.cli.build_item_proposer",
        lambda: FakeItemProposer([response]),
    ):
        yield


# --- relate fakes ------------------------------------------------------------


class CannedLinkProposer:
    """Canned relate AI: proposes one link type to every candidate."""

    def __init__(self, link_type: str = "depends_on") -> None:
        self._link_type = link_type

    def propose_links(self, new_item: Any, candidates: list[Any]) -> Any:
        from ember.relate.link_proposal import LinkProposal, LinkProposalResponse

        proposals = [
            LinkProposal(target_item_id=c.id, link_type=self._link_type)
            for c in candidates
        ]
        return LinkProposalResponse(raw_response="canned", proposals=proposals)


@contextmanager
def relate_phases(link_proposer: CannedLinkProposer) -> Iterator[None]:
    """Fake the embedder boot check, the embedder and the relate AI.

    Same seams as `tests/relate/test_relate_cli.py` (its `_stub_boot_validation`,
    `_patch_phase2_ports`, `_patch_phase34_ports` pattern).
    """
    with mock.patch("ember.cli.validate_embedder_config", lambda: 120.0), \
            mock.patch("ember.cli.build_embedder", lambda: FakeEmbedder()), \
            mock.patch(
                "ember.cli.build_embedding_store",
                lambda conn: SqliteEmbedderStore(conn),
            ), \
            mock.patch(
                "ember.cli.build_link_proposer", lambda env: link_proposer
            ):
        yield


# --- maintain fakes / seed (the `tests/maintain/test_close_proposals_cli.py`
# section-2 seed, credited: shielded stale Questions so the sweep spares them) --


@contextmanager
def maintain_ai(proposer: FakeCloseProposer) -> Iterator[None]:
    with mock.patch("ember.cli.build_close_proposer", lambda env: proposer):
        yield


def _shield(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("UPDATE items SET status_origin = 'manual' WHERE id = ?", (item_id,))
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, NULL, 'status_origin', 'derived', 'manual', ?,"
        " 'user_set_status')",
        (item_id, T_CLEAR),
    )


def seed_two_stale_questions(db_path: str) -> None:
    """Findings 4/5, shielded Questions 7/9, confirmed answers links 11 (5->7)
    and 12 (4->9), both answers old enough to be stale."""
    Path(db_path).touch()
    from ember.adapters.sqlite import open_maintain_database

    conn = open_maintain_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Finding",
            statement="auth measured",
        )
        insert_item(
            conn, source_id=source_id, item_id=5, item_type="Finding",
            statement="tokens measured",
        )
        insert_item(
            conn, source_id=source_id, item_id=7, item_type="Question",
            statement="should we cache tokens?",
        )
        insert_item(
            conn, source_id=source_id, item_id=9, item_type="Question",
            statement="which auth backend?",
        )
        _shield(conn, 7)
        _shield(conn, 9)
        for link_id, source, target in ((11, 5, 7), (12, 4, 9)):
            conn.execute(
                "INSERT INTO links (id, source_item_id, target_item_id,"
                " link_type, status, created_at) VALUES (?, ?, ?, 'answers',"
                " 'Confirmed', ?)",
                (link_id, source, target, T_ANSWER),
            )
        conn.commit()
    finally:
        conn.close()


def seed_supersedes_chain(db_path: str) -> None:
    """Items 11/22/33; a live supersedes chain 11 -> 33 -> 22, so both
    proposed links from 11 are gatekeeper rule-8 rejects (the
    `test_relate_prints_one_rejection_line_per_gatekeeper_rejection` seed)."""
    Path(db_path).touch()
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        insert_item(conn, source_id=source_id, item_id=11, statement="one")
        insert_item(conn, source_id=source_id, item_id=22, statement="two")
        insert_item(conn, source_id=source_id, item_id=33, statement="three")
        insert_link(conn, 11, 33, "supersedes")
        insert_link(conn, 33, 22, "supersedes")
        conn.commit()
    finally:
        conn.close()


def seed_relate_pool(db_path: str) -> None:
    """Items 1..6, one Confirmed and one Rejected answers link from item 1
    (the `_seed_six_items_two_links` shape, distinct statements for stable
    ranking), so exactly items 4, 5, 6 are candidates and 3 proposals come
    back."""
    Path(db_path).touch()
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn)
        # The same item types as `tests/relate/test_relate_cli.py`'s
        # `_seed_six_items_two_links` (an `answers` link needs a Question
        # target), with distinct statements so the ranking is stable.
        seeds = [
            (1, "Decision", "We chose SQLite"),
            (2, "Question", "Weekly ship cadence"),
            (3, "Question", "Auth token cache"),
            (4, "Decision", "Retry backoff"),
            (5, "Assumption", "Rate limits apply"),
            (6, "Finding", "Schema is stable"),
        ]
        for item_id, item_type, statement in seeds:
            insert_item(
                conn,
                source_id=source_id,
                item_id=item_id,
                item_type=item_type,
                statement=statement,
            )
        insert_link(conn, 1, 2, "answers")
        insert_link(conn, 1, 3, "answers", status="Rejected")
        conn.commit()
    finally:
        conn.close()


# --- the sessions ------------------------------------------------------------


def capture_session(
    work: Path, *, input_text: str = "y\nn\n", extra_args: tuple[str, ...] = ()
) -> Any:
    """`ember capture --file note --db ...`: one drop, two proposals, y then n
    (terminal answers) or the JSON answer lines given in `input_text`."""
    work.mkdir(parents=True, exist_ok=True)
    note = work / "note.txt"
    note.write_text(SAMPLE_NOTE, encoding="utf-8")
    db_path = str(work / "capture.db")
    with capture_ai(capture_proposals()):
        return CliRunner().invoke(
            main,
            ["capture", "--file", str(note), "--db", db_path, *extra_args],
            input=input_text,
        )


def relate_session(
    work: Path,
    *,
    input_text: str = "y\nn\ns\n",
    extra_args: tuple[str, ...] = (),
) -> Any:
    """`ember relate --item 1 --db ...`: three proposals accepted/rejected/
    skipped in turn (terminal answers) or the JSON answer lines given."""
    work.mkdir(parents=True, exist_ok=True)
    db_path = str(work / "relate.db")
    seed_relate_pool(db_path)
    with relate_phases(CannedLinkProposer()):
        return CliRunner().invoke(
            main,
            ["relate", "--item", "1", "--db", db_path, *extra_args],
            input=input_text,
        )


def relate_rejections_session(
    work: Path, *, input_text: str = "", extra_args: tuple[str, ...] = ()
) -> Any:
    """`ember relate --item 11 --db ...`: both proposals are gatekeeper
    rejects, so the two `relate rejected: CODE | detail` lines print and no
    prompt is ever asked."""
    work.mkdir(parents=True, exist_ok=True)
    db_path = str(work / "relate-rejections.db")
    seed_supersedes_chain(db_path)
    with relate_phases(CannedLinkProposer(link_type="supersedes")):
        return CliRunner().invoke(
            main,
            ["relate", "--item", "11", "--db", db_path, *extra_args],
            input=input_text,
        )


def maintain_session(
    work: Path, *, input_text: str = "y\nn\n", extra_args: tuple[str, ...] = ()
) -> Any:
    """`ember maintain --db ...`: two stale shielded Questions; the first
    proposal is a decline (no prompt), the second is proposed and the user
    answers y then n (terminal answers) or the JSON answer lines given."""
    work.mkdir(parents=True, exist_ok=True)
    db_path = str(work / "maintain.db")
    seed_two_stale_questions(db_path)
    proposer = FakeCloseProposer([decline_response(), proposal_response()])
    with maintain_ai(proposer):
        return CliRunner().invoke(
            main,
            ["maintain", "--db", db_path, *extra_args],
            input=input_text,
        )


def decline_response() -> Any:
    """The AI declines to propose a close for one stale Question."""
    from ember.maintain.close_proposer import CloseProposalResponse

    return CloseProposalResponse(raw_response="RAW-DECLINE", proposal=None)


def proposal_response() -> Any:
    """The AI proposes one close (expired, confidence 0.8)."""
    from ember.maintain.close_proposer import CloseProposal, CloseProposalResponse

    return CloseProposalResponse(
        raw_response="RAW-PROPOSAL",
        proposal=CloseProposal(
            reason="expired",
            confidence=0.8,
            rationale="answered long ago, no follow-up open",
        ),
    )


SESSIONS = {
    "capture.txt": capture_session,
    "relate.txt": relate_session,
    "maintain.txt": maintain_session,
}


def _generate() -> None:
    """Write the three terminal goldens (run BEFORE changing `ember/cli.py`)."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, session in SESSIONS.items():
        with tempfile.TemporaryDirectory() as tmp:
            result = session(Path(tmp))
        assert result.exit_code == 0, (name, result.exit_code, result.output)
        # stdout only (click 8.2+ mixes stderr into `result.output`).
        (GOLDEN_DIR / name).write_text(result.stdout, encoding="utf-8")
        print(f"{name}: {len(result.stdout.splitlines())} lines, exit 0")


if __name__ == "__main__":
    _generate()

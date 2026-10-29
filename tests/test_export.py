"""`ember export` tests (utility step 02, L2 §5.2).

Every integration case builds a real database through the migration runner
and the real seed helpers, then runs the adapter or the CLI on real temp
files (T3/T4, no mocks). Determinism is checked as byte equality of two
renders, the read-only proofs as sha256 file hashes before and after.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.adapters.errors import (
    OverwriteRefused,
    OutputWriteFailed,
)
from ember.adapters.export import (
    ExportData,
    ExportItem,
    ExportSource,
    gather_export,
    refuse_self_overwrite,
    render_export,
    write_export,
)
from ember.adapters.sqlite import open_database
from ember.cli import main
from ember.query.rows import ChangeRow
from ember.relate.rows import Link
from tests.fakes import (
    FIXED_TIME,
    insert_item,
    insert_link,
    insert_link_reversed,
    insert_source,
)
from tests.query.fakes import make_v9

LATER = "2026-01-02T00:00:00+00:00"
NEWEST = "2026-01-03T00:00:00+00:00"
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "export_source_verbatim.txt"
)
LONG_VALUE = "kept in full, not summarized: " + "x" * 400


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _make_item(item_id: int, **overrides) -> ExportItem:
    fields = dict(
        id=item_id,
        type="Decision",
        statement=f"statement {item_id}",
        status="Active",
        status_origin="derived",
        created_at=FIXED_TIME,
        validated=None,
        close_reason=None,
        metadata=None,
        rationale=None,
        source=None,
        source_id=1,
    )
    fields.update(overrides)
    return ExportItem(**fields)


def _make_link(link_id: int, **overrides) -> Link:
    fields = dict(
        id=link_id,
        source_item_id=1,
        target_item_id=2,
        link_type="depends_on",
        status="Confirmed",
        created_at=FIXED_TIME,
        reversed_at=None,
    )
    fields.update(overrides)
    return Link(**fields)


def _make_source(source_id: int, **overrides) -> ExportSource:
    fields = dict(
        id=source_id,
        timestamp=FIXED_TIME,
        title="t",
        content_hash=f"hash-{source_id}",
        full_text="body",
    )
    fields.update(overrides)
    return ExportSource(**fields)


def _make_ledger(row_id: int, **overrides) -> ChangeRow:
    fields = dict(
        id=row_id,
        item_id=1,
        link_id=None,
        field_changed="status",
        old_value="Active",
        new_value="Challenged",
        timestamp=FIXED_TIME,
        trigger_cause="derived_status_change",
    )
    fields.update(overrides)
    return ChangeRow(**fields)


def _sample_data() -> ExportData:
    """One ExportData with a Rejected link, a reversed link, a multi-line
    source and a two-row ledger in gather order (timestamp, then id)."""
    return ExportData(
        schema_version=12,
        items=[
            _make_item(
                2,
                type="Question",
                statement="why here",
                status="Closed",
                close_reason="answered",
                metadata="cap-plan",
            ),
            _make_item(1, type="Decision", statement="use SQLite"),
        ],
        links=[
            _make_link(2, source_item_id=1, target_item_id=3,
                       link_type="contradicts", status="Rejected"),
            _make_link(3, source_item_id=3, target_item_id=1,
                       link_type="supersedes", reversed_at=LATER),
        ],
        sources=[
            _make_source(1, full_text="line one\n\n  indented line 🕯 naïve"),
        ],
        ledger=[
            _make_ledger(1),
            _make_ledger(2, timestamp=NEWEST, item_id=None,
                         field_changed="item_rejected",
                         old_value=None, new_value=LONG_VALUE),
        ],
    )


def _extract_source_block(rendered: str, source_id: int) -> str:
    """Pull the payload between the pinned markers, per the export marker spec.

    The begin line is `----- source <id> text begin -----`. The end line is
    `----- source <id> text end (bytes=<n>, sha256=<h>) -----` and names the
    exact byte count and sha256 of the raw text, so the block is self-checking
    and no source can ever carry its own end line.
    """
    begin = f"----- source {source_id} text begin -----\n"
    start = rendered.index(begin) + len(begin)
    target = f"----- source {source_id} text end ("
    end_index = rendered.index(target, start)
    line_end = rendered.index("\n", end_index) + 1
    return rendered[start:end_index]


# 1. Pure render unit


def test_render_twice_is_byte_identical() -> None:
    first = render_export(_sample_data())
    second = render_export(_sample_data())

    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_section_order_and_header_pinned_lines() -> None:
    rendered = render_export(_sample_data())

    lines = rendered.split("\n")
    assert lines[0] == "# Ember knowledge base export"
    assert lines[1] == "# schema version: 12"
    assert lines[2] == f"# as of (latest ledger event): {NEWEST}"
    assert (
        lines[3] == "# counts: 2 items, 2 links, 2 ledger rows, 1 sources"
    )
    assert lines[4] == (
        "# embeddings and AI responses are derived, rebuildable data (D2)"
        " and are not exported."
    )
    names = ["== items (2) ==", "== links (2) ==", "== sources (1) ==",
             "== ledger (2) =="]
    positions = [rendered.index(name) for name in names]
    assert positions == sorted(positions)
    assert rendered.index("# Ember knowledge base export") < positions[0]
    assert rendered.index("== items (2) ==") < rendered.index("use SQLite")


def test_header_as_of_is_max_ledger_timestamp_not_wall_clock() -> None:
    data = _sample_data()
    # The ledger given is in gather order, newest last id-wise: the max
    # timestamp is NEWEST. No line of the render may carry a real date.
    rendered = render_export(data)

    assert f"# as of (latest ledger event): {NEWEST}" in rendered
    assert "2026-10" not in rendered  # today's real month must never appear


def test_source_verbatim_fixture_round_trips_exactly() -> None:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    data = ExportData(
        schema_version=12, items=[], links=[],
        sources=[_make_source(1, full_text=fixture_text)],
        ledger=[],
    )

    rendered = render_export(data)

    source = data.sources[0]
    raw = fixture_text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    expected_end = (
        f"----- source 1 text end (bytes={len(raw)}, sha256={digest}) -----"
    )
    # The real end line is present exactly once: the spoof lines inside the
    # fixture text cannot close the block (marker spec, L2 §5.2).
    assert rendered.count(expected_end) == 1
    block = _extract_source_block(rendered, 1)
    # Round trip: when the text ends without a newline, exactly one newline
    # is added so the end marker starts its own line. With one, none is.
    expected = fixture_text if fixture_text.endswith("\n") else fixture_text + "\n"
    assert block == expected
    assert "  two leading spaces" in block
    assert "🕯" in block
    assert "naïve café" in block
    # The bare marker-looking line inside the text is payload, not a boundary:
    # it sits INSIDE the extracted block, so it did not close it.
    assert "\n----- source 1 text end -----\n" in block


def test_source_block_with_trailing_newline_round_trips_verbatim() -> None:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8") + "\n"
    data = ExportData(
        schema_version=12, items=[], links=[],
        sources=[_make_source(1, full_text=fixture_text)],
        ledger=[],
    )

    rendered = render_export(data)

    block = _extract_source_block(rendered, 1)
    assert block == fixture_text


def test_rejected_and_reversed_links_labelled_with_state() -> None:
    rendered = render_export(_sample_data())

    assert "link 2 | contradicts | Rejected (removed)" in rendered
    assert "link 3 | supersedes | Confirmed (reversed)" in rendered
    assert f"reversed_at:        {LATER}" in rendered
    assert "status:             Rejected" in rendered


def test_ledger_values_untruncated() -> None:
    rendered = render_export(_sample_data())

    assert LONG_VALUE in rendered
    assert "..." not in rendered


def test_empty_export_data_renders_valid_header() -> None:
    data = ExportData(
        schema_version=12, items=[], links=[], sources=[], ledger=[]
    )

    rendered = render_export(data)

    lines = rendered.split("\n")
    assert lines[0] == "# Ember knowledge base export"
    assert lines[1] == "# schema version: 12"
    assert lines[2] == "# as of (latest ledger event): (no ledger rows)"
    assert lines[3] == "# counts: 0 items, 0 links, 0 ledger rows, 0 sources"
    assert "== items (0) ==" in rendered
    assert "== links (0) ==" in rendered
    assert "== sources (0) ==" in rendered
    assert "== ledger (0) ==" in rendered


# 2. Coverage proof on a real seeded database


def _log_ledger(
    conn,
    *,
    item_id: int | None,
    link_id: int | None,
    field_changed: str,
    old_value: str | None,
    new_value: str | None,
    timestamp: str,
    cause: str,
) -> None:
    conn.execute(
        "INSERT INTO change_log (item_id, link_id, field_changed, old_value,"
        " new_value, timestamp, trigger_cause)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_id, link_id, field_changed, old_value, new_value, timestamp, cause),
    )


def _seed(db_path: str) -> None:
    """Build a real v12 database: one item per type, rejected and reversed
    links, multiple ledger causes, one multi-line verbatim source."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    Path(db_path).touch()
    conn = open_database(db_path)
    try:
        source_id = insert_source(conn, full_text=fixture_text)
        insert_item(
            conn, source_id=source_id, item_id=1, item_type="Decision",
            statement="Decision statement", metadata="cap-plan",
            rationale="because the panel said so",
        )
        insert_item(
            conn, source_id=source_id, item_id=2, item_type="Assumption",
            statement="Assumption statement", validated=1,
        )
        insert_item(
            conn, source_id=source_id, item_id=3, item_type="Finding",
            statement="Finding statement", source="applied twice on site",
        )
        insert_item(
            conn, source_id=source_id, item_id=4, item_type="Question",
            statement="Question statement", status="Closed",
            close_reason="answered",
        )
        insert_item(
            conn, source_id=source_id, item_id=5, item_type="Decision",
            statement="Decision that superseded item 1",
        )
        kept = insert_link(conn, 1, 2, "depends_on")
        rejected = insert_link(
            conn, 3, 1, "contradicts", status="Rejected"
        )
        reversed_id = insert_link(
            conn, 5, 1, "supersedes", created_at=LATER
        )
        insert_link_reversed(conn, reversed_id, 5)
        conn.execute(
            "UPDATE links SET reversed_at = ? WHERE id = ?",
            (NEWEST, reversed_id),
        )
        _log_ledger(
            conn, item_id=1, link_id=None, field_changed="status",
            old_value="Active", new_value="Challenged",
            timestamp=FIXED_TIME, cause="derived_status_change",
        )
        _log_ledger(
            conn, item_id=None, link_id=kept, field_changed="link_confirmed",
            old_value=None, new_value="depends_on:2",
            timestamp=LATER, cause="user_confirmed",
        )
        _log_ledger(
            conn, item_id=None, link_id=rejected,
            field_changed="link_removed", old_value="Confirmed",
            new_value="Rejected", timestamp=NEWEST, cause="user_removed",
        )
        conn.commit()
    finally:
        conn.close()


def test_every_seeded_row_appears_in_export_text(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["export", "--db", db_path])

    assert result.exit_code == 0
    text = result.output
    assert text.startswith("# Ember knowledge base export\n")
    assert "# schema version: 12" in text
    assert f"# as of (latest ledger event): {NEWEST}" in text
    assert "# counts: 5 items, 3 links, 4 ledger rows, 1 sources" in text
    # Items: every row leads with type, id, status and carries its fields.
    for header in (
        "Decision 1 | Active",
        "Assumption 2 | Active",
        "Finding 3 | Active",
        "Question 4 | Closed",
        "Decision 5 | Active",
    ):
        assert header in text
    for field in (
        "Decision statement",
        "Assumption statement",
        "Finding statement",
        "Question statement",
        "Decision that superseded item 1",
        "metadata:           cap-plan",
        "rationale:          because the panel said so",
        "source:             applied twice on site",
        "validated:          1",
        "close_reason:       answered",
        "status_origin:      derived",
        "created_at:",
    ):
        assert field in text, field
    # Links: kept, removed and reversed, with their states.
    assert "link 1 | depends_on | Confirmed" in text
    assert "link 2 | contradicts | Rejected (removed)" in text
    assert "link 3 | supersedes | Confirmed (reversed)" in text
    assert "reversed_at:        " + NEWEST in text
    assert "source_item_id:     3" in text
    assert "target_item_id:     1" in text
    # Sources: header, hash and the verbatim block, round-tripped.
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    assert f"source 1 | t | {FIXED_TIME}" in text
    # The seeded content_hash is "hash-" + the fixture text: only the label
    # and prefix are asserted here, the bytes are round-tripped below.
    assert "content_hash:       hash-" in text
    raw = fixture_text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    assert (
        f"----- source 1 text end (bytes={len(raw)}, sha256={digest}) -----"
        in text
    )
    assert _extract_source_block(text, 1) == (
        fixture_text if fixture_text.endswith("\n") else fixture_text + "\n"
    )
    # Ledger: every row and every value, in `(timestamp, id)` order.
    # Seed ids: 1 reversal marker, 2 derived status, 3 confirmed link,
    # 4 removed link. The (timestamp, id) order keeps 1 before 2.
    assert "ledger 1 | 2026-01-01T00:00:00+00:00 | reversal" in text
    assert (
        "ledger 2 | 2026-01-01T00:00:00+00:00 | derived_status_change"
        in text
    )
    assert "ledger 3 | 2026-01-02T00:00:00+00:00 | user_confirmed" in text
    assert "ledger 4 | 2026-01-03T00:00:00+00:00 | user_removed" in text
    assert "new_value:          depends_on:2" in text
    assert "old_value:          Confirmed" in text
    assert "field_changed:      link_removed" in text
    assert "trigger_cause:      user_removed" in text


def test_two_exports_of_one_database_are_byte_identical(db_path) -> None:
    _seed(db_path)

    first = CliRunner().invoke(main, ["export", "--db", db_path])
    second = CliRunner().invoke(main, ["export", "--db", db_path])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.output == second.output


# 3. Hash proofs: the database file is never written


def test_export_leaves_db_byte_identical(db_path, tmp_path) -> None:
    _seed(db_path)
    before = _sha256(db_path)

    result = CliRunner().invoke(
        main, ["export", "--db", db_path, "--out", str(tmp_path / "out.txt")]
    )

    assert result.exit_code == 0
    assert _sha256(db_path) == before


def test_gather_export_matches_the_cli_bytes(db_path) -> None:
    _seed(db_path)
    conn = open_database(db_path)
    try:
        data = gather_export(conn)
    finally:
        conn.close()

    assert data.schema_version == 12
    assert len(data.items) == 5
    assert len(data.links) == 3
    assert len(data.sources) == 1
    assert len(data.ledger) == 4
    assert [row.timestamp for row in data.ledger] == sorted(
        row.timestamp for row in data.ledger
    )


# 4. CLI surface: --out and stdout, EXPORT-001 and EXPORT-002


def test_cli_out_writes_file_and_summary(db_path, tmp_path) -> None:
    _seed(db_path)
    out = tmp_path / "export.txt"
    stdout_text = CliRunner().invoke(main, ["export", "--db", db_path]).output

    result = CliRunner().invoke(main, ["export", "--db", db_path, "--out", str(out)])

    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8") == stdout_text
    assert result.output.strip() == (
        "exported 5 items, 3 links, 4 ledger rows, 1 sources"
        f" -> {out}"
    )


def test_cli_stdout_default_prints_rendered_text(db_path) -> None:
    _seed(db_path)

    result = CliRunner().invoke(main, ["export", "--db", db_path])

    assert result.exit_code == 0
    assert result.output.startswith("# Ember knowledge base export\n")
    assert result.output.index("== items (5) ==") < result.output.index(
        "== links (3) =="
    )


def test_cli_out_unwritable_exits_1_export_001(db_path, tmp_path) -> None:
    _seed(db_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    out = locked / "export.txt"
    locked.chmod(0o555)
    try:
        result = CliRunner().invoke(
            main, ["export", "--db", db_path, "--out", str(out)]
        )
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 1
    assert "EXPORT-001" in (result.stderr or "")
    assert "OutputWriteFailed" in (result.stderr or "")
    assert not out.exists()


def test_write_export_raises_export_001(db_path, tmp_path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    target = str(locked / "export.txt")
    locked.chmod(0o555)
    try:
        with pytest.raises(OutputWriteFailed) as raised:
            write_export("text", target)
    finally:
        locked.chmod(0o755)

    assert raised.value.code == "EXPORT-001"
    assert not Path(target).exists()


def test_cli_out_db_path_refused_export_002(db_path) -> None:
    _seed(db_path)
    before = _sha256(db_path)

    result = CliRunner().invoke(main, ["export", "--db", db_path, "--out", db_path])

    assert result.exit_code == 1
    assert "EXPORT-002" in (result.stderr or "")
    assert "OverwriteRefused" in (result.stderr or "")
    assert _sha256(db_path) == before


def test_refuse_self_overwrite_covers_unnormalized_relative(db_path, tmp_path) -> None:
    # The db exists, the out spelling does not: `/./sub/../name` normalizes
    # onto the same absolute path, so the guard must refuse without samefile.
    tricky = str(tmp_path / "." / "sub" / ".." / Path(db_path).name)

    with pytest.raises(OverwriteRefused) as raised:
        refuse_self_overwrite(db_path, tricky)

    assert raised.value.code == "EXPORT-002"
    assert raised.value.context["out"] == tricky


# 5. Floors: export reuses the query opener's QUERY-004 honestly


def test_below_floor_db_refused_query_004(db_path) -> None:
    make_v9(db_path)
    before = _sha256(db_path)

    result = CliRunner().invoke(main, ["export", "--db", db_path])

    assert result.exit_code == 1
    assert "QUERY-004" in (result.stderr or "")
    assert _sha256(db_path) == before


def test_cli_empty_db_exports_with_zero_counts_i8(db_path) -> None:
    Path(db_path).touch()
    conn = open_database(db_path)
    conn.close()

    result = CliRunner().invoke(main, ["export", "--db", db_path])

    assert result.exit_code == 0
    assert "# counts: 0 items, 0 links, 0 ledger rows, 0 sources" in result.output
    assert "# as of (latest ledger event): (no ledger rows)" in result.output
    assert "== items (0) ==" in result.output
    assert "== ledger (0) ==" in result.output

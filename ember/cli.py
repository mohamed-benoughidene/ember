"""Ember command line interface."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass
from functools import partial, wraps
from typing import Any, Callable

import click

from ember import __version__
from ember.adapters.backup import create_backup
from ember.adapters.db_check import check_database
from ember.adapters.export import (
    gather_export,
    refuse_self_overwrite,
    render_export,
    write_export,
)
from ember.adapters.embedder import build_embedder, validate_embedder_config
from ember.adapters.json_confirm import (
    JsonCaptureConfirm,
    JsonMaintainConfirm,
    JsonRelateConfirm,
    JsonSink,
    TerminalSink,
)
from ember.adapters.llm import (
    build_close_proposer,
    build_item_proposer,
    build_link_proposer,
)
from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteItemContext,
    SqliteGroupIdPort,
    SqliteItemGatekeeper,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    SqliteQueryContext,
    SqliteSourceStore,
    build_ai_response_store,
    build_embedding_store,
    init_knowledge_base,
    open_database,
    open_existing_database,
    open_maintain_database,
    open_maintain_database_readonly,
    open_query_database,
    open_relate_database_readonly,
    open_relate_database_write,
    unit_of_work,
)
from ember.bridge.json_out import OutputDocument, render_document
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.errors import UserAbort
from ember.capture.input_reader import InputMode, read_raw_text
from ember.capture.item_gatekeeper import (
    GatekeeperRun,
    load_source_text,
    validate_add_item,
    validate_proposals,
    validate_set_validated,
    validated_change_is_noop,
)
from ember.capture.item_proposal import (
    ProposalResponse,
    build_context,
    propose_items,
    read_context_mode,
)
from ember.capture.source_storage import StoredSource, store_source
from ember.crash_report import write_crash_file
from ember.errors import EmberError
from ember.maintain.close_proposer import ProposalOutcome, stale_close_candidates
from ember.maintain.derive import derive_status_changes
from ember.maintain.errors import (
    CloseReasonInvalid,
    CloseReasonMismatch,
    EditFieldUnknown,
    UserAbort as MaintainUserAbort,
)
from ember.maintain.human_actions import (
    CLOSE_REASONS,
    EDIT_FIELDS,
    HUMAN_SETTABLE_REASONS,
    validate_close_item,
    validate_edit_item,
    validate_remove_link,
)
from ember.maintain.report import (
    format_report,
    format_undo_line,
    summary_counts,
)
from ember.maintain.rows import MaintainSnapshot, StatusChange
from ember.maintain.run_maintain import (
    CloseProposalPorts,
    MaintainPorts,
    MaintainRequest,
    UndoRequest,
    _load,
    run_close_item,
    run_close_proposals,
    run_edit_item,
    run_redo,
    run_remove_link,
    run_reverse_supersedes,
    run_set_status,
    run_sweep,
    run_undo,
)
from ember.query.list_items import count_by_status
from ember.query.rows import HistoryPage, ListPage, TopicFilter
from ember.query.run_query import (
    run_current_state,
    run_history,
    run_list_items,
    run_show_item,
    run_topic_search,
    run_why,
)
from ember.relate.candidate_pool import build_candidate_pool
from ember.relate.errors import UserAbort as RelateUserAbort
from ember.relate.load_filter import load_item_candidates, load_latest_candidates
from ember.relate.rows import Link
from ember.relate.rows import Pool
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate

DEFAULT_DB_PATH = "ember.db"


@dataclass(frozen=True)
class OutputOptions:
    """The output surface and run scope of one command, as ONE bundle (I3).

    `--format` (`fmt`) was added in bridge step 01; `--confirm` (which
    adapter answers the interactive confirm prompts — the terminal, or the
    JSON-lines pipe protocol) is wired in bridge step 03; the `--dry-run`
    flag and the `--db` path ride the bundle so every handler stays at
    <= 4 inputs. The defaults (`text`, `terminal`) are byte-identical to
    the pre-bridge output (I10).
    """

    fmt: str = "text"
    confirm: str = "terminal"
    dry_run: bool = False
    db_path: str = DEFAULT_DB_PATH


def _output_options(
    *, dry_run: bool = False, confirm: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Shared Click decorator: binds `--db`, `--format`, (on the six
    commands that have it, unchanged) `--dry-run` and (on the three
    interactive commands) `--confirm` into ONE `OutputOptions` bundle
    argument named `output` (I3).

    The `--format [text|json]` choice is branched only inside `cli.py` (I2):
    `json` renders the one `OutputDocument`; `text`, the default, prints the
    exact pre-bridge text lines. The `--confirm [terminal|json]` choice
    selects the confirm adapter only here at the composition root (P4):
    `terminal` (the default) keeps today's byte-identical behaviour, `json`
    selects `ember/adapters/json_confirm.py`. An unknown value is Click's
    own usage error (exit 2).
    """

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(
            *args: Any,
            output_fmt: str,
            db_path: str,
            dry_run: bool = False,
            output_confirm: str = "terminal",
            **kwargs: Any,
        ) -> Any:
            return func(
                *args,
                output=OutputOptions(
                    fmt=output_fmt,
                    confirm=output_confirm,
                    dry_run=dry_run,
                    db_path=db_path,
                ),
                **kwargs,
            )

        if dry_run:
            wrapper = click.option(
                "--dry-run",
                is_flag=True,
                default=False,
                help="Print the planned changes and write nothing.",
            )(wrapper)
        if confirm:
            wrapper = click.option(
                "--confirm",
                "output_confirm",
                type=click.Choice(("terminal", "json")),
                default="terminal",
                help=(
                    "Prompt surface: the terminal (default), or JSON events"
                    " on stdout with `{'answer': ...}` lines on stdin (then"
                    " every stdout line is one JSON object)."
                ),
            )(wrapper)
        wrapper = click.option(
            "--format",
            "output_fmt",
            type=click.Choice(("text", "json")),
            default="text",
            help="Output format: text lines (default) or one JSON document.",
        )(wrapper)
        wrapper = click.option(
            "--db",
            "db_path",
            default=DEFAULT_DB_PATH,
            help="SQLite database path.",
        )(wrapper)
        return wrapper

    return decorate


def _confirm_io(
    output: OutputOptions,
    json_cls: type[JsonCaptureConfirm]
    | type[JsonRelateConfirm]
    | type[JsonMaintainConfirm],
    terminal_cls: type[TerminalConfirm]
    | type[RelateTerminalConfirm]
    | type[MaintainTerminalConfirm],
) -> tuple[TerminalSink | JsonSink, Any]:
    """The ONE place the confirm adapter is chosen (P4): the composition
    root. `json_cls` is one of the three `--confirm json` adapters (each
    constructed with the json sink), `terminal_cls` one of the three
    terminal confirms (each constructed bare) — fix C6, I1: the
    parameter types name the real classes instead of bare `type`.
    Returns the output sink every stdout line of the body flows
    through plus the confirm port for the engine loop. `terminal` echoes
    exactly as before the bridge; `json` emits events and `summary`."""
    if output.confirm == "json":
        sink: TerminalSink | JsonSink = JsonSink()
        return sink, json_cls(sink)
    return TerminalSink(), terminal_cls()


class TerminalConfirm:
    """`ConfirmPort` on the terminal. End of input raises `UserAbort`."""

    def ask(self, prompt: str) -> str:
        click.echo(prompt, nl=False)
        try:
            answer = input()
        except EOFError as exc:
            click.echo()
            raise UserAbort("input ended") from exc
        return answer

    def write(self, text: str) -> None:
        click.echo(text)


class RelateTerminalConfirm:
    """`ConfirmPort` on the terminal for the relate loop.

    Like `TerminalConfirm`, but end of input raises the relate `UserAbort`
    (RELATE-031) so the relate confirm loop maps it to `aborted=True`.
    """

    def ask(self, prompt: str) -> str:
        click.echo(prompt, nl=False)
        try:
            answer = input()
        except EOFError as exc:
            click.echo()
            raise RelateUserAbort("input ended") from exc
        return answer

    def write(self, text: str) -> None:
        click.echo(text)


class MaintainTerminalConfirm:
    """`ConfirmPort` on the terminal for the maintain proposal loop.

    Like `RelateTerminalConfirm`, but end of input raises the maintain
    `UserAbort` (MAINTAIN-022) so the proposal loop maps it to `aborted=True`.
    """

    def ask(self, prompt: str) -> str:
        click.echo(prompt, nl=False)
        try:
            answer = input()
        except EOFError as exc:
            click.echo()
            raise MaintainUserAbort("input ended") from exc
        return answer

    def write(self, text: str) -> None:
        click.echo(text)


class EmberGroup(click.Group):
    """The ONE edge handler at the program's exit door (Batch 2 Chunk 2).

    Wraps the whole dispatch: an unexpected non-house exception becomes a
    single `error: EMBER-000 InternalError | ...` line on stderr, exit 1,
    and a crash file with the secrets scrubbed out. A known `EmberError`
    becomes exactly one house line with its own code and name (Chunk 4
    moved the printing of known errors here); click's own usage errors and
    a user abort keep their exit contract (N6: usage error 2, abort 2).
    """

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except (
            SystemExit,
            click.ClickException,
            click.exceptions.Exit,
            click.exceptions.Abort,
        ):
            # A user abort and click usage errors keep their exit contract
            # (N6: usage error 2, abort 2); SystemExit is a verdict already.
            raise
        except Exception as exc:
            # Known house error: the edge handler prints its own line and
            # exits 1 (Chunk 4 — the 19 per-command copies are gone).
            if isinstance(exc, EmberError):
                click.echo(f"error: {exc.log_line()}", err=True)
                sys.exit(1)
            _handle_unexpected(exc, command=ctx.info_name)


def _handle_unexpected(exc: Exception, *, command: str) -> None:
    """Print the ONE EMBER-000 house line and exit 1 for an unexpected
    exception. A broken pipe leaves NO crash file (nothing went wrong in
    the engine — nobody is there to read the output); every other
    unexpected exception writes a secret-scrubbed crash file and names it
    in the line. The handler prints the `InternalError` name itself; the
    base class `ember/errors.py` `code`/`name` stays untouched."""
    if isinstance(exc, BrokenPipeError):
        click.echo(
            f"error: EMBER-000 InternalError | ember.cli.{command} | output pipe closed",
            err=True,
        )
        sys.exit(1)

    frames = traceback.extract_tb(exc.__traceback__)
    innermost = frames[-1] if frames else None
    if innermost is not None:
        module = os.path.splitext(os.path.basename(innermost.filename))[0]
        where = f"{module}.{innermost.name}"
    else:
        where = "ember.cli"

    crash = write_crash_file(
        command=command,
        traceback_text=traceback.format_exc(),
    )
    click.echo(
        f"error: EMBER-000 InternalError | {where} | crash={crash}",
        err=True,
    )
    sys.exit(1)


@click.group(cls=EmberGroup)
@click.version_option(version=__version__, prog_name="ember")
def main() -> None:
    """Ember: project context management system."""


@main.command("init")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path to create or verify.",
)
def init_command(db_path: str) -> None:
    """Create and migrate a new knowledge base file (N8, D-25).

    The ONE command that creates the file, on purpose. On a missing file it
    creates and migrates it; on an existing file it succeeds only when the
    file is a healthy Ember database already at the latest schema version,
    and then changes nothing (byte-identical, exit 0). Anything else — a
    file that is not an Ember database, a version other than the latest,
    missing tables — is refused with CAPTURE-021 and left untouched.
    """
    outcome = init_knowledge_base(db_path)
    if outcome == "created":
        click.echo(f"initialized {db_path}")
    else:
        click.echo(f"{db_path} is already up to date; no changes")


@main.command("capture-source")
@click.option(
    "--file",
    "file_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Read raw text from this file instead of STDIN.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def capture_source(file_path: str | None, db_path: str) -> None:
    """Phase 1: store raw input, dedup by content hash, print source reference."""
    mode = InputMode.FILE if file_path else InputMode.STDIN
    raw_text = read_raw_text(mode=mode, path=file_path)
    conn = open_existing_database(db_path)
    store = SqliteSourceStore(conn)
    result = store_source(store, raw_text)
    if result.reused:
        click.echo("source already stored", err=True)
    click.echo(
        json.dumps(
            {
                "source_id": result.source_id,
                "content_hash": result.content_hash,
                "raw_text": result.raw_text,
            },
            ensure_ascii=False,
        )
    )


@main.command("capture")
@click.option(
    "--file",
    "file_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Read raw text from this file instead of STDIN.",
)
@_output_options(confirm=True)
def capture(file_path: str | None, output: OutputOptions) -> None:
    """Run all 4 capture phases: store, propose, gatekeeper, confirm, write.

    Exit 0 when every proposal is handled, 1 on a phase 1/2/3 error or a DB
    write failure, and 2 when the user quits mid-prompt. `--confirm json`
    (bridge step 03) requires `--file`: stdin then carries the `{"answer":`
    ...}` answer lines instead of the pasted text.
    """
    if output.confirm == "json" and file_path is None:
        raise click.UsageError(
            "--confirm json requires --file (stdin carries the answer lines)"
        )
    mode = InputMode.FILE if file_path else InputMode.STDIN
    sink, confirm = _confirm_io(output, JsonCaptureConfirm, TerminalConfirm)
    raw_text = read_raw_text(mode=mode, path=file_path)
    conn = open_database(db_path=output.db_path)
    stored = _store(conn, raw_text)
    response = _propose(conn, stored)
    _store_ai_response(conn, stored, response)
    for drop in response.batch.dropped:
        sink.echo(f"dropped proposal: {drop.rule}")
    if not response.batch.proposals:
        sink.echo("0 valid proposals")

    gatekeeper = SqliteItemGatekeeper(conn)
    run = _gatekeeper_run(conn, gatekeeper, stored)
    outcome = validate_proposals(response.batch.proposals, run)
    for reject in outcome.rejected:
        sink.echo(f"rejected by gatekeeper: {reject.rule}")

    result = run_confirm_loop(
        outcome.validated,
        confirm=confirm,
        commit=gatekeeper,
        revalidate=lambda draft: validate_add_item(draft, run),
        # One accepted item = one transaction (Batch 4 chunk 8, 4.3 #9).
        unit_of_work=partial(unit_of_work, conn),
    )
    sink.summary(
        f"accepted: {len(result.accepted_ids)}"
        f", rejected: {result.rejected_count}"
        f", warnings: {result.warning_count}"
        f", aborted: {str(result.aborted).lower()}",
        {
            "accepted": len(result.accepted_ids),
            "rejected": result.rejected_count,
            "warnings": result.warning_count,
            "aborted": result.aborted,
        },
    )

    if result.aborted:
        sys.exit(2)


@main.command("set-validated")
@click.option(
    "--item", "item_id", type=int, required=True, help="Item id to mark validated."
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def set_validated(item_id: int, db_path: str) -> None:
    """Mark an Assumption as validated (human-only, spec 3.5)."""
    _write_validated_flag(item_id, db_path, new_value=True)


@main.command("clear-validated")
@click.option(
    "--item", "item_id", type=int, required=True, help="Item id to unmark."
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def clear_validated(item_id: int, db_path: str) -> None:
    """Clear the validated flag on an Assumption (human-only, spec 3.5)."""
    _write_validated_flag(item_id, db_path, new_value=False)


class _RelateWriteConnection:
    """The ONE short-lived relate write connection (decision N9).

    Opened lazily on the first write — after the read-only open and the
    pool reads have done their part — never migrated, no backup, and closed
    as soon as the command ends. Every relate write (embedding-cache upserts
    and the model-change wipe, the raw AI reply save, and the confirmed-link
    writes) goes through the connection this holder returns, so a relate run
    opens at most one writing connection at a time.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._embedding_store: Any = None

    def connection(self) -> sqlite3.Connection:
        """Open the write connection on first use; return it afterwards."""
        if self._conn is None:
            self._conn = open_relate_database_write(self._db_path)
        return self._conn

    def embedding_store(self) -> Any:
        """Build the embedding cache on the write connection (once)."""
        if self._embedding_store is None:
            self._embedding_store = build_embedding_store(self.connection())
        return self._embedding_store

    def close(self) -> None:
        """Close the write connection if one was ever opened."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._embedding_store = None


class _RelateEmbeddingCache:
    """Embedding-cache reads on the read-only connection, writes on the
    ONE short-lived write connection (decision N9).

    Wraps the `EmbeddingStorePort` built on the read-only connection for the
    three reads (`get`, `model_name_of`, `first_model_name`) and routes the
    two writes (`upsert`, `wipe`) to the same port type built on the
    short-lived write connection.
    """

    def __init__(self, read_store: Any, writes: _RelateWriteConnection) -> None:
        self._read_store = read_store
        self._writes = writes

    def get(self, item_id: int) -> Any:
        return self._read_store.get(item_id)

    def model_name_of(self, item_id: int) -> Any:
        return self._read_store.model_name_of(item_id)

    def first_model_name(self) -> Any:
        return self._read_store.first_model_name()

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        self._writes.embedding_store().upsert(item_id, vector, model_name)

    def wipe(self) -> None:
        self._writes.embedding_store().wipe()


@main.command("relate")
@click.option("--item", "item_id", type=int, default=None, help="Item id to relate.")
@click.option(
    "--latest",
    is_flag=True,
    default=False,
    help="Newest Active item with no link from it.",
)
@_output_options(confirm=True)
def relate(item_id: int | None, latest: bool, output: OutputOptions) -> None:
    """Run all 4 relate phases: load, pool, AI propose, confirm, write.

    Prints one `relate rejected: CODE | detail` line per gatekeeper rejection,
    then the summary. Exit 0 when every proposal is handled, 1 on a phase
    error, and 2 when the user quits mid-prompt. An empty candidate pool
    prints the Phase 2 JSON and exits 0 without an AI call. `--confirm json`
    (bridge step 03) turns every stdout line into one JSON event object.

    N9: every read runs on a STRICTLY read-only connection that never
    migrates and never backs up; the writes (embedding cache, raw AI reply,
    confirmed links) share ONE short-lived write connection that never
    migrates either.
    """
    if item_id is not None and latest:
        raise click.UsageError("use either --item or --latest, not both")
    if item_id is None and not latest:
        raise click.UsageError("one of --item or --latest is required")
    sink, confirm = _confirm_io(output, JsonRelateConfirm, RelateTerminalConfirm)
    aborted = False
    validate_embedder_config()
    conn = open_relate_database_readonly(output.db_path)
    writes = _RelateWriteConnection(output.db_path)
    try:
        lookup = SqliteLinkContext(conn)
        link_proposer = build_link_proposer(os.environ)
        if latest:
            result = load_latest_candidates(lookup)
        else:
            result = load_item_candidates(
                lookup, item_id=item_id, db_path=output.db_path
            )
        if result is None:
            sink.echo("no unrelated items")
            return
        if result.universe.items:
            pool = build_candidate_pool(
                result,
                link_lookup=lookup,
                embedding_store=_RelateEmbeddingCache(
                    build_embedding_store(conn), writes
                ),
                embedder=build_embedder(),
            )
        else:
            pool = Pool.empty()
        if pool.warning:
            click.echo(pool.warning, err=True)
        if not pool.ranked:
            sink.echo(
                json.dumps(
                    {"phase": 2, "pool_size": 0, "signals": pool.counts}
                )
            )
            return
        ports = RelatePorts(
            link_lookup=lookup,
            link_store=SqliteLinkStore(writes.connection()),
            link_proposer=link_proposer,
            ai_response_store=build_ai_response_store(writes.connection()),
            confirm=confirm,
        )
        request = RelateRequest(
            new_item=result.new_item, ranked=pool.ranked, env=os.environ
        )
        outcome = run_relate(ports, request)
    finally:
        writes.close()
        conn.close()
    for rejection in outcome.gatekeeper_rejections:
        if rejection.detail:
            sink.echo(
                f"relate rejected: {rejection.code} | {rejection.detail}"
            )
        else:
            sink.echo(f"relate rejected: {rejection.code}")
    sink.summary(
        f"accepted: {len(outcome.accepted)}"
        f", rejected: {outcome.rejected}"
        f", skipped: {outcome.skipped}"
        f", aborted: {str(outcome.aborted).lower()}",
        {
            "accepted": len(outcome.accepted),
            "rejected": outcome.rejected,
            "skipped": outcome.skipped,
            "aborted": outcome.aborted,
        },
    )
    aborted = outcome.aborted
    if aborted:
        sys.exit(2)


@main.command("maintain")
@_output_options(dry_run=True, confirm=True)
def maintain(output: OutputOptions) -> None:
    """Run the maintain sweep, then propose AI closes for the stale shortlist.

    A plain run writes the derived status changes to `items` and appends one
    `change_log` row per change. `--dry-run` loads, derives and prints only, and it
    writes no `items` or `change_log` row. Phase 5 (engine-maintain-plan §14)
    runs the free pre-filter on a fresh snapshot: an empty shortlist prints the
    `stale:` outcome line and builds no AI adapter (no key needed), a
    non-empty one proposes close for each stale card and confirms with
    `[y]es / [n]o / [q]uit`. An accepted close is written through the human
    `close-item` validate path. The AI never closes anything itself. Exit 0
    normally, 1 on an error, 2 when the user quits the proposal loop.
    `--confirm json` (bridge step 03) turns every stdout line into one JSON
    event object.
    """
    outcome = ProposalOutcome(stale=0, proposed=0, accepted=0, rejected=0)
    json_mode = output.fmt == "json"
    sink, confirm = _confirm_io(output, JsonMaintainConfirm, MaintainTerminalConfirm)
    sweep_changes: list[StatusChange] = []
    total_items = 0
    stale_truncated = False
    # The Phase 5 error to re-raise AFTER the document of what completed is
    # printed (Batch 4 chunk 8, 4.6 #3 / 4.3 #22); None keeps today's flow.
    proposal_error: EmberError | None = None
    # G2-B: a `--dry-run` is a read — it opens STRICTLY read-only and
    # never migrates an older file (plan §5.5, story 76).
    conn = (
        open_maintain_database_readonly(output.db_path, required_version=11)
        if output.dry_run
        else open_maintain_database(output.db_path)
    )
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
        # One user action is one transaction (Batch 4 chunk 8, 4.3 #9).
        unit_of_work=partial(unit_of_work, conn),
    )
    if output.dry_run:
        snapshot = _load(ports.lookup)
        changes = derive_status_changes(snapshot)
        total_items = len(snapshot.items)
        if not json_mode:
            for line in format_report(changes, total_items):
                sink.echo(line)
        # Nothing was applied, so this fresh load is still the pre-apply
        # view: the dry-run list deliberately names every candidate
        # before the human commits to a run (review fix 3).
        shortlist = stale_close_candidates(
            _load(ports.lookup), now=datetime.now(timezone.utc)
        )
        stale_truncated = shortlist.truncated
        if shortlist.truncated and not json_mode:
            sink.echo("stale shortlist capped at 10 items (list truncated)")
        if not json_mode:
            for candidate in shortlist.candidates:
                sink.echo(
                    f"item {candidate.item_id}: stale {candidate.item_type}"
                    f" (newest answers link"
                    f" {candidate.newest_answers_link_id},"
                    f" confirmed {candidate.newest_answer_created_at})"
                    " (dry-run)"
                )
        outcome = ProposalOutcome(
            stale=len(shortlist.candidates), proposed=0, accepted=0, rejected=0
        )
        sweep_changes = changes
    else:
        result = run_sweep(ports, MaintainRequest())
        total_items = result.total_items
        sweep_changes = result.changed
        if not json_mode:
            for line in format_report(result.changed, result.total_items):
                sink.echo(line)
        shortlist = stale_close_candidates(
            _load(ports.lookup), now=datetime.now(timezone.utc)
        )
        stale_truncated = shortlist.truncated
        if shortlist.truncated and not json_mode:
            sink.echo("stale shortlist capped at 10 items (list truncated)")
        if shortlist.candidates:
            try:
                outcome = run_close_proposals(
                    CloseProposalPorts(
                        lookup=ports.lookup,
                        store=ports.store,
                        close_proposer=build_close_proposer(os.environ),
                        ai_response_store=SqliteAiResponseStore(conn),
                        confirm=confirm,
                        unit_of_work=ports.unit_of_work,
                    ),
                    now=datetime.now(timezone.utc),
                )
            except EmberError as exc:
                # 4.6 #3 / 4.3 #22 (Batch 4 chunk 8): the sweep completed and
                # WROTE its changes before this later action failed. In JSON
                # mode the document is the report, so it is printed first;
                # the error is re-raised after it, and the edge handler names
                # it and exits 1. Text mode keeps today's single error line.
                if not json_mode:
                    raise
                outcome = ProposalOutcome(
                    stale=len(shortlist.candidates),
                    proposed=0,
                    accepted=0,
                    rejected=0,
                )
                proposal_error = exc
    if json_mode:
        summary = summary_counts(sweep_changes, total_items)
        summary.update(
            stale=outcome.stale,
            stale_truncated=stale_truncated,
            proposed=outcome.proposed,
            accepted=outcome.accepted,
            rejected=outcome.rejected,
            aborted=outcome.aborted,
            # The engine's own StaleShortlist model, serialized whole (D3):
            # in document mode the text-mode shortlist lines live here as
            # data instead of stdout lines (review fix, ticket 24).
            stale_candidates=shortlist,
        )
        sink.echo(
            render_document(
                OutputDocument(
                    command="maintain",
                    changes=sweep_changes,
                    summary=summary,
                    dry_run=output.dry_run,
                )
            )
        )
    else:
        sink.summary(
            f"stale: {outcome.stale}, proposed: {outcome.proposed},"
            f" accepted: {outcome.accepted}, rejected: {outcome.rejected},"
            f" aborted: {str(outcome.aborted).lower()}",
            {
                "stale": outcome.stale,
                "proposed": outcome.proposed,
                "accepted": outcome.accepted,
                "rejected": outcome.rejected,
                "aborted": outcome.aborted,
            },
        )
    if proposal_error is not None:
        raise proposal_error
    if outcome.aborted:
        sys.exit(2)


@main.command("close-item")
@click.option(
    "--item",
    "item_id",
    type=int,
    required=True,
    help="Item id to close.",
)
@click.option(
    "--reason",
    "reason",
    required=True,
    help="Close reason: invalidated or expired.",
)
@_output_options(dry_run=True)
def close_item(item_id: int, reason: str, output: OutputOptions) -> None:
    """Close an item by hand, challenging its live dependents.

    Prints the same report as `maintain`. `--dry-run` loads and validates only;
    it writes no `items` or `change_log` row.
    """
    # Option checks run BEFORE the database opens (B4-01): a bad `--reason`
    # must not create a database file. Same errors, same sentences as the
    # validator in human_actions.py raises.
    if reason not in CLOSE_REASONS:
        raise CloseReasonInvalid(
            "close-item: unknown --reason", item_id=item_id, reason=reason
        )
    if reason not in HUMAN_SETTABLE_REASONS:
        raise CloseReasonMismatch(
            "close-item: reason is not human-settable",
            item_id=item_id,
            reason=reason,
        )
    # G2-B: a `--dry-run` is a read — it opens STRICTLY read-only and
    # never migrates an older file (plan §5.5, story 76).
    conn = (
        open_maintain_database_readonly(output.db_path, required_version=11)
        if output.dry_run
        else open_maintain_database(output.db_path)
    )
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
        # One user action is one transaction (Batch 4 chunk 8, 4.3 #9).
        unit_of_work=partial(unit_of_work, conn),
    )
    if output.dry_run:
        snapshot = _load(ports.lookup)
        changes = validate_close_item(snapshot, item_id, reason)
        total_items = len(snapshot.items)
    else:
        result = run_close_item(
            ports, MaintainRequest(item_id=item_id, reason=reason)
        )
        changes = result.changed
        total_items = result.total_items
    _echo_document(
        output,
        OutputDocument(
            command="close-item",
            changes=changes,
            summary=summary_counts(changes, total_items),
            dry_run=output.dry_run,
        ),
    )
    if output.fmt != "json":
        for line in format_report(changes, total_items):
            if output.dry_run:
                click.echo(f"{line} (dry-run)")
            else:
                click.echo(line)


@main.command("set-status")
@click.option(
    "--item",
    "item_id",
    type=int,
    required=True,
    help="Item id to move.",
)
@click.option(
    "--to",
    "to_status",
    required=True,
    help="Target status: Active or Challenged.",
)
@_output_options()
def set_status(item_id: int, to_status: str, output: OutputOptions) -> None:
    """Move an item between Active and Challenged by hand.

    Exactly one of those two values is accepted; a `--to Active` on a
    `Challenged` item also sets the manual shield. Prints the same report as
    `maintain`.
    """
    conn = open_maintain_database(output.db_path)
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
        # One user action is one transaction (Batch 4 chunk 8, 4.3 #9).
        unit_of_work=partial(unit_of_work, conn),
    )
    result = run_set_status(
        ports, MaintainRequest(item_id=item_id, to_status=to_status)
    )
    changes = result.changed
    total_items = result.total_items
    _echo_document(
        output,
        OutputDocument(
            command="set-status",
            changes=changes,
            summary=summary_counts(changes, total_items),
        ),
    )
    if output.fmt != "json":
        for line in format_report(changes, total_items):
            click.echo(line)


@main.command("reverse-supersedes")
@click.option(
    "--item",
    "item_id",
    type=int,
    required=True,
    help="Item id to restore.",
)
@click.option(
    "--link",
    "link_id",
    type=int,
    required=True,
    help="Confirmed supersedes link id to reverse.",
)
@_output_options()
def reverse_supersedes(
    item_id: int, link_id: int, output: OutputOptions
) -> None:
    """Undo a supersedes: restore the item and mark the link reversed.

    Writes the `reversed_at` column on the `links` row, the item restore, and
    the two `change_log` rows in one transaction from one clock read. Prints
    the same report as `maintain`.
    """
    conn = open_maintain_database(output.db_path)
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
    )
    result = run_reverse_supersedes(
        ports, MaintainRequest(item_id=item_id, link_id=link_id)
    )
    changes = result.changed
    total_items = result.total_items
    _echo_document(
        output,
        OutputDocument(
            command="reverse-supersedes",
            changes=changes,
            summary=summary_counts(changes, total_items),
        ),
    )
    if output.fmt != "json":
        for line in format_report(changes, total_items):
            click.echo(line)


@main.command("edit-item")
@click.option(
    "--item",
    "item_id",
    type=int,
    required=True,
    help="Item id to edit.",
)
@click.option(
    "--field",
    "field",
    required=True,
    help="Field to edit: rationale (on a Decision) or source (on a Finding).",
)
@click.option(
    "--value",
    "value",
    required=True,
    help="New text for the field. An empty string blanks it.",
)
@_output_options(dry_run=True)
def edit_item(
    item_id: int, field: str, value: str, output: OutputOptions
) -> None:
    """Edit an item's rationale or source by hand, ledger row always.

    Under the rule-7 ADR the item text (`statement`) and all raw tables stay
    immutable: `rationale` is writable on a Decision, `source` on a Finding.
    A same-value edit is a no-op (exit 0, nothing written). The human invoking
    the command IS the confirmation and no AI runs in this path.
    """
    # Option checks run BEFORE the database opens (B4-01): a bad `--field`
    # must not create a database file. Same error, same sentence as the
    # validator in human_actions.py raises.
    if field not in EDIT_FIELDS:
        raise EditFieldUnknown(
            "edit-item: unknown --field", item_id=item_id, field=field
        )
    # G2-B: a `--dry-run` is a read — it opens STRICTLY read-only and
    # never migrates an older file (plan §5.5, story 76).
    conn = (
        open_maintain_database_readonly(output.db_path, required_version=11)
        if output.dry_run
        else open_maintain_database(output.db_path)
    )
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
    )
    if output.dry_run:
        snapshot = _load(ports.lookup)
        changes = validate_edit_item(snapshot, item_id, field, value)
    else:
        changes = run_edit_item(
            ports,
            MaintainRequest(item_id=item_id, field=field, value=value),
        )
    _echo_document(
        output,
        OutputDocument(
            command="edit-item",
            changes=changes,
            summary={},
            dry_run=output.dry_run,
        ),
    )
    if output.fmt == "json":
        return
    for change in changes:
        if output.dry_run:
            old = change.old_value if change.old_value is not None else "<null>"
            click.echo(
                f"item {change.item_id}: {change.field}:"
                f" {old} -> {change.new_value} (dry-run)"
            )
        else:
            click.echo(f"item {change.item_id}: {change.field} edited")


@main.command("remove-link")
@click.option(
    "--link",
    "link_id",
    type=int,
    required=True,
    help="Link id to remove.",
)
@_output_options(dry_run=True)
def remove_link(link_id: int, output: OutputOptions) -> None:
    """Remove one confirmed relationship edge, ledger row always.

    The removal is ONE status flip (`Confirmed -> Rejected`) plus its
    `link_removed` ledger row in one transaction: the row is never deleted
    (the ledger's foreign key refuses that) and never flipped back, so a
    removed pair stays blocked forever (the #15 ruling). A second removal of
    the same link is an error (MAINTAIN-015), not a silent no-op. The human
    invoking the command IS the confirmation and no AI runs in this path.
    """
    # G2-B: a `--dry-run` is a read — it opens STRICTLY read-only and
    # never migrates an older file (plan §5.5, story 76).
    conn = (
        open_maintain_database_readonly(output.db_path, required_version=11)
        if output.dry_run
        else open_maintain_database(output.db_path)
    )
    ports = MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
    )
    # The display-only link line is read from the same Phase-1 snapshot
    # the command writes from, BEFORE the flip (a removed link leaves
    # the Confirmed-only read). Step plan 05 §2/§3: display fields are
    # not carried on LinkChange.
    snapshot = _load(ports.lookup)
    link = _confirmed_link(snapshot, link_id)
    if output.dry_run:
        changes = validate_remove_link(snapshot, link_id)
    else:
        changes = run_remove_link(
            ports, MaintainRequest(link_id=link_id)
        )
    _echo_document(
        output,
        OutputDocument(
            command="remove-link",
            changes=changes,
            summary={},
            dry_run=output.dry_run,
        ),
    )
    if output.fmt == "json":
        return
    for change in changes:
        if output.dry_run:
            click.echo(
                f"link {change.link_id}: {change.old_status} ->"
                f" {change.new_status} (dry-run)"
            )
        elif link is not None:
            click.echo(
                f"link {change.link_id}: {link.link_type}"
                f" {link.source_item_id} -> {link.target_item_id} removed"
                f" ({change.old_status} -> {change.new_status})"
            )
        else:
            click.echo(
                f"link {change.link_id}: {change.old_status} ->"
                f" {change.new_status} removed"
            )


def _confirmed_link(snapshot: MaintainSnapshot, link_id: int) -> Link | None:
    """Find one confirmed link in the snapshot, or None (display-only read)."""
    for link in snapshot.links:
        if link.id == link_id and link.status == "Confirmed":
            return link
    return None


def _undo_ports(conn) -> MaintainPorts:
    """Open the write path one undo/redo runs through (undo step 04).

    The ports carry the lookup themselves (`ports.lookup`), so the command
    can make its one display-only read (the group the write just appended)
    afterwards without a second object to pass around.
    """
    return MaintainPorts(
        lookup=SqliteMaintainContext(conn),
        store=SqliteMaintainStore(conn),
        group_ids=SqliteGroupIdPort(conn),
    )


def _newest_group_id(context: SqliteMaintainContext) -> int:
    """The ledger's newest group id: the one an undo/redo just wrote.

    Display-only read (the remove-link link-line precedent). `apply_inverse_group`
    appends the new group, so after a successful run it is the last one.
    """
    return context.list_grouped_ledger()[-1].group_id


def _echo_document(output: OutputOptions, document: OutputDocument) -> None:
    """Print ONE bridge document when `fmt` is json (fix C3: the one
    shape every write/utility command repeats); text mode is silent here
    - each command's own text lines stay at its site."""
    if output.fmt == "json":
        click.echo(render_document(document))


def _run_undo_or_redo(
    command: str, run: Callable[[Any, UndoRequest], Any], output: OutputOptions
) -> None:
    """The ONE body of `ember undo` / `ember redo` (fix C3): the same
    open (G2-B: a dry-run opens strictly read-only), the same error
    edge, the same document and report line. `run` is run_undo or
    run_redo - the only difference between the two commands."""
    conn = (
        # The undo groups are the ledger's `group_id` rows (migration 013),
        # so a read-only dry-run demands floor 13, not the maintain floor
        # 11 (G2-B): an older file gets the honest SchemaOutdated answer
        # instead of a misleading nothing-to-undo (4.6 #11).
        open_maintain_database_readonly(output.db_path, required_version=13)
        if output.dry_run
        else open_maintain_database(output.db_path)
    )
    ports = _undo_ports(conn)
    result = run(ports, UndoRequest(dry_run=output.dry_run))
    new_group_id = (
        None if output.dry_run else _newest_group_id(ports.lookup)
    )
    _echo_document(
        output,
        OutputDocument(
            command=command,
            changes=result.changes,
            summary={
                "direction": result.direction,
                "source_group_id": result.source_group_id,
                "source_action": result.source_action,
                "target_label": result.target_label,
                "new_group_id": new_group_id,
            },
            dry_run=output.dry_run,
        ),
    )
    if output.fmt != "json":
        click.echo(format_undo_line(result, new_group_id))


@main.command("undo")
@_output_options(dry_run=True)
def undo(output: OutputOptions) -> None:
    """Undo the newest human change by appending its inverse to the ledger.

    Nothing is erased: the ledger only grows. The sweep's own changes carry
    no undo group and are never undoable. A refusal (the change's target
    moved since) exits 1 and writes nothing. `--dry-run` prints the same
    line and writes zero rows.
    """
    _run_undo_or_redo("undo", run_undo, output)


@main.command("redo")
@_output_options(dry_run=True)
def redo(output: OutputOptions) -> None:
    """Re-apply the change you just undid, the same append-only way.

    A newer human change clears the redo (exit 1, `MAINTAIN-024`): undo
    again to make it available. Same refusals and `--dry-run` as
    `ember undo`.
    """
    _run_undo_or_redo("redo", run_redo, output)


@main.command("current-state")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def current_state_command(db_path: str) -> None:
    """List the live items: `Challenged` first, then `Active`, as JSON.

    Read-only: the database is opened read-only and never migrated, so a
    database behind the required schema version is refused, not upgraded.
    """
    conn = open_query_database(db_path)
    output = run_current_state(SqliteQueryContext(conn))
    click.echo(output)


@main.command("topic-search")
@click.option(
    "--query",
    "query",
    required=True,
    help="Search text: one or more words, matched as whole tokens.",
)
@click.option(
    "--status",
    "status",
    default=None,
    help="Only score items with this status: Active, Challenged or Closed.",
)
@click.option(
    "--type",
    "item_type",
    default=None,
    help="Only score items of this type: Decision, Assumption, Finding or Question.",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=None,
    help="Keep only the top N ranked results. 0 prints an empty result list.",
)
@click.option(
    "--offset",
    "offset",
    type=int,
    default=None,
    help="Skip N ranked results. Omit it to skip none.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def topic_search_command(
    query: str,
    status: str | None,
    item_type: str | None,
    limit: int | None,
    offset: int | None,
    db_path: str,
) -> None:
    """Rank items by BM25 over their statements, as JSON.

    Every item is searched, `Closed` ones included, and each result carries its
    status. `--status` and `--type` narrow what is scored (the filtered subset
    is the corpus, so counts recompute); behind the ranking, `--offset` skips
    and `--limit` crops the list, while `total` in the envelope counts every
    match before either crop. Read-only, like every query command.
    """
    topic_filter = TopicFilter(
        status=status, type=item_type, limit=limit, offset=offset
    )
    conn = open_query_database(db_path)
    output = run_topic_search(SqliteQueryContext(conn), query, topic_filter)
    click.echo(output)


@main.command("why")
@click.option(
    "--item", "item_id", type=int, required=True, help="Item id to explain."
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def why_command(item_id: int, db_path: str) -> None:
    """Walk the reasons behind an item: `depends_on` back, `supports` back.

    Prints the reasons nearest first, each with the depth it was reached at.
    Read-only, like every query command.
    """
    conn = open_query_database(db_path)
    output = run_why(SqliteQueryContext(conn), item_id)
    click.echo(output)


@main.command("history")
@click.option(
    "--item",
    "item_id",
    type=int,
    default=None,
    help="Item id to show. Omit it for the whole ledger.",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=None,
    help="Show at most N events after the cut. Omit it for no cap.",
)
@click.option(
    "--offset",
    "offset",
    type=int,
    default=None,
    help="Skip N events after the cut. Omit it to skip none.",
)
@click.option(
    "--since",
    "since",
    default=None,
    help=(
        "Keep events at or after this ISO-8601 datetime. The value must name"
        " an offset (for example 2026-01-15T00:00:00+00:00) and is normalised"
        " to UTC."
    ),
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def history_command(
    item_id: int | None, limit: int | None, offset: int | None, since: str | None, db_path: str
) -> None:
    """Show the change ledger: one item's events, or the whole ledger.

    Each event carries what changed and why. With no `--item` every row is
    shown, including the rejected-proposal rows that belong to no item. The
    window composes on both views: `--since` cuts by time first, then
    `--offset` skips, then `--limit` caps, always behind the ledger order.
    Read-only, like every query command.
    """
    conn = open_query_database(db_path)
    page = HistoryPage(limit=limit, offset=offset, since=since)
    output = run_history(SqliteQueryContext(conn), item_id, page)
    click.echo(output)


@main.command("backup")
@click.argument("target_path")
@_output_options()
def backup(target_path: str, output: OutputOptions) -> None:
    """Copy the knowledge base to a restorable snapshot file.

    Uses SQLite's online backup API, so the copy is consistent even while
    another command writes. The source is opened read-only and never
    migrated. An existing target is rotated aside into `.old-1` (with the
    newest 3 kept), never destroyed.

    Restore: copy the file back, or point Ember at it with `--db`. There is
    deliberately no restore command (GLOSSARY).
    """
    report = create_backup(output.db_path, target_path)
    # T9: the adapter report becomes a plain dict on the CLI side, before it
    # could reach the bridge renderer.
    report_dict = {
        "path": report.path,
        "schema_version": report.schema_version,
        "item_count": report.item_count,
        "rotated": report.rotated,
    }
    if report.rotated:
        click.echo(f"rotated to {report.rotated}", err=True)
    _echo_document(
        output,
        OutputDocument(
            command="backup", changes=[], summary=report_dict
        ),
    )
    if output.fmt != "json":
        click.echo(
            f"backup written: {report.path}"
            f" (schema v{report.schema_version}, {report.item_count} items)"
        )


@main.command("export")
@click.option(
    "--out",
    "out_path",
    type=str,
    default=None,
    help="Write the export to this UTF-8 text file instead of STDOUT.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def export(out_path: str | None, db_path: str) -> None:
    """Render the whole knowledge base as one readable UTF-8 text file.

    Deterministic: the same database renders byte-identical every time,
    because the header's time line is the newest ledger event, never the
    wall clock. Embeddings and raw AI answers are derived, rebuildable
    data and are excluded. Raw source text is preserved verbatim.

    This file is for reading without Ember. It is not restorable into
    Ember; that is the backup's job (GLOSSARY).
    """
    conn = open_query_database(db_path)
    try:
        data = gather_export(conn)
    finally:
        conn.close()
    text = render_export(data)
    if out_path is not None:
        refuse_self_overwrite(db_path, out_path)
        write_export(text, out_path)
        click.echo(
            f"exported {len(data.items)} items, {len(data.links)} links,"
            f" {len(data.ledger)} ledger rows, {len(data.sources)} sources"
            f" -> {out_path}"
        )
    else:
        click.echo(text, nl=False)


@main.command("db-check")
@_output_options()
def db_check(output: OutputOptions) -> None:
    """Report database health: version, floors, triggers, drift, replay.

    Read-only: the file is opened `mode=ro` and never migrated or written.
    One command, one job, no mode flags. Exit 0 when the report ends
    `result: OK`, 1 on `result: DRIFT` or `result: UNREADABLE`.
    """
    report = check_database(output.db_path)
    # T9: the adapter report becomes a plain dict on the CLI side, before it
    # could reach the bridge renderer.
    report_dict = {
        "result": report.result,
        "detail": report.detail,
        "lines": report.lines,
    }
    if report.detail is not None:
        click.echo(f"detail: {report.detail}", err=True)
    _echo_document(
        output,
        OutputDocument(
            command="db-check", changes=[], summary=report_dict
        ),
    )
    if output.fmt != "json":
        for line in report.lines:
            click.echo(line)
    if report.result != "OK":
        sys.exit(1)


def _write_validated_flag(item_id: int, db_path: str, *, new_value: bool) -> None:
    """Write the flag on an Assumption. `new_value` is data, not a mode switch.

    Finding 4.5 #18: a set that changes nothing writes NO ledger row — a
    `true -> true` row would be history for a change that never happened.
    The command still exits 0 and says honestly that nothing was written.
    """
    conn = open_existing_database(db_path)
    ids = SqliteGroupIdPort(conn)
    gatekeeper = SqliteItemGatekeeper(conn, group_ids=ids)
    item = validate_set_validated(gatekeeper.find_item(item_id), item_id)
    if validated_change_is_noop(item, new_value):
        click.echo(
            f"item {item.id} validated: {str(new_value).lower()}"
            " (unchanged, nothing written)"
        )
        return
    gatekeeper.save_validated_flag(
        item, validated=new_value, group_id=ids.next_group_id()
    )
    click.echo(f"item {item.id} validated: {str(new_value).lower()}")


def _store(conn, raw_text: str) -> StoredSource:
    stored = store_source(SqliteSourceStore(conn), raw_text)
    if stored.reused:
        click.echo("source already stored", err=True)
    return stored


def _propose(conn, stored: StoredSource) -> ProposalResponse:
    proposer = build_item_proposer()
    context = build_context(SqliteItemContext(conn), read_context_mode(os.environ))
    return propose_items(proposer, raw_text=stored.raw_text, context=context)


def _store_ai_response(
    conn, stored: StoredSource, response: ProposalResponse
) -> None:
    """Store the raw AI answer verbatim, before anything is parsed away (D8)."""
    SqliteAiResponseStore(conn).save(
        source_id=stored.source_id, raw_response=response.raw_response
    )


def _gatekeeper_run(
    conn, gatekeeper: SqliteItemGatekeeper, stored: StoredSource
) -> GatekeeperRun:
    """Read the stored source text, so the quote check uses the stored row."""
    return GatekeeperRun(
        source_id=stored.source_id,
        source_text=load_source_text(SqliteSourceStore(conn), stored.source_id),
        existing=gatekeeper.statements(),
        next_id=gatekeeper.next_item_id,
        clock=gatekeeper.now,
    )


# --- bridge read commands (step 02) -----------------------------------------


@main.command("list-items")
@click.option(
    "--status",
    "status",
    default=None,
    help="Only list items with this status: Active, Challenged or Closed.",
)
@click.option(
    "--type",
    "item_type",
    default=None,
    help="Only list items of this type: Decision, Assumption, Finding or Question.",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=None,
    help="Keep at most N items after the cut. 0 prints an empty list.",
)
@click.option(
    "--offset",
    "offset",
    type=int,
    default=None,
    help="Skip N items after the cut. Omit it to skip none.",
)
@click.option(
    "--counts",
    "counts",
    is_flag=True,
    default=False,
    help=(
        "Print one counts document instead of the list: the four Home"
        " counts (active, challenged, closed, total) in `summary`."
    ),
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def list_items_command(
    status: str | None,
    item_type: str | None,
    limit: int | None,
    offset: int | None,
    counts: bool,
    db_path: str,
) -> None:
    """List every item in any status, as JSON.

    Unlike `current-state`, `Closed` items are listed on purpose, each with
    its status and close reason. `total` is the count after the filters but
    before `--limit`/`--offset` crop the printed window. Read-only: the
    database is opened read-only and never migrated, like every query
    command. With `--counts` the command instead prints one document whose
    `summary` carries the four Home counts (`active`, `challenged`,
    `closed`, `total`), each equal to the per-status call's `total`.

    Rule I3 exception, recorded by the founder 2026-11-01 (fix C1): this
    Click callback takes six parameters because Click binds one option to
    one parameter; the rule's object bundling lives one layer down, where
    the pure core takes the named `TopicFilter` and `ListPage` objects.
    """
    if counts:
        conn = open_query_database(db_path)
        counts_document = count_by_status(SqliteQueryContext(conn).list_items())
        click.echo(json.dumps({"summary": counts_document}, ensure_ascii=False))
        return
    conn = open_query_database(db_path)
    filter_ = TopicFilter(status=status, type=item_type)
    page = ListPage(limit=limit, offset=offset)
    output = run_list_items(SqliteQueryContext(conn), filter_, page)
    click.echo(output)


@main.command("show-item")
@click.option(
    "--item",
    "item_id",
    type=int,
    required=True,
    help="Item id to show.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def show_item_command(item_id: int, db_path: str) -> None:
    """Show one item, its verbatim source text and all its links, as JSON.

    Every link is included in both directions (`links_out`, `links_in`),
    Rejected and reversed ones too, each with the other item's coordinates
    and the `reversed_at` timestamp (`null` on a live link, and always null
    on an older schema file without the column). Read-only, like every
    query command.
    """
    conn = open_query_database(db_path)
    output = run_show_item(SqliteQueryContext(conn), item_id)
    click.echo(output)

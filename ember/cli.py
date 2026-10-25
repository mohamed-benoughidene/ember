"""Ember command line interface."""

from __future__ import annotations

import json
import os
import sys

import click

from ember.adapters.embedder import build_embedder, validate_embedder_config
from ember.adapters.llm import build_item_proposer, build_link_proposer
from ember.adapters.sqlite import (
    SqliteAiResponseStore,
    SqliteItemContext,
    SqliteItemGatekeeper,
    SqliteLinkContext,
    SqliteLinkStore,
    SqliteMaintainContext,
    SqliteMaintainStore,
    SqliteSourceStore,
    build_ai_response_store,
    build_embedding_store,
    open_database,
    open_maintain_database,
    open_relate_database,
)
from ember.capture.confirm_write import run_confirm_loop
from ember.capture.errors import UserAbort
from ember.capture.input_reader import InputMode, read_raw_text
from ember.capture.item_gatekeeper import (
    GatekeeperRun,
    load_source_text,
    validate_add_item,
    validate_proposals,
    validate_set_validated,
)
from ember.capture.item_proposal import (
    ProposalResponse,
    build_context,
    propose_items,
    read_context_mode,
)
from ember.capture.source_storage import StoredSource, store_source
from ember.errors import EmberError
from ember.maintain.derive import derive_status_changes
from ember.maintain.report import format_report
from ember.maintain.run_maintain import MaintainPorts, _load
from ember.relate.candidate_pool import build_candidate_pool
from ember.relate.errors import UserAbort as RelateUserAbort
from ember.relate.load_filter import load_item_candidates, load_latest_candidates
from ember.relate.rows import Pool
from ember.relate.run_relate import RelatePorts, RelateRequest, run_relate

DEFAULT_DB_PATH = "ember.db"


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


@click.group()
def main() -> None:
    """Ember: project context management system."""


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
    try:
        raw_text = read_raw_text(mode=mode, path=file_path)
        conn = open_database(db_path)
        store = SqliteSourceStore(conn)
        result = store_source(store, raw_text)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        sys.exit(1)
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
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def capture(file_path: str | None, db_path: str) -> None:
    """Run all 4 capture phases: store, propose, gatekeeper, confirm, write.

    Exit 0 when every proposal is handled, 1 on a phase 1/2/3 error or a DB
    write failure, and 2 when the user quits mid-prompt.
    """
    mode = InputMode.FILE if file_path else InputMode.STDIN
    try:
        raw_text = read_raw_text(mode=mode, path=file_path)
        conn = open_database(db_path)
        stored = _store(conn, raw_text)
        response = _propose(conn, stored)
        _store_ai_response(conn, stored, response)
        for drop in response.batch.dropped:
            click.echo(f"dropped proposal: {drop.rule}")
        if not response.batch.proposals:
            click.echo("0 valid proposals")

        gatekeeper = SqliteItemGatekeeper(conn)
        run = _gatekeeper_run(conn, gatekeeper, stored)
        outcome = validate_proposals(response.batch.proposals, run)
        for reject in outcome.rejected:
            click.echo(f"rejected by gatekeeper: {reject.rule}")

        result = run_confirm_loop(
            outcome.validated,
            confirm=TerminalConfirm(),
            commit=gatekeeper,
            revalidate=lambda draft: validate_add_item(draft, run),
        )
        click.echo(
            f"accepted: {len(result.accepted_ids)}"
            f", rejected: {result.rejected_count}"
            f", warnings: {result.warning_count}"
            f", aborted: {str(result.aborted).lower()}"
        )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        sys.exit(1)

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


@main.command("relate")
@click.option("--item", "item_id", type=int, default=None, help="Item id to relate.")
@click.option(
    "--latest",
    is_flag=True,
    default=False,
    help="Newest Active item with no link from it.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def relate(item_id: int | None, latest: bool, db_path: str) -> None:
    """Run all 4 relate phases: load, pool, AI propose, confirm, write.

    Exit 0 when every proposal is handled, 1 on a phase error, and 2 when the
    user quits mid-prompt. An empty candidate pool prints the Phase 2 JSON and
    exits 0 without an AI call.
    """
    if item_id is not None and latest:
        raise click.UsageError("use either --item or --latest, not both")
    if item_id is None and not latest:
        raise click.UsageError("one of --item or --latest is required")
    aborted = False
    try:
        validate_embedder_config()
        conn = open_relate_database(db_path)
        lookup = SqliteLinkContext(conn)
        store = SqliteLinkStore(conn)
        link_proposer = build_link_proposer(os.environ)
        ai_response_store = build_ai_response_store(conn)
        if latest:
            result = load_latest_candidates(lookup)
        else:
            result = load_item_candidates(lookup, item_id=item_id, db_path=db_path)
        if result is None:
            click.echo("no unrelated items")
            return
        if result.universe.items:
            pool = build_candidate_pool(
                result,
                link_lookup=lookup,
                embedding_store=build_embedding_store(conn),
                embedder=build_embedder(),
            )
        else:
            pool = Pool.empty()
        if pool.warning:
            click.echo(pool.warning, err=True)
        if not pool.ranked:
            click.echo(
                json.dumps(
                    {"phase": 2, "pool_size": 0, "signals": pool.counts}
                )
            )
            return
        ports = RelatePorts(
            link_lookup=lookup,
            link_store=store,
            link_proposer=link_proposer,
            ai_response_store=ai_response_store,
            confirm=RelateTerminalConfirm(),
        )
        request = RelateRequest(
            new_item=result.new_item, ranked=pool.ranked, env=os.environ
        )
        outcome = run_relate(ports, request)
        click.echo(
            f"accepted: {len(outcome.accepted)}"
            f", rejected: {outcome.rejected}"
            f", skipped: {outcome.skipped}"
            f", aborted: {str(outcome.aborted).lower()}"
        )
        aborted = outcome.aborted
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        sys.exit(1)
    if aborted:
        sys.exit(2)


@main.command("maintain")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned changes and write nothing.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def maintain(dry_run: bool, db_path: str) -> None:
    """Run the maintain sweep: load the graph, derive, apply, report.

    A plain run writes the derived status changes to `items` and appends one
    `change_log` row per change. `--dry-run` loads, derives and prints only; it
    writes no `items` or `change_log` row.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
        )
        snapshot = _load(ports.lookup)
        changes = derive_status_changes(snapshot)
        if not dry_run:
            ports.store.apply_status_changes(changes)
        report = format_report(changes, len(snapshot.items))
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for line in report:
        click.echo(line)


def _write_validated_flag(item_id: int, db_path: str, *, new_value: bool) -> None:
    """Write the flag on an Assumption. `new_value` is data, not a mode switch."""
    try:
        conn = open_database(db_path)
        gatekeeper = SqliteItemGatekeeper(conn)
        item = validate_set_validated(gatekeeper.find_item(item_id), item_id)
        gatekeeper.save_validated_flag(item, validated=new_value)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        sys.exit(1)
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

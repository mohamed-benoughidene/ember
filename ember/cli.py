"""Ember command line interface."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import click

from ember.adapters.backup import create_backup
from ember.adapters.db_check import check_database
from ember.adapters.export import (
    gather_export,
    refuse_self_overwrite,
    render_export,
    write_export,
)
from ember.adapters.embedder import build_embedder, validate_embedder_config
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
    open_database,
    open_maintain_database,
    open_query_database,
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
from ember.maintain.close_proposer import ProposalOutcome, stale_close_candidates
from ember.maintain.derive import derive_status_changes
from ember.maintain.errors import UserAbort as MaintainUserAbort
from ember.maintain.human_actions import (
    validate_close_item,
    validate_edit_item,
    validate_remove_link,
)
from ember.maintain.report import format_report, format_undo_line
from ember.maintain.rows import MaintainSnapshot
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

    Prints one `relate rejected: CODE | detail` line per gatekeeper rejection,
    then the summary. Exit 0 when every proposal is handled, 1 on a phase
    error, and 2 when the user quits mid-prompt. An empty candidate pool
    prints the Phase 2 JSON and exits 0 without an AI call.
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
        for rejection in outcome.gatekeeper_rejections:
            if rejection.detail:
                click.echo(
                    f"relate rejected: {rejection.code} | {rejection.detail}"
                )
            else:
                click.echo(f"relate rejected: {rejection.code}")
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
    """
    outcome = ProposalOutcome(stale=0, proposed=0, accepted=0, rejected=0)
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        if dry_run:
            snapshot = _load(ports.lookup)
            changes = derive_status_changes(snapshot)
            for line in format_report(changes, len(snapshot.items)):
                click.echo(line)
            # Nothing was applied, so this fresh load is still the pre-apply
            # view: the dry-run list deliberately names every candidate
            # before the human commits to a run (review fix 3).
            shortlist = stale_close_candidates(
                _load(ports.lookup), now=datetime.now(timezone.utc)
            )
            if shortlist.truncated:
                click.echo("stale shortlist capped at 10 items (list truncated)")
            for candidate in shortlist.candidates:
                click.echo(
                    f"item {candidate.item_id}: stale {candidate.item_type}"
                    f" (newest answers link"
                    f" {candidate.newest_answers_link_id},"
                    f" confirmed {candidate.newest_answer_created_at})"
                    " (dry-run)"
                )
            outcome = ProposalOutcome(
                stale=len(shortlist.candidates), proposed=0, accepted=0, rejected=0
            )
        else:
            result = run_sweep(ports, MaintainRequest())
            for line in format_report(result.changed, result.total_items):
                click.echo(line)
            shortlist = stale_close_candidates(
                _load(ports.lookup), now=datetime.now(timezone.utc)
            )
            if shortlist.truncated:
                click.echo("stale shortlist capped at 10 items (list truncated)")
            if shortlist.candidates:
                outcome = run_close_proposals(
                    CloseProposalPorts(
                        lookup=ports.lookup,
                        store=ports.store,
                        close_proposer=build_close_proposer(os.environ),
                        ai_response_store=SqliteAiResponseStore(conn),
                        confirm=MaintainTerminalConfirm(),
                    ),
                    now=datetime.now(timezone.utc),
                )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    click.echo(
        f"stale: {outcome.stale}, proposed: {outcome.proposed},"
        f" accepted: {outcome.accepted}, rejected: {outcome.rejected},"
        f" aborted: {str(outcome.aborted).lower()}"
    )
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
def close_item(item_id: int, reason: str, dry_run: bool, db_path: str) -> None:
    """Close an item by hand, challenging its live dependents.

    Prints the same report as `maintain`. `--dry-run` loads and validates only;
    it writes no `items` or `change_log` row.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        if dry_run:
            snapshot = _load(ports.lookup)
            changes = validate_close_item(snapshot, item_id, reason)
            report = format_report(changes, len(snapshot.items))
        else:
            result = run_close_item(
                ports, MaintainRequest(item_id=item_id, reason=reason)
            )
            report = format_report(result.changed, result.total_items)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for line in report:
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
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def set_status(item_id: int, to_status: str, db_path: str) -> None:
    """Move an item between Active and Challenged by hand.

    Exactly one of those two values is accepted; a `--to Active` on a
    `Challenged` item also sets the manual shield. Prints the same report as
    `maintain`.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        result = run_set_status(
            ports, MaintainRequest(item_id=item_id, to_status=to_status)
        )
        report = format_report(result.changed, result.total_items)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for line in report:
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
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def reverse_supersedes(item_id: int, link_id: int, db_path: str) -> None:
    """Undo a supersedes: restore the item and mark the link reversed.

    Writes the `reversed_at` column on the `links` row, the item restore, and
    the two `change_log` rows in one transaction from one clock read. Prints
    the same report as `maintain`.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        result = run_reverse_supersedes(
            ports, MaintainRequest(item_id=item_id, link_id=link_id)
        )
        report = format_report(result.changed, result.total_items)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for line in report:
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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned old -> new change and write nothing.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def edit_item(
    item_id: int, field: str, value: str, dry_run: bool, db_path: str
) -> None:
    """Edit an item's rationale or source by hand, ledger row always.

    Under the rule-7 ADR the item text (`statement`) and all raw tables stay
    immutable: `rationale` is writable on a Decision, `source` on a Finding.
    A same-value edit is a no-op (exit 0, nothing written). The human invoking
    the command IS the confirmation and no AI runs in this path.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = MaintainPorts(
            lookup=SqliteMaintainContext(conn),
            store=SqliteMaintainStore(conn),
            group_ids=SqliteGroupIdPort(conn),
        )
        if dry_run:
            snapshot = _load(ports.lookup)
            changes = validate_edit_item(snapshot, item_id, field, value)
        else:
            changes = run_edit_item(
                ports,
                MaintainRequest(item_id=item_id, field=field, value=value),
            )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for change in changes:
        if dry_run:
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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned status flip and write nothing.",
)
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def remove_link(link_id: int, dry_run: bool, db_path: str) -> None:
    """Remove one confirmed relationship edge, ledger row always.

    The removal is ONE status flip (`Confirmed -> Rejected`) plus its
    `link_removed` ledger row in one transaction: the row is never deleted
    (the ledger's foreign key refuses that) and never flipped back, so a
    removed pair stays blocked forever (the #15 ruling). A second removal of
    the same link is an error (MAINTAIN-015), not a silent no-op. The human
    invoking the command IS the confirmation and no AI runs in this path.
    """
    try:
        conn = open_maintain_database(db_path)
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
        if dry_run:
            changes = validate_remove_link(snapshot, link_id)
        else:
            changes = run_remove_link(
                ports, MaintainRequest(link_id=link_id)
            )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    for change in changes:
        if dry_run:
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


@main.command("undo")
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
def undo(dry_run: bool, db_path: str) -> None:
    """Undo the newest human change by appending its inverse to the ledger.

    Nothing is erased: the ledger only grows. The sweep's own changes carry
    no undo group and are never undoable. A refusal (the change's target
    moved since) exits 1 and writes nothing. `--dry-run` prints the same
    line and writes zero rows.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = _undo_ports(conn)
        result = run_undo(ports, UndoRequest(dry_run=dry_run))
        new_group_id = (
            None if dry_run else _newest_group_id(ports.lookup)
        )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    click.echo(format_undo_line(result, new_group_id, dry_run))


@main.command("redo")
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
def redo(dry_run: bool, db_path: str) -> None:
    """Re-apply the change you just undid, the same append-only way.

    A newer human change clears the redo (exit 1, `MAINTAIN-024`): undo
    again to make it available. Same refusals and `--dry-run` as
    `ember undo`.
    """
    try:
        conn = open_maintain_database(db_path)
        ports = _undo_ports(conn)
        result = run_redo(ports, UndoRequest(dry_run=dry_run))
        new_group_id = (
            None if dry_run else _newest_group_id(ports.lookup)
        )
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    click.echo(format_undo_line(result, new_group_id, dry_run))


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
    try:
        conn = open_query_database(db_path)
        output = run_current_state(SqliteQueryContext(conn))
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
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
    db_path: str,
) -> None:
    """Rank items by BM25 over their statements, as JSON.

    Every item is searched, `Closed` ones included, and each result carries its
    status. `--status` and `--type` narrow what is scored (the filtered subset
    is the corpus, so counts recompute) and `--limit` crops the ranked list.
    Read-only, like every query command.
    """
    try:
        topic_filter = TopicFilter(status=status, type=item_type, limit=limit)
        conn = open_query_database(db_path)
        output = run_topic_search(SqliteQueryContext(conn), query, topic_filter)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
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
    try:
        conn = open_query_database(db_path)
        output = run_why(SqliteQueryContext(conn), item_id)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
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
    try:
        conn = open_query_database(db_path)
        page = HistoryPage(limit=limit, offset=offset, since=since)
        output = run_history(SqliteQueryContext(conn), item_id, page)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    click.echo(output)


@main.command("backup")
@click.argument("target_path")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def backup(target_path: str, db_path: str) -> None:
    """Copy the knowledge base to a restorable snapshot file.

    Uses SQLite's online backup API, so the copy is consistent even while
    another command writes. The source is opened read-only and never
    migrated. An existing target is rotated aside into `.old-1` (with the
    newest 3 kept), never destroyed.

    Restore: copy the file back, or point Ember at it with `--db`. There is
    deliberately no restore command (GLOSSARY).
    """
    try:
        report = create_backup(db_path, target_path)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    if report.rotated:
        click.echo(f"rotated to {report.rotated}", err=True)
    click.echo(
        f"backup written: {report.path}"
        f" (schema v{report.schema_version}, {report.item_count} items)"
    )


@main.command("export")
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False),
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
    try:
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
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)


@main.command("db-check")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB_PATH,
    help="SQLite database path.",
)
def db_check(db_path: str) -> None:
    """Report database health: version, floors, triggers, drift, replay.

    Read-only: the file is opened `mode=ro` and never migrated or written.
    One command, one job, no mode flags. Exit 0 when the report ends
    `result: OK`, 1 on `result: DRIFT` or `result: UNREADABLE`.
    """
    report = check_database(db_path)
    if report.detail is not None:
        click.echo(f"detail: {report.detail}", err=True)
    for line in report.lines:
        click.echo(line)
    if report.result != "OK":
        sys.exit(1)


def _write_validated_flag(item_id: int, db_path: str, *, new_value: bool) -> None:
    """Write the flag on an Assumption. `new_value` is data, not a mode switch."""
    try:
        conn = open_database(db_path)
        ids = SqliteGroupIdPort(conn)
        gatekeeper = SqliteItemGatekeeper(conn, group_ids=ids)
        item = validate_set_validated(gatekeeper.find_item(item_id), item_id)
        gatekeeper.save_validated_flag(
            item, validated=new_value, group_id=ids.next_group_id()
        )
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
    db_path: str,
) -> None:
    """List every item in any status, as JSON.

    Unlike `current-state`, `Closed` items are listed on purpose, each with
    its status and close reason. `total` is the count after the filters but
    before `--limit`/`--offset` crop the printed window. Read-only: the
    database is opened read-only and never migrated, like every query
    command.
    """
    try:
        conn = open_query_database(db_path)
        filter_ = TopicFilter(status=status, type=item_type)
        page = ListPage(limit=limit, offset=offset)
        output = run_list_items(SqliteQueryContext(conn), filter_, page)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
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
    try:
        conn = open_query_database(db_path)
        output = run_show_item(SqliteQueryContext(conn), item_id)
    except EmberError as exc:
        click.echo(f"error: {exc.log_line()}", err=True)
        raise SystemExit(1)
    click.echo(output)

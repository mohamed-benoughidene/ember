"""Ember command line interface."""

from __future__ import annotations

import json
import sys

import click

from ember.adapters.sqlite import SqliteSourceStore, open_database
from ember.capture.input_reader import InputMode, read_raw_text
from ember.capture.source_storage import store_source
from ember.errors import EmberError

DEFAULT_DB_PATH = "ember.db"


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

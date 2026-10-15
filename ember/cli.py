"""Ember command line interface."""

from __future__ import annotations

import json
import os
import sys

import click

from ember.adapters.sqlite import SqliteSourceStore, open_database
from ember.capture.input_reader import InputMode, read_raw_text
from ember.capture.source_storage import store_source
from ember.errors import EmberError

DEFAULT_DB_PATH = "ember.db"
DB_PATH_ENV = "EMBER_DB_PATH"


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
    default=None,
    help="SQLite database path. Defaults to $EMBER_DB_PATH or ember.db.",
)
def capture_source(file_path: str | None, db_path: str | None) -> None:
    """Phase 1: store raw input, dedup by content hash, print source reference."""
    resolved_db = db_path or os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH)
    mode = InputMode.FILE if file_path else InputMode.STDIN
    try:
        raw_input = read_raw_text(mode=mode, path=file_path)
        conn = open_database(resolved_db)
        store = SqliteSourceStore(conn)
        result = store_source(store, raw_input.raw_text)
    except EmberError as exc:
        click.echo(f"error: {exc.message}", err=True)
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

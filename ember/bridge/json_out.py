"""Pure JSON renderers for the bridge (interface-bridge-plan §5.1, T1).

One job: turn named results (engine models and plain dicts) into ONE JSON
document string. No I/O, no clock, no click, deterministic and sorted (T1):
the same inputs always render the same bytes.

The bridge imports NO adapter (T9): `ember/cli.py` converts adapter reports
(`BackupReport`, `DbCheckReport`) into plain dicts BEFORE anything gets here.
Engine result models pass through whole, so no fact is defined twice (D3).

The document shape is pinned (L2 §5.1): top-level keys `command`, `changes`,
`summary`, `dry_run` — sorted keys, `ensure_ascii=False`. A dry run is stated
INSIDE the document as the `dry_run` model field of `OutputDocument`; it is
never a renderer argument and never changes any other key.

`summary` key names per command (L2 §9 defers the exact names to this step;
only facts that already exist on a result model or that today's text output
already prints are used — step 04's contract table pins this table):

| command            | summary keys                                            | source                                                     |
|--------------------|---------------------------------------------------------|------------------------------------------------------------|
| `maintain`         | `closed, challenged, reopened, unchanged` (report counts), `stale, stale_truncated, proposed, accepted, rejected, aborted`, `stale_candidates` (the `StaleShortlist` serialized whole: `candidates` + `truncated`) | report counts + `ProposalOutcome` + the `StaleShortlist` model itself (D3: the engine's own model, no second definition) |
| `close-item`       | `closed, challenged, reopened, unchanged`               | report counts (the text summary line's own numbers)         |
| `set-status`       | `closed, challenged, reopened, unchanged`               | report counts                                               |
| `reverse-supersedes`| `closed, challenged, reopened, unchanged`              | report counts                                               |
| `edit-item`        | (empty; the text output has no summary line)            | —                                                           |
| `remove-link`      | (empty; the text output has no summary line)            | —                                                           |
| `undo` / `redo`    | `direction, source_group_id, source_action, target_label, new_group_id` (new_group_id `null` on a dry run) | `UndoResult` + the display-only newest-group read |
| `backup`           | `path, schema_version, item_count, rotated`             | `BackupReport` as a plain dict built by `cli.py`            |
| `db-check`         | `result, detail, lines`                                 | `DbCheckReport` as a plain dict built by `cli.py`           |

Step-01 note (recorded for step 03): a `maintain` run whose stale shortlist
is non-empty still runs the interactive Phase-5 loop on the terminal in this
step; its text lines ride the confirm port exactly as in text mode and are
not part of the document. The JSON event stream for that loop arrives with
`--confirm json` in step 03. (Review fix, ticket 24: the shortlist FACTS now
reach document mode as `summary.stale_candidates` — the engine's own
`StaleShortlist` — while under `--confirm json` the shortlist text lines
still ride the sink as `message` events, so neither json surface drops them.)
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


class OutputDocument(BaseModel):
    """The one JSON document a command prints under `--format json` (L2 §5.1).

    `changes` holds the run's result models whole (`StatusChange`,
    `EditChange`, `LinkChange`, or an `UndoResult`'s `InverseChange` list) or
    nothing for a read-only command; `summary` holds the plain dict mapped in
    the module docstring; `dry_run` states inside the document whether the
    run was a dry run (a `--dry-run` flag, an I2 exception, reported as data).
    """

    command: str
    changes: list[Any]
    summary: dict[str, Any]
    dry_run: bool = False


def render_document(document: OutputDocument) -> str:
    """Return the document as one JSON string, sorted keys, non-ASCII kept.

    Pure (T1): `json.dumps` only, no click and no print. Sorting lives here,
    matching the query renderers' convention of pinning byte shape in the
    display layer.
    """
    return json.dumps(
        document.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
    )

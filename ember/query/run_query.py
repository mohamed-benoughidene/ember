"""One function per query entry point: validate, load, derive, render.

No mode argument and no boolean flag: the mode is the entry point (I2).
"""

from __future__ import annotations

from ember.query.current_state import current_state
from ember.query.lookup import QueryLookupPort
from ember.query.render import render_current_state


def run_current_state(lookup: QueryLookupPort) -> str:
    """Load every item, derive the live view, render the JSON document."""
    return render_current_state(current_state(lookup.list_items()))

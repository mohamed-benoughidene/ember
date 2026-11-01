"""Error names come from the classes; error context shows file names only.

Story 20: every error class must own its `code` and its `name`, and the
`name` must be the class name itself (the house line then prints a name a
reader can trace straight back to the source). Story 21 / N7 (context
half): opener errors carry only the database file name in their context,
never the full path on the user's disk.
"""

from __future__ import annotations

import inspect

from click.testing import CliRunner

from ember.adapters import errors as adapters_errors
from ember.capture import errors as capture_errors
from ember.cli import main
from ember.errors import EmberError
from ember.maintain import errors as maintain_errors
from ember.query import errors as query_errors
from ember.relate import errors as relate_errors

_ERROR_MODULES = (
    capture_errors,
    query_errors,
    relate_errors,
    maintain_errors,
    adapters_errors,
)


def _error_classes(module: object) -> list[type[EmberError]]:
    """Every error class defined in `module` (subclasses defined elsewhere
    keep their own module, so they are not double-counted here)."""
    return [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, EmberError) and cls.__module__ == module.__name__
    ]


def test_every_error_class_names_itself_and_owns_a_code() -> None:
    checked = 0
    for module in _ERROR_MODULES:
        for cls in _error_classes(module):
            assert cls.code, f"{cls.__module__}.{cls.__name__} has no code"
            assert cls.name, f"{cls.__module__}.{cls.__name__} has no name"
            assert (
                cls.name == cls.__name__
            ), f"{cls.__module__}.{cls.__name__}.name is {cls.name!r}, not the class name"
            checked += 1
    assert checked > 0


def test_open_failure_context_shows_the_file_name_not_the_full_path(tmp_path) -> None:
    db = str(tmp_path / "sub" / "dir" / "x.db")

    result = CliRunner().invoke(main, ["capture-source", "--db", db], input="hello")

    # Codes and data only (I10/I21): the command must fail, and no error
    # line may echo the full temp path — the file name alone is allowed.
    assert result.exit_code == 1
    assert str(tmp_path) not in (result.stderr or "")
    for line in (result.stderr or "").splitlines():
        if line.startswith("error: "):
            assert str(tmp_path) not in line

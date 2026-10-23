"""Link type closed set and source/target compatibility table (V1 spec 3.3)."""

from __future__ import annotations

LINK_TYPES: tuple[str, ...] = (
    "supports",
    "contradicts",
    "depends_on",
    "supersedes",
    "answers",
)

TYPE_COMPAT: dict[tuple[str, str], set[str]] = {
    ("Decision", "Assumption"): {"depends_on"},
    ("Decision", "Finding"): {"depends_on"},
    ("Decision", "Decision"): {"depends_on", "supersedes"},
    ("Decision", "Question"): {"answers"},
    ("Assumption", "Finding"): {"depends_on"},
    ("Assumption", "Assumption"): {"depends_on", "supersedes"},
    ("Finding", "Assumption"): {"supports", "contradicts"},
    ("Finding", "Decision"): {"supports", "contradicts"},
    ("Finding", "Finding"): {"contradicts", "supersedes"},
    ("Finding", "Question"): {"answers"},
    ("Question", "Question"): {"supersedes"},
}


def allowed_link_types(source_type: str, target_type: str) -> set[str]:
    return set(TYPE_COMPAT.get((source_type, target_type), ()))

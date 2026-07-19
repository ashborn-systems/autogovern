"""Doc version stamping: semver ``doc_version`` for generated documents.

The spec's versioning model: ``doc_version`` follows semver, bumped on each
regeneration by the governance significance of the change that caused it:

- **major** — autonomy, permissions (env/scope), or data category change
- **minor** — tool or model change
- **patch** — descriptive updates

Spec-contradiction note: the spec lists tools under both "permissions"
(major) and "tool change" (minor). The resolution applied here: within
``governance.permissions_surface``, a tool add/remove is **minor** (a tool
change) and any other permissions change (env vars, scopes) is **major**
(a permission-scope change). ``context.project.risk_appetite`` is classed **minor**:
it is governance posture, not a descriptive update. These rules are
deliberate and tested; change them deliberately.

The module is composed from existing primitives: the locked profile/context
(previous state), ``diff_profiles`` / ``diff_context`` (what changed), and
the pack's section dependency graph (which documents those fields feed).
First generation (no lockfile) stamps every document ``0.1.0``. Documents
written before semver stamping (hash-style ``doc_version``) restart at
``0.1.0`` on their next regeneration.
"""

from __future__ import annotations

import re
from typing import Literal

from autogovern.detect.diff import FieldDiff
from autogovern.detect.scorer import permission_tool_names
from autogovern.frameworks import SectionDependencyGraph, to_graph_input

BumpLevel = Literal["major", "minor", "patch"]

# The version stamped on every document's first generation.
INITIAL_VERSION = "0.1.0"

_LEVEL_RANK: dict[str, int] = {"patch": 0, "minor": 1, "major": 2}

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: object) -> tuple[int, int, int] | None:
    """Parse ``"X.Y.Z"`` into a tuple, or None for anything else.

    Returns None for legacy hash-style versions and missing values, so
    callers can restart pre-semver documents at :data:`INITIAL_VERSION`.
    """
    if not isinstance(text, str):
        return None
    match = _SEMVER_RE.match(text.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def next_version(current: object, level: BumpLevel) -> str:
    """Bump ``current`` one step at ``level``.

    Unparseable (legacy hash) or missing values restart at
    :data:`INITIAL_VERSION` — the pre-semver baseline.
    """
    parsed = parse_version(current)
    if parsed is None:
        return INITIAL_VERSION
    major, minor, patch = parsed
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def classify_field_diff(fd: FieldDiff) -> BumpLevel:
    """Classify one field diff by the spec's versioning rules."""
    field = fd.field
    if field.startswith("context.agents.") and field.endswith(".autonomy_level"):
        return "major"
    if field == "governance.data_categories":
        return "major"
    if field == "governance.permissions_surface":
        # Tool add/remove is minor; env/scope change is major (see module
        # docstring for the spec-contradiction resolution).
        if permission_tool_names(fd.old) != permission_tool_names(fd.new):
            return "minor"
        return "major"
    if field in ("governance.model_configuration", "context.project.risk_appetite"):
        return "minor"
    return "patch"


def doc_bump_levels(fields: list[FieldDiff], graph: SectionDependencyGraph) -> dict[str, BumpLevel]:
    """Map each affected document to its bump level via the dependency graph.

    A document's level is the most significant classification across the
    fields that feed it. Documents no changed field feeds are absent (they
    are not regenerated, so their version does not move).
    """
    levels: dict[str, BumpLevel] = {}
    for fd in fields:
        level = classify_field_diff(fd)
        graph_input = to_graph_input(fd.field)
        if graph_input is None:
            continue
        for doc in graph.affected_documents(graph_input):
            existing = levels.get(doc)
            if existing is None or _LEVEL_RANK[level] > _LEVEL_RANK[existing]:
                levels[doc] = level
    return levels


def most_significant(levels: list[str]) -> str:
    """The highest-ranking level in ``levels``; "patch" for an empty list."""
    return max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0), default="patch")


__all__ = [
    "INITIAL_VERSION",
    "BumpLevel",
    "classify_field_diff",
    "doc_bump_levels",
    "most_significant",
    "next_version",
    "parse_version",
]

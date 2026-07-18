"""Heuristic pass: fast, deterministic, no LLM.

Checks whether any changed file matches the watched-path set from config.
Runs in pre-commit and as the first stage of ``check``. A negative result
means no profile rebuild is needed, so the expensive passes never run.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from autogovern.models import Config


@dataclass
class HeuristicResult:
    """Outcome of the heuristic pass."""

    matched: bool
    matched_paths: list[str] = field(default_factory=list)


def heuristic_pass(changed_files: list[str | Path], config: Config) -> HeuristicResult:
    """Check whether any changed file matches the watched-path globs.

    Args:
        changed_files: Paths that changed (relative to repo root, or absolute).
        config: The config whose ``watched_paths`` globs define the watched set.

    Returns:
        A :class:`HeuristicResult`. ``matched`` is True if any changed file
        matches a watched glob. No LLM call, no profile rebuild.
    """
    matched: list[str] = []
    for raw in changed_files:
        rel = _to_rel(raw)
        for pattern in config.watched_paths:
            if _glob_match(rel, pattern):
                matched.append(rel)
                break
    return HeuristicResult(matched=bool(matched), matched_paths=sorted(matched))


def _glob_match(path: str, pattern: str) -> bool:
    """Match a path against a glob, supporting ``**`` recursively.

    ``fnmatch`` does not handle ``**`` specially, so we normalise ``**`` to
    a multi-segment wildcard by checking each prefix. For the default watched
    paths (single-segment globs like ``CLAUDE.md`` or ``.claude/**``), this
    is a simple fnmatch.
    """
    # Normalise: ``dir/**`` matches everything under dir/.
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def _to_rel(raw: str | Path) -> str:
    """Normalise a path to a forward-slash relative string."""
    s = str(raw)
    # Strip a leading ./ or /
    if s.startswith("./"):
        s = s[2:]
    if s.startswith("/"):
        s = s.lstrip("/")
    return s.replace("\\", "/")


__all__ = ["HeuristicResult", "heuristic_pass"]

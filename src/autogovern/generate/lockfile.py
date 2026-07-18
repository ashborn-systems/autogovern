"""The ``governance/profile.lock`` and ``governance/context.lock`` lockfiles.

``profile.lock`` is a frozen serialisation of the AgentProfile (AgentCard
plus governance extension), analogous to a package lockfile. ``check`` diffs
the rebuilt profile against it (Phase 9); ``git log governance/profile.lock``
is the agent's governance history.

``context.lock`` is the same idea for the organisational context manifest:
``generate`` writes it, ``check`` diffs the current ``context.yaml`` against
it so context edits (autonomy level, risk appetite, ...) are detected just
like code changes. Absence of the file (older repos) means "no context diff",
which preserves pre-lock behaviour.

Both files are line-stable (keys sorted, no flow style) so diffs are minimal
and git-friendly, and content-addressed (an unchanged lock is not rewritten,
so no-op runs produce zero git noise).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from autogovern.generate.writer import write_if_changed
from autogovern.models import AgentProfile, ContextManifest

LOCKFILE_NAME = "profile.lock"
CONTEXT_LOCK_NAME = "context.lock"


def serialise_profile(profile: AgentProfile) -> str:
    """Serialise a profile to a line-stable YAML document."""
    return yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=True, default_flow_style=False)


def write_lockfile(governance_dir: Path, profile: AgentProfile) -> Path:
    """Write ``governance/profile.lock``, skipping the write when unchanged."""
    path = governance_dir / LOCKFILE_NAME
    write_if_changed(path, serialise_profile(profile))
    return path


def read_lockfile(governance_dir: Path) -> AgentProfile | None:
    """Read the profile lockfile, or return None if absent."""
    path = governance_dir / LOCKFILE_NAME
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return AgentProfile.model_validate(raw)


def write_context_lock(governance_dir: Path, context: ContextManifest) -> Path:
    """Write ``governance/context.lock``, skipping the write when unchanged."""
    path = governance_dir / CONTEXT_LOCK_NAME
    write_if_changed(path, serialise_context(context))
    return path


def read_context_lock(governance_dir: Path) -> ContextManifest | None:
    """Read the context lockfile, or return None if absent."""
    path = governance_dir / CONTEXT_LOCK_NAME
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return ContextManifest.model_validate(raw)


def serialise_context(context: ContextManifest) -> str:
    """Serialise a context manifest to a line-stable YAML document."""
    return yaml.safe_dump(context.model_dump(mode="json"), sort_keys=True, default_flow_style=False)


__all__ = [
    "CONTEXT_LOCK_NAME",
    "LOCKFILE_NAME",
    "read_context_lock",
    "read_lockfile",
    "serialise_context",
    "serialise_profile",
    "write_context_lock",
    "write_lockfile",
]

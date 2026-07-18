"""The ``governance/profile.lock`` lockfile.

A frozen serialisation of the AgentProfile (AgentCard plus governance
extension), analogous to a package lockfile. ``check`` diffs the rebuilt
profile against it (Phase 9); ``git log governance/profile.lock`` is the
agent's governance history.

Output is line-stable: keys sorted, no flow style, so diffs are minimal and
git-friendly.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from autogovern.models import AgentProfile

LOCKFILE_NAME = "profile.lock"


def serialise_profile(profile: AgentProfile) -> str:
    """Serialise a profile to a line-stable YAML document."""
    return yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=True, default_flow_style=False)


def write_lockfile(governance_dir: Path, profile: AgentProfile) -> Path:
    """Write (or overwrite) ``governance/profile.lock`` atomically."""
    path = governance_dir / LOCKFILE_NAME
    _atomic_write(path, serialise_profile(profile))
    return path


def read_lockfile(governance_dir: Path) -> AgentProfile | None:
    """Read the lockfile, or return None if absent."""
    path = governance_dir / LOCKFILE_NAME
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return AgentProfile.model_validate(raw)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


__all__ = ["LOCKFILE_NAME", "read_lockfile", "serialise_profile", "write_lockfile"]

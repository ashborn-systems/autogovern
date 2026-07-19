"""Profile diff pass: rebuild profile, diff against ``profile.lock``.

Produces a field-level diff object. Certain field changes score deterministically
as material (>= 80) without an LLM: a new or removed tool, a widened permission
scope, a changed autonomy level, a new data category, or a model swap. The
remainder (prompt content changes) is left to the semantic scorer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autogovern.models import AgentProfile, ContextManifest

# Each deterministic material change scores this. It is >= the default material
# threshold (80) so these changes are always material by definition, per the
# spec: "a new tool, a widened permission scope, a changed autonomy level, or a
# new data category is material by definition".
DETERMINISTIC_MATERIAL_SCORE = 100


@dataclass
class FieldDiff:
    """A single field-level difference between two profiles."""

    field: str
    old: Any
    new: Any


@dataclass
class ProfileDiff:
    """The field-level diff between the locked and current profiles."""

    fields: list[FieldDiff] = field(default_factory=list)
    # Which fields require the semantic scorer (prompt content changes).
    semantic_fields: list[str] = field(default_factory=list)

    @property
    def has_diff(self) -> bool:
        return bool(self.fields)


def diff_profiles(locked: AgentProfile, current: AgentProfile) -> ProfileDiff:
    """Diff two AgentProfiles at the field level.

    Compares the governance extension fields that the spec names as
    deterministically scorable, plus the card-standard fields. Returns a
    :class:`ProfileDiff` with one :class:`FieldDiff` per changed field.

    Fields whose change requires the semantic scorer (prompt content) are
    listed in ``semantic_fields``; the deterministic scorer skips them.
    """
    diff = ProfileDiff()
    _diff_provenanced(
        diff,
        "governance.model_configuration",
        locked.governance.model_configuration.value.model_dump(mode="json"),
        current.governance.model_configuration.value.model_dump(mode="json"),
    )
    _diff_list(
        diff,
        "governance.permissions_surface",
        [p.model_dump(mode="json") for p in locked.governance.permissions_surface.value],
        [p.model_dump(mode="json") for p in current.governance.permissions_surface.value],
    )
    _diff_list(
        diff,
        "governance.data_categories",
        [c.value for c in locked.governance.data_categories.value],
        [c.value for c in current.governance.data_categories.value],
    )
    _diff_list(
        diff,
        "governance.dependencies",
        [d.model_dump(mode="json") for d in locked.governance.dependencies.value],
        [d.model_dump(mode="json") for d in current.governance.dependencies.value],
    )
    # Prompt inventory: a path change is deterministic; content change is semantic.
    _diff_prompt_inventory(diff, locked, current)
    # Card-standard fields.
    _diff_scalar(diff, "name", locked.name, current.name)
    _diff_scalar(diff, "description", locked.description, current.description)
    _diff_scalar(diff, "version", locked.version, current.version)
    return diff


def diff_context(locked: ContextManifest | None, current: ContextManifest) -> ProfileDiff:
    """Diff two context manifests, one FieldDiff per changed field.

    Recurses into the ``project`` and ``agent`` sub-models so that field-level
    changes (e.g. ``context.agent.autonomy_level``) are reported individually,
    not as whole-section swaps. Autonomy level and risk appetite changes
    score deterministically as material (see :mod:`autogovern.detect.scorer`);
    every other context field change is advisory. A ``None`` locked context
    (no context.lock, e.g. repos predating context locking) yields an empty
    diff.
    """
    diff = ProfileDiff()
    if locked is None:
        return diff
    # Project section: field-by-field diff.
    for field_name in sorted(type(current.project).model_fields):
        old = getattr(locked.project, field_name)
        new = getattr(current.project, field_name)
        if old != new:
            diff.fields.append(FieldDiff(field=f"context.project.{field_name}", old=old, new=new))
    # Agents section: per-agent field diff. An agent added or removed is a
    # change to context.agents.<name> (the whole AgentContext).
    locked_names = set(locked.agents.keys())
    current_names = set(current.agents.keys())
    for name in sorted(locked_names | current_names):
        if name not in locked_names:
            diff.fields.append(
                FieldDiff(field=f"context.agents.{name}", old=None, new=current.agents[name])
            )
        elif name not in current_names:
            diff.fields.append(
                FieldDiff(field=f"context.agents.{name}", old=locked.agents[name], new=None)
            )
        else:
            locked_agent = locked.agents[name]
            current_agent = current.agents[name]
            for field_name in sorted(type(current_agent).model_fields):
                old = getattr(locked_agent, field_name)
                new = getattr(current_agent, field_name)
                if old != new:
                    diff.fields.append(
                        FieldDiff(field=f"context.agents.{name}.{field_name}", old=old, new=new)
                    )
    return diff


def _diff_provenanced(diff: ProfileDiff, name: str, old: Any, new: Any) -> None:
    if old != new:
        diff.fields.append(FieldDiff(field=name, old=old, new=new))


def _diff_list(diff: ProfileDiff, name: str, old: list[Any], new: list[Any]) -> None:
    if old != new:
        diff.fields.append(FieldDiff(field=name, old=old, new=new))


def _diff_scalar(diff: ProfileDiff, name: str, old: Any, new: Any) -> None:
    if old != new:
        diff.fields.append(FieldDiff(field=name, old=old, new=new))


def _diff_prompt_inventory(diff: ProfileDiff, locked: AgentProfile, current: AgentProfile) -> None:
    """A path change is deterministic; a content change (same path, new hash) is semantic."""
    old_paths = {p.path for p in locked.governance.prompt_inventory.value}
    new_paths = {p.path for p in current.governance.prompt_inventory.value}
    if old_paths != new_paths:
        diff.fields.append(
            FieldDiff(
                field="governance.prompt_inventory.paths",
                old=sorted(old_paths),
                new=sorted(new_paths),
            )
        )
    # Same path, changed content → semantic.
    old_hashes = {p.path: p.content_hash for p in locked.governance.prompt_inventory.value}
    new_hashes = {p.path: p.content_hash for p in current.governance.prompt_inventory.value}
    changed_content = [
        path
        for path in (old_hashes.keys() & new_hashes.keys())
        if old_hashes[path] != new_hashes[path]
    ]
    if changed_content:
        diff.fields.append(
            FieldDiff(
                field="governance.prompt_inventory.content",
                old=[old_hashes[p] for p in changed_content],
                new=[new_hashes[p] for p in changed_content],
            )
        )
        diff.semantic_fields.append("governance.prompt_inventory.content")


__all__ = [
    "DETERMINISTIC_MATERIAL_SCORE",
    "FieldDiff",
    "ProfileDiff",
    "diff_context",
    "diff_profiles",
]

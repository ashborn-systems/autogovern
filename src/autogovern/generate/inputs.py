"""Pure helpers for extracting and hashing a section's declared inputs.

The generation engine calls a section's declared inputs (profile fields,
context fields) its "inputs". This module resolves dotted paths against the
Phase 1 models, serialises them canonically, and hashes them so the engine
can decide deterministically whether a section needs regeneration, with zero
LLM calls.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from autogovern.models import AgentProfile, ContextManifest, ProvenancedField

# Paths that always hash to a constant unless the framework pack content
# changes. We fold the pack version into every section hash so a pack upgrade
# forces regeneration even if the profile/context are unchanged.


def extract_input(path: str, profile: AgentProfile, context: ContextManifest) -> Any:
    """Resolve a dotted ``profile.*`` / ``context.*`` path to a JSON-able value.

    ProvenancedField values are auto-unwrapped to their ``.value`` so callers
    write ``profile.governance.model_configuration`` and receive the
    ModelConfiguration, not the wrapper.

    Raises:
        KeyError: The path does not resolve on the given object.
    """
    if not path.startswith(("profile.", "context.")):
        raise KeyError(f"Unknown input root in {path!r}; expected 'profile.' or 'context.'")
    root_name, rest = path.split(".", 1)
    obj: Any = profile if root_name == "profile" else context
    return _traverse(obj, rest)


def _traverse(obj: Any, dotted: str) -> Any:
    current: Any = obj
    for part in dotted.split("."):
        if isinstance(current, ProvenancedField):
            current = current.value
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Missing key {part!r} in {dotted!r}")
            current = current[part]
            continue
        if not hasattr(current, part):
            raise KeyError(f"Missing attribute {part!r} on {type(current).__name__}")
        current = getattr(current, part)
        if isinstance(current, ProvenancedField):
            current = current.value
    # Serialise pydantic models / lists of models to JSON-able structures.
    if hasattr(current, "model_dump"):
        return current.model_dump(mode="json")
    if isinstance(current, list):
        return [_jsonable(item) for item in current]
    return current


def _jsonable(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return item


def canonical_json(value: Any) -> str:
    """Deterministic JSON for hashing: sorted keys, no superfluous whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_section_hash(
    declared_inputs: dict[str, Any],
    pack_section_contents: list[str],
    pack_version: str,
) -> str:
    """Hash a section's inputs + pack sections + pack version into a stable id.

    The pack sections and version are folded in so a framework-pack upgrade
    forces regeneration even when the profile and context are unchanged.
    """
    payload = {
        "inputs": {k: canonical_json(v) for k, v in declared_inputs.items()},
        "pack_sections": pack_section_contents,
        "pack_version": pack_version,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def profile_file_hashes(profile: AgentProfile) -> dict[str, str]:
    """Map of source file path -> content hash, for the frontmatter audit field.

    Drawn from every provenance record on the profile so the frontmatter
    ``input_hashes`` field records which source files fed the profile, not
    just the ones a given section consumes.
    """
    hashes: dict[str, str] = {}
    for prov in profile.provenance.values():
        hashes[prov.source_path] = prov.content_hash
    # Governance extension provenance.
    gov = profile.governance
    for field in (
        gov.model_configuration,
        gov.permissions_surface,
        gov.data_categories,
        gov.dependencies,
        gov.prompt_inventory,
    ):
        if field.provenance.source_path:
            hashes[field.provenance.source_path] = field.provenance.content_hash
    return dict(sorted(hashes.items()))


__all__ = [
    "canonical_json",
    "compute_section_hash",
    "extract_input",
    "profile_file_hashes",
]

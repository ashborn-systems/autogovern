"""YAML frontmatter parsing and rendering for generated documents.

Frontmatter fields (per SPEC.md): ``doc_version``, ``agent_version``,
``generated``, ``generator_version``, ``input_hashes`` (map of source file to
content hash), and ``framework_pack_version``.

Phase 7 adds ``section_hashes`` (map of section id to input hash), the
operational field the engine compares on regeneration to decide whether a
section needs re-rendering. The spec lists the audit fields; the build plan
requires the regeneration field. Both live in frontmatter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

_FRONTMATTER_DELIM = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a document into (frontmatter, body).

    Returns an empty dict and the full text if no frontmatter is present.
    """
    if not text.startswith(_FRONTMATTER_DELIM):
        return {}, text
    lines = text.splitlines(keepends=True)
    # First line is the opening delimiter.
    end_index: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            end_index = i
            break
    if end_index is None:
        return {}, text
    fm_text = "".join(lines[1:end_index])
    body = "".join(lines[end_index + 1 :])
    data = yaml.safe_load(fm_text) if fm_text.strip() else {}
    if not isinstance(data, dict):
        data = {}
    return data, body


def render_document(frontmatter: dict[str, Any], body: str) -> str:
    """Render a document with deterministic frontmatter.

    Keys are sorted so output is byte-stable across runs (idempotence gate).
    The body's leading newlines are stripped so the first body line follows
    the closing delimiter directly.
    """
    fm = yaml.safe_dump(frontmatter, sort_keys=True, default_flow_style=False).strip()
    normalised_body = body.lstrip("\n")
    return f"{_FRONTMATTER_DELIM}\n{fm}\n{_FRONTMATTER_DELIM}\n{normalised_body}"


def build_frontmatter(
    *,
    doc_version: str,
    agent_version: str,
    generated: str,
    generator_version: str,
    input_hashes: dict[str, str],
    framework_pack_version: str,
    section_hashes: dict[str, str],
) -> dict[str, Any]:
    """Assemble the frontmatter dict in the spec's field order.

    Render order is enforced by ``render_document`` (sorted), so this function
    only carries the values; field order is documented here for readers.
    """
    return {
        "doc_version": doc_version,
        "agent_version": agent_version,
        "generated": generated,
        "generator_version": generator_version,
        "input_hashes": input_hashes,
        "framework_pack_version": framework_pack_version,
        "section_hashes": section_hashes,
    }


def now_iso() -> str:
    """UTC timestamp in a fixed ISO format (second precision) for stability."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def existing_section_hashes(text: str) -> dict[str, str]:
    """Read the ``section_hashes`` map from an existing document's frontmatter."""
    fm, _ = parse_frontmatter(text)
    raw = fm.get("section_hashes", {})
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


__all__ = [
    "build_frontmatter",
    "existing_section_hashes",
    "now_iso",
    "parse_frontmatter",
    "render_document",
]

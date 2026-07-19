"""The ``explain`` command: plain-language provenance for a document.

Reads a document's frontmatter and renders its provenance in plain language:
when it was generated, from which generator and framework pack versions, and
which input files (by content hash) fed it.
"""

from __future__ import annotations

from pathlib import Path

from autogovern.generate.frontmatter import parse_frontmatter


def explain_document(doc_path: Path, governance_dir: Path | None = None) -> dict[str, object]:
    """Explain a generated document's provenance.

    Args:
        doc_path: Path to the document (or its name within governance/).
        governance_dir: The governance directory, if doc_path is a name.

    Returns:
        A dict with: document, generated, agent_version, generator_version,
        framework_pack_version, input_files (count), section_hashes.
    """
    path = _resolve_path(doc_path, governance_dir)
    if not path.is_file():
        return {"document": path.name, "error": f"file not found: {path}"}

    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    input_hashes = fm.get("input_hashes", {})
    section_hashes = fm.get("section_hashes", {})

    return {
        "document": path.name,
        "generated": fm.get("generated", "unknown"),
        "agent_version": fm.get("agent_version", "unknown"),
        "generator_version": fm.get("generator_version", "unknown"),
        "framework_pack_version": fm.get("framework_pack_version", "unknown"),
        "input_files": len(input_hashes) if isinstance(input_hashes, dict) else 0,
        "input_hashes": _summarise_hashes(input_hashes) if isinstance(input_hashes, dict) else {},
        "section_hashes": section_hashes if isinstance(section_hashes, dict) else {},
        "body_lines": len(body.strip().splitlines()) if body else 0,
    }


def _resolve_path(doc_path: Path, governance_dir: Path | None) -> Path:
    if doc_path.is_absolute() or doc_path.is_file():
        return doc_path
    if governance_dir is not None:
        candidate = governance_dir / doc_path
        if candidate.is_file():
            return candidate
        # Multi-agent: search subdirectories.
        for child in governance_dir.iterdir():
            if child.is_dir():
                candidate = child / doc_path
                if candidate.is_file():
                    return candidate
    return doc_path


def _summarise_hashes(hashes: dict[str, str]) -> dict[str, str]:
    """Summarise file paths to just the basename for readability."""
    return {Path(k).name: v[:12] for k, v in hashes.items()}


__all__ = ["explain_document"]

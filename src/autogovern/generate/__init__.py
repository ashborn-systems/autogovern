"""The governance document generation engine.

Public entry point: :func:`generate_docs`. See :mod:`autogovern.generate.engine`
for the orchestration and the design rationale (deep module, content-addressed
writes, deterministic regeneration, no verifier pass).
"""

from autogovern.generate.engine import (
    ENGINE_DOCS_ALWAYS,
    GOVERNANCE_DIR,
    LLM_DOCS,
    GenerationResult,
    generate_docs,
)
from autogovern.generate.frontmatter import (
    build_frontmatter,
    parse_frontmatter,
    render_document,
)
from autogovern.generate.inputs import compute_section_hash, extract_input
from autogovern.generate.lockfile import read_lockfile, write_lockfile
from autogovern.generate.prompts import STYLE_PREAMBLE, build_section_messages
from autogovern.generate.writer import write_if_changed

__all__ = [
    "ENGINE_DOCS_ALWAYS",
    "GOVERNANCE_DIR",
    "LLM_DOCS",
    "STYLE_PREAMBLE",
    "GenerationResult",
    "build_frontmatter",
    "build_section_messages",
    "compute_section_hash",
    "extract_input",
    "generate_docs",
    "parse_frontmatter",
    "read_lockfile",
    "render_document",
    "write_if_changed",
    "write_lockfile",
]

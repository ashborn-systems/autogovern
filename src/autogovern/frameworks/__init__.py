"""Bundled framework pack and loader.

The pack ships in this directory (``pack.yaml`` plus the ``agentic-governance``
content, copied verbatim from the source skill). The generation engine treats
it as data; the enterprise tier swaps the directory to supply a larger,
dynamically updated pack.
"""

from autogovern.frameworks.loader import (
    BUNDLED_PACK_DIR,
    DocumentFeed,
    FrameworkEntry,
    Pack,
    PackLoadError,
    ResolvedSection,
    SectionDependencyGraph,
    load_pack,
    resolve_pack_dir,
    resolve_section,
    to_declared_input,
    to_graph_input,
)

__all__ = [
    "BUNDLED_PACK_DIR",
    "DocumentFeed",
    "FrameworkEntry",
    "Pack",
    "PackLoadError",
    "ResolvedSection",
    "SectionDependencyGraph",
    "load_pack",
    "resolve_pack_dir",
    "resolve_section",
    "to_declared_input",
    "to_graph_input",
]

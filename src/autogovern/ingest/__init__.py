"""Repo introspection: scan a codebase into an AgentProfile.

Public API:
    scan_repo(root, config, *, provider=None, write_card=True) -> ScanResult
    read_card(root) -> AgentCard | None

The package is organised as a functional core (discovery, parsers, builder,
summarise) behind a thin orchestration shell (scanner).
"""

from autogovern.ingest.discovery import (
    DiscoveredSignals,
    DiscoveredSources,
    FileSource,
    discover_signals,
    discover_source_files,
)
from autogovern.ingest.scanner import CARD_REL_PATH, ScanResult, read_card, scan_repo

__all__ = [
    "CARD_REL_PATH",
    "DiscoveredSignals",
    "DiscoveredSources",
    "FileSource",
    "ScanResult",
    "discover_signals",
    "discover_source_files",
    "read_card",
    "scan_repo",
]

"""Repo introspection: scan a codebase into an AgentProfile.

Public API:
    scan_repo(root, config, *, provider=None, write_card=True) -> ScanResult
    read_card(root) -> AgentCard | None

The package is organised as a functional core (discovery, parsers, builder,
summarise) behind a thin orchestration shell (scanner).
"""

from autogovern.ingest.discovery import (
    AgentDiscovery,
    DiscoveredSignals,
    DiscoveredSources,
    FileSource,
    discover_agents,
    discover_signals,
    discover_source_files,
)
from autogovern.ingest.scanner import (
    CARD_REL_PATH,
    ScannedAgent,
    ScanResult,
    read_card,
    scan_repo,
)

__all__ = [
    "CARD_REL_PATH",
    "AgentDiscovery",
    "DiscoveredSignals",
    "DiscoveredSources",
    "FileSource",
    "ScanResult",
    "ScannedAgent",
    "discover_agents",
    "discover_signals",
    "discover_source_files",
    "read_card",
    "scan_repo",
]

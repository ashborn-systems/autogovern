"""The scanner shell: orchestrates discovery, parsing, summarisation, and
AgentCard construction for all agents in a repo.

``scan_repo`` is the public entry point used by both the CLI and the library
API. It discovers every agent root in the repo, builds an :class:`AgentProfile`
per root, and returns a :class:`ScanResult` carrying the full list. A repo
with one agent at the root produces a one-element list — the same code path
as a multi-agent repo, no special case.

The functional core (discovery, parsers, builder) is pure; this module wires
it together and owns the side effects (LLM calls, card writes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from autogovern.ingest.builder import build_profile, profile_to_card
from autogovern.ingest.discovery import (
    AgentDiscovery,
    DiscoveredSources,
    discover_agents,
)
from autogovern.ingest.parsers import parse
from autogovern.ingest.summarise import summarise_free_text
from autogovern.models import AgentCard, AgentProfile, Config
from autogovern.provider import ProviderClient, build_provider

CARD_REL_PATH = ".well-known/agent.json"


@dataclass
class ScannedAgent:
    """One agent's scan result: its name, root, profile, and card status."""

    name: str
    root: str
    profile: AgentProfile
    card_written: bool
    card_path: str | None


@dataclass
class ScanResult:
    """The outcome of a scan: all agents discovered in the repo.

    ``agents`` is empty for a non-agent repo. A repo with one agent at the
    root has a one-element list with ``root == "."`` — the degenerate case
    of the multi-agent model.
    """

    agents: list[ScannedAgent] = field(default_factory=list)
    root: str = ""

    @property
    def signals_found(self) -> bool:
        """True if any agent was discovered."""
        return bool(self.agents)

    @classmethod
    def no_signals(cls, root: Path) -> ScanResult:
        return cls(agents=[], root=str(root))

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-friendly dict for ``--json`` output."""
        return {
            "signals_found": self.signals_found,
            "root": self.root,
            "agents": [
                {
                    "name": a.name,
                    "root": a.root,
                    "card_written": a.card_written,
                    "card_path": a.card_path,
                    "profile": a.profile.model_dump(mode="json"),
                }
                for a in self.agents
            ],
        }

    def to_json(self) -> str:
        """Serialise to a JSON string for ``--json`` output."""
        return json.dumps(self.to_dict(), indent=2, default=_json_default)


def scan_repo(
    root: Path,
    config: Config,
    *,
    provider: ProviderClient | None = None,
    write_card: bool = True,
) -> ScanResult:
    """Scan a repo and build an :class:`AgentProfile` for every agent root.

    Args:
        root: The repository root to scan.
        config: The autogovern config (used for the provider when ``provider``
            is not supplied directly).
        provider: An optional pre-built provider client (tests inject a mocked
            transport here). If None, one is built from ``config`` and owned
            by this call.
        write_card: When True and no ``.well-known/agent.json`` exists for an
            agent, write one. When False, never write. Existing cards are
            always parsed and never overwritten.

    Returns:
        A :class:`ScanResult` with one :class:`ScannedAgent` per discovered
        agent root. Empty for a non-agent repo.
    """
    owns_provider = provider is None
    if provider is None:
        provider = build_provider(config)

    try:
        return _scan(root, config, provider, write_card)
    finally:
        if owns_provider:
            provider.close()


def _scan(
    root: Path,
    config: Config,
    provider: ProviderClient,
    write_card: bool,
) -> ScanResult:
    """Inner scan, separated so the provider lifecycle is always handled."""
    _ = config  # reserved for future config-driven discovery overrides
    discoveries = discover_agents(root)
    if not discoveries:
        return ScanResult.no_signals(root)

    agents: list[ScannedAgent] = []
    for discovery in discoveries:
        agent = _scan_one_agent(root, discovery, provider, write_card)
        agents.append(agent)

    return ScanResult(agents=agents, root=str(root))


def _scan_one_agent(
    root: Path,
    discovery: AgentDiscovery,
    provider: ProviderClient,
    write_card: bool,
) -> ScannedAgent:
    """Build one agent's profile from its discovery result."""
    discovered = DiscoveredSources(signals=discovery.signals, source_files=discovery.source_files)
    records = parse(discovered)

    existing_card = _read_card(discovery.signals.agent_card)
    summary, summary_source = summarise_free_text(
        discovery.signals.instruction_files, discovery.signals.readme, provider
    )
    profile = build_profile(discovered, records, summary, summary_source, existing_card)

    card_written = False
    card_path: str | None = None
    agent_root = root if discovery.root == "." else root / discovery.root
    if existing_card is None and write_card:
        card_path = _write_card(agent_root, profile_to_card(profile))
        card_written = True
    elif existing_card is not None:
        card_path = str(agent_root / CARD_REL_PATH)

    return ScannedAgent(
        name=profile.name,
        root=discovery.root,
        profile=profile,
        card_written=card_written,
        card_path=card_path,
    )


def read_card(root: Path) -> AgentCard | None:
    """Read an existing ``.well-known/agent.json``, or None if absent/invalid."""
    card_file = root / CARD_REL_PATH
    if not card_file.is_file():
        return None
    return _read_card_file(card_file)


def _read_card(card_source: object | None) -> AgentCard | None:
    """Read a card from a discovered FileSource, or None."""
    from autogovern.ingest.discovery import FileSource

    if not isinstance(card_source, FileSource):
        return None
    try:
        return AgentCard.model_validate_json(card_source.content)
    except Exception:
        return None


def _read_card_file(path: Path) -> AgentCard | None:
    """Read a card from a path, returning None on any parse failure."""
    try:
        return AgentCard.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_card(agent_root: Path, card: AgentCard) -> str:
    """Write an AgentCard to ``<agent_root>/.well-known/agent.json``."""
    card_path = agent_root / CARD_REL_PATH
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return str(card_path)


def _json_default(obj: object) -> object:
    """Fallback JSON serialiser for pydantic model fields."""
    if isinstance(obj, AgentProfile | AgentCard):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


__all__ = ["CARD_REL_PATH", "ScanResult", "ScannedAgent", "read_card", "scan_repo"]

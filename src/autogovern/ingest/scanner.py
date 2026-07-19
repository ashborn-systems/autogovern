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

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from autogovern.ingest.builder import build_profile, profile_to_card
from autogovern.ingest.discovery import (
    AgentDiscovery,
    DiscoveredSources,
    FileSource,
    agent_key,
    dedupe_keys,
    discover_agents,
)
from autogovern.ingest.parsers import parse
from autogovern.ingest.summarise import FreeTextSummary, summarise_free_text
from autogovern.models import AgentCard, AgentProfile, Config
from autogovern.provider import ProviderClient, build_provider

CARD_REL_PATH = ".well-known/agent.json"

# Type of the lockfile resolver: maps an agent key to its locked profile.
LockResolver = Callable[[str], "AgentProfile | None"]


@dataclass
class ScannedAgent:
    """One agent's scan result: its key, display name, root, profile, and card status.

    ``key`` is the canonical filing key (governance directory, context
    manifest entries, result maps); ``name`` is the display name shown to
    humans (the profile name).
    """

    key: str
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
                    "key": a.key,
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
    lock_resolver: LockResolver | None = None,
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
        lock_resolver: Optional callable mapping an agent key to its locked
            profile. When supplied (``check``/``diff``), an agent whose
            free-text sources are unchanged since the lock was written
            reuses the locked LLM-derived summary instead of re-calling the
            provider — so a clean check makes zero LLM calls.

    Returns:
        A :class:`ScanResult` with one :class:`ScannedAgent` per discovered
        agent root. Empty for a non-agent repo.
    """
    owns_provider = provider is None
    if provider is None:
        provider = build_provider(config)

    try:
        return _scan(root, config, provider, write_card, lock_resolver)
    finally:
        if owns_provider:
            provider.close()


def _scan(
    root: Path,
    config: Config,
    provider: ProviderClient,
    write_card: bool,
    lock_resolver: LockResolver | None,
) -> ScanResult:
    """Inner scan, separated so the provider lifecycle is always handled."""
    _ = config  # reserved for future config-driven discovery overrides
    discoveries = discover_agents(root)
    if not discoveries:
        return ScanResult.no_signals(root)

    agents: list[ScannedAgent] = []
    for discovery in discoveries:
        agents.append(_scan_one_agent(root, discovery, provider, write_card, lock_resolver))

    # Disambiguate keys deterministically (a collision is only possible
    # between the root agent's profile-name key and a nested agent's path
    # key). Sorted discovery order makes the assignment stable.
    keys = dedupe_keys([a.key for a in agents])
    for agent, key in zip(agents, keys, strict=True):
        agent.key = key

    return ScanResult(agents=agents, root=str(root))


def _scan_one_agent(
    root: Path,
    discovery: AgentDiscovery,
    provider: ProviderClient,
    write_card: bool,
    lock_resolver: LockResolver | None,
) -> ScannedAgent:
    """Build one agent's profile from its discovery result."""
    discovered = DiscoveredSources(signals=discovery.signals, source_files=discovery.source_files)
    records = parse(discovered)

    existing_card = _read_card(discovery.signals.agent_card)

    # Deterministic first pass (no LLM): learns the profile name (and hence
    # the agent key) so the lockfile can be consulted before deciding
    # whether the summariser needs to run at all.
    deterministic_profile = build_profile(discovered, records, None, None, existing_card)
    key = agent_key(discovery.root, deterministic_profile.name)

    locked = lock_resolver(key) if lock_resolver is not None else None
    free_text_source = _free_text_source(discovery)
    if locked is not None and _summary_reusable(locked, deterministic_profile, free_text_source):
        summary = _summary_from_locked(locked, deterministic_profile)
        summary_source = free_text_source
    else:
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
        # Rebuild the profile against the just-written card so this run's
        # profile (and lockfile) matches what every later scan produces by
        # reading the card back — otherwise the card-field provenance flips
        # from manifest to card on the second run and idempotence breaks.
        card_source = _file_source_for(agent_root, root, CARD_REL_PATH)
        existing_card = _read_card_file(Path(card_path))
        if card_source is not None and existing_card is not None:
            discovered = DiscoveredSources(
                signals=replace(discovery.signals, agent_card=card_source),
                source_files=discovery.source_files,
            )
            profile = build_profile(discovered, records, summary, summary_source, existing_card)
    elif existing_card is not None:
        card_path = str(agent_root / CARD_REL_PATH)

    return ScannedAgent(
        key=key,
        name=profile.name,
        root=discovery.root,
        profile=profile,
        card_written=card_written,
        card_path=card_path,
    )


def discover_agent_identities(root: Path) -> list[tuple[str, str]]:
    """Discover each agent's (key, display name) deterministically — no LLM.

    Used by the ``init`` wizard to ask agent-level questions keyed the same
    way the engine looks them up. Returns ``[]`` for a non-agent repo.
    """
    identities: list[tuple[str, str]] = []
    for discovery in discover_agents(root):
        discovered = DiscoveredSources(
            signals=discovery.signals, source_files=discovery.source_files
        )
        records = parse(discovered)
        profile = build_profile(
            discovered, records, None, None, _read_card(discovery.signals.agent_card)
        )
        identities.append((agent_key(discovery.root, profile.name), profile.name))
    keys = dedupe_keys([key for key, _ in identities])
    return [(key, name) for key, (_, name) in zip(keys, identities, strict=True)]


# ---------------------------------------------------------------------------
# Summary reuse (zero-LLM check path)
# ---------------------------------------------------------------------------


def _free_text_source(discovery: AgentDiscovery) -> FileSource | None:
    """The free-text file a summary would be grounded in (mirrors summarise)."""
    sources = list(discovery.signals.instruction_files)
    if discovery.signals.readme is not None:
        sources.append(discovery.signals.readme)
    return sources[0] if sources else None


def _summary_reusable(
    locked: AgentProfile,
    deterministic_profile: AgentProfile,
    current_source: FileSource | None,
) -> bool:
    """True when the locked LLM-derived summary can be reused as-is.

    Reuse is safe when the free-text source file the summary was grounded in
    is byte-identical to the current one (same relative path, same content
    hash). The locked provenance records exactly that path and hash.
    """
    locked_prov = locked.governance.data_categories.provenance
    if current_source is None:
        return locked_prov.source_path == ""
    return (
        locked_prov.source_path == current_source.rel_path
        and locked_prov.content_hash == current_source.content_hash
    )


def _summary_from_locked(
    locked: AgentProfile, deterministic_profile: AgentProfile
) -> FreeTextSummary:
    """Rebuild a FreeTextSummary from a locked profile's LLM-derived fields.

    Only fields the summary could have supplied are taken: the description
    (when no deterministic source provides one), skills (likewise), and the
    data categories (always summary-derived).
    """
    description = (
        locked.description if not deterministic_profile.description and locked.description else None
    )
    skills = list(locked.skills) if not deterministic_profile.skills else []
    return FreeTextSummary(
        description=description,
        skills=skills,
        data_categories=list(locked.governance.data_categories.value),
    )


def read_card(root: Path) -> AgentCard | None:
    """Read an existing ``.well-known/agent.json``, or None if absent/invalid."""
    card_file = root / CARD_REL_PATH
    if not card_file.is_file():
        return None
    return _read_card_file(card_file)


def _read_card(card_source: object | None) -> AgentCard | None:
    """Read a card from a discovered FileSource, or None."""
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


def _file_source_for(agent_root: Path, root: Path, rel: str) -> FileSource | None:
    """Read a just-written file back as a FileSource (repo-root-relative)."""
    path = agent_root / rel
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return FileSource(
        rel_path=path.relative_to(root).as_posix(),
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _json_default(obj: object) -> object:
    """Fallback JSON serialiser for pydantic model fields."""
    if isinstance(obj, AgentProfile | AgentCard):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


__all__ = [
    "CARD_REL_PATH",
    "LockResolver",
    "ScanResult",
    "ScannedAgent",
    "discover_agent_identities",
    "read_card",
    "scan_repo",
]

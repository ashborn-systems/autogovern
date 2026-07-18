"""The scanner shell: orchestrates discovery, parsing, summarisation, and
AgentCard construction.

``scan_repo`` is the public entry point used by both the CLI and the library
API. It is the only place in ``ingest/`` with side effects beyond file reads:
it may call the LLM (via the summariser) and write ``.well-known/agent.json``.

The functional core (discovery, parsers, builder) is pure; this module wires
it together and owns the ``ScanResult`` contract returned to callers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from autogovern.ingest.builder import build_profile, profile_to_card
from autogovern.ingest.discovery import (
    DiscoveredSources,
    discover_signals,
    discover_source_files,
)
from autogovern.ingest.parsers import parse
from autogovern.ingest.summarise import summarise_free_text
from autogovern.models import AgentCard, AgentProfile, Config
from autogovern.provider import ProviderClient, build_provider

CARD_REL_PATH = ".well-known/agent.json"


@dataclass
class ScanResult:
    """The outcome of a scan.

    When ``signals_found`` is False, ``profile`` is None and the repo is not
    an agent. Otherwise ``profile`` is the full AgentProfile and ``card_written``
    records whether a new AgentCard was written to ``.well-known/agent.json``.
    """

    profile: AgentProfile | None
    signals_found: bool
    card_written: bool
    card_path: str | None
    root: str

    @classmethod
    def no_signals(cls, root: Path) -> ScanResult:
        return cls(
            profile=None,
            signals_found=False,
            card_written=False,
            card_path=None,
            root=str(root),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-friendly dict for ``--json`` output."""
        return {
            "signals_found": self.signals_found,
            "card_written": self.card_written,
            "card_path": self.card_path,
            "root": self.root,
            "profile": self.profile.model_dump(mode="json") if self.profile else None,
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
    """Scan a repo and build its AgentProfile.

    Args:
        root: The repository root to scan.
        config: The autogovern config (used for the provider when ``provider``
            is not supplied directly).
        provider: An optional pre-built provider client (tests inject a mocked
            transport here). If None, one is built from ``config`` and owned
            by this call.
        write_card: When True and no ``.well-known/agent.json`` exists, write
            one. When False, never write. An existing card is always parsed
            and never overwritten.

    Returns:
        A :class:`ScanResult`.
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
    signals = discover_signals(root)
    if not signals.has_agent_signals:
        return ScanResult.no_signals(root)

    source_files = discover_source_files(root)
    discovered = DiscoveredSources(signals=signals, source_files=source_files)
    records = parse(discovered)

    existing_card = _read_card(signals.agent_card)
    summary, summary_source = summarise_free_text(
        signals.instruction_files, signals.readme, provider
    )
    profile = build_profile(discovered, records, summary, summary_source, existing_card)

    card_written = False
    card_path: str | None = None
    if existing_card is None and write_card:
        card_path = _write_card(root, profile_to_card(profile))
        card_written = True
    elif existing_card is not None:
        card_path = str(root / CARD_REL_PATH)

    return ScanResult(
        profile=profile,
        signals_found=True,
        card_written=card_written,
        card_path=card_path,
        root=str(root),
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


def _write_card(root: Path, card: AgentCard) -> str:
    """Write an AgentCard to ``.well-known/agent.json`` and return its path."""
    card_path = root / CARD_REL_PATH
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return str(card_path)


def _json_default(obj: object) -> object:
    """Fallback JSON serialiser for pydantic model fields."""
    if isinstance(obj, AgentProfile | AgentCard):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


__all__ = ["CARD_REL_PATH", "ScanResult", "read_card", "scan_repo"]

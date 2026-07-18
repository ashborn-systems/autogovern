"""Pure assembly of an AgentProfile from parsed records and summaries.

No I/O, no LLM. The builder merges sources by a fixed precedence and attaches
provenance to every field. Given identical inputs it produces an identical
profile, which is the foundation of the determinism acceptance criterion.

Field precedence (card fields, highest first):
  1. An existing ``.well-known/agent.json`` (standards-compliant base)
  2. Project metadata from the manifest (name, version, description)
  3. The LLM free-text summary (description, skills fallback)
  4. A safe default

Governance extension fields are always populated; when a signal is absent the
field is empty with empty-string provenance, and the gap is a candidate for the
Phase 8 attention ledger.
"""

from __future__ import annotations

from autogovern.ingest.discovery import DiscoveredSources, FileSource
from autogovern.ingest.parsers import ParsedRecords, provider_from_dependencies
from autogovern.ingest.summarise import FreeTextSummary
from autogovern.models import (
    AgentAuthentication,
    AgentCapabilities,
    AgentCard,
    AgentProfile,
    DataCategory,
    Dependency,
    GovernanceExtension,
    ModelConfiguration,
    Permission,
    PromptEntry,
    Provenance,
    ProvenancedField,
)

# Sentinel provenance for fields with no discoverable source. Empty strings
# are valid (the model requires ``str``, not non-empty) and clearly mean "no
# source found".
_NO_SOURCE = Provenance(source_path="", content_hash="")


def build_profile(
    discovered: DiscoveredSources,
    records: ParsedRecords,
    summary: FreeTextSummary | None,
    summary_source: FileSource | None,
    existing_card: AgentCard | None,
) -> AgentProfile:
    """Assemble an AgentProfile from all scanner inputs.

    Args:
        discovered: The full set of discovered files.
        records: The deterministic parsed records.
        summary: The LLM free-text summary, or None in degraded mode.
        summary_source: The file the summary is grounded in, for provenance.
        existing_card: A parsed ``.well-known/agent.json``, or None.
    """
    summary = summary or FreeTextSummary()
    card_file = discovered.signals.agent_card
    card_prov = _provenance(card_file)
    manifest = _first_manifest(discovered)

    # --- Card-standard fields, by precedence ---
    meta = records.project_meta
    name = existing_card.name if existing_card else (meta.name or "unknown")
    description = (
        existing_card.description
        if existing_card
        else (meta.description or summary.description or "")
    )
    url = existing_card.url if existing_card else ""
    version = existing_card.version if existing_card else (meta.version or "0.0.0")
    capabilities = existing_card.capabilities if existing_card else AgentCapabilities()
    skills = existing_card.skills if existing_card else list(summary.skills)
    authentication = existing_card.authentication if existing_card else AgentAuthentication()
    provider_org = existing_card.provider if existing_card else None

    # --- Provenance map for card-standard fields ---
    provenance: dict[str, Provenance] = {}
    if existing_card is not None and card_file is not None:
        for field_name in ("name", "description", "url", "version", "capabilities", "skills"):
            provenance[field_name] = card_prov
        if provider_org is not None:
            provenance["provider"] = card_prov
    else:
        # No card: name/description/version come from the manifest.
        if manifest is not None and (meta.name or meta.version or meta.description):
            for field_name in ("name", "description", "version"):
                provenance[field_name] = _provenance(manifest)
        if skills and summary_source is not None:
            provenance["skills"] = _provenance(summary_source)

    # --- Governance extension ---
    governance = GovernanceExtension(
        model_configuration=_build_model_configuration(records, discovered),
        permissions_surface=_build_permissions(records, discovered),
        data_categories=_build_data_categories(summary, summary_source),
        dependencies=_build_dependencies(records, manifest),
        prompt_inventory=_build_prompt_inventory(discovered),
    )

    return AgentProfile(
        name=name,
        description=description,
        url=url,
        version=version,
        capabilities=capabilities,
        skills=skills,
        authentication=authentication,
        provider=provider_org,
        governance=governance,
        provenance=provenance,
    )


def profile_to_card(profile: AgentProfile) -> AgentCard:
    """Project an AgentProfile back to a standards-compliant AgentCard.

    Used when the scanner constructs a card for a repo that lacks one. The
    card carries only the A2A-standard fields, never the governance extension.
    """
    return AgentCard(
        name=profile.name,
        description=profile.description,
        url=profile.url,
        version=profile.version,
        capabilities=profile.capabilities,
        skills=profile.skills,
        authentication=profile.authentication,
        provider=profile.provider,
    )


# ---------------------------------------------------------------------------
# Governance field builders
# ---------------------------------------------------------------------------


def _build_model_configuration(
    records: ParsedRecords, discovered: DiscoveredSources
) -> ProvenancedField[ModelConfiguration]:
    """Build the model configuration field with provenance."""
    manifest = _first_manifest(discovered)
    if records.model_config is not None:
        mc = records.model_config
        return ProvenancedField(
            value=ModelConfiguration(
                provider=mc.provider or "unknown",
                model=mc.model or "unknown",
                temperature=mc.temperature,
                api_base=mc.api_base,
            ),
            provenance=_provenance(mc.source),
        )
    # No source-level model signal: fall back to a dep-derived provider, if any.
    provider = provider_from_dependencies(records.dependencies)
    return ProvenancedField(
        value=ModelConfiguration(provider=provider or "unknown", model="unknown"),
        provenance=_provenance(manifest) if manifest is not None else _NO_SOURCE,
    )


def _build_permissions(
    records: ParsedRecords, discovered: DiscoveredSources
) -> ProvenancedField[list[Permission]]:
    """Build the permissions surface: MCP tools plus env-var references."""
    permissions: list[Permission] = []
    for tool in records.tools:
        detail = f"{tool.name} — {tool.description}" if tool.description else tool.name
        permissions.append(Permission(kind="tool", detail=detail))
    for env in records.env_vars:
        permissions.append(Permission(kind="env", detail=env.name))

    # Provenance: the MCP config (where tools live) is primary; otherwise the
    # first source file (where env vars live).
    source: FileSource | None = None
    if discovered.signals.mcp_configs:
        source = discovered.signals.mcp_configs[0]
    elif records.env_vars:
        source = records.env_vars[0].source
    return ProvenancedField(value=permissions, provenance=_provenance(source))


def _build_data_categories(
    summary: FreeTextSummary, summary_source: FileSource | None
) -> ProvenancedField[list[DataCategory]]:
    """Build the data categories field, grounded in the summarised free text."""
    return ProvenancedField(
        value=list(summary.data_categories),
        provenance=_provenance(summary_source),
    )


def _build_dependencies(
    records: ParsedRecords, manifest: FileSource | None
) -> ProvenancedField[list[Dependency]]:
    """Build the dependency inventory from parsed manifests."""
    deps = [
        Dependency(name=d.name, version=d.version, manifest=d.manifest)
        for d in records.dependencies
    ]
    return ProvenancedField(value=deps, provenance=_provenance(manifest))


def _build_prompt_inventory(discovered: DiscoveredSources) -> ProvenancedField[list[PromptEntry]]:
    """Build the prompt inventory from discovered prompt files."""
    entries = [
        PromptEntry(path=p.rel_path, content_hash=p.content_hash)
        for p in discovered.signals.prompt_files
    ]
    source = discovered.signals.prompt_files[0] if discovered.signals.prompt_files else None
    return ProvenancedField(value=entries, provenance=_provenance(source))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provenance(source: FileSource | None) -> Provenance:
    """Build a Provenance from a FileSource, or the no-source sentinel."""
    if source is None:
        return _NO_SOURCE
    return Provenance(source_path=source.rel_path, content_hash=source.content_hash)


def _first_manifest(discovered: DiscoveredSources) -> FileSource | None:
    """Return the first manifest (pyproject before package.json before requirements)."""
    manifests = discovered.signals.manifests
    if not manifests:
        return None
    order = {"pyproject.toml": 0, "package.json": 1, "requirements.txt": 2}
    return min(manifests, key=lambda m: order.get(m.rel_path.split("/")[-1], 3))


__all__ = ["build_profile", "profile_to_card"]

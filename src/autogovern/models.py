"""Core data models for autogovern.

All models are pydantic v2 BaseModels. Provenance (source path plus content
hash) is attached to every scanner-derived field via the generic
``ProvenancedField`` wrapper; AgentCard-standard fields carry provenance
through the profile-level ``provenance`` map so the card shape stays
standards-compliant when serialised on its own.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class Provenance(BaseModel):
    """Records where a profile field came from.

    Every scanner-derived field carries one. Malformed provenance (missing
    path or hash) fails validation.
    """

    source_path: str
    content_hash: str


class ProvenancedField[T](BaseModel):
    """A value paired with the provenance of its source."""

    value: T
    provenance: Provenance


# ---------------------------------------------------------------------------
# AgentCard (A2A standard)
# ---------------------------------------------------------------------------


class AgentProvider(BaseModel):
    """The organisation that provides the agent."""

    organization: str
    url: str


class AgentSkill(BaseModel):
    """A distinct capability the agent can perform."""

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)


class AgentCapabilities(BaseModel):
    """Optional capability flags advertised by the agent."""

    streaming: bool | None = None
    push_notifications: bool | None = None
    state_transition_history: bool | None = None


class AgentAuthentication(BaseModel):
    """Authentication schemes the agent accepts."""

    schemes: list[str] = Field(default_factory=list)


class AgentCard(BaseModel):
    """A2A AgentCard — the standards-compliant agent business card."""

    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = Field(default_factory=list)
    authentication: AgentAuthentication = Field(default_factory=AgentAuthentication)
    provider: AgentProvider | None = None
    extensions: list[AgentCardExtension] = Field(
        default_factory=list,
        description="A2A Extensions for vendor-specific data. "
        "Subagent topology is carried in the subagent-topology extension.",
    )


# ---------------------------------------------------------------------------
# Subagent relationship
# ---------------------------------------------------------------------------


class SubagentRelationship(StrEnum):
    """How a subagent relates to its parent agent."""

    DELEGATION = "delegation"
    PIPELINE = "pipeline"
    PEER_HANDOFF = "peer-handoff"


class Subagent(BaseModel):
    """A subagent the parent agent orchestrates.

    Recorded in the parent's AgentCard via an A2A Extension so deployers
    can see which subagents a parent controls, what each does, and how
    they relate. This is a governance requirement: the deployer must be
    able to audit the full agent topology.
    """

    id: str
    name: str
    description: str
    relationship: SubagentRelationship
    parent_agent: str = ""
    count: int = 1
    model: str = ""


# A2A AgentCard Extension (standards-compliant custom data)
# ---------------------------------------------------------------------------

SUBAGENT_TOPOLOGY_EXTENSION_URI = "https://ashbornsystems.com/extensions/subagent-topology/v1"


class AgentCardExtension(BaseModel):
    """An A2A Extension block on an AgentCard.

    Extensions are the A2A-standard mechanism for vendor-specific data.
    Each extension is identified by a URI and carries opaque params that
    A2A consumers can inspect or ignore.
    """

    uri: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Governance extension (autogovern-specific)
# ---------------------------------------------------------------------------


class ModelConfiguration(BaseModel):
    """Model configuration observed in the agent's code."""

    provider: str
    model: str
    temperature: float | None = None
    api_base: str | None = None


class Permission(BaseModel):
    """A single permission or scope the agent exercises."""

    kind: str
    detail: str = ""


class DataCategory(StrEnum):
    """Categories of data the agent processes."""

    NONE = "none"
    PERSONAL = "personal"
    SPECIAL_CATEGORY = "special-category"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"


class Dependency(BaseModel):
    """A runtime or build dependency discovered in the manifest."""

    name: str
    version: str | None = None
    manifest: str = ""


class PromptEntry(BaseModel):
    """A prompt or instruction file discovered in the agent's code."""

    path: str
    content_hash: str


class GovernanceExtension(BaseModel):
    """The governance-specific extension block of an AgentProfile.

    Each field is provenance-tracked because the scanner derives it from code.
    """

    model_configuration: ProvenancedField[ModelConfiguration]
    permissions_surface: ProvenancedField[list[Permission]]
    data_categories: ProvenancedField[list[DataCategory]]
    dependencies: ProvenancedField[list[Dependency]]
    prompt_inventory: ProvenancedField[list[PromptEntry]]


class AgentProfile(BaseModel):
    """The single structured representation of an agent.

    A superset of the AgentCard: the standard fields plus a governance
    extension block. Card-standard fields carry provenance through the
    ``provenance`` map keyed by field name.
    """

    # AgentCard fields
    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = Field(default_factory=list)
    authentication: AgentAuthentication = Field(default_factory=AgentAuthentication)
    provider: AgentProvider | None = None
    extensions: list[AgentCardExtension] = Field(
        default_factory=list,
        description="A2A Extensions for vendor-specific data.",
    )

    # Governance extension
    governance: GovernanceExtension

    # Provenance for the card-standard fields, keyed by field name.
    provenance: dict[str, Provenance] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context manifest (organisational context)
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    HUMAN_IN_THE_LOOP = "human-in-the-loop"
    HUMAN_ON_THE_LOOP = "human-on-the-loop"
    FULLY_AUTONOMOUS = "fully-autonomous"


class RiskAppetite(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class DeploymentContext(StrEnum):
    INTERNAL = "internal"
    CUSTOMER_FACING = "customer-facing"
    THIRD_PARTY_DISTRIBUTED = "third-party-distributed"


class ProjectContext(BaseModel):
    """Organisation-level context, true for the whole repo.

    Asked once during ``init``. Stable across agents within a project;
    the fields here describe the organisation, not any single agent.
    """

    organisation: str
    sector: str
    jurisdictions: list[str] = Field(default_factory=list)
    risk_appetite: str = "conservative"
    owner: str = ""
    review_cadence: str = ""
    strategy: str = ""


class AgentContext(BaseModel):
    """Per-agent context, describing one specific agent.

    The deployment context, autonomy level, and risk appetite fields are
    free text at capture time; :func:`autogovern.generate.normalise.normalise_context`
    resolves them to canonical enum values during generation.
    """

    deployment_context: str = "internal"
    autonomy_level: str = "human-in-the-loop"
    intended_users: str = ""
    oversight_model: str = ""


class NormalisedContext(BaseModel):
    """Canonical enum values resolved from free-text context fields.

    Populated by :func:`autogovern.generate.normalise.normalise_context`
    during ``generate``. Not stored in ``context.yaml``; the raw free-text
    values are what the user edits and what the lockfile tracks.
    """

    deployment_context: DeploymentContext
    autonomy_level: AutonomyLevel
    risk_appetite: RiskAppetite


class ContextManifest(BaseModel):
    """Project context captured by the ``init`` wizard.

    Two sections: project-level (org-wide, one copy) and a per-agent map
    keyed by agent name. The agent-level enum fields are free text here and
    normalised to canonical enums at generation time. Agents not present in
    the dict get default context during ``generate``.
    """

    project: ProjectContext
    agents: dict[str, AgentContext] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Config (.autogovern/config.yaml)
# ---------------------------------------------------------------------------


class ModelProviderConfig(BaseModel):
    """Provider settings for generation and verification LLM passes."""

    api_base: str
    model: str
    api_key_env: str
    temperature: float = 0.0


class Thresholds(BaseModel):
    """Materiality score bands. Defaults: >=80 material, <=20 immaterial."""

    material: int = 80
    immaterial: int = 20


# Default watched-path globs for the heuristic pass. Module-level so the
# pre-commit hook can use them when no config file exists yet.
DEFAULT_WATCHED_PATHS: list[str] = [
    "CLAUDE.md",
    "AGENTS.md",
    "agent.md",
    ".claude/**",
    ".mcp.json",
    "mcp.json",
    ".well-known/agent.json",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "prompts/**",
]


class ObservabilityConfig(BaseModel):
    """Tracing configuration. Off by default; nothing leaves the machine."""

    tracing: bool = False


class Config(BaseModel):
    """The ``.autogovern/config.yaml`` document."""

    model_provider: ModelProviderConfig
    watched_paths: list[str] = Field(default_factory=lambda: list(DEFAULT_WATCHED_PATHS))
    thresholds: Thresholds = Field(default_factory=Thresholds)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    framework_pack: str | None = Field(
        default=None,
        description=(
            "Path to a custom framework pack directory (containing pack.yaml), "
            "relative to the repo root or absolute. None uses the bundled pack."
        ),
    )
    documents: dict[str, bool] = Field(
        default_factory=lambda: {
            "quickstart": True,
            "attention": True,
            "system-card": True,
            "risk-assessment": True,
            "data-protection": True,
            "oversight": True,
            "inventory": True,
            "testing": True,
            "incident-response": True,
            "changelog": True,
        }
    )


# ---------------------------------------------------------------------------
# Run manifest (observability)
# ---------------------------------------------------------------------------


class SectionRegeneration(BaseModel):
    """A section that was regenerated and the hash change that triggered it."""

    section: str
    changed_input: str


class CallRecord(BaseModel):
    """One LLM call's usage, attributed to the pipeline stage that made it."""

    label: str
    prompt: int | None = None
    completion: int | None = None
    total: int | None = None


class NormalisationOutcome(BaseModel):
    """The result of the free-text context normalisation pass.

    Recorded in the run manifest so a bad generation can be traced back to a
    normalisation fallback.
    """

    used_llm: bool
    fallback: bool = False
    fields: list[str] = Field(default_factory=list)


class TokenCounts(BaseModel):
    """Token usage reported by the provider for a run."""

    prompt: int | None = None
    completion: int | None = None
    total: int | None = None


class MaterialityCriterion(BaseModel):
    """One scored criterion within a materiality assessment."""

    criterion: str
    score: int
    reasoning: str = ""


class MaterialityResult(BaseModel):
    """The outcome of the material change detection pass."""

    score: int
    band: str
    criteria: list[MaterialityCriterion] = Field(default_factory=list)


class RunManifest(BaseModel):
    """The audit trail written for every scan, generate, check, and diff."""

    command: str
    tool_version: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    sections_regenerated: list[SectionRegeneration] = Field(default_factory=list)
    model_id: str | None = None
    token_counts: TokenCounts | None = None
    call_log: list[CallRecord] = Field(default_factory=list)
    normalisation: NormalisationOutcome | None = None
    prompt_template_versions: dict[str, str] = Field(default_factory=dict)
    materiality: MaterialityResult | None = None


__all__ = [
    "AgentAuthentication",
    "AgentCapabilities",
    "AgentCard",
    "AgentCardExtension",
    "AgentContext",
    "AgentProfile",
    "AgentProvider",
    "AgentSkill",
    "AutonomyLevel",
    "CallRecord",
    "Config",
    "ContextManifest",
    "DEFAULT_WATCHED_PATHS",
    "DataCategory",
    "DeploymentContext",
    "Dependency",
    "GovernanceExtension",
    "MaterialityCriterion",
    "MaterialityResult",
    "ModelConfiguration",
    "ModelProviderConfig",
    "NormalisedContext",
    "NormalisationOutcome",
    "ObservabilityConfig",
    "Permission",
    "ProjectContext",
    "PromptEntry",
    "Provenance",
    "ProvenancedField",
    "RiskAppetite",
    "RunManifest",
    "SectionRegeneration",
    "Subagent",
    "SubagentRelationship",
    "Thresholds",
    "TokenCounts",
]

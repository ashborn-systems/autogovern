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


class ContextManifest(BaseModel):
    """Organisational context captured by the ``init`` wizard."""

    organisation: str
    sector: str
    jurisdictions: list[str] = Field(default_factory=list)
    deployment_context: DeploymentContext
    intended_users: str = ""
    autonomy_level: AutonomyLevel
    oversight_model: str = ""
    data_categories: list[DataCategory] = Field(default_factory=list)
    risk_appetite: RiskAppetite
    strategy: str = ""
    owner: str = ""
    review_cadence: str = ""


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


class Config(BaseModel):
    """The ``.autogovern/config.yaml`` document."""

    model_provider: ModelProviderConfig
    watched_paths: list[str] = Field(
        default_factory=lambda: [
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
        ]
    )
    thresholds: Thresholds = Field(default_factory=Thresholds)
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


class VerifierResult(BaseModel):
    """The verifier's verdict on one regenerated section."""

    section: str
    supported_claims: int = 0
    unsupported_claims: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)


class AttentionItem(BaseModel):
    """An item requiring human attention, opened or closed in a run."""

    item_id: str
    action: str
    detail: str = ""


class RunManifest(BaseModel):
    """The audit trail written for every scan, generate, check, and diff."""

    command: str
    tool_version: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    sections_regenerated: list[SectionRegeneration] = Field(default_factory=list)
    model_id: str | None = None
    token_counts: TokenCounts | None = None
    prompt_template_versions: dict[str, str] = Field(default_factory=dict)
    materiality: MaterialityResult | None = None
    verifier_results: list[VerifierResult] = Field(default_factory=list)
    attention_items: list[AttentionItem] = Field(default_factory=list)


__all__ = [
    "AgentAuthentication",
    "AgentCapabilities",
    "AgentCard",
    "AgentProfile",
    "AgentProvider",
    "AgentSkill",
    "AttentionItem",
    "AutonomyLevel",
    "Config",
    "ContextManifest",
    "DataCategory",
    "DeploymentContext",
    "Dependency",
    "GovernanceExtension",
    "MaterialityCriterion",
    "MaterialityResult",
    "ModelConfiguration",
    "ModelProviderConfig",
    "Permission",
    "PromptEntry",
    "Provenance",
    "ProvenancedField",
    "RiskAppetite",
    "RunManifest",
    "SectionRegeneration",
    "Thresholds",
    "TokenCounts",
    "VerifierResult",
]

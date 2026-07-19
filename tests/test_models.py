"""Phase 1 model tests: round-trip serialisation, rejection, and schema export."""

import pytest
from pydantic import ValidationError

from autogovern.models import (
    AgentCard,
    AgentContext,
    AgentProfile,
    AgentProvider,
    AgentSkill,
    AutonomyLevel,
    Config,
    ContextManifest,
    DataCategory,
    Dependency,
    DeploymentContext,
    GovernanceExtension,
    MaterialityCriterion,
    MaterialityResult,
    ModelConfiguration,
    ModelProviderConfig,
    NormalisedContext,
    Permission,
    ProjectContext,
    PromptEntry,
    Provenance,
    ProvenancedField,
    RiskAppetite,
    RunManifest,
    SectionRegeneration,
    Thresholds,
    TokenCounts,
)

# Models that must round-trip and export a JSON schema.
ROUND_TRIP_MODELS = [
    AgentCard,
    AgentProfile,
    ContextManifest,
    Config,
    RunManifest,
    GovernanceExtension,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provenance() -> Provenance:
    return Provenance(source_path="src/agent.py", content_hash="abc123")


def _governance() -> GovernanceExtension:
    return GovernanceExtension(
        model_configuration=ProvenancedField(
            value=ModelConfiguration(provider="openrouter", model="claude-3"),
            provenance=_provenance(),
        ),
        permissions_surface=ProvenancedField(
            value=[Permission(kind="filesystem", detail="read ./data")],
            provenance=_provenance(),
        ),
        data_categories=ProvenancedField(value=[DataCategory.PERSONAL], provenance=_provenance()),
        dependencies=ProvenancedField(
            value=[Dependency(name="typer", version="0.27.0", manifest="pyproject.toml")],
            provenance=_provenance(),
        ),
        prompt_inventory=ProvenancedField(
            value=[PromptEntry(path="prompts/system.md", content_hash="def456")],
            provenance=_provenance(),
        ),
    )


def _profile() -> AgentProfile:
    return AgentProfile(
        name="test-agent",
        description="A test agent.",
        url="https://example.com/agent",
        version="0.1.0",
        skills=[AgentSkill(id="s1", name="Summarise", description="Summarises text")],
        provider=AgentProvider(organization="Acme", url="https://acme.example"),
        governance=_governance(),
        provenance={"name": _provenance()},
    )


def _context() -> ContextManifest:
    return ContextManifest(
        project=ProjectContext(
            organisation="Acme Ltd",
            sector="financial services",
            jurisdictions=["UK", "EU"],
            risk_appetite="balanced",
        ),
        agents={
            "default": AgentContext(
                deployment_context="internal",
                autonomy_level="human-in-the-loop",
            )
        },
    )


def _config() -> Config:
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://openrouter.ai/api/v1",
            model="claude-3",
            api_key_env="OPENROUTER_API_KEY",
        )
    )


def _run_manifest() -> RunManifest:
    return RunManifest(
        command="generate",
        tool_version="0.1.0",
        config_snapshot={"model": "claude-3"},
        input_hashes={"src/agent.py": "abc123"},
        sections_regenerated=[
            SectionRegeneration(section="system-card", changed_input="model_configuration")
        ],
        model_id="claude-3",
        token_counts=TokenCounts(prompt=1200, completion=800, total=2000),
        materiality=MaterialityResult(
            score=85,
            band="material",
            criteria=[MaterialityCriterion(criterion="tool change", score=90)],
        ),
    )


# ---------------------------------------------------------------------------
# Round-trip serialisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_cls", ROUND_TRIP_MODELS, ids=lambda m: m.__name__)
def test_round_trip_serialisation(model_cls: type) -> None:
    """Every model round-trips through JSON without loss."""
    instances = {
        AgentCard: lambda: AgentCard(name="a", description="d", url="https://x", version="1"),
        AgentProfile: _profile,
        ContextManifest: _context,
        Config: _config,
        RunManifest: _run_manifest,
        GovernanceExtension: _governance,
    }
    instance = instances[model_cls]()
    dumped = instance.model_dump_json()
    rebuilt = model_cls.model_validate_json(dumped)
    assert rebuilt == instance


def test_provenanced_field_round_trip() -> None:
    """A generic provenanced field round-trips with its inner type intact."""
    field: ProvenancedField[ModelConfiguration] = ProvenancedField(
        value=ModelConfiguration(provider="p", model="m"),
        provenance=_provenance(),
    )
    dumped = field.model_dump_json()
    rebuilt = ProvenancedField[ModelConfiguration].model_validate_json(dumped)
    assert rebuilt == field
    assert rebuilt.value.provider == "p"


# ---------------------------------------------------------------------------
# Free-text acceptance: context fields accept arbitrary strings
# ---------------------------------------------------------------------------


def test_context_accepts_free_text_autonomy_level() -> None:
    """Autonomy level is free text; the LLM normalises it at generation time."""
    ctx = ContextManifest(
        project=ProjectContext(organisation="x", sector="x"),
        agents={
            "default": AgentContext(
                deployment_context="internal",
                autonomy_level="fully-autonomous, human-on-the-loop",
            )
        },
    )
    assert ctx.agents["default"].autonomy_level == "fully-autonomous, human-on-the-loop"


def test_context_accepts_free_text_deployment_context() -> None:
    """Deployment context is free text; the LLM normalises it at generation time."""
    ctx = ContextManifest(
        project=ProjectContext(organisation="x", sector="x"),
        agents={
            "default": AgentContext(
                deployment_context="customer-facing, internal",
                autonomy_level="human-in-the-loop",
            )
        },
    )
    assert ctx.agents["default"].deployment_context == "customer-facing, internal"


def test_context_accepts_free_text_risk_appetite() -> None:
    """Risk appetite is free text; the LLM normalises it at generation time."""
    ctx = ContextManifest(
        project=ProjectContext(organisation="x", sector="x", risk_appetite="conservative"),
        agents={"default": AgentContext()},
    )
    assert ctx.project.risk_appetite == "conservative"


def test_normalised_context_validates_canonical_enums() -> None:
    """NormalisedContext still enforces the canonical enum vocabulary."""
    n = NormalisedContext(
        deployment_context=DeploymentContext.CUSTOMER_FACING,
        autonomy_level=AutonomyLevel.FULLY_AUTONOMOUS,
        risk_appetite=RiskAppetite.AGGRESSIVE,
    )
    assert n.deployment_context == DeploymentContext.CUSTOMER_FACING
    with pytest.raises(ValidationError):
        NormalisedContext(
            deployment_context="mars",  # type: ignore[arg-type]
            autonomy_level=AutonomyLevel.HUMAN_IN_THE_LOOP,
            risk_appetite=RiskAppetite.BALANCED,
        )


def test_profile_rejects_invalid_data_category() -> None:
    """An invalid data category string is rejected at validation time."""
    gov = _governance().model_dump()
    gov["data_categories"]["value"] = ["telepathic"]
    with pytest.raises(ValidationError):
        GovernanceExtension.model_validate(gov)


# ---------------------------------------------------------------------------
# Rejection: missing required fields
# ---------------------------------------------------------------------------


def test_agent_card_requires_name() -> None:
    with pytest.raises(ValidationError):
        AgentCard(description="d", url="https://x", version="1")  # type: ignore[call-arg]


def test_context_requires_organisation() -> None:
    with pytest.raises(ValidationError):
        ContextManifest(  # type: ignore[call-arg]
            sector="x",
        )


def test_config_requires_model_provider() -> None:
    with pytest.raises(ValidationError):
        Config()  # type: ignore[call-arg]


def test_model_provider_requires_api_key_env() -> None:
    with pytest.raises(ValidationError):
        ModelProviderConfig(api_base="https://x", model="m")  # type: ignore[call-arg]


def test_run_manifest_requires_command() -> None:
    with pytest.raises(ValidationError):
        RunManifest(tool_version="0.1.0")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Rejection: malformed provenance
# ---------------------------------------------------------------------------


def test_provenance_requires_source_path() -> None:
    with pytest.raises(ValidationError):
        Provenance(content_hash="abc")  # type: ignore[call-arg]


def test_provenance_requires_content_hash() -> None:
    with pytest.raises(ValidationError):
        Provenance(source_path="src/x.py")  # type: ignore[call-arg]


def test_provenanced_field_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        ProvenancedField(value=ModelConfiguration(provider="p", model="m"))  # type: ignore[call-arg]


def test_profile_governance_field_requires_provenance() -> None:
    """A governance field missing its provenance wrapper is rejected."""
    raw = _profile().model_dump()
    # Corrupt: replace a provenanced field with a bare value.
    raw["governance"]["model_configuration"] = {"value": {"provider": "p", "model": "m"}}
    raw["governance"]["model_configuration"].pop("provenance", None)
    with pytest.raises(ValidationError):
        AgentProfile.model_validate(raw)


# ---------------------------------------------------------------------------
# JSON schema export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_cls", ROUND_TRIP_MODELS, ids=lambda m: m.__name__)
def test_json_schema_export(model_cls: type) -> None:
    """Every model exports a JSON schema without error."""
    schema = model_cls.model_json_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") in {"object", None}


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_thresholds_default_bands() -> None:
    t = Thresholds()
    assert t.material == 80
    assert t.immaterial == 20


def test_config_default_documents_include_undisableable() -> None:
    """QUICKSTART and ATTENTION cannot be disabled — they default on."""
    cfg = _config()
    assert cfg.documents["quickstart"] is True
    assert cfg.documents["attention"] is True


def test_config_default_watched_paths_nonempty() -> None:
    cfg = _config()
    assert len(cfg.watched_paths) > 0

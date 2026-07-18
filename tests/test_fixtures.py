"""Phase 3 fixture tests: every fixture file parses, and the standalone
profile validates against the Phase 1 AgentProfile schema.

Fixtures are small fake agent repos used as known inputs by later phases.
This module guards two invariants:
  1. Every JSON/YAML file under tests/fixtures parses cleanly.
  2. fixture-profile.json is a valid AgentProfile (the headless input for
     Phase 11's --profile flag), and fixture-carded's agent.json is a valid
     AgentCard (Phase 4 reads it instead of writing one).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from autogovern.models import AgentCard, AgentProfile

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _json_files() -> list[Path]:
    return sorted(FIXTURES.rglob("*.json"))


def _yaml_files() -> list[Path]:
    return sorted([*FIXTURES.rglob("*.yaml"), *FIXTURES.rglob("*.yml")])


# ---------------------------------------------------------------------------
# Parse validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _json_files(), ids=lambda p: str(p.relative_to(FIXTURES)))
def test_json_fixtures_parse(path: Path) -> None:
    """Every JSON fixture parses to a structured value without error."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, (dict, list))


@pytest.mark.parametrize("path", _yaml_files(), ids=lambda p: str(p.relative_to(FIXTURES)))
def test_yaml_fixtures_parse(path: Path) -> None:
    """Every YAML fixture parses without error.

    context-invalid.yaml is intentionally invalid at the model level but must
    still parse as YAML so init's error is schema-level, not a parse failure.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data is not None


# ---------------------------------------------------------------------------
# Schema validity
# ---------------------------------------------------------------------------


def test_fixture_profile_validates_as_agent_profile() -> None:
    """fixture-profile.json validates against the Phase 1 AgentProfile schema.

    This is the headless input for Phase 11's --profile flag and must carry
    the full governance extension block with provenance on every field.
    """
    raw = json.loads((FIXTURES / "fixture-profile.json").read_text(encoding="utf-8"))
    profile = AgentProfile.model_validate(raw)
    assert profile.name == "support-triage-agent"
    # Every governance field is provenance-tracked — the Phase 1 hallmark.
    gov = profile.governance
    for field_name in (
        "model_configuration",
        "permissions_surface",
        "data_categories",
        "dependencies",
        "prompt_inventory",
    ):
        field = getattr(gov, field_name)
        assert field.provenance.source_path, f"{field_name} missing source_path"
        assert field.provenance.content_hash, f"{field_name} missing content_hash"


def test_carded_agent_json_validates_as_agent_card() -> None:
    """fixture-carded's .well-known/agent.json is a valid A2A AgentCard.

    Phase 4's scanner must parse this instead of constructing one, so the
    fixture must be standards-compliant.
    """
    raw = json.loads(
        (FIXTURES / "fixture-carded" / ".well-known" / "agent.json").read_text(encoding="utf-8")
    )
    card = AgentCard.model_validate(raw)
    assert card.name == "support-triage-agent"
    assert card.version == "0.3.0"

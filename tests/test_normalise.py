"""Tests for free-text context normalisation.

The ``init`` wizard captures deployment context, autonomy level, and risk
appetite as free text. ``normalise_context`` resolves them to canonical
enum values via one LLM call, with a zero-LLM fast path and a graceful
fallback.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from autogovern.generate.normalise import normalise_context
from autogovern.models import (
    AgentContext,
    AutonomyLevel,
    DeploymentContext,
    RiskAppetite,
)


def _agent_context(*, deployment="internal", autonomy="human-in-the-loop") -> AgentContext:
    return AgentContext(deployment_context=deployment, autonomy_level=autonomy)


def test_direct_resolution_skips_llm() -> None:
    """When raw values are already canonical, no LLM call is made."""
    provider = MagicMock()
    agent_ctx = _agent_context(
        deployment="customer-facing",
        autonomy="fully-autonomous",
    )
    result, outcome = normalise_context(agent_ctx, "aggressive", provider)
    assert result.deployment_context == DeploymentContext.CUSTOMER_FACING
    assert result.autonomy_level == AutonomyLevel.FULLY_AUTONOMOUS
    assert result.risk_appetite == RiskAppetite.AGGRESSIVE
    provider.chat_json.assert_not_called()


def test_llm_resolves_multi_value_deployment_context() -> None:
    """'customer-facing, internal' resolves to the higher-risk option."""
    provider = MagicMock()
    provider.chat_json.return_value = {
        "deployment_context": "customer-facing",
        "autonomy_level": "human-in-the-loop",
        "risk_appetite": "conservative",
    }
    agent_ctx = _agent_context(deployment="customer-facing, internal")
    result, outcome = normalise_context(agent_ctx, "conservative", provider)
    assert result.deployment_context == DeploymentContext.CUSTOMER_FACING


def test_llm_resolves_multi_value_autonomy() -> None:
    """'fully-autonomous, human-on-the-loop' resolves to fully-autonomous."""
    provider = MagicMock()
    provider.chat_json.return_value = {
        "deployment_context": "internal",
        "autonomy_level": "fully-autonomous",
        "risk_appetite": "conservative",
    }
    agent_ctx = _agent_context(autonomy="fully-autonomous, human-on-the-loop")
    result, outcome = normalise_context(agent_ctx, "conservative", provider)
    assert result.autonomy_level == AutonomyLevel.FULLY_AUTONOMOUS


def test_llm_resolves_free_text_risk_appetite() -> None:
    """'customer data' style free text for risk resolves to a canonical enum."""
    provider = MagicMock()
    provider.chat_json.return_value = {
        "deployment_context": "internal",
        "autonomy_level": "human-in-the-loop",
        "risk_appetite": "conservative",
    }
    agent_ctx = _agent_context()
    result, outcome = normalise_context(agent_ctx, "conservative but leaning balanced", provider)
    assert result.risk_appetite == RiskAppetite.CONSERVATIVE


def test_llm_fallback_on_provider_error() -> None:
    """A provider error falls back to higher-risk defaults, never blocks."""
    provider = MagicMock()
    provider.chat_json.side_effect = RuntimeError("network down")
    agent_ctx = _agent_context(deployment="something weird", autonomy="also weird")
    result, outcome = normalise_context(agent_ctx, "conservative", provider)
    assert result.deployment_context == DeploymentContext.CUSTOMER_FACING
    assert result.autonomy_level == AutonomyLevel.FULLY_AUTONOMOUS
    assert result.risk_appetite == RiskAppetite.AGGRESSIVE


def test_llm_fallback_on_invalid_response() -> None:
    """An unparseable LLM response falls back to higher-risk defaults."""
    provider = MagicMock()
    provider.chat_json.return_value = {"unexpected": "shape"}
    agent_ctx = _agent_context(deployment="something weird", autonomy="also weird")
    result, outcome = normalise_context(agent_ctx, "conservative", provider)
    assert result.deployment_context == DeploymentContext.CUSTOMER_FACING
    assert result.autonomy_level == AutonomyLevel.FULLY_AUTONOMOUS


def test_whitespace_tolerant_direct_resolution() -> None:
    """Leading/trailing whitespace is stripped before direct resolution."""
    provider = MagicMock()
    agent_ctx = _agent_context(deployment="  internal  ", autonomy=" fully-autonomous ")
    result, outcome = normalise_context(agent_ctx, "aggressive", provider)
    assert result.deployment_context == DeploymentContext.INTERNAL
    assert result.autonomy_level == AutonomyLevel.FULLY_AUTONOMOUS
    provider.chat_json.assert_not_called()

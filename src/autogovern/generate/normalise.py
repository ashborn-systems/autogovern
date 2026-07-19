"""Free-text context normalisation.

The ``init`` wizard captures deployment context, autonomy level, and risk
appetite as free text. Generation needs canonical enum values for prompt
construction. This module resolves the two in one LLM call, with a
zero-LLM fast path when the raw value is already canonical and a graceful
fallback to the higher-risk default on any failure.

Called once at the top of :func:`autogovern.generate.engine.generate_docs`.
Never blocks: a provider error or unparseable response falls back to
defaults and records a warning, so generation proceeds.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from autogovern.models import (
    AgentContext,
    AutonomyLevel,
    DeploymentContext,
    NormalisationOutcome,
    NormalisedContext,
    RiskAppetite,
)

if TYPE_CHECKING:
    from autogovern.provider import ProviderClient

# Higher-risk fallback for each field, used when the LLM call fails or the
# response cannot be parsed. Errs toward caution: a failed normalisation
# should not silently downgrade the governance posture.
_FALLBACK = NormalisedContext(
    deployment_context=DeploymentContext.CUSTOMER_FACING,
    autonomy_level=AutonomyLevel.FULLY_AUTONOMOUS,
    risk_appetite=RiskAppetite.AGGRESSIVE,
)

# The allowed vocabulary, embedded in the LLM prompt.
_VOCABULARY = {
    "deployment_context": [e.value for e in DeploymentContext],
    "autonomy_level": [e.value for e in AutonomyLevel],
    "risk_appetite": [e.value for e in RiskAppetite],
}

_NORMALISE_PROMPT = """\
You are normalising free-text governance context into canonical enum values.

For each field, choose the single value from the allowed list that best \
matches the user's free-text answer. If the answer mentions multiple values, \
pick the higher-risk one (customer-facing > internal; fully-autonomous > \
human-on-the-loop > human-in-the-loop; aggressive > balanced > conservative).

Allowed values:
- deployment_context: {deployment_context}
- autonomy_level: {autonomy_level}
- risk_appetite: {risk_appetite}

User's free-text answers:
- deployment_context: {deployment_context_answer}
- autonomy_level: {autonomy_level_answer}
- risk_appetite: {risk_appetite_answer}

Respond with a JSON object with three keys: deployment_context, \
autonomy_level, risk_appetite. Each value must be one of the allowed values.
""".format


def normalise_context(
    agent_context: AgentContext,
    risk_appetite: str,
    provider: ProviderClient,
) -> tuple[NormalisedContext, NormalisationOutcome]:
    """Resolve free-text context fields to canonical enums via one LLM call.

    Takes the per-agent context (deployment_context, autonomy_level) and the
    project-level risk_appetite. Returns the normalised context plus an
    outcome record (used_llm, fallback, fields) for the run manifest.

    Fast path: if all three raw values are already valid enum members, no
    LLM call is made. Otherwise one ``chat_json`` call resolves the
    ambiguous fields.

    Fallback: on any provider error or unparseable response, each field
    defaults to the higher-risk enum value.
    """
    direct = _try_direct_resolution(agent_context, risk_appetite)
    if direct is not None:
        return direct, NormalisationOutcome(
            used_llm=False,
            fallback=False,
            fields=[
                agent_context.deployment_context,
                agent_context.autonomy_level,
                risk_appetite,
            ],
        )

    try:
        result = _normalise_via_llm(agent_context, risk_appetite, provider)
        return result, NormalisationOutcome(
            used_llm=True,
            fallback=False,
            fields=[
                result.deployment_context.value,
                result.autonomy_level.value,
                result.risk_appetite.value,
            ],
        )
    except Exception:
        # Provider error, JSON parse error, or validation error. Fall back
        # to higher-risk defaults so generation never blocks.
        return _FALLBACK, NormalisationOutcome(
            used_llm=True,
            fallback=True,
            fields=[
                _FALLBACK.deployment_context.value,
                _FALLBACK.autonomy_level.value,
                _FALLBACK.risk_appetite.value,
            ],
        )


def _try_direct_resolution(
    agent_context: AgentContext, risk_appetite: str
) -> NormalisedContext | None:
    """Return a NormalisedContext if all three raw values are already canonical.

    Matching is case-insensitive and whitespace-tolerant: "Internal" and
    " conservative " resolve directly, avoiding a pointless LLM call on
    every generate for values that are canonical in every way but casing.
    """
    try:
        return NormalisedContext(
            deployment_context=DeploymentContext(agent_context.deployment_context.strip().lower()),
            autonomy_level=AutonomyLevel(agent_context.autonomy_level.strip().lower()),
            risk_appetite=RiskAppetite(risk_appetite.strip().lower()),
        )
    except ValueError:
        return None


def _normalise_via_llm(
    agent_context: AgentContext, risk_appetite: str, provider: ProviderClient
) -> NormalisedContext:
    """Ask the LLM to resolve ambiguous free-text values to canonical enums."""
    prompt = _NORMALISE_PROMPT(
        deployment_context=", ".join(_VOCABULARY["deployment_context"]),
        autonomy_level=", ".join(_VOCABULARY["autonomy_level"]),
        risk_appetite=", ".join(_VOCABULARY["risk_appetite"]),
        deployment_context_answer=agent_context.deployment_context,
        autonomy_level_answer=agent_context.autonomy_level,
        risk_appetite_answer=risk_appetite,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a governance context normaliser. You resolve free-text "
                "answers to canonical enum values. Always respond with valid JSON."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    raw = provider.chat_json(messages, label="normalise")
    parsed = _coerce_to_dict(raw)
    return NormalisedContext(
        deployment_context=DeploymentContext(parsed["deployment_context"]),
        autonomy_level=AutonomyLevel(parsed["autonomy_level"]),
        risk_appetite=RiskAppetite(parsed["risk_appetite"]),
    )


def _coerce_to_dict(raw: object) -> dict[str, str]:
    """Coerce a chat_json response to a str-keyed dict, raising on bad shape."""
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    raise ValueError(f"Expected a JSON object, got {type(raw).__name__}")


__all__ = ["normalise_context"]

"""Scoring: deterministic rules plus semantic (LLM) pass for the remainder.

Deterministic rules score certain field changes as material (>= 80) without
an LLM, per the spec: a new tool, a widened permission scope, a changed
autonomy level, a new data category, or a model swap. Prompt content changes
fall to the semantic scorer (one LLM call, profile diff in, 0-100 plus
per-criterion reasoning out).

Band logic: >= material threshold → material, <= immaterial threshold →
immaterial, between → advisory. Thresholds from config (defaults 80/20).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from autogovern.detect.diff import FieldDiff, ProfileDiff
from autogovern.models import MaterialityCriterion, MaterialityResult, Thresholds
from autogovern.provider import ProviderClient

# Fields that score deterministically. Each names the diff field and a scorer.
_DETERMINISTIC_FIELDS = {
    "governance.model_configuration",
    "governance.permissions_surface",
    "governance.data_categories",
    "context.autonomy_level",
    "context.risk_appetite",
    "governance.prompt_inventory.paths",
}

PROMPT_TEMPLATE_VERSION = "semantic-scorer-1.0.0"


def score_deterministic(diff: ProfileDiff) -> list[MaterialityCriterion]:
    """Score the deterministic fields. Returns criteria, or an empty list.

    A non-empty list means the change is material by definition; the caller
    takes the max score and skips the semantic pass. An empty list means no
    deterministic rule fired, so the semantic scorer should run if there are
    semantic fields.
    """
    criteria: list[MaterialityCriterion] = []
    for fd in diff.fields:
        criterion = _score_field(fd)
        if criterion is not None:
            criteria.append(criterion)
    return criteria


def _score_field(fd: FieldDiff) -> MaterialityCriterion | None:
    field = fd.field
    if field == "governance.model_configuration":
        return MaterialityCriterion(
            criterion="model swap",
            score=100,
            reasoning=f"model changed from {fd.old!r} to {fd.new!r}",
        )
    if field == "governance.permissions_surface":
        old_tools = _tools(fd.old)
        new_tools = _tools(fd.new)
        added = new_tools - old_tools
        removed = old_tools - new_tools
        if added:
            return MaterialityCriterion(
                criterion="new tool",
                score=100,
                reasoning=f"tools added: {sorted(added)}",
            )
        if removed:
            return MaterialityCriterion(
                criterion="removed tool",
                score=100,
                reasoning=f"tools removed: {sorted(removed)}",
            )
        # Permission scope widened (env vars changed).
        return MaterialityCriterion(
            criterion="permission scope change",
            score=90,
            reasoning="permissions surface changed without tool add/remove",
        )
    if field == "governance.data_categories":
        old_cats = set(fd.old) if isinstance(fd.old, list) else set()
        new_cats = set(fd.new) if isinstance(fd.new, list) else set()
        added = new_cats - old_cats
        if added:
            return MaterialityCriterion(
                criterion="new data category",
                score=100,
                reasoning=f"data categories added: {sorted(added)}",
            )
        return MaterialityCriterion(
            criterion="data category change",
            score=90,
            reasoning=f"data categories changed: {sorted(new_cats)}",
        )
    if field == "context.autonomy_level":
        return MaterialityCriterion(
            criterion="autonomy change",
            score=100,
            reasoning=f"autonomy changed from {fd.old!r} to {fd.new!r}",
        )
    if field == "context.risk_appetite":
        return MaterialityCriterion(
            criterion="risk appetite change",
            score=90,
            reasoning=f"risk appetite changed from {fd.old!r} to {fd.new!r}",
        )
    if field == "governance.prompt_inventory.paths":
        return MaterialityCriterion(
            criterion="prompt file added or removed",
            score=90,
            reasoning=f"prompt paths changed: {fd.old!r} → {fd.new!r}",
        )
    return None


def score_semantic(diff: ProfileDiff, provider: ProviderClient) -> MaterialityCriterion:
    """Score the semantic remainder (prompt content changes) via one LLM call.

    The scorer receives the field-level profile diff, not raw git hunks,
    which keeps token use minimal. Returns one criterion with a 0-100 score
    and per-criterion reasoning.
    """
    messages = _build_semantic_messages(diff)
    try:
        result = provider.chat_json(messages, schema=SemanticScore)
        assert isinstance(result, SemanticScore)
    except Exception:
        # Degrade gracefully: assume material so docs get regenerated rather
        # than a silent pass on a scorer outage.
        return MaterialityCriterion(
            criterion="semantic (degraded)",
            score=100,
            reasoning="semantic scorer failed; assuming material",
        )
    return MaterialityCriterion(
        criterion="prompt content change",
        score=result.score,
        reasoning=result.reasoning,
    )


class SemanticScore(BaseModel):
    """The semantic scorer's structured response."""

    score: int = Field(ge=0, le=100)
    reasoning: str = ""


def _build_semantic_messages(diff: ProfileDiff) -> list[dict[str, str]]:
    system = (
        "You are a materiality scorer for AI agent governance documentation. "
        "Given a field-level profile diff, score how materially the agent has "
        "changed on a scale of 0-100. 0 means no governance impact; 100 means "
        "the documentation no longer describes the agent. Return JSON with "
        "'score' (0-100) and 'reasoning' (one sentence)."
    )
    user = "Score this profile diff for materiality:\n\n" + json.dumps(
        [
            {"field": fd.field, "old": _serialise(fd.old), "new": _serialise(fd.new)}
            for fd in diff.fields
        ],
        indent=2,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _serialise(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def band_for(score: int, thresholds: Thresholds) -> str:
    """Return the band name for a score given the thresholds."""
    if score >= thresholds.material:
        return "material"
    if score <= thresholds.immaterial:
        return "immaterial"
    return "advisory"


def build_result(criteria: list[MaterialityCriterion], thresholds: Thresholds) -> MaterialityResult:
    """Assemble a MaterialityResult from the scored criteria."""
    score = max((c.score for c in criteria), default=0)
    return MaterialityResult(score=score, band=band_for(score, thresholds), criteria=criteria)


def _tools(permissions: Any) -> set[str]:
    """Extract tool names from a permissions surface list."""
    if not isinstance(permissions, list):
        return set()
    tools: set[str] = set()
    for perm in permissions:
        if isinstance(perm, dict) and perm.get("kind") == "tool":
            detail = perm.get("detail", "")
            # The detail is "tool_name — description"; take the part before the dash.
            name = detail.split(" — ")[0].split(" - ")[0].strip()
            if name:
                tools.add(name)
    return tools


__all__ = [
    "PROMPT_TEMPLATE_VERSION",
    "SemanticScore",
    "band_for",
    "build_result",
    "score_deterministic",
    "score_semantic",
]

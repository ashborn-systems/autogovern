"""Material change detection: three stages, ordered by cost.

1. **Heuristic pass** (fast, deterministic, no LLM): did a watched file change?
2. **Profile diff pass** (CI, mostly deterministic): rebuild the profile, diff
   against the lockfile. Certain field changes score material without an LLM.
3. **Semantic pass** (LLM, only when needed): prompt content changes are
   scored 0-100 via one LLM call.

The orchestrator runs the stages in order and stops as early as possible: a
negative heuristic pass means no rebuild, no diff, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autogovern.detect.diff import FieldDiff, ProfileDiff, diff_context, diff_profiles
from autogovern.detect.heuristic import HeuristicResult, heuristic_pass
from autogovern.detect.scorer import (
    build_result,
    score_deterministic,
    score_semantic,
)
from autogovern.models import (
    AgentProfile,
    Config,
    ContextManifest,
    MaterialityCriterion,
    MaterialityResult,
)
from autogovern.provider import ProviderClient


@dataclass
class DetectionResult:
    """The full outcome of material change detection."""

    heuristic: HeuristicResult
    profile_diff: ProfileDiff | None = None
    materiality: MaterialityResult | None = None
    llm_call_count: int = 0

    @property
    def changed(self) -> bool:
        """Whether a materiality-relevant change was detected."""
        return self.profile_diff is not None and self.profile_diff.has_diff

    @property
    def stale_sections(self) -> list[str]:
        """Document sections affected by the changed inputs (from the graph).

        Computed by the caller (which has the pack); this is a placeholder
        that the caller fills from the dependency graph.
        """
        return []


def detect_material_change(
    changed_files: list[str | Path],
    config: Config,
    locked_profile: AgentProfile | None,
    current_profile: AgentProfile,
    locked_context: ContextManifest | None = None,
    current_context: ContextManifest | None = None,
    *,
    provider: ProviderClient | None = None,
    ci_mode: bool = False,
) -> DetectionResult:
    """Run the three-stage material change detection.

    Args:
        changed_files: Paths that changed (for the heuristic pass).
        config: The config (watched_paths, thresholds).
        locked_profile: The profile from ``profile.lock``, or None if no lockfile.
        current_profile: The freshly scanned profile.
        locked_context: The locked context manifest, if available.
        current_context: The current context manifest, if available.
        provider: An optional provider for the semantic pass. If None, the
            semantic pass is skipped (degraded: assumed material).
        ci_mode: When True, always run the profile diff pass (CI behaviour:
            the heuristic is informational, not a gate). When False
            (pre-commit), a negative heuristic stops early.

    Returns:
        A :class:`DetectionResult`.
    """
    # Stage 1: heuristic pass.
    heuristic = heuristic_pass(changed_files, config)
    if not heuristic.matched and not ci_mode:
        return DetectionResult(heuristic=heuristic)

    # Stage 2: profile diff pass.
    if locked_profile is None:
        # No lockfile: everything is new. Treat as material.
        diff = ProfileDiff(fields=[])
        diff.fields.append(_new_profile_diff(current_profile))
        criteria = score_deterministic(diff)
        if not criteria:
            criteria = [
                _new_profile_criterion(),
            ]
        materiality = build_result(criteria, config.thresholds)
        return DetectionResult(heuristic=heuristic, profile_diff=diff, materiality=materiality)

    diff = diff_profiles(locked_profile, current_profile)
    if current_context is not None:
        ctx_diff = diff_context(locked_context, current_context)
        diff.fields.extend(ctx_diff.fields)
        diff.semantic_fields.extend(ctx_diff.semantic_fields)

    if not diff.has_diff:
        return DetectionResult(heuristic=heuristic, profile_diff=diff)

    # Deterministic scoring first.
    criteria = score_deterministic(diff)
    llm_calls = 0

    # Semantic pass only if there are semantic fields and no deterministic hit.
    if diff.semantic_fields and not criteria and provider is not None:
        semantic = score_semantic(diff, provider)
        criteria.append(semantic)
        llm_calls = 1
    elif diff.semantic_fields and not criteria and provider is None:
        # Degrade: no provider, assume material.
        from autogovern.models import MaterialityCriterion

        criteria.append(
            MaterialityCriterion(
                criterion="semantic (degraded, no provider)",
                score=100,
                reasoning="semantic scorer unavailable; assuming material",
            )
        )

    materiality = build_result(criteria, config.thresholds)
    return DetectionResult(
        heuristic=heuristic, profile_diff=diff, materiality=materiality, llm_call_count=llm_calls
    )


def _new_profile_diff(profile: AgentProfile) -> FieldDiff:
    """A FieldDiff representing a brand-new profile (no lockfile)."""
    return FieldDiff(field="profile", old=None, new=profile.model_dump(mode="json"))


def _new_profile_criterion() -> MaterialityCriterion:
    return MaterialityCriterion(
        criterion="new profile (no lockfile)",
        score=100,
        reasoning="no profile.lock exists; treating as material",
    )


__all__ = [
    "DetectionResult",
    "detect_material_change",
]

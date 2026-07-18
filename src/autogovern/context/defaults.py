"""Default context manifest values.

Standalone module with no dependencies on config_loader, so both
config_loader (vanilla mode) and wizard (init --defaults) can import it
without creating a cycle.
"""

from __future__ import annotations

from autogovern.models import (
    AutonomyLevel,
    ContextManifest,
    DataCategory,
    DeploymentContext,
    RiskAppetite,
)


def default_context() -> ContextManifest:
    """A conservative default context for vanilla mode and ``--defaults`` init.

    These are deliberately plain starting values. In vanilla mode (no init),
    docs generated against this context are generic. Running ``init``
    replaces these with organisation-specific values.
    """
    return ContextManifest(
        organisation="My Organisation",
        sector="general",
        jurisdictions=["UK"],
        deployment_context=DeploymentContext.INTERNAL,
        intended_users="internal developers",
        autonomy_level=AutonomyLevel.HUMAN_IN_THE_LOOP,
        oversight_model="human reviews agent outputs before acting on them",
        data_categories=[DataCategory.NONE],
        risk_appetite=RiskAppetite.CONSERVATIVE,
        strategy="exploring agent-assisted development",
        owner="engineering lead",
        review_cadence="quarterly",
    )


__all__ = ["default_context"]

"""The verifier agent.

A second LLM pass that checks every claim in each regenerated section against
its declared inputs and provenance, and scores the section against the
in-scope criteria of the pack's verifier rubric. Returns structured JSON:
claims (supported/unsupported, source reference, resolving input) and rubric
findings.

Unsupported claims are removed from the section by the cleaner; the gap is
written to ``ATTENTION.md`` by the ledger. Rubric findings appear in the run
manifest, never in the documents.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from autogovern.frameworks import DocumentFeed, Pack
from autogovern.provider import ProviderClient

# The prompt template version, recorded in the run manifest for traceability.
PROMPT_TEMPLATE_VERSION = "verifier-1.0.0"


class VerifierClaim(BaseModel):
    """One claim extracted from a section, with its support verdict."""

    claim: str
    supported: bool
    source_reference: str = ""
    # The init/scan input that would resolve an unsupported claim, e.g.
    # "context.oversight_model" or "profile.governance.data_categories".
    resolving_input: str = ""


class RubricFinding(BaseModel):
    """One finding from the verifier rubric for a section."""

    criterion: str
    finding: str = ""
    severity: str = ""  # pass, warning, or fail


class SectionVerification(BaseModel):
    """The verifier's structured verdict on one regenerated section."""

    section: str = ""
    claims: list[VerifierClaim] = Field(default_factory=list)
    rubric_findings: list[RubricFinding] = Field(default_factory=list)

    @property
    def unsupported_claims(self) -> list[VerifierClaim]:
        return [c for c in self.claims if not c.supported]


def verify_section(
    doc: str,
    content: str,
    feed: DocumentFeed,
    declared_inputs: dict[str, Any],
    provenance: dict[str, str],
    provider: ProviderClient,
    pack: Pack,
) -> SectionVerification:
    """Run the verifier on one section's generated content.

    The verifier receives the section content, its declared inputs, the
    provenance of those inputs, and the in-scope rubric. It returns a
    structured verdict. A failing provider call degrades gracefully: an empty
    verification (no claims, no findings) rather than aborting the run, so a
    verifier outage does not block generation.
    """
    messages = build_verify_messages(doc, content, feed, declared_inputs, provenance, pack)
    try:
        result = provider.chat_json(messages, schema=SectionVerification)
        assert isinstance(result, SectionVerification)
    except Exception:
        # Degrade gracefully: no verification is better than blocking
        # generation. The gap is invisible to the verifier but the section
        # is still generated; the run manifest records the absence.
        return SectionVerification(section=doc)
    result.section = doc
    return result


def build_verify_messages(
    doc: str,
    content: str,
    feed: DocumentFeed,
    declared_inputs: dict[str, Any],
    provenance: dict[str, str],
    pack: Pack,
) -> list[dict[str, str]]:
    """Build the chat messages for the verifier pass on one section."""
    rubric = pack.verifier_rubric
    scope_notes = "\n".join(f"- {n}" for n in pack.scope_notes) or "(none)"

    system = (
        "You are a governance documentation verifier. Check every claim in the "
        "section against the declared inputs and provenance provided. For each "
        "claim, state whether it is supported by the inputs, give the source "
        "reference if supported, and if unsupported name the init or scan input "
        "that would resolve it (e.g. context.oversight_model or "
        "profile.governance.data_categories). Also score the section against "
        "the in-scope criteria of the verifier rubric.\n\n"
        f"Verifier rubric ({rubric.ref}):\n{rubric.content}\n\n"
        f"In-scope notes:\n{scope_notes}\n"
    )

    user = (
        f"Verify the section `{doc}`.\n\n"
        f"## Section content\n\n{content}\n\n"
        f"## Declared inputs\n\n{_render_inputs(declared_inputs)}\n\n"
        f"## Provenance (source file to content hash)\n\n{_render_provenance(provenance)}\n\n"
        "Return JSON with a 'claims' list (each with claim, supported, "
        "source_reference, resolving_input) and a 'rubric_findings' list "
        "(each with criterion, finding, severity).\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _render_inputs(declared_inputs: dict[str, Any]) -> str:
    if not declared_inputs:
        return "(none)"
    return "\n".join(
        f"- {path}: {json.dumps(value, ensure_ascii=False, default=str)}"
        for path, value in declared_inputs.items()
    )


def _render_provenance(provenance: dict[str, str]) -> str:
    if not provenance:
        return "(none)"
    return "\n".join(f"- {path}: {hash_}" for path, hash_ in provenance.items())


def to_manifest_result(
    verification: SectionVerification,
) -> tuple[str, int, int, list[dict[str, Any]]]:
    """Reduce a SectionVerification to the manifest summary fields.

    Returns (section, supported_count, unsupported_count, findings) for the
    RunManifest's VerifierResult. Kept here so the manifest (Phase 12) has a
    single reduction point.
    """
    supported = sum(1 for c in verification.claims if c.supported)
    unsupported = len(verification.claims) - supported
    findings = [f.model_dump() for f in verification.rubric_findings]
    return verification.section, supported, unsupported, findings


__all__ = [
    "PROMPT_TEMPLATE_VERSION",
    "RubricFinding",
    "SectionVerification",
    "VerifierClaim",
    "build_verify_messages",
    "to_manifest_result",
    "verify_section",
]

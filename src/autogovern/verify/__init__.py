"""Verifier agent and claim cleaning.

The verifier is a second LLM pass that checks every claim in each regenerated
section against its declared inputs and provenance. Unsupported claims are
removed by the cleaner; the gap is written to ``ATTENTION.md`` by the ledger
(in :mod:`autogovern.generate.ledger`).
"""

from autogovern.verify.clean import remove_unsupported_claims
from autogovern.verify.verifier import (
    PROMPT_TEMPLATE_VERSION,
    RubricFinding,
    SectionVerification,
    VerifierClaim,
    build_verify_messages,
    to_manifest_result,
    verify_section,
)

__all__ = [
    "PROMPT_TEMPLATE_VERSION",
    "RubricFinding",
    "SectionVerification",
    "VerifierClaim",
    "build_verify_messages",
    "remove_unsupported_claims",
    "to_manifest_result",
    "verify_section",
]

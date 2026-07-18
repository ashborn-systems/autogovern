"""Verifier package.

Previously held a second-LLM-pass verifier that checked generated docs
against their inputs and queued human review work for unsupported claims.
Removed in the Phase 8 rework: the docs are generated from the scan and
match reality by construction. A post-hoc verifier that argues with itself
and routes the fallout to humans was the wrong design.

The package is kept as an empty namespace for future quality-feedback
features (e.g. prompt improvement signals), but no verifier runs during
generation.
"""

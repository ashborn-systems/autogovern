"""Claim removal: strip unsupported claims from a section's content.

The verifier returns claim text for each unsupported assertion. The cleaner
removes the lines that carry those claims, deterministically and without
another LLM call. This is the "unsupported claims are removed from the
section" step.
"""

from __future__ import annotations


def remove_unsupported_claims(content: str, unsupported_claim_texts: list[str]) -> str:
    """Remove lines containing any unsupported claim's text.

    Matching is case-insensitive substring: if a claim's text appears in a
    line, the whole line is dropped. This is deliberately conservative — a
    line carrying an unsupported claim is removed rather than edited, so no
    partial or rewritten claim survives. Blank lines around removed lines are
    collapsed so the document does not develop gaps.
    """
    if not unsupported_claim_texts:
        return content
    needles = [text.lower().strip() for text in unsupported_claim_texts if text.strip()]
    if not needles:
        return content

    kept: list[str] = []
    prev_was_blank = False
    for line in content.splitlines():
        lowered = line.lower()
        if any(needle in lowered for needle in needles):
            continue  # drop the line
        is_blank = line.strip() == ""
        if is_blank and prev_was_blank and not kept:
            continue  # trim leading blanks
        kept.append(line)
        prev_was_blank = is_blank

    # Trim trailing blank lines.
    while kept and kept[-1].strip() == "":
        kept.pop()
    return "\n".join(kept)


__all__ = ["remove_unsupported_claims"]

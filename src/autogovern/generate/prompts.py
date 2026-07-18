"""Section prompt construction.

Each section prompt receives only its declared inputs plus the pack sections
that supply it. The style authority is embedded as a fixed preamble so every
generation call is governed by the same writing rules; the verifier (Phase 8)
also checks adherence.

The preamble is exported as :data:`STYLE_PREAMBLE` so Phase 7's snapshot test
can assert the banned-constructions instruction block is present in every
generated prompt.
"""

from __future__ import annotations

import json
from typing import Any

from autogovern.frameworks import DocumentFeed, ResolvedSection

# The banned-constructions instruction block, derived from the framework
# pack's style authority. This is the snapshot target for the Phase 7 style
# check. Edit deliberately; the snapshot test will flag any drift.
STYLE_PREAMBLE = """\
You are writing governance documentation for an AI agent. Follow these \
writing rules strictly. They are enforced by a verifier pass that rejects \
non-conforming output.

- Write in plain declarative sentences.
- Use concrete thresholds and figures. State the assumption behind every number.
- Do not use em-dashes or en-dashes for parenthetical breaks. Use commas or separate sentences.
- Do not use contrastive negation ("not only ... but also", "it is not X, it is Y"). State the affirmative directly.
- Do not use significance inflation ("crucial", "vital", "essential", "game-changing", "revolutionary"). State the fact and let the reader judge.
- Do not use meta-signposting ("it is important to note", "it should be noted that", "interestingly"). Write the content directly.
- Do not avoid the copula by contortion. "The agent processes tickets" is fine; "ticket processing occurs" is not.
- Do not use rhetorical triplets ("fast, reliable, and scalable"). Use one concrete claim or a list with a stated basis.
- One consistent currency for all financial figures.
"""


def build_section_messages(
    document: str,
    feed: DocumentFeed,
    declared_inputs: dict[str, Any],
    style_authority: ResolvedSection,
) -> list[dict[str, str]]:
    """Build the chat messages for one document's generation call.

    The system message carries the style preamble plus the full style-authority
    text from the pack. The user message carries the document's pack sections
    (templates then knowledge) and the resolved declared inputs, serialised.

    Only the declared inputs are included, never the whole profile or repo,
    which is the primary token-efficiency mechanism.
    """
    system = (
        f"{STYLE_PREAMBLE}\nStyle authority ({style_authority.ref}):\n{style_authority.content}\n"
    )

    sections_text = _render_pack_sections(feed)
    inputs_text = _render_inputs(declared_inputs)

    user = (
        f"Generate the governance document `{document}`.\n\n"
        f"Pack sections (templates then knowledge):\n{sections_text}\n\n"
        f"Declared inputs (profile and context fields):\n{inputs_text}\n\n"
        f"Write the document body in Markdown. Start with a single H1 heading. "
        f"Do not include YAML frontmatter; the engine adds it. Do not wrap the "
        f"output in fences.\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _render_pack_sections(feed: DocumentFeed) -> str:
    lines: list[str] = []
    for section in feed.pack_sections:
        lines.append(f"### {section.ref} — {section.title}\n{section.content}\n")
    return "\n".join(lines) if lines else "(none)"


def _render_inputs(declared_inputs: dict[str, Any]) -> str:
    if not declared_inputs:
        return "(none)"
    lines = [
        f"- {path}: {json.dumps(value, ensure_ascii=False, default=str)}"
        for path, value in declared_inputs.items()
    ]
    return "\n".join(lines)


__all__ = ["STYLE_PREAMBLE", "build_section_messages"]

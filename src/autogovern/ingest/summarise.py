"""LLM summarisation of free-text sources into structured fields.

The scanner is deterministic wherever a file can be parsed; the LLM is used
only to turn prose (instruction files, README) into structured governance
fields that require judgement: data categories, and a description or skills
fallback when no manifest supplies them.

This module is the single LLM seam in the scanner. Everything else in
``ingest/`` is pure. A missing or failing provider leaves the summary empty
so the deterministic profile is still produced (degraded mode).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from autogovern.ingest.discovery import FileSource
from autogovern.models import AgentSkill, DataCategory
from autogovern.provider import ProviderClient

logger = logging.getLogger(__name__)

# Hard cap on free-text bytes sent to the model. Instruction files and READMEs
# are small in practice; the cap guards against pathological inputs.
_MAX_FREE_TEXT_CHARS = 16_000


class FreeTextSummary(BaseModel):
    """Structured fields the LLM derives from free text.

    All fields are optional: the builder uses them only as fallbacks when
    deterministic sources (manifest, existing card) do not supply a value.
    """

    description: str | None = None
    data_categories: list[DataCategory] = Field(default_factory=list)
    skills: list[AgentSkill] = Field(default_factory=list)


def summarise_free_text(
    instruction_files: list[FileSource],
    readme: FileSource | None,
    provider: ProviderClient | None,
) -> tuple[FreeTextSummary, FileSource | None]:
    """Summarise free-text sources via the provider.

    Args:
        instruction_files: Agent instruction files (CLAUDE.md, AGENTS.md, ...).
        readme: The project README, if present.
        provider: The provider client, or None for degraded (no-LLM) mode.

    Returns:
        A (summary, provenance_source) pair. ``provenance_source`` is the
        free-text file the summary is grounded in (the first instruction
        file, else the README), used by the builder to attach provenance to
        LLM-derived fields. Both are empty/None when no provider is available
        or no free text exists.
    """
    sources = list(instruction_files)
    if readme is not None:
        sources.append(readme)
    if not sources:
        return FreeTextSummary(), None
    provenance_source = sources[0]

    if provider is None:
        logger.debug("No provider configured; skipping free-text summarisation.")
        return FreeTextSummary(), provenance_source

    prompt = _build_prompt(instruction_files, readme)
    try:
        summary = provider.chat_json(prompt, schema=FreeTextSummary, label="scan.summarise")
    except Exception:
        # Degraded mode: a provider failure must not abort the scan. The
        # deterministic profile is still produced, with free-text fields empty.
        logger.warning("Free-text summarisation failed; producing degraded profile.")
        return FreeTextSummary(), provenance_source
    return summary, provenance_source


def _build_prompt(
    instruction_files: list[FileSource], readme: FileSource | None
) -> list[dict[str, str]]:
    """Build the chat messages asking the model to summarise the free text."""
    parts: list[str] = []
    for source in instruction_files:
        parts.append(f"## {source.rel_path}\n\n{source.content[:_MAX_FREE_TEXT_CHARS]}")
    if readme is not None:
        parts.append(f"## {readme.rel_path}\n\n{readme.content[:_MAX_FREE_TEXT_CHARS]}")
    free_text = "\n\n".join(parts)

    system = (
        "You are summarising an AI agent's source material into governance "
        "metadata. Read the instruction files and README, then return a JSON "
        "object with these fields: description (one-sentence agent purpose, or "
        "null), data_categories (list from: none, personal, special-category, "
        "financial, operational), skills (list of objects with id, name, "
        "description, tags). Infer data categories from what the agent "
        "processes. Only include fields you can ground in the text."
    )
    user = f"Agent source material:\n\n{free_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


__all__ = ["FreeTextSummary", "summarise_free_text"]

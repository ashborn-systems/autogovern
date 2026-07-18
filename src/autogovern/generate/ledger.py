"""The attention ledger (``ATTENTION.md``).

The single source of truth for anything requiring human action. Each item
carries a stable id derived from its section and resolving input, so the same
gap across runs is the same item. Items open when the verifier finds an
unsupported claim or a generation-time gap; items close when the next generate
finds the section clean.

Storage is YAML frontmatter (the structured item list, for reliable parsing)
plus a human-readable body rendered from it. An empty ledger means the
governance set is fully automated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from autogovern.generate.frontmatter import parse_frontmatter, render_document

LEDGER_FILENAME = "ATTENTION.md"


@dataclass
class AttentionEntry:
    """One item in the attention ledger."""

    item_id: str
    section: str
    detail: str
    resolving_input: str
    status: str = "open"  # "open" or "closed"
    opened: str = ""
    closed: str = ""


@dataclass
class AttentionLedger:
    """The attention ledger, read from and written to ``ATTENTION.md``."""

    entries: list[AttentionEntry] = field(default_factory=list)

    @property
    def open_entries(self) -> list[AttentionEntry]:
        return [e for e in self.entries if e.status == "open"]

    @property
    def closed_entries(self) -> list[AttentionEntry]:
        return [e for e in self.entries if e.status == "closed"]

    @classmethod
    def from_markdown(cls, text: str) -> AttentionLedger:
        """Parse an existing ATTENTION.md, or return an empty ledger."""
        if not text.strip():
            return cls()
        fm, _ = parse_frontmatter(text)
        raw_items = fm.get("items", [])
        if not isinstance(raw_items, list):
            return cls()
        entries: list[AttentionEntry] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            entries.append(
                AttentionEntry(
                    item_id=str(item.get("item_id", "")),
                    section=str(item.get("section", "")),
                    detail=str(item.get("detail", "")),
                    resolving_input=str(item.get("resolving_input", "")),
                    status=str(item.get("status", "open")),
                    opened=str(item.get("opened", "")),
                    closed=str(item.get("closed", "")),
                )
            )
        return cls(entries=entries)

    def open_item(
        self,
        *,
        section: str,
        detail: str,
        resolving_input: str,
        timestamp: str,
    ) -> AttentionEntry:
        """Open an item, or return the existing open one if the id matches.

        The id is stable across runs (derived from section + resolving_input),
        so re-opening the same gap on a subsequent generate is a no-op: the
        item stays open with its original opened timestamp.
        """
        item_id = stable_item_id(section, resolving_input)
        existing = _find(self.entries, item_id)
        if existing is not None:
            if existing.status == "open":
                return existing
            # Re-open a previously closed item.
            existing.status = "open"
            existing.opened = timestamp
            existing.closed = ""
            return existing
        entry = AttentionEntry(
            item_id=item_id,
            section=section,
            detail=detail,
            resolving_input=resolving_input,
            status="open",
            opened=timestamp,
        )
        self.entries.append(entry)
        return entry

    def close_item(self, *, section: str, resolving_input: str, timestamp: str) -> bool:
        """Close an open item matching the section + resolving_input.

        Returns True if an item was closed, False if no matching open item.
        """
        item_id = stable_item_id(section, resolving_input)
        existing = _find(self.entries, item_id)
        if existing is None or existing.status != "open":
            return False
        existing.status = "closed"
        existing.closed = timestamp
        return True

    def close_section(self, section: str, timestamp: str) -> int:
        """Close all open items for a section that was verified clean.

        Called when a regenerated section's verifier returned all-supported
        claims: every previously-open item for that section is now resolved.
        Returns the count of items closed.
        """
        count = 0
        for entry in self.entries:
            if entry.section == section and entry.status == "open":
                entry.status = "closed"
                entry.closed = timestamp
                count += 1
        return count

    def to_markdown(
        self,
        *,
        generated: str = "",
        agent_version: str = "",
        generator_version: str = "",
        framework_pack_version: str = "",
        input_hashes: dict[str, str] | None = None,
    ) -> str:
        """Render the ledger as frontmatter + human-readable body."""
        items = [
            {
                "item_id": e.item_id,
                "section": e.section,
                "detail": e.detail,
                "resolving_input": e.resolving_input,
                "status": e.status,
                "opened": e.opened,
                "closed": e.closed,
            }
            for e in self.entries
        ]
        fm: dict[str, Any] = {
            "doc_version": stable_item_id("ledger", str(len(self.open_entries))),
            "agent_version": agent_version,
            "generated": generated,
            "generator_version": generator_version,
            "input_hashes": input_hashes or {},
            "framework_pack_version": framework_pack_version,
            "section_hashes": {"ATTENTION": stable_item_id("ledger", str(len(self.entries)))},
            "items": items,
        }
        body = _render_body(self)
        return render_document(fm, body)


def stable_item_id(section: str, resolving_input: str) -> str:
    """A stable id from section + resolving_input, so the same gap persists."""
    raw = f"{section}:{resolving_input}"
    return "ATT-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _find(entries: list[AttentionEntry], item_id: str) -> AttentionEntry | None:
    for entry in entries:
        if entry.item_id == item_id:
            return entry
    return None


def _render_body(ledger: AttentionLedger) -> str:
    lines = [
        "# Attention ledger",
        "",
        "Items requiring human action. Each names the init or scan input that "
        "would resolve it. An empty ledger means the governance set is fully "
        "automated.",
        "",
    ]
    open_items = ledger.open_entries
    if open_items:
        lines.append("## Open")
        lines.append("")
        for entry in open_items:
            lines.append(_format_entry(entry))
        lines.append("")
    else:
        lines.append("## Open")
        lines.append("")
        lines.append("(none)")
        lines.append("")

    closed_items = ledger.closed_entries
    if closed_items:
        lines.append("## Closed")
        lines.append("")
        for entry in closed_items:
            lines.append(_format_entry(entry, closed=True))
        lines.append("")
    return "\n".join(lines)


def _format_entry(entry: AttentionEntry, *, closed: bool = False) -> str:
    parts = [
        f"- **[{entry.item_id}]** `{entry.section}`",
        f"— {entry.detail}.",
        f"Resolving input: `{entry.resolving_input}`.",
    ]
    if closed and entry.closed:
        parts.append(f"Resolved: {entry.closed}.")
    return " ".join(parts)


def empty_ledger_markdown(
    *,
    agent_version: str = "",
    generator_version: str = "",
    framework_pack_version: str = "",
    input_hashes: dict[str, str] | None = None,
) -> str:
    """The markdown for a ledger with no items, for first-run writes."""
    return AttentionLedger().to_markdown(
        agent_version=agent_version,
        generator_version=generator_version,
        framework_pack_version=framework_pack_version,
        input_hashes=input_hashes,
    )


__all__ = [
    "AttentionEntry",
    "AttentionLedger",
    "LEDGER_FILENAME",
    "empty_ledger_markdown",
    "stable_item_id",
]

"""Framework pack loader.

A deep module: a small public surface (``load_pack`` returning a ``Pack``
with a queryable :class:`SectionDependencyGraph`) over a pure core that
resolves ``file.md#N`` / ``file.md#slug`` references against the bundled
pack directory.

The pack is data, never code. The enterprise tier swaps the pack directory;
this loader is the only thing that reads it.

Reference syntax
----------------
- ``dir/file.md`` — the whole file. ``title`` is its H1; ``content`` is the
  full text.
- ``dir/file.md#N`` — the numbered ``## N. ...`` heading and its body, up to
  the next ``## `` heading (sub-headings ``###`` are included in the body).
- ``dir/file.md#slug`` — the heading whose slugified text matches the
  fragment. Matches on exact slug or a prefix at a word boundary, so a
  fragment truncated to the first phrase of a long heading still resolves.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Directory shipping the bundled pack. Resolved relative to this file so the
# loader works regardless of the caller's cwd.
BUNDLED_PACK_DIR = Path(__file__).resolve().parent


class PackLoadError(Exception):
    """Raised when the pack cannot be loaded or a reference is dangling."""


# ---------------------------------------------------------------------------
# Resolved section
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedSection:
    """A pack section resolved to a title and body text."""

    ref: str
    path: Path
    title: str
    content: str

    def __str__(self) -> str:
        return self.ref


# ---------------------------------------------------------------------------
# Document feed + graph
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentFeed:
    """One document's declared inputs: pack sections plus profile/context fields."""

    document: str
    templates: list[ResolvedSection]
    knowledge: list[ResolvedSection]
    profile_inputs: list[str]
    context_inputs: list[str]

    @property
    def pack_sections(self) -> list[ResolvedSection]:
        """All pack sections feeding this document, templates first."""
        return [*self.templates, *self.knowledge]

    @property
    def all_inputs(self) -> list[str]:
        return [*self.profile_inputs, *self.context_inputs]


@dataclass
class SectionDependencyGraph:
    """Document section → declared inputs, with a reverse index for queries.

    Built by :func:`load_pack` from the ``document_feeds`` mapping. The
    reverse index lets a material-change detector ask "which document
    sections depend on this profile/context field?" in constant time, with
    zero LLM calls — the primary token-efficiency mechanism's prerequisite.
    """

    # document name -> set of input paths it depends on
    forward: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # input path -> set of documents that depend on it
    reverse: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def register(self, document: str, inputs: list[str]) -> None:
        for inp in inputs:
            self.forward[document].add(inp)
            self.reverse[inp].add(document)

    def affected_documents(self, changed_input: str) -> list[str]:
        """Documents whose declared inputs include ``changed_input``.

        Returns a sorted list so output is deterministic across runs. An
        unknown input returns an empty list — an unwatched field changes
        nothing.

        Agent context fields carry a variable agent name (e.g.
        ``context.agents.support-agent.autonomy_level``). The pack declares
        these as ``context.agents.*.autonomy_level``; the match is by suffix.
        """
        docs = self.reverse.get(changed_input, set())
        if not docs and changed_input.startswith("context.agents."):
            # Match by suffix: the field name after the last segment.
            suffix = changed_input.split(".")[-1]
            wildcard = f"context.agents.*.{suffix}"
            docs = self.reverse.get(wildcard, set())
        return sorted(docs)


# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameworkEntry:
    """One framework in the pack (e.g. agentic-governance)."""

    id: str
    role: str
    files: dict[str, Path]
    scope_notes: list[str]


@dataclass(frozen=True)
class Pack:
    """The loaded, validated, reference-resolved framework pack."""

    id: str
    version: str
    pack_dir: Path
    frameworks: list[FrameworkEntry]
    style_authority: ResolvedSection
    document_feeds: dict[str, DocumentFeed]
    enterprise_hooks: dict[str, ResolvedSection]
    scope_notes: list[str]
    graph: SectionDependencyGraph


# ---------------------------------------------------------------------------
# Reference resolver (pure)
# ---------------------------------------------------------------------------

_H1 = re.compile(r"^# +(.*?)\s*$")
_H2 = re.compile(r"^## +(.+?)\s*$")
_NUMBERED_H2 = re.compile(r"^## +(\d+)\.?\s+(.+)$")


def _slugify(text: str) -> str:
    """Slugify a heading: lowercase, alnum runs joined by single hyphens."""
    # Normalise em/en dashes and punctuation to spaces before slugifying so
    # "Writing rules for all output — avoid ..." splits at the dash.
    cleaned = re.sub(r"[—–\-]", " ", text)
    words = re.findall(r"[a-z0-9]+", cleaned.lower())
    return "-".join(words)


def _split_ref(ref: str) -> tuple[str, str]:
    """Split a reference into (relative_path, fragment). Fragment is "" if none."""
    if "#" not in ref:
        return ref, ""
    path_part, fragment = ref.split("#", 1)
    return path_part, fragment


def resolve_section(ref: str, pack_dir: Path) -> ResolvedSection:
    """Resolve a single ``file.md``, ``file.md#N``, or ``file.md#slug`` ref.

    Raises:
        PackLoadError: The file is missing, or the numbered/slug heading is
            not found. The error names the exact reference.
    """
    rel_path, fragment = _split_ref(ref)
    file_path = pack_dir / rel_path
    if not file_path.is_file():
        raise PackLoadError(f"Unresolved pack reference: {ref!r} (file not found: {file_path})")
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not fragment:
        title = _extract_h1(lines, ref)
        return ResolvedSection(ref=ref, path=file_path, title=title, content=text)

    # Numbered fragment: ## N. Title
    if fragment.isdigit():
        return _resolve_numbered(ref, file_path, lines, fragment)

    # Slug fragment: match heading by slugified text.
    return _resolve_slug(ref, file_path, lines, fragment)


def _extract_h1(lines: list[str], ref: str) -> str:
    for line in lines:
        match = _H1.match(line)
        if match:
            return match.group(1)
    raise PackLoadError(f"Unresolved pack reference: {ref!r} (no H1 heading in file)")


def _resolve_numbered(
    ref: str, file_path: Path, lines: list[str], fragment: str
) -> ResolvedSection:
    start: int | None = None
    title = ""
    for i, line in enumerate(lines):
        match = _NUMBERED_H2.match(line)
        if match and match.group(1) == fragment:
            start = i
            title = match.group(2)
            break
    if start is None:
        raise PackLoadError(
            f"Unresolved pack reference: {ref!r} "
            f"(no section numbered {fragment} in {file_path.name})"
        )
    body = _section_body(lines, start)
    return ResolvedSection(ref=ref, path=file_path, title=title, content=body)


def _resolve_slug(ref: str, file_path: Path, lines: list[str], fragment: str) -> ResolvedSection:
    for i, line in enumerate(lines):
        match = _H2.match(line)
        if not match:
            continue
        heading = match.group(1)
        slug = _slugify(heading)
        if slug == fragment or slug.startswith(fragment + "-"):
            body = _section_body(lines, i)
            return ResolvedSection(ref=ref, path=file_path, title=heading, content=body)
    raise PackLoadError(
        f"Unresolved pack reference: {ref!r} "
        f"(no heading matching slug {fragment!r} in {file_path.name})"
    )


def _section_body(lines: list[str], heading_index: int) -> str:
    """Return the section body: from the heading line to the next ``## `` line.

    Sub-headings (``###``) are included; the body stops at the next sibling
    ``##`` heading or EOF. The returned content includes the heading line
    itself so callers keep the section title with its body.
    """
    body_lines = [lines[heading_index]]
    for line in lines[heading_index + 1 :]:
        if _H2.match(line):
            break
        body_lines.append(line)
    # Trim trailing blank lines for stable storage.
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()
    return "\n".join(body_lines)


# ---------------------------------------------------------------------------
# Field name → graph input mapping
# ---------------------------------------------------------------------------


def to_graph_input(field: str) -> str | None:
    """Convert a profile/context diff field name to a graph input path.

    The diff uses field names like ``governance.model_configuration``;
    the graph declares inputs like ``profile.governance.model_configuration``.
    Prompt inventory sub-fields (``.paths`` / ``.content``) collapse to the
    single graph input ``profile.governance.prompt_inventory``. Returns None
    for fields no document consumes.
    """
    if field.startswith("governance.prompt_inventory."):
        return "profile.governance.prompt_inventory"
    if field.startswith("governance.") or field in ("name", "description", "version"):
        return f"profile.{field}"
    if field.startswith("context."):
        return field
    return None


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_pack(pack_dir: Path | None = None) -> Pack:
    """Load and fully resolve the framework pack.

    Every reference in ``pack.yaml`` is resolved eagerly. A single dangling
    reference aborts the load with a :class:`PackLoadError` naming it, so the
    generation engine never sees a half-resolved pack.

    Args:
        pack_dir: Directory containing ``pack.yaml``. Defaults to the
            bundled pack shipped with the package.
    """
    root = pack_dir or BUNDLED_PACK_DIR
    pack_file = root / "pack.yaml"
    if not pack_file.is_file():
        raise PackLoadError(f"Pack index not found: {pack_file}")
    try:
        raw = yaml.safe_load(pack_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackLoadError(f"Pack index {pack_file} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackLoadError(f"Pack index {pack_file} must contain a YAML mapping at the top level")

    pack_meta = raw.get("pack", {})
    if not isinstance(pack_meta, dict):
        raise PackLoadError("pack.yaml: 'pack' block must be a mapping")

    frameworks = _load_frameworks(raw.get("frameworks", []), root)
    style_authority = _resolve_one(raw, "style_authority", root)
    enterprise_hooks = _load_enterprise_hooks(raw.get("enterprise_hooks", {}), root)
    scope_notes = _collect_scope_notes(frameworks)
    feeds, graph = _load_document_feeds(raw.get("document_feeds", {}), root)

    return Pack(
        id=str(pack_meta.get("id", "")),
        version=str(pack_meta.get("version", "")),
        pack_dir=root,
        frameworks=frameworks,
        style_authority=style_authority,
        document_feeds=feeds,
        enterprise_hooks=enterprise_hooks,
        scope_notes=scope_notes,
        graph=graph,
    )


def _load_frameworks(raw_frameworks: object, root: Path) -> list[FrameworkEntry]:
    if not isinstance(raw_frameworks, list):
        raise PackLoadError("pack.yaml: 'frameworks' must be a list")
    entries: list[FrameworkEntry] = []
    for fw in raw_frameworks:
        if not isinstance(fw, dict):
            raise PackLoadError("pack.yaml: each framework entry must be a mapping")
        files_raw = fw.get("files", {})
        if not isinstance(files_raw, dict):
            raise PackLoadError(f"pack.yaml: framework {fw.get('id')!r} 'files' must be a mapping")
        files: dict[str, Path] = {}
        for role, rel in files_raw.items():
            path = root / rel
            if not path.is_file():
                raise PackLoadError(f"Framework {fw.get('id')!r} references missing file: {rel!r}")
            files[str(role)] = path
        notes = [str(n) for n in fw.get("scope_notes", []) if isinstance(n, str)]
        entries.append(
            FrameworkEntry(
                id=str(fw.get("id", "")),
                role=str(fw.get("role", "")),
                files=files,
                scope_notes=notes,
            )
        )
    return entries


def _resolve_one(raw: dict[str, object], key: str, root: Path) -> ResolvedSection:
    value = raw.get(key)
    if not isinstance(value, str):
        raise PackLoadError(f"pack.yaml: {key!r} must be a reference string")
    return resolve_section(value, root)


def _load_enterprise_hooks(raw_hooks: object, root: Path) -> dict[str, ResolvedSection]:
    if not isinstance(raw_hooks, dict):
        raise PackLoadError("pack.yaml: 'enterprise_hooks' must be a mapping")
    hooks: dict[str, ResolvedSection] = {}
    for name, ref in raw_hooks.items():
        if not isinstance(ref, str):
            raise PackLoadError(f"pack.yaml: enterprise hook {name!r} must be a reference string")
        hooks[str(name)] = resolve_section(ref, root)
    return hooks


def _collect_scope_notes(frameworks: list[FrameworkEntry]) -> list[str]:
    notes: list[str] = []
    for fw in frameworks:
        notes.extend(fw.scope_notes)
    return notes


def _load_document_feeds(
    raw_feeds: object, root: Path
) -> tuple[dict[str, DocumentFeed], SectionDependencyGraph]:
    if not isinstance(raw_feeds, dict):
        raise PackLoadError("pack.yaml: 'document_feeds' must be a mapping")
    feeds: dict[str, DocumentFeed] = {}
    graph = SectionDependencyGraph()
    for doc_name, feed_raw in raw_feeds.items():
        if not isinstance(feed_raw, dict):
            raise PackLoadError(f"pack.yaml: document feed {doc_name!r} must be a mapping")
        templates = [resolve_section(r, root) for r in feed_raw.get("templates", []) or []]
        knowledge = [resolve_section(r, root) for r in feed_raw.get("knowledge", []) or []]
        profile_inputs = [str(x) for x in feed_raw.get("profile_inputs", []) or []]
        context_inputs = [str(x) for x in feed_raw.get("context_inputs", []) or []]
        feeds[str(doc_name)] = DocumentFeed(
            document=str(doc_name),
            templates=templates,
            knowledge=knowledge,
            profile_inputs=profile_inputs,
            context_inputs=context_inputs,
        )
        graph.register(str(doc_name), [*profile_inputs, *context_inputs])
    return feeds, graph


__all__ = [
    "BUNDLED_PACK_DIR",
    "DocumentFeed",
    "FrameworkEntry",
    "Pack",
    "PackLoadError",
    "ResolvedSection",
    "SectionDependencyGraph",
    "load_pack",
    "resolve_section",
    "to_graph_input",
]

"""Deterministic source-file discovery for the scanner.

Two-phase by design: signal files (cheap, specific globs) are found first so
the scanner can bail out before touching any source code when a repo has no
agent signals. Source files (.py/.ts/.js) are only read when signals exist,
which keeps ``scan`` fast on large non-agent repos and satisfies the
performance acceptance criterion.

Discovery globs are internal defaults, separate from ``Config.watched_paths``
(which drives Phase 9 change detection). Watched paths answer "what changed
matters?"; discovery globs answer "what does the scanner read?". They overlap
but are not identical — discovery needs prompt and source globs the change
set does not. Later phases may expose these in the config reference.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from autogovern.models import Config

# Directories never descended into. Keeps discovery off vendored, build, and
# tool-owned paths, including the tool's own governance/ output and .autogovern
# config directory.
_IGNORED_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".git",
        ".autogovern",
        "governance",
        ".ruff_cache",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
        "__pypackages__",
        ".tox",
    }
)

# Discovery globs. Strong signals (instruction files, MCP configs, agent
# cards) are searched recursively so agents in subdirectories are found.
# Manifests and READMEs are per-agent-root, found within each root.
_INSTRUCTION_GLOBS = (
    "CLAUDE.md",
    "AGENTS.md",
    "agent.md",
    "**/CLAUDE.md",
    "**/AGENTS.md",
    "**/agent.md",
    ".claude/**/*.md",
    "**/.claude/**/*.md",
)
_README_GLOBS = ("README.md", "README.rst")
_MCP_GLOBS = (".mcp.json", "mcp.json", "**/.mcp.json", "**/mcp.json")
_MANIFEST_GLOBS = ("pyproject.toml", "package.json", "requirements.txt")
# Recursive variants used by the single-pass multi-agent discovery; files
# are bucketed per agent root after one glob.
_README_GLOBS_RECURSIVE = ("README.md", "README.rst", "**/README.md", "**/README.rst")
_MANIFEST_GLOBS_RECURSIVE = (
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "**/pyproject.toml",
    "**/package.json",
    "**/requirements.txt",
)
_PROMPT_GLOBS = (
    "prompts/**/*.md",
    "prompts/**/*.txt",
    "**/prompts/**/*.md",
    "**/prompts/**/*.txt",
)
_CARD_GLOBS = (".well-known/agent.json", "**/.well-known/agent.json")
_SOURCE_GLOBS = ("**/*.py", "**/*.ts", "**/*.js")


@dataclass(frozen=True)
class FileSource:
    """A discovered file's path, contents, and content hash."""

    rel_path: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class DiscoveredSignals:
    """The signal-bearing files found in a repo.

    These are the files whose mere presence (or absence) determines whether
    the repo is an agent at all. ``has_agent_signals`` is the scanner's
    early-exit gate.
    """

    instruction_files: list[FileSource] = field(default_factory=list)
    readme: FileSource | None = None
    mcp_configs: list[FileSource] = field(default_factory=list)
    manifests: list[FileSource] = field(default_factory=list)
    prompt_files: list[FileSource] = field(default_factory=list)
    agent_card: FileSource | None = None

    @property
    def has_agent_signals(self) -> bool:
        """True if the repo shows any agent-specific signal.

        A manifest alone is not a signal (every Python project has one). The
        signal is an instruction file, an MCP config, a prompt file, or an
        existing agent card.
        """
        return bool(
            self.instruction_files
            or self.mcp_configs
            or self.prompt_files
            or self.agent_card is not None
        )


@dataclass(frozen=True)
class DiscoveredSources:
    """Everything the scanner found: signals plus source code.

    ``source_files`` is populated only when ``signals.has_agent_signals`` is
    true, so non-agent repos pay nothing for source scanning.
    """

    signals: DiscoveredSignals
    source_files: list[FileSource] = field(default_factory=list)


@dataclass(frozen=True)
class AgentDiscovery:
    """One agent's discovery result: its root directory plus all its files.

    An agent root is a directory containing a strong signal (instruction
    file, MCP config, or existing agent card). Prompt files and source files
    attach to the nearest enclosing agent root.

    ``root`` is relative to the project root: ``"."`` for a root-level agent,
    ``"billing-agent"`` for one in a subdirectory.
    """

    root: str
    signals: DiscoveredSignals
    source_files: list[FileSource] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent keys: the single canonical naming scheme
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Slugify a name for use as a directory or manifest key."""
    return name.lower().replace(" ", "-").replace("/", "-").strip(".")


def agent_key(root: str, profile_name: str) -> str:
    """The canonical filing key for an agent.

    One shared rule, used by the engine (governance directory names), the
    context manifest (``agents:`` keys), the wizard, and check — so answers
    and documents always land where the engine looks.

    - Root agent (``root == "."``): the profile name (from its project file
      or agent card), or ``default`` when no name is discoverable.
    - Nested agent: its root path joined with hyphens (``agents/billing`` →
      ``agents-billing``). Filesystem paths are unique by construction, so
      collisions between nested agents are impossible.

    The pretty profile name remains the display name everywhere humans read;
    the key is plumbing (directories, manifest keys), never presentation.
    """
    if root == ".":
        slug = slugify(profile_name)
        return slug if slug and slug != "unknown" else "default"
    return slugify(root.replace("/", "-"))


def dedupe_keys(keys: list[str]) -> list[str]:
    """Disambiguate duplicated keys by appending ``-2``, ``-3``, ... in order.

    A collision is only possible between the root agent's profile-name key
    and a nested agent whose path happens to slugify to the same string.
    Resolution is deterministic (first agent, in sorted root order, keeps
    the bare key) and automatic — the user is never asked.
    """
    counts: dict[str, int] = {}
    out: list[str] = []
    for key in keys:
        if key in counts:
            counts[key] += 1
            out.append(f"{key}-{counts[key]}")
        else:
            counts[key] = 1
            out.append(key)
    return out


def discover_signals(root: Path, config: Config | None = None) -> DiscoveredSignals:
    """Find all signal-bearing files under ``root``.

    Args:
        root: The repository root to scan.
        config: Reserved for future per-config discovery overrides. The
            default globs are used regardless, for now.

    Returns:
        A :class:`DiscoveredSignals` with every category sorted by path for
        deterministic ordering.
    """
    _ = config  # reserved for future config-driven globs
    return DiscoveredSignals(
        instruction_files=_discover_globs(root, _INSTRUCTION_GLOBS),
        readme=_first(_discover_globs(root, _README_GLOBS)),
        mcp_configs=_discover_globs(root, _MCP_GLOBS),
        manifests=_discover_globs(root, _MANIFEST_GLOBS),
        prompt_files=_discover_globs(root, _PROMPT_GLOBS),
        agent_card=_first(_discover_globs(root, _CARD_GLOBS)),
    )


def discover_source_files(root: Path) -> list[FileSource]:
    """Find all source files under ``root`` for model/env-var scanning.

    Only called when the repo has agent signals, so this broad glob never
    runs against a plain non-agent project.
    """
    return _discover_globs(root, _SOURCE_GLOBS)


def discover_agents(root: Path, config: Config | None = None) -> list[AgentDiscovery]:
    """Discover all agents in a repo by finding strong signals recursively.

    An agent root is a directory containing at least one strong signal: an
    instruction file, an MCP config, or an existing agent card. Prompt files
    and source files attach to the nearest enclosing agent root.

    Returns one :class:`AgentDiscovery` per agent root. The repo root itself
    is an agent root if it has strong signals. A non-agent repo returns an
    empty list — no ``None``, no special case.

    Every glob set is applied exactly once per call (single pass): files are
    read and hashed once, then bucketed per agent root. Nothing is cached
    across calls, so re-scanning a repo in the same process always sees the
    current filesystem.
    """
    _ = config  # reserved for future config-driven globs

    # Strong signals first: they define the agent roots.
    instruction_files = _discover_globs(root, _INSTRUCTION_GLOBS)
    mcp_configs = _discover_globs(root, _MCP_GLOBS)
    agent_cards = _discover_globs(root, _CARD_GLOBS)
    strong_dirs = _strong_signal_dirs(root, instruction_files, mcp_configs, agent_cards)

    agent_root_dirs: set[Path] = set()
    for source in [*instruction_files, *mcp_configs, *agent_cards]:
        agent_root_dirs.add(_agent_root_for(root, Path(source.rel_path), strong_dirs))

    if not agent_root_dirs:
        return []

    # Single pass over the remaining categories; bucketed per root below.
    prompt_files = _discover_globs(root, _PROMPT_GLOBS)
    source_files = _discover_globs(root, _SOURCE_GLOBS)
    readmes = _discover_globs(root, _README_GLOBS_RECURSIVE)
    manifests = _discover_globs(root, _MANIFEST_GLOBS_RECURSIVE)

    discoveries: list[AgentDiscovery] = []
    for agent_root in sorted(agent_root_dirs):
        rel_root = _rel_path(root, agent_root) if agent_root != root else "."

        def attached(s: FileSource, _agent_root: Path = agent_root) -> bool:
            return _agent_root_for(root, Path(s.rel_path), strong_dirs) == _agent_root

        # READMEs and manifests attach only when they sit directly in the
        # agent root (they describe the project at that directory, not a
        # package nested beneath it).
        agent_readmes = [s for s in readmes if (root / s.rel_path).parent == agent_root]
        agent_manifests = [s for s in manifests if (root / s.rel_path).parent == agent_root]

        signals = DiscoveredSignals(
            instruction_files=[s for s in instruction_files if attached(s)],
            readme=_first(agent_readmes),
            mcp_configs=[s for s in mcp_configs if attached(s)],
            manifests=agent_manifests,
            prompt_files=[s for s in prompt_files if attached(s)],
            agent_card=_first([s for s in agent_cards if attached(s)]),
        )
        discoveries.append(
            AgentDiscovery(
                root=rel_root,
                signals=signals,
                source_files=[s for s in source_files if attached(s)],
            )
        )
    return discoveries


def _agent_root_for(root: Path, file_rel: Path, strong_dirs: frozenset[Path]) -> Path:
    """The nearest enclosing agent root for a file.

    Walks up from the file's directory to the repo root. The first directory
    that contains a strong signal (instruction file, MCP config, or agent card)
    is the agent root. Files in a non-agent repo map to the repo root, but
    this function is only called when agent roots exist.
    """
    current = (root / file_rel).parent
    while current >= root:
        if current in strong_dirs:
            return current
        if current == root:
            return root if root in strong_dirs else current
        current = current.parent
    return root


def _strong_signal_dirs(
    root: Path,
    instruction_files: list[FileSource],
    mcp_configs: list[FileSource],
    agent_cards: list[FileSource],
) -> frozenset[Path]:
    """The set of directories that directly contain a strong signal.

    Agent card files (``.well-known/agent.json``) are metadata, not agent
    roots. Their parent directory (``.well-known/``) must not be treated as
    an agent root — the card belongs to the agent root above it.

    Computed fresh on every scan from the already-globbed sources: no cache,
    so a long-lived process re-scanning a repo always sees the current
    filesystem.
    """
    dirs: set[Path] = set()
    for source in [*instruction_files, *mcp_configs]:
        dirs.add((root / Path(source.rel_path)).parent)
    # Card files contribute their parent's parent (the agent root), not
    # the .well-known directory itself.
    for source in agent_cards:
        card_parent = (root / Path(source.rel_path)).parent
        dirs.add(card_parent.parent)
    return frozenset(dirs)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _discover_globs(root: Path, patterns: tuple[str, ...]) -> list[FileSource]:
    """Apply ``patterns`` under ``root``, dedupe, sort, and read each file."""
    seen: set[str] = set()
    sources: list[FileSource] = []
    for pattern in patterns:
        for path in _glob(root, pattern):
            rel = _rel_path(root, path)
            if rel in seen:
                continue
            seen.add(rel)
            source = _read_source(path, rel)
            if source is not None:
                sources.append(source)
    sources.sort(key=lambda s: s.rel_path)
    return sources


def _glob(root: Path, pattern: str) -> list[Path]:
    """Glob ``pattern`` under ``root``, filtering ignored directories."""
    results: list[Path] = []
    for path in root.glob(pattern):
        if _is_ignored(path.relative_to(root)):
            continue
        if path.is_file():
            results.append(path)
    return results


def _is_ignored(rel: Path) -> bool:
    """True if any path component is an ignored directory."""
    return any(part in _IGNORED_DIRS for part in rel.parts)


def _read_source(path: Path, rel_path: str) -> FileSource | None:
    """Read a file as UTF-8 text and compute its sha256 hash.

    Returns None for unreadable or non-text files so a single broken file
    never aborts a scan.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return FileSource(rel_path=rel_path, content=content, content_hash=content_hash)


def _rel_path(root: Path, path: Path) -> str:
    """Posix-form relative path from ``root`` to ``path``."""
    return path.relative_to(root).as_posix()


def _first(sources: list[FileSource]) -> FileSource | None:
    """Return the first source, or None. Lists are pre-sorted by path."""
    return sources[0] if sources else None


__all__ = [
    "AgentDiscovery",
    "DiscoveredSignals",
    "DiscoveredSources",
    "FileSource",
    "agent_key",
    "dedupe_keys",
    "discover_agents",
    "discover_signals",
    "discover_source_files",
    "slugify",
]

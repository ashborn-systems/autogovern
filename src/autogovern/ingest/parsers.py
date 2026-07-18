"""Pure parsing of discovered source files into typed records.

No I/O, no LLM. Each parser takes :class:`~autogovern.ingest.discovery.FileSource`
objects (already read and hashed by discovery) and extracts structured
records. Determinism is guaranteed by sorting every input and output.

The records are the deterministic half of the AgentProfile; the LLM
summariser (``summarise.py``) supplies only the free-text-derived fields.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field

from autogovern.ingest.discovery import DiscoveredSources, FileSource

# ---------------------------------------------------------------------------
# Dependency → provider mapping
# ---------------------------------------------------------------------------

# Python dependency names that imply a model provider.
_PROVIDER_PY_DEPS = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google-generativeai": "google",
    "google-genai": "google",
    "ollama": "ollama",
}

# npm package names that imply a model provider.
_PROVIDER_NPM_DEPS = {
    "openai": "openai",
    "@anthropic-ai/sdk": "anthropic",
    "@google/generative-ai": "google",
}

# Source-level provider imports: ``from <pkg> import ...``.
_PROVIDER_IMPORT_RE = re.compile(r"from\s+(anthropic|openai|google\.generativeai|ollama)\s+import")

# ---------------------------------------------------------------------------
# Model configuration patterns
# ---------------------------------------------------------------------------

# An explicit assignment to a model-like variable: ``model = "claude-..."``.
# The word boundary prevents matching the ``model`` inside ``some_model``.
_MODEL_ASSIGN_RE = re.compile(r"""\bmodel\s*[:=]\s*["']([A-Za-z0-9][\w.\-]*)["']""", re.IGNORECASE)

# A known model-name prefix appearing anywhere: ``claude-3-5-sonnet``.
# The whole match is captured in group 1 so callers get the full name.
_MODEL_PREFIX_RE = re.compile(
    r"""\b((?:claude|gpt|gemini|o[1-4]|llama|mistral|deepseek|qwen|command-r)-[\w.\-]+)"""
)

_TEMPERATURE_RE = re.compile(r"""\btemperature\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)""", re.IGNORECASE)
_API_BASE_RE = re.compile(r"""\bapi_base\s*[:=]\s*["'](https?://[^"']+)["']""", re.IGNORECASE)

# Environment variable references: ``os.environ["X"]``, ``os.environ.get("X")``,
# ``os.getenv("X")``.
_ENV_RE = re.compile(r"""os\.environ(?:\.get)?\s*[\[(]\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
_GETENV_RE = re.compile(r"""os\.getenv\s*\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")

# Dependency requirement line: ``name>=1.0``, ``name==2``, ``name``.
_REQUIREMENT_RE = re.compile(
    r"""^([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(?:[<>=!~]=?\s*[A-Za-z0-9.*]+)?\s*(?:#.*)?$"""
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolRecord:
    """An MCP tool discovered in a config."""

    name: str
    description: str
    source: FileSource


@dataclass(frozen=True)
class DependencyRecord:
    """A runtime or build dependency from a manifest."""

    name: str
    version: str | None
    manifest: str  # relative path of the manifest file


@dataclass(frozen=True)
class ModelConfigRecord:
    """Model configuration signals extracted from source and manifests."""

    provider: str | None
    model: str | None
    temperature: float | None
    api_base: str | None
    source: FileSource  # the file that primarily yielded these signals


@dataclass(frozen=True)
class EnvVarRecord:
    """An environment variable referenced in source code."""

    name: str
    source: FileSource


@dataclass(frozen=True)
class ProjectMeta:
    """Project-level metadata from the manifest (name, version, description)."""

    name: str | None = None
    version: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ParsedRecords:
    """The deterministic, fully-parsed view of an agent repo."""

    tools: list[ToolRecord] = field(default_factory=list)
    dependencies: list[DependencyRecord] = field(default_factory=list)
    model_config: ModelConfigRecord | None = None
    env_vars: list[EnvVarRecord] = field(default_factory=list)
    project_meta: ProjectMeta = field(default_factory=ProjectMeta)


def parse(discovered: DiscoveredSources) -> ParsedRecords:
    """Parse all discovered sources into deterministic records.

    Order of operations is fixed so output is deterministic for a given input.
    """
    tools = _parse_tools(discovered.signals.mcp_configs)
    dependencies = _parse_dependencies(discovered.signals.manifests)
    env_vars = _scan_env_vars(discovered.source_files)
    model_config = _scan_model_config(discovered.source_files, dependencies)
    project_meta = _parse_project_meta(discovered.signals.manifests)
    return ParsedRecords(
        tools=tools,
        dependencies=dependencies,
        model_config=model_config,
        env_vars=env_vars,
        project_meta=project_meta,
    )


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


def _parse_tools(mcp_configs: list[FileSource]) -> list[ToolRecord]:
    """Extract every tool across all MCP server configs."""
    tools: list[ToolRecord] = []
    for config in mcp_configs:
        try:
            data = json.loads(config.content)
        except json.JSONDecodeError:
            continue
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            continue
        for server_name in sorted(servers):
            server = servers[server_name]
            if not isinstance(server, dict):
                continue
            for tool in server.get("tools", []):
                if not isinstance(tool, dict):
                    continue
                name = tool.get("name")
                if not isinstance(name, str) or not name:
                    continue
                description = tool.get("description", "")
                if not isinstance(description, str):
                    description = ""
                tools.append(ToolRecord(name=name, description=description, source=config))
    return tools


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _parse_dependencies(manifests: list[FileSource]) -> list[DependencyRecord]:
    """Parse dependency manifests in priority order: pyproject, package, requirements."""
    deps: list[DependencyRecord] = []
    seen: set[str] = set()
    for manifest in sorted(manifests, key=lambda m: _manifest_priority(m.rel_path)):
        for name, version in _deps_from_manifest(manifest):
            key = f"{name}@{manifest.rel_path}"
            if key in seen:
                continue
            seen.add(key)
            deps.append(DependencyRecord(name=name, version=version, manifest=manifest.rel_path))
    return deps


def _manifest_priority(rel_path: str) -> int:
    """Sort key so pyproject precedes package.json precedes requirements.txt."""
    if rel_path.endswith("pyproject.toml"):
        return 0
    if rel_path.endswith("package.json"):
        return 1
    return 2


def _deps_from_manifest(manifest: FileSource) -> list[tuple[str, str | None]]:
    """Yield (name, version) pairs from a single manifest."""
    if manifest.rel_path.endswith("pyproject.toml"):
        return _deps_from_pyproject(manifest.content)
    if manifest.rel_path.endswith("package.json"):
        return _deps_from_package_json(manifest.content)
    if manifest.rel_path.endswith("requirements.txt"):
        return _deps_from_requirements(manifest.content)
    return []


def _deps_from_pyproject(content: str) -> list[tuple[str, str | None]]:
    """Parse [project.dependencies] and optional-dependencies from pyproject.toml."""
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project")
    if not isinstance(project, dict):
        return []
    deps: list[tuple[str, str | None]] = []
    for req in project.get("dependencies", []):
        if isinstance(req, str):
            parsed = _parse_requirement(req)
            if parsed is not None:
                deps.append(parsed)
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in sorted(optional):
            for req in optional[group]:
                if isinstance(req, str):
                    parsed = _parse_requirement(req)
                    if parsed is not None:
                        deps.append(parsed)
    return deps


def _deps_from_package_json(content: str) -> list[tuple[str, str | None]]:
    """Parse dependencies and devDependencies from package.json."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    deps: list[tuple[str, str | None]] = []
    if not isinstance(data, dict):
        return deps
    for section in ("dependencies", "devDependencies"):
        section_deps = data.get(section)
        if isinstance(section_deps, dict):
            for name in sorted(section_deps):
                version = section_deps[name]
                deps.append((name, version if isinstance(version, str) else None))
    return deps


def _deps_from_requirements(content: str) -> list[tuple[str, str | None]]:
    """Parse a requirements.txt file."""
    deps: list[tuple[str, str | None]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_requirement(line)
        if parsed is not None:
            deps.append(parsed)
    return deps


def _parse_requirement(req: str) -> tuple[str, str | None] | None:
    """Split a PEP 508-ish requirement into (name, version) or None."""
    match = _REQUIREMENT_RE.match(req)
    if match is None:
        return None
    name = match.group(1)
    version_match = re.search(r"[<>=!~]=?\s*([A-Za-z0-9.*]+)", req[len(name) :])
    version = version_match.group(1) if version_match else None
    return (name, version)


def provider_from_dependencies(deps: list[DependencyRecord]) -> str | None:
    """Return the model provider implied by a dependency, if any.

    Public so the builder can corroborate source-level provider signals with
    the declared manifest dependency.
    """
    for dep in deps:
        mapped = _PROVIDER_PY_DEPS.get(dep.name.lower()) or _PROVIDER_NPM_DEPS.get(dep.name)
        if mapped:
            return mapped
    return None


# ---------------------------------------------------------------------------
# Model configuration and env vars (source scanning)
# ---------------------------------------------------------------------------


def _scan_model_config(
    source_files: list[FileSource], deps: list[DependencyRecord]
) -> ModelConfigRecord | None:
    """Scan source files for model name, temperature, api_base, and provider."""
    model: str | None = None
    model_source: FileSource | None = None
    temperature: float | None = None
    api_base: str | None = None
    provider_import: str | None = None
    provider_source: FileSource | None = None

    for src in source_files:  # already sorted by path
        if model is None:
            match = _MODEL_ASSIGN_RE.search(src.content)
            if match is None:
                match = _MODEL_PREFIX_RE.search(src.content)
            if match is not None:
                model = match.group(1)
                model_source = src
        if temperature is None:
            temp_match = _TEMPERATURE_RE.search(src.content)
            if temp_match is not None:
                temperature = float(temp_match.group(1))
        if api_base is None:
            base_match = _API_BASE_RE.search(src.content)
            if base_match is not None:
                api_base = base_match.group(1)
        if provider_import is None:
            import_match = _PROVIDER_IMPORT_RE.search(src.content)
            if import_match is not None:
                provider_import = import_match.group(1)
                provider_source = src

    provider = provider_import or provider_from_dependencies(deps)

    # The source file that primarily yielded the signals: prefer the file
    # where the model name was found, then the provider import file. If no
    # source file matched (e.g. provider inferred only from a manifest dep),
    # return None and let the builder supply a fallback with manifest
    # provenance. The common case — model name and provider import in the
    # same source file — yields a single, honest source.
    source = model_source or provider_source
    if source is None:
        return None

    return ModelConfigRecord(
        provider=provider,
        model=model,
        temperature=temperature,
        api_base=api_base,
        source=source,
    )


def _scan_env_vars(source_files: list[FileSource]) -> list[EnvVarRecord]:
    """Find all environment variable references in source files."""
    seen: set[str] = set()
    records: list[EnvVarRecord] = []
    for src in source_files:  # already sorted by path
        names: list[str] = []
        names.extend(_ENV_RE.findall(src.content))
        names.extend(_GETENV_RE.findall(src.content))
        for name in sorted(set(names)):
            if name in seen:
                continue
            seen.add(name)
            records.append(EnvVarRecord(name=name, source=src))
    return records


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------


def _parse_project_meta(manifests: list[FileSource]) -> ProjectMeta:
    """Extract project name, version, and description from the first manifest."""
    for manifest in sorted(manifests, key=lambda m: _manifest_priority(m.rel_path)):
        meta = _meta_from_manifest(manifest)
        if meta.name or meta.version or meta.description:
            return meta
    return ProjectMeta()


def _meta_from_manifest(manifest: FileSource) -> ProjectMeta:
    if manifest.rel_path.endswith("pyproject.toml"):
        return _meta_from_pyproject(manifest.content)
    if manifest.rel_path.endswith("package.json"):
        return _meta_from_package_json(manifest.content)
    return ProjectMeta()


def _meta_from_pyproject(content: str) -> ProjectMeta:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return ProjectMeta()
    project = data.get("project")
    if not isinstance(project, dict):
        return ProjectMeta()
    name = project.get("name")
    version = project.get("version")
    description = project.get("description")
    return ProjectMeta(
        name=name if isinstance(name, str) else None,
        version=version if isinstance(version, str) else None,
        description=description if isinstance(description, str) else None,
    )


def _meta_from_package_json(content: str) -> ProjectMeta:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return ProjectMeta()
    if not isinstance(data, dict):
        return ProjectMeta()
    name = data.get("name")
    version = data.get("version")
    description = data.get("description")
    return ProjectMeta(
        name=name if isinstance(name, str) else None,
        version=version if isinstance(version, str) else None,
        description=description if isinstance(description, str) else None,
    )


__all__ = [
    "DependencyRecord",
    "EnvVarRecord",
    "ModelConfigRecord",
    "ParsedRecords",
    "ProjectMeta",
    "ToolRecord",
    "parse",
    "provider_from_dependencies",
]

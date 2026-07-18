"""Unit tests for the deterministic parsing core (ingest.parsers).

These lock down the pure functions that turn discovered files into records,
independent of discovery and the LLM. Determinism is the contract.
"""

from __future__ import annotations

import json

from autogovern.ingest.discovery import DiscoveredSignals, DiscoveredSources, FileSource
from autogovern.ingest.parsers import (
    parse,
    provider_from_dependencies,
)


def _source(rel_path: str, content: str) -> FileSource:
    return FileSource(rel_path=rel_path, content=content, content_hash="h:" + rel_path)


def _sources(*sources: FileSource) -> DiscoveredSources:
    return DiscoveredSources(signals=DiscoveredSignals(), source_files=list(sources))


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


def test_parse_mcp_tools_both_extracted() -> None:
    """Both tools in an MCP config are extracted, sorted by server then name."""
    mcp = _source(
        ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "ticketing": {
                        "tools": [
                            {"name": "fetch_ticket", "description": "Fetch a ticket by ID."},
                            {"name": "assign_ticket", "description": "Assign a ticket."},
                        ]
                    }
                }
            }
        ),
    )
    discovered = DiscoveredSources(signals=DiscoveredSignals(mcp_configs=[mcp]))
    records = parse(discovered)
    assert [t.name for t in records.tools] == ["fetch_ticket", "assign_ticket"]
    assert records.tools[0].description == "Fetch a ticket by ID."


def test_parse_mcp_invalid_json_skipped() -> None:
    """A malformed MCP config is skipped, not fatal."""
    mcp = _source(".mcp.json", "{not json")
    discovered = DiscoveredSources(signals=DiscoveredSignals(mcp_configs=[mcp]))
    assert parse(discovered).tools == []


def test_parse_mcp_multiple_servers_sorted() -> None:
    """Tools across servers are gathered deterministically (server-sorted)."""
    mcp = _source(
        ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "zeta": {"tools": [{"name": "z_tool", "description": "z"}]},
                    "alpha": {"tools": [{"name": "a_tool", "description": "a"}]},
                }
            }
        ),
    )
    discovered = DiscoveredSources(signals=DiscoveredSignals(mcp_configs=[mcp]))
    records = parse(discovered)
    # alpha server precedes zeta.
    assert [t.name for t in records.tools] == ["a_tool", "z_tool"]


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def test_parse_pyproject_dependencies() -> None:
    pyproject = _source(
        "pyproject.toml",
        """
[project]
name = "demo"
version = "1.2.3"
description = "A demo agent."
dependencies = ["anthropic>=0.40.0", "httpx>=0.28.0"]
""",
    )
    discovered = DiscoveredSources(signals=DiscoveredSignals(manifests=[pyproject]))
    records = parse(discovered)
    deps = {d.name: d.version for d in records.dependencies}
    assert deps == {"anthropic": "0.40.0", "httpx": "0.28.0"}
    assert records.project_meta.name == "demo"
    assert records.project_meta.version == "1.2.3"
    assert records.project_meta.description == "A demo agent."


def test_parse_requirements_txt() -> None:
    req = _source(
        "requirements.txt",
        "anthropic>=0.40.0\n# a comment\nopenai==1.0\nrequests\n",
    )
    discovered = DiscoveredSources(signals=DiscoveredSignals(manifests=[req]))
    records = parse(discovered)
    deps = {d.name: d.version for d in records.dependencies}
    assert deps == {"anthropic": "0.40.0", "openai": "1.0", "requests": None}


def test_parse_package_json_dependencies() -> None:
    pkg = _source(
        "package.json",
        json.dumps(
            {
                "name": "js-agent",
                "version": "0.1.0",
                "dependencies": {"openai": "^4.0.0"},
                "devDependencies": {"@anthropic-ai/sdk": "0.20.0"},
            }
        ),
    )
    discovered = DiscoveredSources(signals=DiscoveredSignals(manifests=[pkg]))
    records = parse(discovered)
    deps = {d.name: d.version for d in records.dependencies}
    assert deps == {"@anthropic-ai/sdk": "0.20.0", "openai": "^4.0.0"}
    assert records.project_meta.name == "js-agent"


# ---------------------------------------------------------------------------
# Model configuration and env vars
# ---------------------------------------------------------------------------


def test_scan_model_config_from_source() -> None:
    """Model name, temperature, and provider import are scanned from source."""
    src = _source(
        "src/agent.py",
        'from anthropic import Anthropic\nMODEL = "claude-3-5-sonnet"\nTEMPERATURE = 0.0\n',
    )
    discovered = _sources(src)
    records = parse(discovered)
    mc = records.model_config
    assert mc is not None
    assert mc.model == "claude-3-5-sonnet"
    assert mc.provider == "anthropic"
    assert mc.temperature == 0.0
    assert mc.source.rel_path == "src/agent.py"


def test_scan_model_config_prefix_fallback() -> None:
    """A known model-name prefix is found without an explicit assignment."""
    src = _source("src/agent.py", "# This agent uses claude-3-haiku for inference.\n")
    # No `model = "..."` assignment, so the prefix regex supplies the name.
    discovered = _sources(src)
    records = parse(discovered)
    assert records.model_config is not None
    assert records.model_config.model == "claude-3-haiku"


def test_scan_env_vars() -> None:
    """os.environ and os.getenv references are both found."""
    src = _source(
        "src/agent.py",
        'key = os.environ["ANTHROPIC_API_KEY"]\nregion = os.getenv("AWS_REGION")\n',
    )
    discovered = _sources(src)
    records = parse(discovered)
    assert {e.name for e in records.env_vars} == {"ANTHROPIC_API_KEY", "AWS_REGION"}


def test_scan_env_vars_deduped() -> None:
    """The same env var referenced twice appears once."""
    src = _source("src/agent.py", 'os.environ["X"]\nos.getenv("X")\n')
    discovered = _sources(src)
    records = parse(discovered)
    assert [e.name for e in records.env_vars] == ["X"]


def test_provider_from_dependencies() -> None:
    """provider_from_dependencies maps known deps to provider names."""
    from autogovern.ingest.parsers import DependencyRecord

    deps = [DependencyRecord(name="anthropic", version="0.40.0", manifest="pyproject.toml")]
    assert provider_from_dependencies(deps) == "anthropic"

    deps = [DependencyRecord(name="openai", version=None, manifest="package.json")]
    assert provider_from_dependencies(deps) == "openai"

    deps = [DependencyRecord(name="numpy", version=None, manifest="pyproject.toml")]
    assert provider_from_dependencies(deps) is None


def test_model_config_none_when_no_signal() -> None:
    """No model or provider signal yields None (builder falls back)."""
    src = _source("src/util.py", "def add(a, b):\n    return a + b\n")
    discovered = _sources(src)
    records = parse(discovered)
    assert records.model_config is None


# ---------------------------------------------------------------------------
# Discovery determinism (sorting + ignore)
# ---------------------------------------------------------------------------


def test_discovery_ignores_venv_and_governance(tmp_path) -> None:
    """Ignored directories are never descended into."""
    from autogovern.ingest.discovery import discover_signals

    (tmp_path / "CLAUDE.md").write_text("# agent")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "CLAUDE.md").write_text("# imposter")
    (tmp_path / "governance").mkdir()
    (tmp_path / "governance" / "CLAUDE.md").write_text("# output")

    signals = discover_signals(tmp_path)
    paths = [s.rel_path for s in signals.instruction_files]
    assert paths == ["CLAUDE.md"]


def test_discovery_signals_sorted(tmp_path) -> None:
    """Instruction files are sorted by relative path for determinism."""
    from autogovern.ingest.discovery import discover_signals

    (tmp_path / "AGENTS.md").write_text("agents")
    (tmp_path / "CLAUDE.md").write_text("claude")
    signals = discover_signals(tmp_path)
    assert [s.rel_path for s in signals.instruction_files] == ["AGENTS.md", "CLAUDE.md"]


def test_has_agent_signals_false_for_plain(tmp_path) -> None:
    """A repo with only a manifest has no agent signals."""
    from autogovern.ingest.discovery import discover_signals

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    signals = discover_signals(tmp_path)
    assert signals.has_agent_signals is False


def test_has_agent_signals_true_for_instruction_file(tmp_path) -> None:
    """A CLAUDE.md alone is an agent signal."""
    from autogovern.ingest.discovery import discover_signals

    (tmp_path / "CLAUDE.md").write_text("# agent")
    signals = discover_signals(tmp_path)
    assert signals.has_agent_signals is True

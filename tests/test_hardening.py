"""Regression tests for the hardening pass (bug-fix batch).

One test per fixed bug, named after the behaviour it locks in. See
docs/BUILDLOG.md for the pass that introduced them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.check import run_check
from autogovern.cli import app
from autogovern.context import default_context
from autogovern.detect import detect_material_change
from autogovern.detect.heuristic import heuristic_pass
from autogovern.generate import generate_docs
from autogovern.ingest import (
    dedupe_keys,
    discover_agent_identities,
    discover_agents,
    scan_repo,
)
from autogovern.models import DEFAULT_WATCHED_PATHS, AgentContext, ContextManifest
from tests.conftest import FIXTURES, make_mock_provider, make_smart_mock_provider, mock_config

runner = CliRunner()

FIXTURE_BASIC = FIXTURES / "fixture-basic"
FIXTURE_MULTI = FIXTURES / "fixture-multi"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    subprocess.run(["git", "init", "-q"], cwd=r)
    return r


@pytest.fixture
def key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test")


def _generate(repo: Path, provider) -> None:
    config = mock_config()
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    generate_docs(repo, config, scan, default_context(), provider=provider)


# ---------------------------------------------------------------------------
# Clean check makes zero LLM calls (lock summary reuse)
# ---------------------------------------------------------------------------


def test_clean_check_makes_zero_llm_calls(repo: Path, key_env: None) -> None:
    config = mock_config()
    provider = make_mock_provider(config)
    _generate(repo, provider)
    calls_after_generate = len(provider.call_log)
    assert calls_after_generate > 0  # generate did call the LLM

    result = run_check(repo, config, default_context(), provider=provider)
    assert result.exit_code == 0
    assert len(provider.call_log) == calls_after_generate, (
        f"check made {len(provider.call_log) - calls_after_generate} LLM call(s) on a clean repo"
    )
    provider.close()


def test_changed_free_text_triggers_one_call(repo: Path, key_env: None) -> None:
    config = mock_config()
    provider = make_mock_provider(config)
    _generate(repo, provider)
    calls_after_generate = len(provider.call_log)

    (repo / "CLAUDE.md").write_text("Completely rewritten instructions for the agent.\n")

    run_check(repo, config, default_context(), provider=provider)
    assert len(provider.call_log) > calls_after_generate
    provider.close()


# ---------------------------------------------------------------------------
# Corrupt lockfiles never crash check
# ---------------------------------------------------------------------------


def test_corrupt_profile_lock_does_not_crash_check(repo: Path, key_env: None) -> None:
    config = mock_config()
    provider = make_mock_provider(config)
    _generate(repo, provider)

    lock = repo / "governance" / "support-triage-agent" / "profile.lock"
    lock.write_text("this: is-not-a-valid-profile-lock\n")

    result = run_check(repo, config, default_context(), provider=provider)
    assert result is not None  # no exception; treated as no lockfile
    provider.close()


def test_corrupt_context_lock_does_not_crash_check(repo: Path, key_env: None) -> None:
    config = mock_config()
    provider = make_mock_provider(config)
    _generate(repo, provider)

    lock = repo / "governance" / "support-triage-agent" / "context.lock"
    lock.write_text("- just\n- a\n- list\n")

    result = run_check(repo, config, default_context(), provider=provider)
    assert result is not None
    provider.close()


# ---------------------------------------------------------------------------
# Unresolved profile diffs route to the semantic scorer (never silent 0)
# ---------------------------------------------------------------------------


def test_description_change_semantic_verdict(repo: Path, key_env: None) -> None:
    """End-to-end: description edit produces a scored (non-zero) result via check."""
    from autogovern.generate.lockfile import read_lockfile

    config = mock_config()
    provider = make_smart_mock_provider(config)
    _generate(repo, provider)

    locked = read_lockfile(repo / "governance" / "support-triage-agent")
    assert locked is not None

    pyproj = repo / "pyproject.toml"
    pyproj.write_text(pyproj.read_text().replace('description = "', 'description = "CHANGED '))

    scan = scan_repo(repo, config, provider=provider, write_card=False)
    detection = detect_material_change(
        [],
        config,
        locked_profile=locked,
        current_profile=scan.agents[0].profile,
        provider=provider,
        ci_mode=True,
    )
    assert detection.materiality is not None
    # The smart mock scores 10: immaterial, but deliberately scored — not 0.
    assert detection.materiality.score == 10
    assert any("description" in fd.field for fd in detection.profile_diff.fields)
    provider.close()


# ---------------------------------------------------------------------------
# Heuristic pass matches nested agent files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "agents/billing-agent/CLAUDE.md",
        "agents/billing-agent/AGENTS.md",
        "agents/x/.mcp.json",
        "agents/x/prompts/system.md",
        "agents/x/.well-known/agent.json",
        "agents/x/pyproject.toml",
        "CLAUDE.md",
        "prompts/system.md",
    ],
)
def test_heuristic_matches_nested_and_root(path: str) -> None:
    assert heuristic_pass([path], DEFAULT_WATCHED_PATHS).matched, path


@pytest.mark.parametrize(
    "path",
    [
        "src/agent.py",
        "docs/guide.md",
        "my-prompts/system.md",
        "CLAUDE.md.bak",
        "tests/test_agent.py",
    ],
)
def test_heuristic_ignores_unwatched(path: str) -> None:
    assert not heuristic_pass([path], DEFAULT_WATCHED_PATHS).matched, path


# ---------------------------------------------------------------------------
# Agent keys: canonical, unique, automatic
# ---------------------------------------------------------------------------


def test_dedupe_keys_appends_counters() -> None:
    assert dedupe_keys(["a", "b", "a", "a"]) == ["a", "b", "a-2", "a-3"]


def test_discover_agent_identities_keys_by_path(tmp_path: Path) -> None:
    repo = tmp_path / "multi"
    shutil.copytree(FIXTURE_MULTI, repo)
    identities = dict(discover_agent_identities(repo))
    assert identities == {
        "agents-billing-agent": "billing-agent",
        "agents-support-agent": "support-agent",
    }


def test_rescan_in_same_process_sees_new_agents(tmp_path: Path) -> None:
    """No filesystem caching: a second scan in one process sees new agent roots."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "CLAUDE.md").write_text("agent one")
    assert len(discover_agents(root)) == 1

    sub = root / "agents" / "billing"
    sub.mkdir(parents=True)
    (sub / "CLAUDE.md").write_text("agent two")
    roots = {a.root for a in discover_agents(root)}
    assert roots == {".", "agents/billing"}


# ---------------------------------------------------------------------------
# check --fix in multi-agent repos keeps the project docs complete
# ---------------------------------------------------------------------------


def test_check_fix_multi_agent_keeps_full_register(tmp_path: Path, key_env: None) -> None:
    repo = tmp_path / "multi"
    shutil.copytree(FIXTURE_MULTI, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo)

    config = mock_config()
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    generate_docs(repo, config, scan, default_context(), provider=provider)

    # Make both agents stale: add a tool to each .mcp.json.
    for mcp in repo.glob("agents/*/.mcp.json"):
        data = json.loads(mcp.read_text())
        server = next(iter(data["mcpServers"].values()))
        server.setdefault("tools", []).append({"name": "new_tool", "description": "x"})
        mcp.write_text(json.dumps(data, indent=2))

    result = run_check(repo, config, default_context(), provider=provider, fix=True)
    assert result.exit_code == 0
    provider.close()

    register = (repo / "governance" / "REGISTER.md").read_text()
    assert "billing-agent" in register
    assert "support-agent" in register
    # Both agents' docs directories still exist with lockfiles.
    assert (repo / "governance" / "agents-billing-agent" / "profile.lock").is_file()
    assert (repo / "governance" / "agents-support-agent" / "profile.lock").is_file()


# ---------------------------------------------------------------------------
# Run manifests record normalisation and field-level regeneration reasons
# ---------------------------------------------------------------------------


def test_generate_manifest_records_normalisation(repo: Path, key_env: None, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    manifests = sorted((repo / ".autogovern" / "runs").glob("generate_*.json"))
    assert manifests
    data = json.loads(manifests[-1].read_text())
    assert data["normalisation"] is not None
    assert data["normalisation"]["used_llm"] is False  # canonical defaults


def test_regeneration_reasons_name_changed_fields(repo: Path, key_env: None) -> None:
    config = mock_config()
    provider = make_mock_provider(config)
    _generate(repo, provider)

    mcp = json.loads((repo / ".mcp.json").read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append({"name": "close_ticket", "description": "x"})
    (repo / ".mcp.json").write_text(json.dumps(mcp, indent=2))

    scan = scan_repo(repo, config, provider=provider, write_card=False)
    result = generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    reasons = result.regeneration_reasons
    assert reasons
    assert any("profile.governance.permissions_surface" in r for r in reasons.values()), reasons


# ---------------------------------------------------------------------------
# Check verdict shows per-criterion reasoning
# ---------------------------------------------------------------------------


def test_check_verdict_shows_criteria(repo: Path, key_env: None, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    runner.invoke(app, ["generate", str(repo)])

    mcp = json.loads((repo / ".mcp.json").read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append({"name": "close_ticket", "description": "x"})
    (repo / ".mcp.json").write_text(json.dumps(mcp, indent=2))

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1
    assert "new tool" in result.output.lower()


# ---------------------------------------------------------------------------
# Missing API key exits cleanly (no traceback)
# ---------------------------------------------------------------------------


def test_missing_api_key_exits_cleanly(repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_DEFINITELY_UNSET_KEY")
    monkeypatch.delenv("AUTOGOVERN_DEFINITELY_UNSET_KEY", raising=False)
    # Use the real provider builder (not the mock) so the key lookup happens.
    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "AUTOGOVERN_DEFINITELY_UNSET_KEY" in result.output


# ---------------------------------------------------------------------------
# QUICKSTART is written even when every LLM document is disabled
# ---------------------------------------------------------------------------


def test_quickstart_written_when_all_llm_docs_disabled(repo: Path, key_env: None) -> None:
    config = mock_config()
    for key in list(config.documents):
        if key not in ("quickstart", "attention"):
            config.documents[key] = False

    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    assert (repo / "governance" / "QUICKSTART.md").is_file()
    assert (repo / "governance" / "ATTENTION.md").is_file()


# ---------------------------------------------------------------------------
# Status view: honest lockfile reporting
# ---------------------------------------------------------------------------


def test_status_view_reports_lockfiles_honestly(repo: Path, key_env: None, monkeypatch) -> None:
    from autogovern.tui.status import print_status

    provider = make_mock_provider(mock_config())
    _generate(repo, provider)
    provider.close()

    monkeypatch.chdir(repo)
    from autogovern.tui.console import get_console

    with get_console().capture() as capture:
        print_status(repo)
    out = capture.get()
    assert "not written" not in out
    assert "matches working tree" not in out  # the old unverified claim is gone
    assert "1 agent(s)" in out


# ---------------------------------------------------------------------------
# Wizard context keys match the engine's lookup keys
# ---------------------------------------------------------------------------


def test_wizard_agent_context_keys_match_engine(tmp_path: Path) -> None:
    """discover_agent_identities keys are exactly what generate looks up."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    identities = discover_agent_identities(repo)
    assert identities == [("support-triage-agent", "support-triage-agent")]


def test_engine_uses_wizard_keyed_context(repo: Path, key_env: None) -> None:
    """A context keyed by the agent key actually reaches the generated docs."""
    config = mock_config()
    context = ContextManifest(
        project=default_context().project,
        agents={
            "support-triage-agent": AgentContext(
                autonomy_level="fully-autonomous",
                oversight_model="no human in the loop",
            )
        },
    )
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    generate_docs(repo, config, scan, context, provider=provider)
    provider.close()

    context_lock = yaml.safe_load(
        (repo / "governance" / "support-triage-agent" / "context.lock").read_text()
    )
    assert context_lock["agents"]["support-triage-agent"]["autonomy_level"] == "fully-autonomous"


# ---------------------------------------------------------------------------
# Real-world MCP config shapes yield a non-empty permissions surface
# ---------------------------------------------------------------------------


def test_mcp_server_without_inline_tools_still_recorded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("agent")
    (repo / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                        "env": {"FS_API_KEY": "secret"},
                    }
                }
            }
        )
    )
    config = mock_config()
    provider = make_mock_provider(config)
    result = scan_repo(repo, config, provider=provider, write_card=False)
    provider.close()

    perms = result.agents[0].profile.governance.permissions_surface.value
    kinds = {(p.kind, p.detail.split(" — ")[0]) for p in perms}
    assert ("tool", "filesystem") in kinds  # server-level entry
    assert ("env", "FS_API_KEY") in kinds  # server env key surfaced
    # The secret VALUE must never appear anywhere in the profile.
    assert "secret" not in result.agents[0].profile.model_dump_json()

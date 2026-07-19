"""Multi-agent discovery, generation, and check tests.

Proves the core design: a repo with two agents in subdirectories is scanned
as two agents, each gets its own doc set, and check works per-agent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.ingest import scan_repo
from autogovern.models import (
    ContextManifest,
    ProjectContext,
)
from tests.conftest import FIXTURES, make_mock_provider, mock_config

runner = CliRunner()

FIXTURE_MULTI = FIXTURES / "fixture-multi"


@pytest.fixture
def multi_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copy fixture-multi into a temp dir for isolation."""
    import shutil

    repo = tmp_path / "multi-repo"
    shutil.copytree(FIXTURE_MULTI, repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test")
    return repo


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_multi_agent_discovers_two_agents(multi_repo: Path) -> None:
    """scan_repo finds both agents in the subdirectories."""
    config = mock_config()
    provider = make_mock_provider(config)
    try:
        result = scan_repo(multi_repo, config, provider=provider, write_card=False)
        assert len(result.agents) == 2
        names = {a.name for a in result.agents}
        assert "billing-agent" in names
        assert "support-agent" in names
    finally:
        provider.close()


def test_multi_agent_roots_are_subdirectories(multi_repo: Path) -> None:
    """Each agent's root is its subdirectory, not the repo root."""
    config = mock_config()
    provider = make_mock_provider(config)
    try:
        result = scan_repo(multi_repo, config, provider=provider, write_card=False)
        roots = {a.root for a in result.agents}
        assert all(r != "." for r in roots)
        assert "agents/billing-agent" in roots or any("billing" in r for r in roots)
    finally:
        provider.close()


# ---------------------------------------------------------------------------
# CLI scan
# ---------------------------------------------------------------------------


def test_cli_multi_agent_scan_json(multi_repo: Path) -> None:
    """scan --json returns an agents array with two entries."""
    result = runner.invoke(app, ["scan", str(multi_repo), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["signals_found"] is True
    assert len(data["agents"]) == 2


def test_cli_multi_agent_scan_human(multi_repo: Path) -> None:
    """scan human output names both agents."""
    result = runner.invoke(app, ["scan", str(multi_repo)])
    assert result.exit_code == 0, result.output
    assert "billing-agent" in result.output
    assert "support-agent" in result.output


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def test_multi_agent_generate_creates_per_agent_dirs(multi_repo: Path) -> None:
    """generate writes docs into governance/<slug>/ per agent."""
    config = mock_config()
    context = ContextManifest(
        project=ProjectContext(organisation="Test Org", sector="tech"),
        agents={},
    )
    provider = make_mock_provider(config)
    try:
        scan_result = scan_repo(multi_repo, config, provider=provider, write_card=False)
        from autogovern.generate import generate_docs

        generate_docs(multi_repo, config, scan_result, context, provider=provider)
    finally:
        provider.close()

    gov = multi_repo / "governance"
    assert (gov / "REGISTER.md").is_file()
    # Nested agents key by their root path: agents/billing-agent -> agents-billing-agent.
    assert (gov / "agents-billing-agent" / "system-card.md").is_file()
    assert (gov / "agents-support-agent" / "system-card.md").is_file()
    assert (gov / "agents-billing-agent" / "profile.lock").is_file()
    assert (gov / "agents-support-agent" / "profile.lock").is_file()


def test_multi_agent_register_lists_both_agents(multi_repo: Path) -> None:
    """REGISTER.md contains both agent names."""
    config = mock_config()
    context = ContextManifest(
        project=ProjectContext(organisation="Test Org", sector="tech"),
        agents={},
    )
    provider = make_mock_provider(config)
    try:
        scan_result = scan_repo(multi_repo, config, provider=provider, write_card=False)
        from autogovern.generate import generate_docs

        generate_docs(multi_repo, config, scan_result, context, provider=provider)
    finally:
        provider.close()

    register = (multi_repo / "governance" / "REGISTER.md").read_text()
    assert "billing-agent" in register
    assert "support-agent" in register


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


def test_multi_agent_check_current_after_generate(multi_repo: Path) -> None:
    """check after generate returns current (exit 0) across both agents."""
    from autogovern.api import check as check_api

    config = mock_config()
    context = ContextManifest(
        project=ProjectContext(organisation="Test Org", sector="tech"),
        agents={},
    )
    provider = make_mock_provider(config)
    try:
        scan_result = scan_repo(multi_repo, config, provider=provider, write_card=False)
        from autogovern.generate import generate_docs

        generate_docs(multi_repo, config, scan_result, context, provider=provider)

        check_result = check_api(multi_repo, config, context, provider=provider, fix=False)
        assert check_result.exit_code == 0
    finally:
        provider.close()

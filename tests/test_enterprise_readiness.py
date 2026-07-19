"""Tests for the enterprise-readiness batch.

- Atomic generate: a mid-run provider failure leaves zero partial writes.
- Headless stdin: ``--profile -`` reads the profile JSON from stdin.
- Per-agent verdicts: multi-agent check reports every agent in one run.
- Custom framework packs: config-driven, validated at load time.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.frameworks import PackLoadError, load_pack
from autogovern.generate import generate_docs
from autogovern.ingest import scan_repo
from autogovern.models import Config, ModelProviderConfig
from autogovern.provider import ProviderResponseError
from tests.conftest import FIXTURES, make_failing_mock_provider, make_mock_provider, mock_config

runner = CliRunner()

FIXTURE_BASIC = FIXTURES / "fixture-basic"
FIXTURE_MULTI = FIXTURES / "fixture-multi"
FIXTURE_PROFILE = FIXTURES / "fixture-profile.json"
PACK_CUSTOM = FIXTURES / "pack-custom"
PACK_BROKEN = FIXTURES / "pack-broken"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    subprocess.run(["git", "init", "-q"], cwd=r)
    return r


@pytest.fixture
def key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test")


# ---------------------------------------------------------------------------
# Atomic generate: no partial writes on provider failure
# ---------------------------------------------------------------------------


def test_failed_generate_writes_nothing(repo: Path, key_env: None) -> None:
    """Provider dies on the 3rd call: governance/ must not exist afterwards."""
    config = mock_config()
    provider = make_failing_mock_provider(config, fail_after=2)

    scan = scan_repo(repo, config, provider=provider, write_card=False)
    with pytest.raises(ProviderResponseError):
        generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    governance = repo / "governance"
    leftover = list(governance.rglob("*")) if governance.exists() else []
    assert leftover == [], f"partial writes left behind: {leftover}"


def test_failed_regenerate_leaves_previous_state_intact(repo: Path, key_env: None) -> None:
    """A failed second run must not touch the docs written by the first."""
    config = mock_config()
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    before = {
        str(p.relative_to(repo)): p.read_bytes()
        for p in (repo / "governance").rglob("*")
        if p.is_file()
    }
    assert before

    # Make something stale so the second run has work to do, then fail it.
    mcp = json.loads((repo / ".mcp.json").read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append({"name": "close_ticket", "description": "x"})
    (repo / ".mcp.json").write_text(json.dumps(mcp, indent=2))

    failing = make_failing_mock_provider(config, fail_after=1)
    scan2 = scan_repo(repo, config, provider=failing, write_card=False)
    with pytest.raises(ProviderResponseError):
        generate_docs(repo, config, scan2, default_context(), provider=failing)
    failing.close()

    after = {
        str(p.relative_to(repo)): p.read_bytes()
        for p in (repo / "governance").rglob("*")
        if p.is_file()
    }
    assert after == before


def test_successful_generate_commits_everything(repo: Path, key_env: None) -> None:
    """The batch commit still writes the complete document set."""
    config = mock_config()
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    result = generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    agent_gov = repo / "governance" / "support-triage-agent"
    assert (agent_gov / "system-card.md").is_file()
    assert (agent_gov / "profile.lock").is_file()
    assert (agent_gov / "context.lock").is_file()
    assert (repo / "governance" / "REGISTER.md").is_file()
    assert result.written_files  # commit reported what it wrote


# ---------------------------------------------------------------------------
# Headless stdin profile input
# ---------------------------------------------------------------------------


def test_check_profile_from_stdin(repo: Path, key_env: None, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    profile_json = FIXTURE_PROFILE.read_text()
    result = runner.invoke(app, ["check", "--json", "--profile", "-"], input=profile_json)
    assert result.exit_code in (0, 1)  # a verdict, not a usage error
    verdict = json.loads(result.output)
    assert "current" in verdict


def test_generate_profile_from_stdin(repo: Path, key_env: None, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    profile_json = FIXTURE_PROFILE.read_text()
    result = runner.invoke(app, ["generate", "--json", "--profile", "-"], input=profile_json)
    assert result.exit_code == 0, result.output
    assert (repo / "governance").is_dir()


def test_profile_stdin_invalid_json_exits_cleanly(repo: Path, key_env: None, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")

    result = runner.invoke(app, ["check", "--profile", "-"], input="not json at all")
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "stdin" in result.output.lower()


# ---------------------------------------------------------------------------
# Per-agent verdicts on multi-agent checks
# ---------------------------------------------------------------------------


def _write_multi_init(repo: Path) -> None:
    (repo / ".autogovern").mkdir(exist_ok=True)
    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock-provider.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    (repo / ".autogovern" / "config.yaml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
    )
    (repo / ".autogovern" / "context.yaml").write_text(
        yaml.safe_dump(default_context().model_dump(mode="json"), sort_keys=False)
    )


def test_multi_agent_check_reports_each_agent(tmp_path: Path, key_env, monkeypatch) -> None:
    repo = tmp_path / "multi"
    shutil.copytree(FIXTURE_MULTI, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo)
    _write_multi_init(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock-provider.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    # Make ONLY the billing agent stale.
    mcp_path = repo / "agents" / "billing-agent" / ".mcp.json"
    data = json.loads(mcp_path.read_text())
    server = next(iter(data["mcpServers"].values()))
    server.setdefault("tools", []).append({"name": "refund", "description": "x"})
    mcp_path.write_text(json.dumps(data, indent=2))

    check = runner.invoke(app, ["check", str(repo), "--json"])
    assert check.exit_code == 1
    verdict = json.loads(check.output)
    agents = {a["key"]: a for a in verdict["agents"]}
    assert set(agents) == {"agents-billing-agent", "agents-support-agent"}
    assert agents["agents-billing-agent"]["current"] is False
    assert agents["agents-billing-agent"]["score"] >= 80
    assert agents["agents-support-agent"]["current"] is True

    # Human output names both agents, so the stale one is never hidden.
    check_human = runner.invoke(app, ["check", str(repo)])
    assert "billing-agent" in check_human.output
    assert "support-agent" in check_human.output


# ---------------------------------------------------------------------------
# Custom framework packs
# ---------------------------------------------------------------------------


def test_bundled_pack_passes_validation() -> None:
    pack = load_pack()
    assert pack.id and pack.version


def test_custom_pack_generates_docs(repo: Path, key_env: None) -> None:
    config = mock_config().model_copy(update={"framework_pack": str(PACK_CUSTOM)})
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    result = generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()

    assert (repo / "governance" / "support-triage-agent" / "system-card.md").is_file()
    assert result.pack_version == "9.9.9"
    # The pack version flows into the document frontmatter.
    text = (repo / "governance" / "support-triage-agent" / "system-card.md").read_text()
    assert "framework_pack_version: 9.9.9" in text


def test_custom_pack_via_config_file(repo: Path, key_env: None, monkeypatch) -> None:
    """End-to-end: framework_pack in config.yaml drives the CLI."""
    monkeypatch.chdir(repo)
    (repo / ".autogovern").mkdir(exist_ok=True)
    (repo / ".autogovern" / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model_provider": {
                    "api_base": "https://mock-provider.example.com/v1",
                    "model": "mock-model",
                    "api_key_env": "AUTOGOVERN_TEST_KEY",
                },
                "framework_pack": str(PACK_CUSTOM),
            }
        )
    )
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))
    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output
    text = (repo / "governance" / "support-triage-agent" / "system-card.md").read_text()
    assert "framework_pack_version: 9.9.9" in text


def test_broken_pack_fails_at_load_with_named_input() -> None:
    with pytest.raises(PackLoadError) as excinfo:
        load_pack(PACK_BROKEN)
    message = str(excinfo.value)
    assert "system-card.md" in message
    assert "profile.governance.nonexistent_field" in message


def test_broken_pack_fails_before_any_llm_call(repo: Path, key_env: None) -> None:
    """A broken custom pack aborts the run before the provider is touched."""
    config = mock_config().model_copy(update={"framework_pack": str(PACK_BROKEN)})
    provider = make_mock_provider(config)
    scan = scan_repo(repo, config, provider=provider, write_card=False)
    calls_before = len(provider.call_log)
    with pytest.raises(PackLoadError):
        generate_docs(repo, config, scan, default_context(), provider=provider)
    provider.close()
    assert len(provider.call_log) == calls_before

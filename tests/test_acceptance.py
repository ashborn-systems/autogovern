"""Phase 13: acceptance criteria — one test per criterion.

All seven acceptance criteria from SPEC.md, each mapped to a named test.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.models import Config, ModelProviderConfig

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    import subprocess

    subprocess.run(["git", "init"], cwd=r, capture_output=True)
    return r


@pytest.fixture
def config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test")


def _write_init(repo: Path) -> None:
    (repo / ".autogovern").mkdir(exist_ok=True)
    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
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


def _mock_provider_factory(config):
    from tests.conftest import make_mock_provider

    return make_mock_provider(config)


# ---------------------------------------------------------------------------
# Criterion 1: init + generate produces the full document set
# ---------------------------------------------------------------------------


def test_criterion_1_init_generate_full_set(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init + generate produces the full document set, AgentCard, frontmatter, manifest."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    gov = repo / "governance"
    agent_gov = gov / "support-triage-agent"
    expected_project = {
        "QUICKSTART.md",
        "ATTENTION.md",
        "REGISTER.md",
        "CHANGELOG.md",
    }
    expected_agent = {
        "system-card.md",
        "risk-assessment.md",
        "data-protection.md",
        "oversight.md",
        "inventory.md",
        "testing.md",
        "incident-response.md",
        "profile.lock",
        "context.lock",
    }
    actual_project = {f.name for f in gov.iterdir() if f.is_file()}
    actual_agent = {f.name for f in agent_gov.iterdir() if f.is_file()}
    assert expected_project <= actual_project
    assert expected_agent <= actual_agent

    # AgentCard was written (generate scans with card writing enabled).
    assert (repo / ".well-known" / "agent.json").is_file()

    # Every doc has frontmatter.
    for doc in gov.iterdir():
        if doc.name in ("profile.lock", "context.lock") or not doc.is_file():
            continue
        assert doc.read_text().startswith("---"), f"{doc.name} missing frontmatter"
    for doc in agent_gov.iterdir():
        if doc.name in ("profile.lock", "context.lock") or not doc.is_file():
            continue
        assert doc.read_text().startswith("---"), f"{doc.name} missing frontmatter"

    # Run manifest exists.
    manifests = list((repo / ".autogovern" / "runs").glob("*.json"))
    assert len(manifests) >= 1


# ---------------------------------------------------------------------------
# Criterion 2: check fails on material change, --fix regenerates
# ---------------------------------------------------------------------------


def test_criterion_2_check_fix_cycle(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    # Edit tool definition.
    mcp = json.loads((repo / ".mcp.json").read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append(
        {"name": "close_ticket", "description": "Close a ticket."}
    )
    (repo / ".mcp.json").write_text(json.dumps(mcp, indent=2))

    # check exits 1 with materiality, stale sections, remediation.
    check_result = runner.invoke(app, ["check", str(repo)])
    assert check_result.exit_code == 1
    assert "stale" in check_result.output.lower()
    assert "materiality" in check_result.output.lower()

    # check --fix regenerates.
    fix_result = runner.invoke(app, ["check", str(repo), "--fix"])
    assert fix_result.exit_code == 0

    # Subsequent check exits 0.
    final = runner.invoke(app, ["check", str(repo)])
    assert final.exit_code == 0
    assert "current" in final.output.lower()


# ---------------------------------------------------------------------------
# Criterion 3: unwatched file → check exits 0, no LLM
# ---------------------------------------------------------------------------


def test_criterion_3_unwatched_file_no_impact(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    # Edit an unwatched file (README).
    readme = repo / "README.md"
    readme.write_text(readme.read_text() + "\n\nNew content.\n")

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 0
    assert "current" in result.output.lower()


# ---------------------------------------------------------------------------
# Criterion 4: two consecutive generates produce zero diff
# ---------------------------------------------------------------------------


def test_criterion_4_idempotent_generate(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    snapshot = {
        str(f.relative_to(repo / "governance")): f.read_text()
        for f in (repo / "governance").rglob("*")
        if f.is_file()
    }

    runner.invoke(app, ["generate", str(repo)])

    for name, content in snapshot.items():
        assert (repo / "governance" / name).read_text() == content, f"{name} changed"


# ---------------------------------------------------------------------------
# Criterion 5: pre-commit hook < 500ms, never blocks
# ---------------------------------------------------------------------------


def test_criterion_5_pre_commit_hook_fast_and_nonblocking(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installed hook prints an impact flag in <500ms and never blocks."""
    import subprocess
    import time

    from autogovern.hooks import install_pre_commit_hook

    install_pre_commit_hook(repo)
    hook = repo / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111  # executable

    # Stage a watched file: the hook prints the impact flag, exit 0, fast.
    (repo / "CLAUDE.md").write_text("edited\n")
    subprocess.run(["git", "add", "CLAUDE.md"], cwd=repo, capture_output=True)
    start = time.monotonic()
    proc = subprocess.run([str(hook)], cwd=repo, capture_output=True, text=True, timeout=10)
    elapsed = (time.monotonic() - start) * 1000
    assert proc.returncode == 0
    assert "governance impact: yes" in proc.stdout
    assert "CLAUDE.md" in proc.stdout
    assert elapsed < 500, f"hook took {elapsed:.0f}ms"

    # Nothing staged: impact no, still exit 0 (never blocks).
    subprocess.run(["git", "reset", "-q"], cwd=repo, capture_output=True)
    proc2 = subprocess.run([str(hook)], cwd=repo, capture_output=True, text=True, timeout=10)
    assert proc2.returncode == 0
    assert "governance impact: no" in proc2.stdout


# ---------------------------------------------------------------------------
# Criterion 6: vanilla mode works without init
# ---------------------------------------------------------------------------


def test_criterion_6_vanilla_mode(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate runs without init (vanilla mode): env vars, generic context, docs produced."""
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    # No .autogovern/ directory at all.
    assert not (repo / ".autogovern").exists()

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output
    assert (repo / "governance" / "support-triage-agent" / "system-card.md").is_file()
    assert "without a context manifest" in result.output.lower()

    # With init, docs are specific.
    _write_init(repo)
    result2 = runner.invoke(app, ["generate", str(repo)])
    assert result2.exit_code == 0, result2.output
    assert "without a context manifest" not in result2.output.lower()


# ---------------------------------------------------------------------------
# Criterion 7: GitHub Action in check --fix mode
# ---------------------------------------------------------------------------


def test_criterion_7_github_action_exists() -> None:
    """The GitHub Action wraps check and generate for CI."""
    action_dir = Path(__file__).resolve().parent.parent / "action"
    assert action_dir.is_dir(), "action/ directory missing"
    action_yml = action_dir / "action.yml"
    assert action_yml.is_file(), "action/action.yml missing"
    data = yaml.safe_load(action_yml.read_text())
    assert "name" in data
    assert "runs" in data
    # The action runs check or generate.
    steps = data.get("runs", {}).get("steps", [])
    assert any("autogovern" in str(s.get("run", "")) for s in steps)


# ---------------------------------------------------------------------------
# E2E: full journey
# ---------------------------------------------------------------------------


def test_e2e_full_journey(repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """init --defaults then generate, idempotent, edit, check fails, fix, check passes."""
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_provider)

    # init --defaults.
    init_result = runner.invoke(app, ["init", "--defaults"])
    assert init_result.exit_code == 0, init_result.output

    # generate.
    gen_result = runner.invoke(app, ["generate", str(repo)])
    assert gen_result.exit_code == 0, gen_result.output

    # idempotent regenerate.
    gen2 = runner.invoke(app, ["generate", str(repo)])
    assert gen2.exit_code == 0
    assert "nothing regenerated" in gen2.output.lower()

    # material edit.
    src = repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))

    # check fails.
    check_fail = runner.invoke(app, ["check", str(repo)])
    assert check_fail.exit_code == 1

    # check --fix.
    check_fix = runner.invoke(app, ["check", str(repo), "--fix"])
    assert check_fix.exit_code == 0

    # check passes.
    check_pass = runner.invoke(app, ["check", str(repo)])
    assert check_pass.exit_code == 0

    # manifest and changelog inspected.
    manifests = list((repo / ".autogovern" / "runs").glob("*.json"))
    assert len(manifests) >= 3  # generate + check + check --fix
    changelog = (repo / "governance" / "CHANGELOG.md").read_text()
    assert "regenerated" in changelog.lower()


def _mock_provider_provider(config):
    from tests.conftest import make_mock_provider

    return make_mock_provider(config)

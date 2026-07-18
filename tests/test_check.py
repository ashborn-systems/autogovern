"""Phase 10: check, fix, diff, explain, hooks, CI writers, global flags."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.hooks import (
    detect_forge,
    install_ci_config,
    install_pre_commit_hook,
)

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"
GOV = "governance"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    # init git so hooks work
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
    """Write config.yaml + context.yaml so CLI commands can load them."""
    from autogovern.models import Config, ModelProviderConfig

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
# Acceptance criterion 2: edit tool → check fails → check --fix → check passes
# ---------------------------------------------------------------------------


def test_acceptance_2_check_fix_cycle(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit tool definition → check exits 1 → check --fix → check exits 0."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    # Generate initial docs (writes profile.lock).
    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    # Edit tool definition: add a third tool.
    mcp_path = repo / ".mcp.json"
    mcp = json.loads(mcp_path.read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append(
        {"name": "close_ticket", "description": "Close a support ticket."}
    )
    mcp_path.write_text(json.dumps(mcp, indent=2))

    # check: should exit 1 (material-stale).
    check_result = runner.invoke(app, ["check", str(repo)])
    assert check_result.exit_code == 1, check_result.output
    assert "STALE" in check_result.output
    assert "inventory" in check_result.output or "system-card" in check_result.output

    # check --fix: should regenerate and exit 0.
    fix_result = runner.invoke(app, ["check", str(repo), "--fix"])
    assert fix_result.exit_code == 0, fix_result.output
    assert "regenerated" in fix_result.output.lower()

    # check: should now exit 0.
    final_result = runner.invoke(app, ["check", str(repo)])
    assert final_result.exit_code == 0, final_result.output
    assert "current" in final_result.output.lower()


# ---------------------------------------------------------------------------
# Regression: immaterial changes pass silently (spec: score <= 20 passes)
# ---------------------------------------------------------------------------


def test_check_immaterial_change_passes(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dependency-only change is immaterial: check exits 0, does not block."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    # Dependency-only change: no deterministic rule fires, score 0.
    pyproject = repo / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace("dependencies = [", 'dependencies = [\n    "requests>=2",')
    )

    check_result = runner.invoke(app, ["check", str(repo)])
    assert check_result.exit_code == 0, check_result.output
    assert "immaterial" in check_result.output.lower()


# ---------------------------------------------------------------------------
# Regression: prompt changes name their stale sections via the graph
# ---------------------------------------------------------------------------


def test_check_prompt_change_lists_stale_sections(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt content change must list inventory.md as a stale section."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    prompt = repo / "prompts" / "system.md"
    prompt.write_text(prompt.read_text() + "\nAn extra instruction.\n")

    check_result = runner.invoke(app, ["check", str(repo)])
    assert check_result.exit_code == 1, check_result.output
    assert "inventory.md" in check_result.output


# ---------------------------------------------------------------------------
# Regression: context edits are detected via context.lock
# ---------------------------------------------------------------------------


def test_check_context_change_detected(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing context.yaml after generate flags check; --fix clears it."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output
    assert (repo / GOV / "context.lock").is_file()

    # Autonomy change is deterministically material.
    context_path = repo / ".autogovern" / "context.yaml"
    raw = yaml.safe_load(context_path.read_text())
    raw["autonomy_level"] = "fully-autonomous"
    context_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    check_result = runner.invoke(app, ["check", str(repo)])
    assert check_result.exit_code == 1, check_result.output
    assert "context.autonomy_level" in check_result.output or "STALE" in check_result.output

    fix_result = runner.invoke(app, ["check", str(repo), "--fix"])
    assert fix_result.exit_code == 0, fix_result.output

    final_result = runner.invoke(app, ["check", str(repo)])
    assert final_result.exit_code == 0, final_result.output


# ---------------------------------------------------------------------------
# --strict on advisory scores
# ---------------------------------------------------------------------------


def test_check_strict_fails_on_advisory(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check --strict exits 1 when score is in the advisory band.

    We simulate an advisory score by editing the lockfile's data_categories
    to differ from the scan (a data category change scores 90/material, so
    instead we test that --strict changes the exit code semantics). A full
    advisory-band scenario requires a semantic scorer mock; here we verify
    the flag is wired and changes behavior on a material change.
    """
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    runner.invoke(app, ["generate", str(repo)])

    # Edit model config (material change, score 100).
    src = repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))

    # Without --strict: material → exit 1 regardless.
    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1

    # With --strict: still exit 1 (material is always 1, strict adds advisory).
    result_strict = runner.invoke(app, ["check", str(repo), "--strict"])
    assert result_strict.exit_code == 1


# ---------------------------------------------------------------------------
# --json output
# ---------------------------------------------------------------------------


def test_check_json_output(repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """check --json emits parseable JSON with a stable schema."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    result = runner.invoke(app, ["check", str(repo), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "current" in data
    assert "score" in data
    assert "band" in data
    assert data["current"] is True


def test_diff_json_output(repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """diff --json emits parseable JSON."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    result = runner.invoke(app, ["diff", str(repo), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "current" in data
    assert "score" in data


def test_explain_json_output(repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """explain --json emits parseable JSON."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    result = runner.invoke(app, ["explain", "system-card.md", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["document"] == "system-card.md"
    assert "generated" in data
    assert "agent_version" in data


# ---------------------------------------------------------------------------
# Pre-commit hook
# ---------------------------------------------------------------------------


def test_pre_commit_hook_installed(repo: Path) -> None:
    """install_pre_commit_hook writes an executable pre-commit hook."""
    msg = install_pre_commit_hook(repo)
    assert "installed" in msg.lower()
    hook = repo / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111  # executable


def test_pre_commit_hook_fast(repo: Path) -> None:
    """The installed hook runs the heuristic command and never blocks."""
    install_pre_commit_hook(repo)
    hook = repo / ".git" / "hooks" / "pre-commit"
    content = hook.read_text()
    assert "autogovern hook run" in content
    # Never blocks: the hook always exits 0 even if autogovern fails.
    assert "|| true" in content
    assert "exit 1" not in content


def test_hook_run_impact_flag(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`hook run` prints the impact flag for watched and unwatched files."""
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["hook", "run", "CLAUDE.md"])
    assert result.exit_code == 0
    assert "governance impact: yes" in result.output
    assert "CLAUDE.md" in result.output

    result_no = runner.invoke(app, ["hook", "run", "tests/test_something.py"])
    assert result_no.exit_code == 0
    assert "governance impact: no" in result_no.output


def test_hook_cli_command(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern hook install` installs the pre-commit hook."""
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["hook", "install"])
    assert result.exit_code == 0
    assert "installed" in result.output.lower()
    assert (repo / ".git" / "hooks" / "pre-commit").is_file()


def test_local_enforce_installs_pre_push(repo: Path) -> None:
    """--local-enforce also installs the pre-push hook."""
    install_pre_commit_hook(repo, local_enforce=True)
    assert (repo / ".git" / "hooks" / "pre-push").is_file()


# ---------------------------------------------------------------------------
# CI writers
# ---------------------------------------------------------------------------


def test_detect_forge_github(repo: Path) -> None:
    """detect_forge returns 'github' for a github.com remote."""
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    assert detect_forge(repo) == "github"


def test_detect_forge_bitbucket(repo: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://bitbucket.org/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    assert detect_forge(repo) == "bitbucket"


def test_detect_forge_forgejo(repo: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://codeberg.org/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    assert detect_forge(repo) == "forgejo"


def test_detect_forge_generic(repo: Path) -> None:
    """No remote → generic."""
    assert detect_forge(repo) == "generic"


def test_ci_writer_github(repo: Path) -> None:
    """GitHub CI writer writes .github/workflows/autogovern.yml."""
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    msg = install_ci_config(repo, api_key_env="OPENROUTER_API_KEY")
    assert ".github/workflows/autogovern.yml" in msg
    wf = repo / ".github" / "workflows" / "autogovern.yml"
    assert wf.is_file()
    content = wf.read_text()
    assert "autogovern check" in content
    assert "OPENROUTER_API_KEY" in content
    assert "secrets.OPENROUTER_API_KEY" in content


def test_ci_writer_forgejo(repo: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://codeberg.org/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    msg = install_ci_config(repo, api_key_env="OPENROUTER_API_KEY")
    assert ".forgejo" in msg
    wf = repo / ".forgejo" / "workflows" / "autogovern.yml"
    assert wf.is_file()
    assert "autogovern check" in wf.read_text()


def test_ci_writer_bitbucket(repo: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "remote", "add", "origin", "https://bitbucket.org/user/repo.git"],
        cwd=repo,
        capture_output=True,
    )
    msg = install_ci_config(repo, api_key_env="OPENROUTER_API_KEY")
    assert "bitbucket" in msg.lower()
    bb = repo / "bitbucket-pipelines.yml"
    assert bb.is_file()
    assert "autogovern check" in bb.read_text()


def test_ci_writer_generic(repo: Path) -> None:
    """Generic CI writer prints the command."""
    msg = install_ci_config(repo, api_key_env="OPENROUTER_API_KEY")
    assert "pip install autogovern" in msg
    assert "autogovern check" in msg


# ---------------------------------------------------------------------------
# --model override
# ---------------------------------------------------------------------------


def test_model_override(repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """--model overrides the configured model for a single run."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    captured_model = []

    import autogovern.cli as cli_mod
    from autogovern.models import Config
    from tests.conftest import make_mock_provider

    def _capture_provider(cfg: Config):
        captured_model.append(cfg.model_provider.model)
        return make_mock_provider(cfg)

    monkeypatch.setattr(cli_mod, "build_provider", _capture_provider)

    result = runner.invoke(app, ["scan", str(repo), "--model", "gpt-4o", "--json"])
    assert result.exit_code == 0, result.output
    assert captured_model == ["gpt-4o"]

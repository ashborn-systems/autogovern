"""Phase 11: headless input and library surface."""

from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import autogovern
from autogovern.cli import app
from autogovern.context import default_context
from autogovern.models import Config, ModelProviderConfig

runner = CliRunner()

FIXTURE_PROFILE = Path(__file__).resolve().parent / "fixtures" / "fixture-profile.json"
FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"


@pytest.fixture
def config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test")


# ---------------------------------------------------------------------------
# Headless generate: --profile with no repo
# ---------------------------------------------------------------------------


def test_generate_profile_no_repo(
    tmp_path: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate --profile produces docs with no repo present."""
    monkeypatch.chdir(tmp_path)
    import autogovern.cli as cli_mod
    from tests.conftest import make_mock_provider

    monkeypatch.setattr(cli_mod, "build_provider", lambda cfg: make_mock_provider(cfg))

    result = runner.invoke(app, ["generate", str(tmp_path), "--profile", str(FIXTURE_PROFILE)])
    assert result.exit_code == 0, result.output
    profile = autogovern.load_profile(FIXTURE_PROFILE)
    slug = profile.name.lower().replace(" ", "-").replace("/", "-").strip(".")
    assert (tmp_path / "governance" / slug / "system-card.md").is_file()
    assert (tmp_path / "governance" / slug / "profile.lock").is_file()


# ---------------------------------------------------------------------------
# Library API: import and call without CLI
# ---------------------------------------------------------------------------


def test_library_scan_returns_typed_result(tmp_path: Path, config_env: None) -> None:
    """Import the library, run scan, receive a typed result."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    from tests.conftest import make_mock_provider

    provider = make_mock_provider(cfg)
    result = autogovern.scan(repo, cfg, provider=provider)
    provider.close()

    assert isinstance(result, autogovern.ScanResult)
    assert result.agents
    assert result.agents[0].profile.name == "support-triage-agent"


def test_library_check_returns_typed_result(tmp_path: Path, config_env: None) -> None:
    """Library check against a repo returns a CheckResult."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    from tests.conftest import make_mock_provider

    provider = make_mock_provider(cfg)
    # Generate first so there's a lockfile.
    scan_result = autogovern.scan(repo, cfg, provider=provider)
    assert scan_result.agents
    autogovern.generate_docs(repo, cfg, scan_result, default_context(), provider=provider)
    # Now check.
    result = autogovern.check(repo, cfg, default_context(), provider=provider)
    provider.close()

    assert isinstance(result, autogovern.CheckResult)
    assert result.current is True


def test_library_check_headless_profile(tmp_path: Path, config_env: None) -> None:
    """Library check with a profile argument (headless mode)."""
    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    from tests.conftest import make_mock_provider

    provider = make_mock_provider(cfg)
    profile = autogovern.load_profile(FIXTURE_PROFILE)

    # Generate first so there's a lockfile to diff against.
    from autogovern.ingest import ScannedAgent, ScanResult

    scan_result = ScanResult(
        agents=[
            ScannedAgent(
                name=profile.name, root=".", profile=profile, card_written=False, card_path=None
            )
        ],
        root=str(tmp_path),
    )
    autogovern.generate_docs(tmp_path, cfg, scan_result, default_context(), provider=provider)

    result = autogovern.check(tmp_path, cfg, default_context(), provider=provider, profile=profile)
    provider.close()

    assert isinstance(result, autogovern.CheckResult)
    assert result.current is True  # same profile → no diff


# ---------------------------------------------------------------------------
# Parity: check --profile vs check with repo scan
# ---------------------------------------------------------------------------


def test_check_profile_parity_with_repo(
    tmp_path: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check --profile returns the same verdict as check with a repo scan."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    monkeypatch.chdir(repo)

    import autogovern.cli as cli_mod
    from autogovern.models import Config, ModelProviderConfig
    from tests.conftest import make_mock_provider

    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    (repo / ".autogovern").mkdir(exist_ok=True)
    (repo / ".autogovern" / "config.yaml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
    )
    (repo / ".autogovern" / "context.yaml").write_text(
        yaml.safe_dump(default_context().model_dump(mode="json"), sort_keys=False)
    )
    monkeypatch.setattr(cli_mod, "build_provider", lambda c: make_mock_provider(c))

    # Generate docs from repo scan (writes lockfile from scan result).
    runner.invoke(app, ["generate", str(repo)])

    # Export the scanned profile to a temp file for the headless check.
    import autogovern as ag_mod

    scan_provider = make_mock_provider(cfg)
    scan_result = ag_mod.scan(repo, cfg, provider=scan_provider)
    scan_provider.close()
    assert scan_result.agents
    profile_file = tmp_path / "scanned-profile.json"
    profile_file.write_text(scan_result.agents[0].profile.model_dump_json(indent=2))

    # Check via repo scan → current.
    result_repo = runner.invoke(app, ["check", str(repo), "--json"])
    assert result_repo.exit_code == 0
    repo_verdict = json.loads(result_repo.output)

    # Check via --profile (headless, same profile data) → same verdict.
    result_profile = runner.invoke(
        app, ["check", str(repo), "--profile", str(profile_file), "--json"]
    )
    assert result_profile.exit_code == 0
    profile_verdict = json.loads(result_profile.output)

    # Same verdict (both current).
    assert repo_verdict["current"] == profile_verdict["current"]
    assert repo_verdict["score"] == profile_verdict["score"]


# ---------------------------------------------------------------------------
# API stability: public function signatures frozen
# ---------------------------------------------------------------------------


def test_public_api_signatures_stable() -> None:
    """The public function signatures are frozen for API stability."""
    # Each function must accept these parameter names.
    expected = {
        "scan": {"root", "config", "provider"},
        "generate_docs": {"root", "config", "scan_result", "context", "provider"},
        "check": {
            "root",
            "config",
            "context",
            "provider",
            "strict",
            "fix",
            "context_from_file",
            "profile",
        },
        "load_profile": {"path"},
    }
    for name, expected_params in expected.items():
        func = getattr(autogovern, name)
        sig = inspect.signature(func)
        actual = set(sig.parameters.keys())
        assert expected_params <= actual, f"{name}: missing params {expected_params - actual}"


def test_public_exports_present() -> None:
    """All expected public names are exported from the package."""
    for name in [
        "scan",
        "generate_docs",
        "check",
        "load_profile",
        "build_provider",
        "ScanResult",
        "GenerationResult",
        "CheckResult",
        "app",
    ]:
        assert hasattr(autogovern, name), f"missing public export: {name}"

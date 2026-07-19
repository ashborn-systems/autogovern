"""Phase 12: run manifests and observability."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.models import Config, ModelProviderConfig, RunManifest
from autogovern.observability import build_manifest, read_manifests, write_manifest

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    return r


@pytest.fixture
def config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://mock.example.com/v1")
    monkeypatch.setenv("AUTOGOVERN_MODEL", "mock-model")
    monkeypatch.setenv("AUTOGOVERN_API_KEY_ENV", "AUTOGOVERN_TEST_KEY")
    monkeypatch.setenv("AUTOGOVERN_TEST_KEY", "sk-test-secret-value")


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
# Manifests written on every command
# ---------------------------------------------------------------------------


def test_generate_writes_manifest(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    result = runner.invoke(app, ["generate", str(repo)])
    assert result.exit_code == 0, result.output

    manifests = read_manifests(repo)
    assert len(manifests) >= 1
    gen_manifests = [m for m in manifests if json.loads(m.read_text())["command"] == "generate"]
    assert gen_manifests
    data = json.loads(gen_manifests[-1].read_text())
    assert data["command"] == "generate"
    assert data["model_id"] == "mock-model"
    assert len(data["sections_regenerated"]) > 0


def test_check_writes_manifest(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)

    runner.invoke(app, ["generate", str(repo)])
    runner.invoke(app, ["check", str(repo)])

    manifests = read_manifests(repo)
    check_manifests = [
        json.loads(m.read_text())
        for m in manifests
        if json.loads(m.read_text())["command"] == "check"
    ]
    assert len(check_manifests) >= 1
    assert check_manifests[-1]["command"] == "check"


def test_manifest_validates_against_runmanifest_schema(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    manifests = read_manifests(repo)
    gen_manifests = [m for m in manifests if json.loads(m.read_text())["command"] == "generate"]
    assert gen_manifests
    data = json.loads(gen_manifests[-1].read_text())
    manifest = RunManifest.model_validate(data)
    assert manifest.command == "generate"
    assert manifest.model_id == "mock-model"


# ---------------------------------------------------------------------------
# No secrets in manifests
# ---------------------------------------------------------------------------


def test_manifest_contains_no_secret_values(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API key value never appears in any manifest."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])
    runner.invoke(app, ["check", str(repo)])

    manifests = read_manifests(repo)
    for m in manifests:
        text = m.read_text()
        assert "sk-test-secret-value" not in text
        assert "sk-test" not in text


def test_manifest_config_snapshot_strips_key_env(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The config snapshot does not include the api_key_env name."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])

    manifests = read_manifests(repo)
    gen_manifests = [m for m in manifests if json.loads(m.read_text())["command"] == "generate"]
    assert gen_manifests
    data = json.loads(gen_manifests[-1].read_text())
    snapshot = data.get("config_snapshot", {})
    mp = snapshot.get("model_provider", {})
    assert "api_key_env" not in mp
    assert mp.get("api_base") == "https://mock.example.com/v1"
    assert mp.get("model") == "mock-model"


# ---------------------------------------------------------------------------
# Token counts: null when not reported
# ---------------------------------------------------------------------------


def test_token_counts_null_when_not_reported() -> None:
    """When the provider doesn't report usage, token_counts is null."""

    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    manifest = build_manifest(command="test", config=cfg)
    assert manifest.token_counts is None


def test_token_counts_present_when_reported() -> None:
    """When usage is reported, token_counts carries the values."""

    cfg = Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )
    manifest = build_manifest(
        command="test",
        config=cfg,
        token_counts={"prompt": 100, "completion": 50, "total": 150},
    )
    assert manifest.token_counts is not None
    assert manifest.token_counts.prompt == 100
    assert manifest.token_counts.total == 150


# ---------------------------------------------------------------------------
# Manifest file naming and structure
# ---------------------------------------------------------------------------


def test_manifest_files_are_json(tmp_path: Path) -> None:
    """Manifest files are valid JSON with sorted keys."""

    cfg = Config(
        model_provider=ModelProviderConfig(api_base="https://x", model="m", api_key_env="K")
    )
    manifest = build_manifest(command="test", config=cfg)
    path = write_manifest(tmp_path, manifest)
    assert path.suffix == ".json"
    data = json.loads(path.read_text())
    assert data["command"] == "test"
    assert data["tool_version"]  # non-empty


def test_multiple_manifests_accumulate(
    repo: Path, config_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple commands write multiple manifests, accumulating over time."""
    _write_init(repo)
    monkeypatch.chdir(repo)
    import autogovern.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_provider", _mock_provider_factory)
    runner.invoke(app, ["generate", str(repo)])
    runner.invoke(app, ["check", str(repo)])
    runner.invoke(app, ["generate", str(repo)])  # idempotent re-run

    manifests = read_manifests(repo)
    assert len(manifests) >= 3  # generate + check + generate
    commands = [json.loads(m.read_text())["command"] for m in manifests]
    assert commands.count("generate") >= 2
    assert commands.count("check") >= 1

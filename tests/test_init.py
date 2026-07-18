"""Phase 5: the ``init`` wizard.

Covers the three validation gates from the build plan:
- ``init --defaults`` in a temp dir writes both files, valid against the
  Phase 1 models
- ``init --from tests/fixtures/context-invalid.yaml`` exits non-zero listing
  every invalid field
- re-running init on an initialised repo prompts before overwriting
  (auto-answered in tests)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.config_loader import load_config, provider_from_env
from autogovern.context import (
    CONFIG_FILE,
    CONTEXT_FILE,
    ContextImportError,
    default_context,
    format_context_errors,
    load_context_from_file,
    write_init,
)
from autogovern.models import Config, ContextManifest

runner = CliRunner()

# Provider env vars the wizard reads in non-interactive mode.
PROVIDER_ENV = {
    "AUTOGOVERN_API_BASE": "https://openrouter.example.com/api/v1",
    "AUTOGOVERN_MODEL": "test-model",
    "AUTOGOVERN_API_KEY_ENV": "OPENROUTER_API_KEY",
    "AUTOGOVERN_TEMPERATURE": "0",
}


@pytest.fixture
def provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in PROVIDER_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def clean_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run init in an empty temp directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Library-level helpers (pure core)
# ---------------------------------------------------------------------------


def test_default_context_is_valid() -> None:
    """The --defaults manifest validates against the Phase 1 model."""
    default_context().model_validate(default_context().model_dump())


def test_provider_from_env_reads_all_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in PROVIDER_ENV.items():
        monkeypatch.setenv(key, value)
    provider = provider_from_env()
    assert provider is not None
    assert provider.api_base == PROVIDER_ENV["AUTOGOVERN_API_BASE"]
    assert provider.model == PROVIDER_ENV["AUTOGOVERN_MODEL"]
    assert provider.api_key_env == PROVIDER_ENV["AUTOGOVERN_API_KEY_ENV"]
    assert provider.temperature == 0.0


def test_provider_from_env_returns_none_when_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGOVERN_API_BASE", "https://x.example.com")
    monkeypatch.delenv("AUTOGOVERN_MODEL", raising=False)
    monkeypatch.delenv("AUTOGOVERN_API_KEY_ENV", raising=False)
    assert provider_from_env() is None


def test_load_context_from_file_invalid_lists_every_field() -> None:
    """The invalid fixture raises with one line per invalid field.

    The fixture has five invalid fields: jurisdictions, deployment_context,
    autonomy_level, data_categories, risk_appetite.
    """
    invalid_path = Path(__file__).resolve().parent / "fixtures" / "context-invalid.yaml"
    with pytest.raises(ContextImportError) as exc_info:
        load_context_from_file(invalid_path)

    field_errors = exc_info.value.field_errors
    # Five distinct field problems, one line each.
    assert len(field_errors) == 5
    joined = "\n".join(field_errors)
    for field in (
        "jurisdictions",
        "deployment_context",
        "autonomy_level",
        "data_categories",
        "risk_appetite",
    ):
        assert field in joined


def test_load_context_from_file_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ContextImportError, match="file not found"):
        load_context_from_file(tmp_path / "nope.yaml")


def test_write_init_writes_both_files(tmp_path: Path) -> None:
    from autogovern.context import build_config

    config = build_config(_manual_provider())
    context = default_context()
    result = write_init(
        root=tmp_path,
        config=config,
        context=context,
        force=True,
        no_hooks=False,
        confirm=None,
    )
    assert result.wrote_files is True
    assert result.overwritten is False
    assert (tmp_path / CONFIG_FILE).is_file()
    assert (tmp_path / CONTEXT_FILE).is_file()

    # Both files round-trip through the Phase 1 models.
    loaded_config = load_config(tmp_path / CONFIG_FILE)
    assert loaded_config.model_provider.model == "test-model"
    raw_context = yaml.safe_load((tmp_path / CONTEXT_FILE).read_text())
    assert ContextManifest.model_validate(raw_context).organisation == "My Organisation"


def test_write_init_declines_without_confirm(tmp_path: Path) -> None:
    from autogovern.context import build_config

    config = build_config(_manual_provider())
    context = default_context()
    write_init(root=tmp_path, config=config, context=context, force=True, confirm=None)
    # Second run: existing files, no force, declining confirm.
    result = write_init(
        root=tmp_path,
        config=config,
        context=context,
        force=False,
        confirm=lambda _msg: False,
    )
    assert result.wrote_files is False
    assert result.overwritten is False


def test_write_init_confirm_true_overwrites(tmp_path: Path) -> None:
    from autogovern.context import build_config

    config = build_config(_manual_provider())
    context = default_context()
    write_init(root=tmp_path, config=config, context=context, force=True, confirm=None)
    result = write_init(
        root=tmp_path,
        config=config,
        context=context,
        force=False,
        confirm=lambda _msg: True,
    )
    assert result.wrote_files is True
    assert result.overwritten is True


def _manual_provider():
    from autogovern.models import ModelProviderConfig

    return ModelProviderConfig(
        api_base="https://openrouter.example.com/api/v1",
        model="test-model",
        api_key_env="OPENROUTER_API_KEY",
    )


# ---------------------------------------------------------------------------
# CLI: init --defaults
# ---------------------------------------------------------------------------


def test_init_defaults_writes_valid_files(clean_cwd: Path, provider_env: None) -> None:
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    assert (clean_cwd / CONFIG_FILE).is_file()
    assert (clean_cwd / CONTEXT_FILE).is_file()

    config = load_config(clean_cwd / CONFIG_FILE)
    assert config.model_provider.api_base == PROVIDER_ENV["AUTOGOVERN_API_BASE"]
    assert config.model_provider.model == PROVIDER_ENV["AUTOGOVERN_MODEL"]
    assert config.model_provider.api_key_env == PROVIDER_ENV["AUTOGOVERN_API_KEY_ENV"]

    raw_context = yaml.safe_load((clean_cwd / CONTEXT_FILE).read_text())
    assert ContextManifest.model_validate(raw_context)


def test_init_defaults_prints_next_steps(clean_cwd: Path, provider_env: None) -> None:
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    assert "Next steps" in result.output
    assert "autogovern scan" in result.output
    assert "autogovern generate" in result.output


def test_init_defaults_installs_hooks_and_ci(
    clean_cwd: Path, provider_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init installs the pre-commit hook and writes CI config."""
    monkeypatch.chdir(clean_cwd)
    # init git so hook installation finds .git
    import subprocess

    subprocess.run(["git", "init"], cwd=clean_cwd, capture_output=True)
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    assert "pre-commit hook" in result.output.lower()
    assert "CI" in result.output
    assert (clean_cwd / ".git" / "hooks" / "pre-commit").is_file()


def test_init_defaults_no_hooks_skips_hook_message(clean_cwd: Path, provider_env: None) -> None:
    result = runner.invoke(app, ["init", "--defaults", "--no-hooks"])
    assert result.exit_code == 0, result.output
    assert "--no-hooks" in result.output


def test_init_defaults_refuses_without_provider_env(
    clean_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in PROVIDER_ENV:
        monkeypatch.delenv(key, raising=False)
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 1
    assert "AUTOGOVERN_API_BASE" in result.output
    assert "AUTOGOVERN_MODEL" in result.output
    assert "AUTOGOVERN_API_KEY_ENV" in result.output


def test_init_defaults_does_not_persist_key_value(
    clean_cwd: Path, provider_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API key value is never written to config or context files."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-must-not-leak")
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    config_text = (clean_cwd / CONFIG_FILE).read_text()
    context_text = (clean_cwd / CONTEXT_FILE).read_text()
    assert "sk-secret-must-not-leak" not in config_text
    assert "sk-secret-must-not-leak" not in context_text
    # Only the env var *name* appears.
    assert "OPENROUTER_API_KEY" in config_text


# ---------------------------------------------------------------------------
# CLI: init --from
# ---------------------------------------------------------------------------


def test_init_from_invalid_exits_nonzero_listing_fields(
    clean_cwd: Path, provider_env: None
) -> None:
    invalid = Path(__file__).resolve().parent / "fixtures" / "context-invalid.yaml"
    result = runner.invoke(app, ["init", "--from", str(invalid)])
    assert result.exit_code == 1
    for field in (
        "jurisdictions",
        "deployment_context",
        "autonomy_level",
        "data_categories",
        "risk_appetite",
    ):
        assert field in result.output
    # Nothing written when validation fails.
    assert not (clean_cwd / CONFIG_FILE).exists()


def test_init_from_valid_writes_context(
    clean_cwd: Path, provider_env: None, tmp_path: Path
) -> None:
    manifest = default_context()
    manifest_file = tmp_path / "ctx.yaml"
    manifest_file.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False))
    result = runner.invoke(app, ["init", "--from", str(manifest_file)])
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load((clean_cwd / CONTEXT_FILE).read_text())
    assert ContextManifest.model_validate(raw).organisation == "My Organisation"


# ---------------------------------------------------------------------------
# CLI: overwrite prompt
# ---------------------------------------------------------------------------


def test_init_rerun_prompts_before_overwrite(clean_cwd: Path, provider_env: None) -> None:
    first = runner.invoke(app, ["init", "--defaults"])
    assert first.exit_code == 0, first.output

    # Answer "y" to the overwrite prompt.
    second_yes = runner.invoke(app, ["init", "--defaults"], input="y\n")
    assert second_yes.exit_code == 0, second_yes.output
    assert "overwrote" in second_yes.output.lower()

    # Answer "n" -> no files written.
    second_no = runner.invoke(app, ["init", "--defaults"], input="n\n")
    assert second_no.exit_code == 0, second_no.output
    assert "no files written" in second_no.output.lower()


def test_init_force_overwrites_without_prompt(clean_cwd: Path, provider_env: None) -> None:
    runner.invoke(app, ["init", "--defaults"])
    result = runner.invoke(app, ["init", "--defaults", "--force"])
    assert result.exit_code == 0, result.output
    assert "overwrote" in result.output.lower()


# ---------------------------------------------------------------------------
# Config round-trip: written config is loadable by the Phase 2 loader
# ---------------------------------------------------------------------------


def test_init_defaults_config_loadable_by_phase2_loader(
    clean_cwd: Path, provider_env: None
) -> None:
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    config = load_config()  # reads .autogovern/config.yaml from cwd
    assert isinstance(config, Config)
    assert config.thresholds.material == 80
    assert config.thresholds.immaterial == 20
    assert config.documents["quickstart"] is True
    assert config.documents["attention"] is True


def test_format_context_errors_renders_each_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ContextManifest(
            organisation="x",
            sector="x",
            deployment_context="mars",
            autonomy_level="telepathic",
            risk_appetite="reckless",
        )
    lines = format_context_errors(exc_info.value)
    assert len(lines) == 3
    assert any("deployment_context" in line for line in lines)
    assert any("autonomy_level" in line for line in lines)
    assert any("risk_appetite" in line for line in lines)

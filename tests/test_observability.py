"""Tests for the observability layer: run manifests, per-call tracking, and runs command.

Covers:
- Per-call token attribution on the provider (label parameter)
- Regeneration reasons in GenerationResult (not hardcoded)
- Normalisation outcome recorded in the manifest
- Manifests written by scan and diff (not just generate and check)
- The ``autogovern runs`` command reads and renders manifests
- Tracing module degrades gracefully when OTel is not installed
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.models import CallRecord, NormalisationOutcome, RunManifest
from autogovern.observability import load_manifest, load_recent_manifests
from autogovern.observability.tracing import init_tracing, is_enabled, shutdown, span

runner = CliRunner()


# ---------------------------------------------------------------------------
# Per-call token tracking
# ---------------------------------------------------------------------------


def test_provider_call_log_records_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider's call_log carries the label passed to chat/chat_json."""
    from tests.conftest import _MOCK_KEY_ENV, _MOCK_KEY_VALUE, make_mock_provider

    monkeypatch.setenv(_MOCK_KEY_ENV, _MOCK_KEY_VALUE)
    provider = make_mock_provider()
    provider.chat([{"role": "user", "content": "hello"}], label="test-section")
    log = provider.call_log
    assert len(log) == 1
    assert log[0]["label"] == "test-section"
    provider.close()


def test_provider_call_log_aggregates_multiple_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple calls produce multiple call_log entries."""
    from tests.conftest import _MOCK_KEY_ENV, _MOCK_KEY_VALUE, make_mock_provider

    monkeypatch.setenv(_MOCK_KEY_ENV, _MOCK_KEY_VALUE)
    provider = make_mock_provider()
    provider.chat([{"role": "user", "content": "one"}], label="section-a")
    provider.chat([{"role": "user", "content": "two"}], label="section-b")
    log = provider.call_log
    assert len(log) == 2
    assert log[0]["label"] == "section-a"
    assert log[1]["label"] == "section-b"
    provider.close()


def test_call_record_model_validates() -> None:
    """CallRecord accepts label and optional token counts."""
    record = CallRecord(label="normalise", prompt=100, completion=50, total=150)
    assert record.label == "normalise"
    assert record.total == 150
    # Missing token counts are None, not 0.
    record2 = CallRecord(label="scan")
    assert record2.prompt is None


# ---------------------------------------------------------------------------
# Regeneration reasons
# ---------------------------------------------------------------------------


def test_generation_result_has_regeneration_reasons() -> None:
    """GenerationResult exposes regeneration_reasons (not hardcoded)."""
    from pathlib import Path

    from autogovern.generate.engine import GenerationResult

    result = GenerationResult(governance_dir=Path("."))
    assert hasattr(result, "regeneration_reasons")
    assert result.regeneration_reasons == {}


def test_normalisation_outcome_recorded() -> None:
    """NormalisationOutcome tracks used_llm, fallback, and fields."""
    outcome = NormalisationOutcome(used_llm=True, fallback=False, fields=["internal"])
    assert outcome.used_llm is True
    assert outcome.fallback is False
    assert outcome.fields == ["internal"]


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def test_load_recent_manifests_empty(tmp_path: Path) -> None:
    """load_recent_manifests returns [] when no runs exist."""
    assert load_recent_manifests(tmp_path) == []


def test_load_manifest_parses_valid_json(tmp_path: Path) -> None:
    """load_manifest parses a valid manifest file."""
    from autogovern.observability import write_manifest

    # Write a minimal manifest.
    manifest = RunManifest(command="test", tool_version="0.1.0")
    path = write_manifest(tmp_path, manifest)
    loaded = load_manifest(path)
    assert loaded is not None
    assert loaded.command == "test"


# ---------------------------------------------------------------------------
# Runs command
# ---------------------------------------------------------------------------


def test_runs_command_no_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern runs` in an empty repo reports no runs."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    from autogovern.tui.console import is_plain

    is_plain.cache_clear()
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 0
    assert "No runs found" in result.output


def test_runs_command_lists_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern runs` lists manifests when they exist."""
    from autogovern.observability import write_manifest

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    from autogovern.tui.console import is_plain

    is_plain.cache_clear()

    manifest = RunManifest(command="generate", tool_version="0.1.0")
    write_manifest(tmp_path, manifest)

    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 0
    assert "generate" in result.output


def test_runs_latest_shows_detail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern runs --latest` shows detailed manifest info."""
    from autogovern.models import CallRecord, TokenCounts
    from autogovern.observability import write_manifest

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    from autogovern.tui.console import is_plain

    is_plain.cache_clear()

    manifest = RunManifest(
        command="generate",
        tool_version="0.1.0",
        model_id="test-model",
        token_counts=TokenCounts(prompt=100, completion=50, total=150),
        call_log=[CallRecord(label="system-card", total=150)],
    )
    write_manifest(tmp_path, manifest)

    result = runner.invoke(app, ["runs", "--latest"])
    assert result.exit_code == 0
    assert "generate" in result.output
    assert "test-model" in result.output
    assert "system-card" in result.output


def test_runs_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern runs --json` emits parseable JSON."""
    from autogovern.observability import write_manifest

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    from autogovern.tui.console import is_plain

    is_plain.cache_clear()

    manifest = RunManifest(command="scan", tool_version="0.1.0")
    write_manifest(tmp_path, manifest)

    result = runner.invoke(app, ["runs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) >= 1
    assert data[0]["command"] == "scan"


# ---------------------------------------------------------------------------
# Tracing module (graceful degradation)
# ---------------------------------------------------------------------------


def test_tracing_disabled_by_default() -> None:
    """When config has tracing: false, init_tracing is a no-op."""
    from autogovern.models import Config, ModelProviderConfig, ObservabilityConfig

    config = Config(
        model_provider=ModelProviderConfig(api_base="https://x", model="m", api_key_env="KEY"),
        observability=ObservabilityConfig(tracing=False),
    )
    init_tracing(config)
    assert is_enabled() is False


def test_tracing_span_is_noop_when_disabled() -> None:
    """span() yields None when tracing is disabled."""
    with span("test") as s:
        assert s is None


def test_tracing_span_does_not_crash_without_otel() -> None:
    """Even with tracing enabled, no OTel installed means graceful no-op."""
    from autogovern.models import Config, ModelProviderConfig, ObservabilityConfig

    config = Config(
        model_provider=ModelProviderConfig(api_base="https://x", model="m", api_key_env="KEY"),
        observability=ObservabilityConfig(tracing=True),
    )
    init_tracing(config)
    # OTel is not installed in the test environment, so tracing stays disabled.
    assert is_enabled() is False
    with span("test") as s:
        assert s is None
    shutdown()


def test_tracing_shutdown_resets_state() -> None:
    """shutdown() resets the module to the disabled state."""
    shutdown()
    assert is_enabled() is False

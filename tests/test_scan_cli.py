"""Phase 4 CLI tests for the ``scan`` command.

Uses a real config file plus a monkeypatched ``build_provider`` so the CLI
calls a mocked provider. No live LLM.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from autogovern.cli import app

from .conftest import FIXTURES

runner = CliRunner()

_CONFIG_YAML = """\
model_provider:
  api_base: https://mock-provider.example.com/v1
  model: mock-model
  api_key_env: AUTOGOVERN_TEST_KEY
  temperature: 0
"""


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / ".autogovern" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_CONFIG_YAML, encoding="utf-8")
    return config_path


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURES / name, dest)
    return dest


def test_cli_scan_json_basic(tmp_path: Path, provider_factory, monkeypatch) -> None:
    """scan --json on fixture-basic emits parseable JSON with a valid profile."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: provider_factory())
    basic = _copy_fixture("fixture-basic", tmp_path)
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["scan", str(basic), "--json", "--config", str(config)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["signals_found"] is True
    assert len(data["agents"]) == 1
    agent = data["agents"][0]
    assert agent["card_written"] is True
    profile = agent["profile"]
    assert profile["name"] == "support-triage-agent"
    tool_perms = [
        p["detail"].split(" — ")[0]
        for p in profile["governance"]["permissions_surface"]["value"]
        if p["kind"] == "tool"
    ]
    assert sorted(tool_perms) == ["assign_ticket", "fetch_ticket"]


def test_cli_scan_human_basic(tmp_path: Path, provider_factory, monkeypatch) -> None:
    """Human output names the agent and reports the written card."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: provider_factory())
    basic = _copy_fixture("fixture-basic", tmp_path)
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["scan", str(basic), "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "support-triage-agent" in result.output
    assert "AgentCard: written" in result.output


def test_cli_scan_no_write_card(tmp_path: Path, provider_factory, monkeypatch) -> None:
    """--no-write-card suppresses card writing."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: provider_factory())
    basic = _copy_fixture("fixture-basic", tmp_path)
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["scan", str(basic), "--no-write-card", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert not (basic / ".well-known" / "agent.json").is_file()


def test_cli_scan_plain_no_signals(tmp_path: Path, provider_factory, monkeypatch) -> None:
    """scan on fixture-plain exits 0 with an explicit no-signals message."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: provider_factory())
    plain = _copy_fixture("fixture-plain", tmp_path)
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["scan", str(plain), "--json", "--config", str(config)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["signals_found"] is False
    assert data["agents"] == []

    # Human form also states it clearly.
    result_human = runner.invoke(app, ["scan", str(plain), "--config", str(config)])
    assert result_human.exit_code == 0
    assert "No agent signals found" in result_human.output


def test_cli_scan_carded_no_write(tmp_path: Path, provider_factory, monkeypatch) -> None:
    """scan on fixture-carded leaves the existing card untouched."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: provider_factory())
    carded = _copy_fixture("fixture-carded", tmp_path)
    config = _write_config(tmp_path)
    card_path = carded / ".well-known" / "agent.json"
    before = card_path.read_text(encoding="utf-8")

    result = runner.invoke(app, ["scan", str(carded), "--json", "--config", str(config)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert len(data["agents"]) == 1
    assert data["agents"][0]["card_written"] is False
    assert card_path.read_text(encoding="utf-8") == before


def test_cli_scan_no_config_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    """scan with no config exits 1 and mentions init."""
    monkeypatch.setattr("autogovern.cli.build_provider", lambda cfg: None)
    # Run in a clean CWD with no .autogovern/config.yaml.
    clean = tmp_path / "clean"
    clean.mkdir()
    monkeypatch.chdir(clean)

    result = runner.invoke(app, ["scan", str(clean)])

    assert result.exit_code == 1
    assert "init" in result.output.lower()

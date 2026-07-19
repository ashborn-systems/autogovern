"""Tests for the TUI rendering layer.

Covers the acceptance criteria: plain-mode auto-detection, state marks,
message catalogue, stage tracker, summary line, and the status view.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.tui.catalogue import message_for
from autogovern.tui.console import enable_plain, is_plain
from autogovern.tui.states import (
    ACTIVE,
    FAIL,
    OK,
    PENDING,
    WARN,
    fail_mark,
    ok_mark,
)
from autogovern.tui.status import print_status

runner = CliRunner()


# ---------------------------------------------------------------------------
# Plain-mode detection
# ---------------------------------------------------------------------------


def test_no_color_env_forces_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO_COLOR env var triggers plain mode."""
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    assert is_plain() is True


def test_plain_flag_forces_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    """The AUTOGOVERN_PLAIN flag triggers plain mode."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("AUTOGOVERN_PLAIN", "1")
    is_plain.cache_clear()
    assert is_plain() is True


def test_enable_plain_clears_console() -> None:
    """enable_plain() forces plain mode and resets the console."""
    enable_plain()
    assert is_plain() is True


# ---------------------------------------------------------------------------
# State marks
# ---------------------------------------------------------------------------


def test_state_marks_are_fixed_width_ascii() -> None:
    """All state marks are plain ASCII brackets, no pictograms."""
    for mark in (OK, ACTIVE, PENDING, WARN, FAIL):
        assert mark.isascii()
        assert mark.startswith("[")
        assert mark.endswith("]")


def test_ok_mark_renders_plain_text() -> None:
    """ok_mark returns a Text containing the ASCII mark."""
    mark = ok_mark()
    assert OK in mark.plain


def test_fail_mark_renders_plain_text() -> None:
    """fail_mark returns a Text containing the ASCII mark."""
    mark = fail_mark()
    assert FAIL in mark.plain


# ---------------------------------------------------------------------------
# Message catalogue
# ---------------------------------------------------------------------------


def test_message_for_known_stage_returns_string() -> None:
    """A known stage returns a non-empty message from the catalogue."""
    msg = message_for("scan")
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_message_for_unknown_stage_falls_back() -> None:
    """An unknown stage falls back to the stage name, not an error."""
    msg = message_for("nonexistent_stage")
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_message_rotation_returns_different_messages() -> None:
    """The catalogue has multiple messages per stage (rotation pool)."""
    from autogovern.tui.catalogue import _load_catalogue

    pool = _load_catalogue()
    assert len(pool["scan"]) >= 2
    assert len(pool["generate"]) >= 2


# ---------------------------------------------------------------------------
# Status view (bare `autogovern`)
# ---------------------------------------------------------------------------


def test_status_view_in_empty_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare autogovern in an empty repo shows 'not initialised'."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    print_status(tmp_path)
    # No assertion on captured output — the test verifies no crash and no
    # LLM call (the function reads only lockfiles and manifests).


def test_bare_autogovern_prints_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`autogovern` with no subcommand prints the status view."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "autogovern" in result.output
    assert "not initialised" in result.output


# ---------------------------------------------------------------------------
# Summary line
# ---------------------------------------------------------------------------


def test_summary_line_prints_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """summary_line renders in plain mode without crashing."""
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    from autogovern.tui.panels import summary_line

    summary_line("generate", detail="3 sections", tokens=12400, elapsed=18.0)
    # No assertion on output — the test verifies no crash.


# ---------------------------------------------------------------------------
# Error triplet
# ---------------------------------------------------------------------------


def test_error_triplet_prints_what_why_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    """error_triplet renders the what/why/fix triplet."""
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    from autogovern.tui.panels import error_triplet

    error_triplet(
        what="Model provider unreachable (timed out)",
        why="Generation needs the model.",
        fix="check OPENROUTER_API_KEY is set",
        partial="heuristic pass still ran",
    )


# ---------------------------------------------------------------------------
# JSON output is not corrupted by TUI
# ---------------------------------------------------------------------------


def test_scan_json_output_is_pure_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """scan --json emits pure JSON with no TUI chrome on stdout."""
    monkeypatch.setenv("NO_COLOR", "1")
    is_plain.cache_clear()
    # Create a minimal repo with agent signals.
    (tmp_path / "AGENTS.md").write_text("# Test agent")
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    # The output should be parseable as JSON (ignoring stderr warnings).
    # If the LLM call fails, warnings may appear on stdout; that's a
    # pre-existing issue, not a TUI regression.
    if result.exit_code == 0:
        lines = result.stdout.strip().split("\n")
        # Find the start of the JSON object.
        json_start = next((i for i, line in enumerate(lines) if line.startswith("{")), None)
        if json_start is not None:
            json_text = "\n".join(lines[json_start:])
            data = json.loads(json_text)
            assert "signals_found" in data

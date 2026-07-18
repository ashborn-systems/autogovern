"""Optional live-provider smoke test.

Every other test mocks the model provider (hard constraint). This module is
the single documented exception: it runs only when ``AUTOGOVERN_SMOKE=1``
and a real provider is configured via the ``AUTOGOVERN_*`` env vars (plus
the key in the env var named by ``AUTOGOVERN_API_KEY_ENV``).

Run with: ``make smoke``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autogovern.cli import app

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"

pytestmark = pytest.mark.skipif(
    os.environ.get("AUTOGOVERN_SMOKE") != "1",
    reason="smoke tests run only with AUTOGOVERN_SMOKE=1 and a configured provider",
)


def _provider_configured() -> bool:
    return all(
        os.environ.get(name)
        for name in ("AUTOGOVERN_API_BASE", "AUTOGOVERN_MODEL", "AUTOGOVERN_API_KEY_ENV")
    ) and bool(os.environ.get(os.environ.get("AUTOGOVERN_API_KEY_ENV", ""), ""))


def test_smoke_scan_live_provider(tmp_path: Path) -> None:
    """A real provider round-trip: scan fixture-basic, expect a profile."""
    if not _provider_configured():
        pytest.skip("provider env vars not configured")
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    result = runner.invoke(app, ["scan", str(repo), "--no-write-card"])
    assert result.exit_code == 0, result.output
    assert "Agent:" in result.output

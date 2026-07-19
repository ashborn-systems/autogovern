"""Phase 4 performance test: scan completes in under 5 s on a 10k-file repo.

Generates a repo with 10,000 files (mostly noise) plus the fixture-basic
agent signals, then times a scan with a mocked provider. The bound is the
spec's non-functional requirement; CI is expected to be well under it.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from autogovern.ingest import scan_repo

from .conftest import FIXTURES, make_mock_provider, mock_config

_PERF_BOUND_SECONDS = 5.0


def _generate_large_repo(dest: Path) -> None:
    """Create a 10k-file repo: fixture-basic signals plus 10k noise files."""
    shutil.copytree(FIXTURES / "fixture-basic", dest)
    # 100 dirs x 100 files = 10,000 noise files. ~500 are .py to exercise the
    # source-scanning glob; the rest are .txt.
    for d in range(100):
        dir_path = dest / f"noise_{d:03d}"
        dir_path.mkdir()
        for f in range(100):
            ext = ".py" if (d + f) % 20 == 0 else ".txt"
            (dir_path / f"file_{f:03d}{ext}").write_text("noise\n", encoding="utf-8")


def test_scan_perf_under_5_seconds(tmp_path: Path) -> None:
    """Scan of a 10k-file repo completes in under 5 seconds."""
    repo = tmp_path / "large"
    _generate_large_repo(repo)

    config = mock_config()
    provider = make_mock_provider(config)
    try:
        start = time.perf_counter()
        result = scan_repo(repo, config, provider=provider)
        elapsed = time.perf_counter() - start
    finally:
        provider.close()

    assert result.signals_found is True
    assert result.agents
    assert elapsed < _PERF_BOUND_SECONDS, f"scan took {elapsed:.2f}s (bound {_PERF_BOUND_SECONDS}s)"

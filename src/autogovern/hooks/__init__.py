"""Pre-commit and CI entrypoints.

Phase 5 leaves these as clearly-marked stubs. Phase 10 implements the real
pre-commit hook, the forge-aware CI writers, and the ``--local-enforce``
pre-push hook. Each stub returns a status message and installs nothing.
"""

from __future__ import annotations

from pathlib import Path


def install_pre_commit_hook(root: Path, *, local_enforce: bool = False) -> str:
    """Phase 10 stub. Installs nothing; returns a status message.

    When implemented, this writes the warning-only pre-commit hook and, if
    ``local_enforce`` is set, the pre-push hook that runs the full check.
    """
    mode = " (with --local-enforce pre-push hook)" if local_enforce else ""
    return f"pre-commit hook installation: not implemented (Phase 10){mode}"


def install_ci_config(root: Path) -> str:
    """Phase 10 stub. Writes no workflow files; returns a status message.

    When implemented, this detects the forge from the git remote and writes
    the matching CI configuration (GitHub, Forgejo, Bitbucket, or generic).
    """
    return "CI configuration: not implemented (Phase 10)"


__all__ = ["install_ci_config", "install_pre_commit_hook"]

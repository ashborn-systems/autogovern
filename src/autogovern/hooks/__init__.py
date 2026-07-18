"""Pre-commit hook and forge-aware CI writers.

Phase 10 implements:
- ``install_pre_commit_hook``: writes a warning-only pre-commit hook that
  runs the heuristic pass. Never blocks, no LLM, completes in < 500ms.
- ``install_ci_config``: detects the forge from the git remote and writes
  the matching CI configuration (GitHub, Forgejo, Bitbucket, or generic).

Keys are never written to the repo or to config files. The CI writers map
the platform's secret store to the configured key env var and print
instructions for setting it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Pre-commit hook
# ---------------------------------------------------------------------------

_PRE_COMMIT_HOOK_CONTENT = """#!/bin/sh
# autogovern pre-commit hook (warning-only heuristic pass, no LLM, never blocks)
# Installed by `autogovern init`. Re-install with `autogovern hook install`.
autogovern hook run --staged || true
"""

_PRE_PUSH_HOOK_CONTENT = """#!/bin/sh
# autogovern pre-push hook (--local-enforce: full check, LLM included)
# Blocks the push while docs are stale. Installed by `autogovern init --local-enforce`.
echo "[autogovern] running full check before push..."
autogovern check --json || {
    echo "[autogovern] check failed. Run 'autogovern generate' to fix."
    exit 1
}
"""


def install_pre_commit_hook(root: Path, *, local_enforce: bool = False) -> str:
    """Install the pre-commit hook into ``.git/hooks/``.

    The pre-commit hook is warning-only and never blocks (spec requirement).
    When ``local_enforce`` is True, also installs a pre-push hook that runs
    the full ``check`` (LLM included) and blocks on failure.
    """
    git_dir = _find_git_dir(root)
    if git_dir is None:
        return "pre-commit hook: skipped (no .git directory found)"

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Pre-commit hook (warning-only).
    pc_path = hooks_dir / "pre-commit"
    pc_path.write_text(_PRE_COMMIT_HOOK_CONTENT)
    pc_path.chmod(0o755)

    messages = ["pre-commit hook: installed (warning-only)"]

    if local_enforce:
        pp_path = hooks_dir / "pre-push"
        pp_path.write_text(_PRE_PUSH_HOOK_CONTENT)
        pp_path.chmod(0o755)
        messages.append("pre-push hook: installed (--local-enforce, full check)")

    return "; ".join(messages)


# ---------------------------------------------------------------------------
# CI writers
# ---------------------------------------------------------------------------

GITHUB_WORKFLOW = """name: autogovern

on:
  push:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install autogovern
      - run: autogovern check --json
        env:
          {api_key_env}: ${{{{ secrets.{api_key_env} }}}}
"""

FORGEJO_WORKFLOW = """name: autogovern

on:
  push:
  pull_request:

jobs:
  check:
    runs-on: docker
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install autogovern
      - run: autogovern check --json
        env:
          {api_key_env}: ${{{{ secrets.{api_key_env} }}}}
"""

BITBUCKET_PIPELINE = """image: python:3.12

pipelines:
  default:
    - step:
        name: autogovern check
        script:
          - pip install autogovern
          - autogovern check --json
        env:
          {api_key_env}: ${api_key_env}
"""

GENERIC_CI_COMMAND = (
    "pip install autogovern && autogovern check --json\n"
    "# Set the {api_key_env} environment variable in your CI secrets."
)


def install_ci_config(root: Path, *, api_key_env: str = "OPENROUTER_API_KEY") -> str:
    """Detect the forge from the git remote and write CI configuration.

    Returns a status message describing what was written (or printed for
    the generic case).
    """
    forge = detect_forge(root)

    if forge == "github":
        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "autogovern.yml").write_text(GITHUB_WORKFLOW.format(api_key_env=api_key_env))
        return _github_secret_message(api_key_env)
    elif forge == "forgejo":
        wf_dir = root / ".forgejo" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "autogovern.yml").write_text(FORGEJO_WORKFLOW.format(api_key_env=api_key_env))
        return (
            f"CI: wrote .forgejo/workflows/autogovern.yml. "
            f"Set the {api_key_env} secret in repo settings."
        )
    elif forge == "bitbucket":
        bb_path = root / "bitbucket-pipelines.yml"
        if bb_path.exists():
            content = bb_path.read_text()
            if "autogovern" not in content:
                content += "\n" + BITBUCKET_PIPELINE.format(api_key_env=api_key_env)
                bb_path.write_text(content)
        else:
            bb_path.write_text(BITBUCKET_PIPELINE.format(api_key_env=api_key_env))
        return (
            f"CI: wrote bitbucket-pipelines.yml. Set the {api_key_env} "
            f"repository variable in settings."
        )
    else:
        cmd = GENERIC_CI_COMMAND.format(api_key_env=api_key_env)
        indented = cmd.replace("\n", "\n  ")
        return f"CI (generic): add this to your CI config:\n  {indented}"


def detect_forge(root: Path) -> str:
    """Detect the forge from the git remote URL.

    Returns one of: "github", "forgejo", "bitbucket", or "generic".
    """
    remote = _git_remote(root)
    if not remote:
        return "generic"
    remote_lower = remote.lower()
    if "github.com" in remote_lower:
        return "github"
    if "forgejo" in remote_lower or "codeberg.org" in remote_lower:
        return "forgejo"
    if "bitbucket.org" in remote_lower:
        return "bitbucket"
    return "generic"


def _github_secret_message(api_key_env: str) -> str:
    """Return instructions for setting the GitHub secret."""
    if _gh_authenticated():
        return f"CI: wrote .github/workflows/autogovern.yml. Run: gh secret set {api_key_env}"
    return (
        f"CI: wrote .github/workflows/autogovern.yml. "
        f"Set the {api_key_env} secret at: Settings → Secrets and variables → Actions"
    )


def _gh_authenticated() -> bool:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _find_git_dir(root: Path) -> Path | None:
    """Find the .git directory by walking up from root."""
    current = root.resolve()
    for _ in range(20):
        git_dir = current / ".git"
        if git_dir.is_dir():
            return git_dir
        if current == current.parent:
            break
        current = current.parent
    return None


def _git_remote(root: Path) -> str | None:
    """Get the first git remote URL, or None."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


__all__ = [
    "BITBUCKET_PIPELINE",
    "FORGEJO_WORKFLOW",
    "GITHUB_WORKFLOW",
    "GENERIC_CI_COMMAND",
    "detect_forge",
    "install_ci_config",
    "install_pre_commit_hook",
]

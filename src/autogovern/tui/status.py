"""The bare ``autogovern`` status view (the 'git status' move).

Running ``autogovern`` with no arguments prints the repo's governance
state at a glance: docs status, lockfile match, last run summary, and
what to do next. Reads only lockfiles and the last run manifest — no
LLM calls, under 500ms.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text

from autogovern.tui.console import get_console
from autogovern.tui.states import dim, primary

GOVERNANCE_DIR = Path("governance")
CONFIG_DIR = Path(".autogovern")


def print_status(root: Path | None = None) -> None:
    """Print the repo's governance state at a glance."""
    root = root or Path.cwd()
    console = get_console()

    name = root.name
    console.print(primary(f"autogovern · {name}"))
    console.print("")

    docs_state = _docs_state(root)
    lock_state = _lock_state(root)
    last_run = _last_run(root)

    console.print(Text.assemble(dim("  Docs        "), docs_state))
    console.print(Text.assemble(dim("  Lockfile    "), lock_state))
    console.print(Text.assemble(dim("  Last run    "), last_run))
    console.print("")

    if docs_state.plain == "not initialised":
        console.print(dim("  Nothing here yet. Run: autogovern init"))
    elif "stale" in docs_state.plain.lower():
        console.print(dim("  Run: autogovern check --fix"))
    else:
        console.print(dim("  Nothing to do."))


def _docs_state(root: Path) -> Text:
    gov_dir = root / GOVERNANCE_DIR
    if not gov_dir.is_dir():
        return dim("not initialised")
    docs = list(gov_dir.rglob("*.md"))
    if not docs:
        return dim("not initialised")
    return primary(f"{len(docs)} document(s) in governance/")


def _lock_state(root: Path) -> Text:
    """Report lockfile presence honestly: what exists, not what matches.

    Lockfiles live per agent at ``governance/<agent-key>/profile.lock``.
    Verifying they match the working tree requires a full scan (that is
    what ``check`` does); the status view is a sub-500ms glance and only
    claims what it can see.
    """
    gov_dir = root / GOVERNANCE_DIR
    if not gov_dir.is_dir():
        return dim("not written")
    locks = list(gov_dir.glob("*/profile.lock"))
    if not locks:
        return dim("not written")
    return primary(f"written for {len(locks)} agent(s); run `check` to verify currency")


def _last_run(root: Path) -> Text:
    runs_dir = root / CONFIG_DIR / "runs"
    if not runs_dir.is_dir():
        return dim("none")
    manifests = sorted(runs_dir.glob("*.json"), reverse=True)
    if not manifests:
        return dim("none")
    try:
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dim("unreadable")
    command = data.get("command", "?")
    sections = len(data.get("sections_regenerated", []))
    tokens = data.get("token_counts", {}).get("total")
    parts = [command]
    if sections:
        parts.append(f"{sections} section(s)")
    if tokens:
        parts.append(f"{tokens / 1000:.1f}k tokens")
    return dim(" · ".join(parts))


__all__ = ["print_status"]

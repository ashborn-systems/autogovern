"""Verdict panels, summary lines, and error triplets.

These are the high-impact visual moments: the end-of-run summary line,
the ``check`` verdict panel, and the what/why/fix error triplet. Each is
a projection of data the command already produces — no TUI-only
information.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from autogovern.tui.console import get_console, is_plain
from autogovern.tui.states import (
    advisory,
    dim,
    fail_mark,
    material,
    ok_mark,
    primary,
    warn_mark,
)


def summary_line(
    command: str,
    *,
    detail: str = "",
    tokens: int | None = None,
    elapsed: float | None = None,
    ok: bool = True,
) -> None:
    """Print the end-of-run summary line.

    One scannable line the eye can find in CI logs::

        [ OK ] generate · 3 sections regenerated · 12.4k tokens · 18s
    """
    mark = ok_mark() if ok else fail_mark()
    parts: list[Any] = [mark, Text(" "), Text(command)]
    if detail:
        parts.append(Text(f" · {detail}"))
    if tokens:
        parts.append(dim(f" · {tokens / 1000:.1f}k tokens"))
    if elapsed is not None:
        parts.append(dim(f" · {elapsed:.0f}s"))
    get_console().print(Text.assemble(*parts))


def check_verdict(
    *,
    current: bool,
    fixed: bool,
    band: str,
    score: int | None,
    stale_sections: list[str],
    criteria: list[dict[str, Any]] | None = None,
    remediation: str = "",
) -> None:
    """Print the ``check`` verdict as a colour-coded panel or plain line.

    - Current: one plain line, neutral palette (passing earns no colour).
    - Advisory (immaterial): amber accent on the score line.
    - Material: red panel with score, per-criterion bars, stale sections,
      and the fix command.
    """
    console = get_console()

    if current:
        console.print(primary("governance: current"))
        return

    if fixed:
        console.print(
            Text.assemble(
                ok_mark(),
                Text(" "),
                Text(
                    f"check --fix: regenerated {len(stale_sections)} section(s), lockfile updated"
                ),
            )
        )
        return

    if band == "immaterial":
        score_text = f"current (immaterial changes only, score {score})"
        console.print(Text.assemble(warn_mark(), Text(" "), advisory(score_text)))
        return

    # Material: the red-accent panel.
    if is_plain():
        console.print(f"[FAIL] Governance stale · materiality {score}/100")
        if criteria:
            for c in criteria:
                console.print(f"  {c.get('criterion', '?')} · {c.get('score', '?')}")
        if stale_sections:
            console.print(f"  Stale: {', '.join(stale_sections)}")
        if remediation:
            console.print(f"  Fix:  {remediation}")
        return

    # Rich panel with bars.
    lines: list[Any] = [material(f"Governance stale · materiality {score}/100"), Text("")]

    if criteria:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("criterion", style="white")
        table.add_column("bar")
        table.add_column("type", style="dim")
        for c in criteria:
            c_score = c.get("score", 0)
            bar = _score_bar(c_score)
            table.add_row(c.get("criterion", "?"), bar, dim(c.get("reasoning", "")).plain)
        lines.append(table)
        lines.append(Text(""))

    if stale_sections:
        lines.append(dim(f"Stale: {', '.join(stale_sections)}"))
        lines.append(Text(""))

    if remediation:
        lines.append(dim("Fix: "))
        lines.append(Text(f"  {remediation}", style="bold"))

    console.print(Panel(Text.assemble(*_flatten(lines)), border_style="red", padding=(0, 1)))


def _score_bar(score: int, width: int = 10) -> Text:
    """A compact bar list for a materiality criterion."""
    filled = score * width // 100
    bar = "█" * filled + "░" * (width - filled)
    return Text(bar, style="red")


def _flatten(items: list[Any]) -> list[Any]:
    """Flatten nested lists into a single list for Text.assemble."""
    out: list[Any] = []
    for item in items:
        if isinstance(item, list):
            out.extend(item)
        else:
            out.append(item)
    return out


def error_triplet(what: str, why: str, fix: str, *, partial: str = "") -> None:
    """Print a what / why / fix error, with optional degraded-mode note.

    ::
        [FAIL] Model provider unreachable (api.openrouter.ai timed out)
          Generation needs the model; the heuristic pass still ran.
          Fix: check OPENROUTER_API_KEY is set, or retry with --model <id>
    """
    console = get_console()
    console.print(Text.assemble(fail_mark(), Text(" "), material(what)))
    if partial:
        console.print(dim(f"  {partial}"))
    console.print(dim(f"  {why}"))
    console.print(Text(f"  Fix:  {fix}", style="bold" if not is_plain() else ""))


def init_summary(
    *,
    config_path: Path,
    context_path: Path,
    overwritten: bool,
    hook_message: str,
    ci_message: str,
) -> None:
    """Print the post-init 'what happens next' panel."""
    console = get_console()
    console.print(ok_mark(), Text(" init complete"))
    console.print(dim(f"  wrote {config_path}"))
    console.print(dim(f"  wrote {context_path}"))
    if overwritten:
        console.print(dim("  overwrote existing files"))
    if hook_message:
        console.print(dim(f"  {hook_message}"))
    if ci_message:
        console.print(dim(f"  {ci_message}"))
    console.print("")
    console.print(primary("Next steps:"))
    console.print(dim("  1. autogovern scan      # build the AgentProfile and AgentCard"))
    console.print(dim("  2. autogovern generate  # write the governance document set"))


__all__ = ["check_verdict", "error_triplet", "init_summary", "summary_line"]

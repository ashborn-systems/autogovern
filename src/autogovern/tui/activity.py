"""Live activity line and stage checklist.

During multi-stage commands (scan, generate, check), the CLI renders:

1. A stage checklist — completed stages dim to ``[ OK ]`` with their
   headline result, the active stage shows ``[ .. ]``, pending stages
   sit at ``[ -- ]``.
2. A live activity line beneath the active stage — a spinner, a rotating
   status message, and real counters (files, sections, tokens, elapsed).

In plain mode (CI, piped, NO_COLOR), the spinner is replaced by
timestamped log lines — one per stage transition.

Progressive elaboration: after 5s the activity line gains detail; after
15s it adds ``still working (model latency)`` so slow calls never look
like hangs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Group, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from autogovern.tui.catalogue import message_for
from autogovern.tui.console import get_console, is_plain
from autogovern.tui.states import active_mark, dim, ok_mark, pending_mark


@dataclass
class Stage:
    """One stage in a pipeline checklist."""

    name: str
    label: str
    status: str = "pending"  # pending, active, done
    result: str = ""  # headline result when done, e.g. "12 files · 2 tools"

    @property
    def mark(self) -> Text:
        if self.status == "done":
            return ok_mark()
        if self.status == "active":
            return active_mark()
        return pending_mark()


@dataclass
class StageTracker:
    """Tracks pipeline stages and renders the live checklist + activity line.

    Usage::

        tracker = StageTracker([Stage("scan", "Scan"), Stage("generate", "Generate")])
        tracker.start()
        tracker.begin("scan")
        ... do scan work ...
        tracker.complete("scan", "12 files · 2 tools")
        tracker.begin("generate")
        ... do generate work ...
        tracker.complete("generate", "3 sections · 12.4k tokens · 18s")
        tracker.stop()
    """

    stages: list[Stage]
    _live: Live | None = None
    _start_time: float = 0.0
    _stage_start: dict[str, float] = field(default_factory=dict)
    _counters: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Begin rendering the checklist. In plain mode, prints a header."""
        self._start_time = time.time()
        if is_plain():
            get_console().print(dim(f"[start] {len(self.stages)} stages"))
            return
        self._live = Live(self._render(), console=get_console(), refresh_per_second=10)
        self._live.start()

    def begin(self, name: str) -> None:
        """Mark a stage as active and start its timer."""
        for stage in self.stages:
            if stage.name == name:
                stage.status = "active"
                self._stage_start[name] = time.time()
                break
        if is_plain():
            get_console().print(dim(f"[begin] {name}"))
        elif self._live is not None:
            self._live.update(self._render())

    def set_counters(self, **kwargs: Any) -> None:
        """Update the live counters shown on the activity line."""
        self._counters.update(kwargs)
        if not is_plain() and self._live is not None:
            self._live.update(self._render())

    def complete(self, name: str, result: str = "") -> None:
        """Mark a stage as done with a headline result."""
        for stage in self.stages:
            if stage.name == name:
                stage.status = "done"
                stage.result = result
                break
        if is_plain():
            elapsed = time.time() - self._stage_start.get(name, time.time())
            line = f"[done]  {name}"
            if result:
                line += f" · {result}"
            line += f" · {elapsed:.0f}s"
            get_console().print(dim(line))
        elif self._live is not None:
            self._live.update(self._render())

    def stop(self) -> None:
        """Stop rendering. In plain mode, prints nothing (stages already logged)."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _render(self) -> RenderableType:
        """Render the checklist plus the activity line."""
        lines: list[RenderableType] = []
        active_stage: Stage | None = None
        for stage in self.stages:
            line = Text()
            line.append(stage.mark)
            line.append(" ")
            line.append(stage.label.ljust(10))
            if stage.status == "done" and stage.result:
                line.append("  ")
                line.append(dim(stage.result))
            lines.append(line)
            if stage.status == "active":
                active_stage = stage

        if active_stage is not None:
            lines.append(self._activity_line(active_stage))

        return Group(*lines)

    def _activity_line(self, stage: Stage) -> RenderableType:
        """The spinner + message + counters line for the active stage."""
        elapsed = time.time() - self._stage_start.get(stage.name, time.time())
        msg = message_for(stage.name)

        # Progressive elaboration.
        counter_strs = self._format_counters(elapsed)
        counter_text = f" ({counter_strs})" if counter_strs else ""
        latency = " still working (model latency)" if elapsed > 15 else ""
        line = f"{msg}{counter_text}{latency}"

        if is_plain():
            return Text(line)
        return Group(Spinner("dots", text=Text(line), style="dim"))

    def _format_counters(self, elapsed: float) -> str:
        """Format the live counters as a comma-separated string."""
        bits: list[str] = []
        c = self._counters
        if "sections" in c and "total" in c and c["total"]:
            bits.append(f"{c['sections']}/{c['total']} sections")
        if "files" in c:
            bits.append(f"{c['files']} files")
        if "tokens" in c and c["tokens"]:
            bits.append(f"{c['tokens'] / 1000:.1f}k tokens")
        bits.append(f"{elapsed:.0f}s")
        return ", ".join(bits)


__all__ = ["Stage", "StageTracker"]

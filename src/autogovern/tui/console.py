"""Console factory and TTY/plain mode detection.

One :class:`rich.console.Console` instance is shared across a command run.
When stdout is not a terminal (piped, CI) or ``NO_COLOR`` is set, the
console is forced to plain text with no styling, no unicode, and no
spinners. A ``--plain`` flag on the CLI can force this on; there is no
force-on path because CI output should never carry colour.

The detection is checked once per run and cached; the console itself is a
module-level singleton so all output goes to one place.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache

from rich.console import Console

# Module-level singleton. Built on first call to get_console().
_console: Console | None = None


def get_console() -> Console:
    """Return the shared console, building it on first call."""
    global _console
    if _console is None:
        _console = Console(
            force_terminal=not is_plain(),
            force_interactive=not is_plain(),
            no_color=is_plain(),
            color_system=None if is_plain() else "auto",
            highlight=False,
            soft_wrap=False,
            width=80 if is_plain() else None,
        )
    return _console


@lru_cache(maxsize=1)
def is_plain() -> bool:
    """True when output should be plain (no colour, no spinners, ASCII only).

    Triggers: ``NO_COLOR`` env var, stdout not a TTY, or the ``AUTOVERN_PLAIN``
    flag set by the ``--plain`` CLI option. Cached because it does not change
    during a run.
    """
    if "NO_COLOR" in os.environ:
        return True
    if os.environ.get("AUTOGOVERN_PLAIN") == "1":
        return True
    return not sys.stdout.isatty()


def enable_plain() -> None:
    """Force plain mode for this run (wired to the ``--plain`` flag)."""
    os.environ["AUTOGOVERN_PLAIN"] = "1"
    is_plain.cache_clear()
    global _console
    _console = None


__all__ = ["enable_plain", "get_console", "is_plain"]

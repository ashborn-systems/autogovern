"""The terminal user interface layer.

A rendering surface over the data the CLI already produces. Every visual
is a projection of the same objects ``--json`` emits (principle: visuals
never diverge from data). The layer auto-disables styling when stdout is
not a TTY or ``NO_COLOR`` is set, so CI and piped output stay clean.

Components:

- :mod:`autogovern.tui.console` — console factory, TTY/plain detection
- :mod:`autogovern.tui.states` — bracketed state marks and the palette
- :mod:`autogovern.tui.catalogue` — rotating status messages from data
- :mod:`autogovern.tui.activity` — live activity line and stage checklist
- :mod:`autogovern.tui.panels` — verdict panels, summaries, error triplets
- :mod:`autogovern.tui.status` — the bare ``autogovern`` status view
"""

from autogovern.tui.console import enable_plain, get_console, is_plain

__all__ = ["enable_plain", "get_console", "is_plain"]

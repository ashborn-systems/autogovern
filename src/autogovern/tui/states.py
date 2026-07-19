"""Bracketed state marks and the neutral palette.

The palette is grey and white by default. Colour is reserved for moments
that require a decision or action, and its scarcity is what gives it force:

- **red** — material finding or failure requiring action
- **amber** — attention item or advisory the user should know about

Nothing else is coloured. Success reads as calm plain white, not
celebration. A screen with any colour on it means something needs the
user; a fully grey/white screen means all is well.

State marks are plain ASCII brackets so every environment renders
identically — no fallback tier exists:

    [ OK ]   done
    [ .. ]   active (alongside the spinner)
    [ -- ]   pending
    [WARN]   attention
    [FAIL]   error
"""

from __future__ import annotations

from rich.text import Text

from autogovern.tui.console import is_plain

# State marks: fixed-width so they self-align into a scannable column.
OK = "[ OK ]"
ACTIVE = "[ .. ]"
PENDING = "[ -- ]"
WARN = "[WARN]"
FAIL = "[FAIL]"

# Rich style names. In plain mode these render as plain text (no colour).
_STYLE_RED = "bold red"
_STYLE_AMBER = "bold yellow"
_STYLE_DIM = "dim"
_STYLE_PLAIN = ""


def _styled(text: str, style: str) -> Text:
    """Return a Text with style, or plain when in plain mode."""
    if is_plain() or not style:
        return Text(text)
    return Text(text, style=style)


def ok_mark() -> Text:
    return Text(OK, style=_STYLE_DIM if not is_plain() else "")


def active_mark() -> Text:
    return Text(ACTIVE)


def pending_mark() -> Text:
    return Text(PENDING, style=_STYLE_DIM if not is_plain() else "")


def warn_mark() -> Text:
    return _styled(WARN, _STYLE_AMBER)


def fail_mark() -> Text:
    return _styled(FAIL, _STYLE_RED)


def dim(text: str) -> Text:
    """Secondary text in the dim style, or plain in plain mode."""
    return Text(text, style=_STYLE_DIM if not is_plain() else "")


def primary(text: str) -> Text:
    """Primary text, always plain white (no styling needed)."""
    return Text(text)


def material(text: str) -> Text:
    """Material-finding or failure text in red."""
    return _styled(text, _STYLE_RED)


def advisory(text: str) -> Text:
    """Advisory or attention text in amber."""
    return _styled(text, _STYLE_AMBER)


__all__ = [
    "ACTIVE",
    "FAIL",
    "OK",
    "PENDING",
    "WARN",
    "active_mark",
    "advisory",
    "dim",
    "fail_mark",
    "material",
    "ok_mark",
    "pending_mark",
    "primary",
    "warn_mark",
]

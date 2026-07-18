"""Atomic file writer for generated documents.

Content-addressed: a file is written only when its intended content differs
from what is on disk. This is the foundation of the idempotence gate: a
second ``generate`` with no input changes produces zero writes and therefore
zero git diff. It also means regeneration failure leaves existing files
intact.
"""

from __future__ import annotations

from pathlib import Path


def write_if_changed(path: Path, content: str) -> bool:
    """Write ``content`` to ``path`` atomically, only if it differs.

    Returns True if the file was written (new or changed), False if it was
    unchanged and left untouched.
    """
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return True


__all__ = ["write_if_changed"]

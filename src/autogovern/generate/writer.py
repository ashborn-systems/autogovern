"""Atomic file writing for generated documents.

Two layers:

- :func:`write_if_changed` — single-file, content-addressed, atomic via
  same-directory rename. The foundation of the idempotence gate: a second
  ``generate`` with no input changes produces zero writes and therefore
  zero git diff.
- :class:`WriteSet` — a staged set of writes committed as one batch. The
  engine renders everything (LLM calls included) into a WriteSet first and
  commits only when every stage succeeded, so a provider failure mid-run
  leaves the governance directory exactly as it was (the spec's "no partial
  writes" guarantee). A commit that itself fails rolls back the files it
  already wrote.
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
    _atomic_write(path, content)
    return True


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` via a same-directory rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


class WriteSet:
    """A batch of intended writes, applied together by :meth:`commit`.

    Staging is free: ``add`` only records path and content. ``commit``
    skips unchanged files (the idempotence gate), writes the rest
    atomically, and returns the paths actually written. If any write fails,
    every file written so far is restored to its original bytes (new files
    are removed) and the exception propagates — no partial state.
    """

    def __init__(self) -> None:
        self._writes: dict[Path, str] = {}

    def add(self, path: Path, content: str) -> None:
        """Stage ``content`` for ``path``. A later add for the same path wins."""
        self._writes[path] = content

    def commit(self) -> list[Path]:
        """Apply every staged write, rolling back on any failure.

        Returns the list of paths actually written (unchanged files are
        skipped, so a no-change commit returns an empty list).
        """
        originals: dict[Path, bytes | None] = {}
        written: list[Path] = []
        try:
            for path, content in self._writes.items():
                if path.is_file() and path.read_text(encoding="utf-8") == content:
                    continue
                originals[path] = path.read_bytes() if path.is_file() else None
                _atomic_write(path, content)
                written.append(path)
        except OSError:
            for path, original in originals.items():
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            raise
        return written


__all__ = ["WriteSet", "write_if_changed"]

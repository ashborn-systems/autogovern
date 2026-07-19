"""Rotating status messages, loaded from a YAML data file.

Messages live in ``messages.yaml`` so adding a message is a data change,
not a code change (acceptance criterion #5). Each stage has a pool of
messages; one is picked at random per invocation. Every message truthfully
names the stage's actual work — charm comes from phrasing, never from
fiction.
"""

from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import yaml

_MESSAGES_FILE = Path(__file__).parent / "messages.yaml"


@lru_cache(maxsize=1)
def _load_catalogue() -> dict[str, list[str]]:
    """Load the message catalogue, cached for the run."""
    raw = yaml.safe_load(_MESSAGES_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {stage: list(msgs) for stage, msgs in raw.items() if isinstance(msgs, list)}


def message_for(stage: str) -> str:
    """Pick a rotating status message for ``stage``.

    Falls back to the stage name itself if the catalogue has no entry, so
    a missing stage never breaks output.
    """
    pool = _load_catalogue().get(stage, [])
    if not pool:
        return stage.replace("_", " ") + "…"
    return random.choice(pool)


__all__ = ["message_for"]

"""Run manifest writer: observability for every command.

Every scan, generate, check, and diff writes a run manifest to
``.autogovern/runs/<timestamp>.json``. The manifest is the audit trail:
command, tool version, config snapshot (minus secrets), input hashes,
sections regenerated and why, model id, token counts, materiality scores.

Token counts are present when the provider reports usage; null (not
fabricated) when it does not. No secret values ever appear in a manifest.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autogovern.models import RunManifest

RUNS_DIR = Path(".autogovern") / "runs"


def write_manifest(
    root: Path,
    manifest: RunManifest,
) -> Path:
    """Write a run manifest to ``.autogovern/runs/<timestamp>.json``.

    Returns the path to the written file.
    """
    runs_dir = root / RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (
        manifest.command.replace(" ", "_") + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    path = runs_dir / f"{timestamp}.json"
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_manifest(
    command: str,
    config: Any,
    *,
    sections_regenerated: list[dict[str, Any]] | None = None,
    input_hashes: dict[str, str] | None = None,
    model_id: str | None = None,
    token_counts: dict[str, int | None] | None = None,
    prompt_template_versions: dict[str, str] | None = None,
    materiality: dict[str, Any] | None = None,
) -> RunManifest:
    """Build a RunManifest with a config snapshot minus secrets.

    The config snapshot strips the api_key_env value (the env var name is
    kept, but the actual key is never in config to begin with — it's read
    from the environment at call time).
    """
    from autogovern.models import (
        MaterialityCriterion,
        MaterialityResult,
        SectionRegeneration,
        TokenCounts,
    )

    # Config snapshot: model_provider without the key (which is never stored
    # in config anyway, but we strip the env var name too for safety).
    config_snapshot: dict[str, Any] = {}
    if hasattr(config, "model_dump"):
        raw = config.model_dump(mode="json")
        mp = raw.get("model_provider", {})
        config_snapshot = {
            "model_provider": {
                "api_base": mp.get("api_base"),
                "model": mp.get("model"),
                # Don't include the env var name in the snapshot.
            },
            "thresholds": raw.get("thresholds"),
        }

    sections: list[SectionRegeneration] = []
    if sections_regenerated:
        for s in sections_regenerated:
            sections.append(
                SectionRegeneration(
                    section=s.get("section", ""),
                    changed_input=s.get("changed_input", ""),
                )
            )

    tc: TokenCounts | None = None
    if token_counts:
        tc = TokenCounts(
            prompt=token_counts.get("prompt"),
            completion=token_counts.get("completion"),
            total=token_counts.get("total"),
        )

    mat: MaterialityResult | None = None
    if materiality:
        criteria = [MaterialityCriterion(**c) for c in materiality.get("criteria", [])]
        mat = MaterialityResult(
            score=materiality.get("score", 0),
            band=materiality.get("band", ""),
            criteria=criteria,
        )

    return RunManifest(
        command=command,
        tool_version=_tool_version(),
        config_snapshot=config_snapshot,
        input_hashes=input_hashes or {},
        sections_regenerated=sections,
        model_id=model_id,
        token_counts=tc,
        prompt_template_versions=prompt_template_versions or {},
        materiality=mat,
    )


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("autogovern")
    except Exception:  # pragma: no cover
        return "0.0.0+dev"


def read_manifests(root: Path) -> list[Path]:
    """List all run manifest files, oldest first."""
    runs_dir = root / RUNS_DIR
    if not runs_dir.is_dir():
        return []
    return sorted(runs_dir.glob("*.json"))


__all__ = [
    "RUNS_DIR",
    "build_manifest",
    "read_manifests",
    "write_manifest",
]

"""The ``check`` command: CI gate for stale governance documentation.

Five-step sequence from the spec:
1. Rebuild the AgentProfile from the current code (scan)
2. Diff it against the committed ``profile.lock``
3. No diff: exit 0, print "governance: current". No LLM call
4. Diff: score it (deterministic rules first, semantic pass for the remainder).
   Score >= material threshold means docs no longer describe the agent: exit 1
   with the score, stale sections, and the remediation command
5. With ``--fix``, skip the exit and regenerate the stale sections plus the
   updated lockfile immediately, ready to commit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autogovern.detect import DetectionResult, detect_material_change
from autogovern.frameworks import Pack, load_pack, to_graph_input
from autogovern.generate import GOVERNANCE_DIR, generate_docs
from autogovern.generate.lockfile import read_context_lock, read_lockfile
from autogovern.ingest import scan_repo
from autogovern.models import Config, ContextManifest
from autogovern.provider import ProviderClient


@dataclass
class CheckResult:
    """The outcome of a check run."""

    current: bool
    score: int = 0
    band: str = "immaterial"
    stale_sections: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)
    remediation: str = ""
    fixed: bool = False
    strict: bool = False
    detection: DetectionResult | None = None

    @property
    def exit_code(self) -> int:
        """The single source of truth for the CLI exit code.

        0: current, fixed, immaterial (passes silently per the spec), or
           advisory without --strict.
        1: material, or advisory with --strict.
        """
        if self.current or self.fixed:
            return 0
        if self.band == "immaterial":
            return 0
        if self.band == "advisory" and not self.strict:
            return 0
        return 1

    def to_dict(self) -> dict[str, object]:
        return {
            "current": self.current,
            "score": self.score,
            "band": self.band,
            "stale_sections": self.stale_sections,
            "changed_fields": self.changed_fields,
            "remediation": self.remediation,
            "fixed": self.fixed,
        }


def run_check(
    root: Path,
    config: Config,
    context: ContextManifest,
    *,
    provider: ProviderClient,
    strict: bool = False,
    fix: bool = False,
    pack: Pack | None = None,
    context_from_file: bool = True,
) -> CheckResult:
    """Run the check sequence and optionally fix in place.

    Args:
        root: Repository root.
        config: The autogovern config.
        context: The organisational context manifest.
        provider: The provider client (for semantic scoring and --fix).
        strict: Treat advisory-band scores as failures.
        fix: Regenerate stale sections and update the lockfile.
        pack: Optional pre-loaded pack.
        context_from_file: Whether context came from a file (vanilla mode flag).
    """
    pack = pack or load_pack()
    governance_dir = root / GOVERNANCE_DIR

    # Step 1: rebuild the profile.
    scan_result = scan_repo(root, config, provider=provider, write_card=False)
    if not scan_result.signals_found or scan_result.profile is None:
        return CheckResult(
            current=True,
            remediation="no agent signals found; nothing to check",
        )
    current_profile = scan_result.profile

    # Step 2: diff against the lockfiles.
    locked_profile = read_lockfile(governance_dir)
    locked_context = read_context_lock(governance_dir)

    # Step 3-4: detect and score.
    detection = detect_material_change(
        changed_files=[],  # CI mode: always run the profile diff
        config=config,
        locked_profile=locked_profile,
        current_profile=current_profile,
        locked_context=locked_context,
        current_context=context,
        provider=provider,
        ci_mode=True,
    )

    if not detection.changed or detection.materiality is None:
        return CheckResult(current=True, detection=detection)

    materiality = detection.materiality
    changed_fields = [
        fd.field for fd in (detection.profile_diff.fields if detection.profile_diff else [])
    ]

    # Map changed fields to affected document sections via the dependency graph.
    stale_sections = _stale_sections(changed_fields, pack)

    result = CheckResult(
        current=False,
        score=materiality.score,
        band=materiality.band,
        stale_sections=stale_sections,
        changed_fields=changed_fields,
        remediation=(
            f"autogovern generate  # regenerate: {', '.join(stale_sections) or 'affected sections'}"
        ),
        detection=detection,
    )

    result.strict = strict

    # Step 5: --fix regenerates in place.
    if fix:
        generate_docs(
            root,
            config,
            current_profile,
            context,
            provider=provider,
            pack=pack,
            context_from_file=context_from_file,
            materiality=detection.materiality,
        )
        result.fixed = True

    return result


def _stale_sections(changed_fields: list[str], pack: Pack) -> list[str]:
    """Map changed profile/context fields to affected documents via the graph."""
    sections: set[str] = set()
    for changed in changed_fields:
        graph_input = to_graph_input(changed)
        if graph_input:
            sections.update(pack.graph.affected_documents(graph_input))
    return sorted(sections)


__all__ = ["CheckResult", "run_check"]

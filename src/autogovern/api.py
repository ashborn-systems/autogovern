"""Public library API for autogovern.

Platform callers and programmatic users import these functions instead of
the CLI. The CLI itself is refactored to call these, so the library and the
CLI share one code path.

Functions:
    scan(root, config, *, provider=None) -> ScanResult
    generate_docs(root, config, profile, context, *, provider, ...) -> GenerationResult
    check(root, config, context, *, provider, ...) -> CheckResult
"""

from __future__ import annotations

from pathlib import Path

from autogovern.check import CheckResult, run_check
from autogovern.generate import GenerationResult, generate_docs
from autogovern.generate.lockfile import read_lockfile
from autogovern.ingest import ScanResult, scan_repo
from autogovern.models import AgentProfile, Config, ContextManifest
from autogovern.provider import ProviderClient, build_provider

__all__ = [
    "CheckResult",
    "GenerationResult",
    "ScanResult",
    "build_provider",
    "check",
    "generate_docs",
    "load_profile",
    "scan",
]


def scan(root: Path, config: Config, *, provider: ProviderClient | None = None) -> ScanResult:
    """Scan a repo and build its AgentProfile.

    The public wrapper around :func:`autogovern.ingest.scan_repo`. If
    ``provider`` is None, one is built from config and owned by this call.
    """
    return scan_repo(root, config, provider=provider, write_card=False)


def load_profile(path: Path) -> AgentProfile:
    """Load an AgentProfile from a JSON file (headless input)."""
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    return AgentProfile.model_validate(raw)


def check(
    root: Path,
    config: Config,
    context: ContextManifest,
    *,
    provider: ProviderClient,
    strict: bool = False,
    fix: bool = False,
    context_from_file: bool = True,
    profile: AgentProfile | None = None,
) -> CheckResult:
    """Run the check sequence.

    When ``profile`` is given (headless mode), it is used instead of scanning
    the repo. This is the path platform callers use: they supply a profile
    JSON directly, bypassing the filesystem scan.
    """
    if profile is not None:
        return _check_headless(
            root, config, context, provider, profile, strict, fix, context_from_file
        )
    return run_check(
        root,
        config,
        context,
        provider=provider,
        strict=strict,
        fix=fix,
        context_from_file=context_from_file,
    )


def _check_headless(
    root: Path,
    config: Config,
    context: ContextManifest,
    provider: ProviderClient,
    current_profile: AgentProfile,
    strict: bool,
    fix: bool,
    context_from_file: bool,
) -> CheckResult:
    """Check using a supplied profile instead of scanning the repo."""
    from autogovern.detect import detect_material_change
    from autogovern.frameworks import load_pack

    pack = load_pack()
    governance_dir = root / "governance"
    locked_profile = read_lockfile(governance_dir)

    detection = detect_material_change(
        changed_files=[],
        config=config,
        locked_profile=locked_profile,
        current_profile=current_profile,
        provider=provider,
        ci_mode=True,
    )

    if not detection.changed or detection.materiality is None:
        return CheckResult(current=True, detection=detection)

    from autogovern.check import _stale_sections

    materiality = detection.materiality
    changed_fields = [
        fd.field for fd in (detection.profile_diff.fields if detection.profile_diff else [])
    ]
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

    if fix:
        generate_docs(
            root,
            config,
            current_profile,
            context,
            provider=provider,
            pack=pack,
            context_from_file=context_from_file,
        )
        result.fixed = True

    if strict and result.band == "advisory":
        return CheckResult(
            current=False,
            score=materiality.score,
            band="advisory",
            stale_sections=stale_sections,
            changed_fields=changed_fields,
            remediation="autogovern generate  # advisory: regenerate to clear",
            detection=detection,
        )

    return result

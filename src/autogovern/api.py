"""Public library API for autogovern.

Thin wrappers over the package entry points so library callers (tests,
enterprise consumers, automation) get a stable surface without importing
internals.

Public API:
    scan(root, config, *, provider=None) -> ScanResult
    load_profile(path) -> AgentProfile
    check(root, config, context, *, provider, ...) -> CheckResult
    generate_docs(root, config, scan_result, context, *, provider, ...) -> GenerationResult
"""

from __future__ import annotations

from pathlib import Path

from autogovern.check import CheckResult, run_check
from autogovern.generate import generate_docs
from autogovern.generate.lockfile import read_context_lock, read_lockfile
from autogovern.ingest import ScannedAgent, ScanResult, scan_repo
from autogovern.models import AgentProfile, Config, ContextManifest
from autogovern.provider import ProviderClient, build_provider

__all__ = [
    "CheckResult",
    "ScanResult",
    "build_provider",
    "check",
    "generate_docs",
    "load_profile",
    "scan",
]


def scan(root: Path, config: Config, *, provider: ProviderClient | None = None) -> ScanResult:
    """Scan a repo and build an AgentProfile for every agent root.

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
    JSON directly, bypassing the filesystem scan. In the multi-agent model
    this is the degenerate single-agent case.
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
    """Check using a supplied profile instead of scanning the repo.

    The supplied profile is wrapped in a single-agent ScanResult — the
    degenerate case of the multi-agent model. The lockfile is read from the
    agent's governance subdirectory.
    """
    from autogovern.check import _slug, _stale_sections
    from autogovern.detect import detect_material_change
    from autogovern.frameworks import load_pack

    pack = load_pack()
    slug = _slug(current_profile.name)
    agent_gov_dir = root / "governance" / slug
    locked_profile = read_lockfile(agent_gov_dir)
    locked_context = read_context_lock(agent_gov_dir)

    # Build a per-agent context for the diff (project + this agent's portion).
    from autogovern.check import _default_agent_context

    agent_context = context.agents.get(current_profile.name, _default_agent_context())
    agent_manifest = ContextManifest(
        project=context.project, agents={current_profile.name: agent_context}
    )

    detection = detect_material_change(
        changed_files=[],
        config=config,
        locked_profile=locked_profile,
        current_profile=current_profile,
        locked_context=locked_context,
        current_context=agent_manifest,
        provider=provider,
        ci_mode=True,
    )

    if not detection.changed or detection.materiality is None:
        return CheckResult(current=True, detection=detection)

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
        strict=strict,
        detection=detection,
    )

    if fix:
        scanned = ScannedAgent(
            name=current_profile.name,
            root=".",
            profile=current_profile,
            card_written=False,
            card_path=None,
        )
        scan_result = ScanResult(agents=[scanned], root=str(root))
        generate_docs(
            root,
            config,
            scan_result,
            context,
            provider=provider,
            pack=pack,
            context_from_file=context_from_file,
        )
        result.fixed = True

    return result

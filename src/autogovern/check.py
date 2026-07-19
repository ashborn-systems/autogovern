"""The ``check`` command: CI gate for stale governance documentation.

Five-step sequence from the spec:
1. Rebuild the profile for every agent (scan)
2. Diff each against its committed ``profile.lock``
3. No diff: exit 0, print "governance: current". No LLM call
4. Diff: score it (deterministic rules first, semantic pass for the remainder).
   Score >= material threshold means docs no longer describe the agent: exit 1
   with the score, stale sections, and the remediation command
5. With ``--fix``, skip the exit and regenerate the stale sections plus the
   updated lockfile immediately, ready to commit

Multi-agent: checks every agent in the repo. Exit code is the worst across
all agents (1 if any is stale).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autogovern.context.defaults import default_agent_context
from autogovern.detect import DetectionResult, detect_material_change
from autogovern.frameworks import Pack, load_pack, to_graph_input
from autogovern.generate import GOVERNANCE_DIR, generate_docs
from autogovern.generate.lockfile import read_context_lock, read_lockfile
from autogovern.ingest import ScannedAgent, scan_repo
from autogovern.models import Config, ContextManifest
from autogovern.provider import ProviderClient


@dataclass
class AgentVerdict:
    """One agent's verdict within a check run."""

    key: str
    name: str
    current: bool
    score: int = 0
    band: str = "immaterial"
    stale_sections: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)
    fixed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "current": self.current,
            "score": self.score,
            "band": self.band,
            "stale_sections": self.stale_sections,
            "changed_fields": self.changed_fields,
            "fixed": self.fixed,
        }


@dataclass
class CheckResult:
    """The outcome of a check run.

    The top-level fields describe the worst agent (the one that decides the
    exit code); ``per_agent`` carries every agent's individual verdict so
    multi-agent repos see the full picture in one run.
    """

    current: bool
    score: int = 0
    band: str = "immaterial"
    stale_sections: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)
    remediation: str = ""
    fixed: bool = False
    strict: bool = False
    detection: DetectionResult | None = None
    per_agent: list[AgentVerdict] = field(default_factory=list)

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
            "agents": [v.to_dict() for v in self.per_agent],
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
    """Run the check sequence across all agents and optionally fix in place.

    Returns the worst result across all agents (exit code 1 if any is stale).
    """
    pack = pack or load_pack()
    governance_dir = root / GOVERNANCE_DIR

    # The lock resolver lets the scanner reuse locked LLM summaries for
    # agents whose free-text sources are unchanged: a clean check then
    # makes zero LLM calls, as the spec requires.
    scan_result = scan_repo(
        root,
        config,
        provider=provider,
        write_card=False,
        lock_resolver=lambda key: read_lockfile(governance_dir / key),
    )
    if not scan_result.agents:
        return CheckResult(
            current=True,
            remediation="no agent signals found; nothing to check",
        )

    results: list[CheckResult] = []
    for scanned in scan_result.agents:
        agent_result = _check_one_agent(governance_dir, config, context, provider, scanned, pack)
        agent_result.strict = strict
        results.append(agent_result)

    if fix and any(not r.current for r in results):
        # One generation pass over the FULL scan result: the engine's
        # incremental logic regenerates exactly the stale sections per agent
        # and writes the project-level docs (REGISTER, QUICKSTART, ...) from
        # the complete agent set. Fixing agent-by-agent would rewrite those
        # shared docs once per agent, each time seeing only one agent.
        generate_docs(
            root,
            config,
            scan_result,
            context,
            provider=provider,
            pack=pack,
            context_from_file=context_from_file,
        )
        for r in results:
            if not r.current:
                r.fixed = True

    verdicts = [
        AgentVerdict(
            key=scanned.key,
            name=scanned.name,
            current=r.current,
            score=r.score,
            band=r.band,
            stale_sections=r.stale_sections,
            changed_fields=r.changed_fields,
            fixed=r.fixed,
        )
        for scanned, r in zip(scan_result.agents, results, strict=True)
    ]

    worst: CheckResult | None = None
    for agent_result in results:
        if worst is None or agent_result.exit_code > worst.exit_code:
            worst = agent_result

    if worst is None:
        return CheckResult(current=True)
    worst.per_agent = verdicts
    return worst


def _check_one_agent(
    governance_dir: Path,
    config: Config,
    context: ContextManifest,
    provider: ProviderClient,
    scanned: ScannedAgent,
    pack: Pack,
) -> CheckResult:
    """Check one agent against its lockfile."""
    agent_gov_dir = governance_dir / scanned.key
    current_profile = scanned.profile

    locked_profile = read_lockfile(agent_gov_dir)
    locked_context = read_context_lock(agent_gov_dir)

    # Build this agent's context for the diff (project + this agent's portion).
    agent_context = context.agents.get(scanned.key, default_agent_context())
    agent_manifest = ContextManifest(project=context.project, agents={scanned.key: agent_context})

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

    return CheckResult(
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


def _stale_sections(changed_fields: list[str], pack: Pack) -> list[str]:
    """Map changed profile/context fields to affected documents via the graph."""
    sections: set[str] = set()
    for changed in changed_fields:
        graph_input = to_graph_input(changed)
        if graph_input:
            sections.update(pack.graph.affected_documents(graph_input))
    return sorted(sections)


__all__ = ["AgentVerdict", "CheckResult", "run_check"]

# Changelog

All notable changes to autogovern are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] - 2026-07-19

### Changed — multi-agent from the ground up

The tool now operates at project level, governing multiple agents in one
repo. This is a fundamental redesign, not a bolt-on: agents are first-class
collections at every layer. Single-agent-at-root is the N=1 case through the
same code path — no branches, no special cases, no shims.

- **Discovery** walks the repo recursively, finding agent roots by strong
  signals (instruction files, MCP configs, agent cards). Each agent root gets
  its own `AgentDiscovery`. The old `_first()` hack that picked one signal is
  gone.
- **ScanResult** carries `agents: list[ScannedAgent]` instead of a single
  `profile`. Each `ScannedAgent` has a name, root, profile, and card status.
- **ContextManifest** is `{project, agents: dict[str, AgentContext]}` — one
  project context, per-agent contexts keyed by name. The old `agent:`
  singular field is gone (clean break, no format shims).
- **generate_docs** takes a `ScanResult` and maps over agents. Each agent gets
  its own governance subdirectory (`governance/<agent-slug>/`) with its doc
  set and lockfiles. Project-level docs (`REGISTER.md`, `QUICKSTART.md`,
  `ATTENTION.md`, `CHANGELOG.md`) sit at `governance/`.
- **check / diff** iterate agents, checking each against its per-agent
  lockfile. Exit code is the worst across all agents.
- **normalise_context** takes an `AgentContext` and `risk_appetite` string,
  called per-agent in the generation loop.
- **Lockfiles** are per-agent: `governance/<slug>/profile.lock` and
  `governance/<slug>/context.lock`.

### Breaking changes

- `generate_docs()` signature: `(root, config, scan_result, context, *, provider)`
  (was `profile` instead of `scan_result`).
- `ScanResult.profile` → `ScanResult.agents` (list).
- `ContextManifest.agent` → `ContextManifest.agents` (dict).
- `context.yaml` format: `{project, agents}` (was `{project, agent}`).
- Governance docs move from `governance/system-card.md` to
  `governance/<agent-slug>/system-card.md`.
- `materiality` parameter removed from `generate_docs()`.
- `normalise_context()` signature changed to `(agent_context, risk_appetite,
  provider)`.

### Added

- `REGISTER.md` — project-level agent inventory listing every governed agent.
- `AgentDiscovery` and `ScannedAgent` dataclasses.
- `AgentGenerationResult` — per-agent generation result, aggregated by the
  project-level `GenerationResult`.
- `fixture-multi/` — two-agent fixture for multi-agent tests.
- A2A relationship modelling and dynamic platform discovery noted as
  roadmap items in SPEC.md.

## [0.1.2] - 2026-07-19

### Changed
- Removed the `agentic-business-case` framework from the bundled pack. Its
  two live sections (the 7-point agentic viability checklist and the rule of
  ten) are inlined as sections 12 and 13 of `governance-frameworks.md`. The
  `rubric.md` and 14 unused sections were deleted. The pack now ships a
  single framework (`agentic-governance`) with no scope-note duplication to
  manage.

## [0.1.1] - 2026-07-19

### Changed
- `ContextManifest` split into `project` (org-level) and `agent` (per-agent)
  sections. The wizard now asks project questions first, then agent questions,
  with a bordered preamble clarifying that agent-level fields describe this
  specific agent, not the whole organisation.
- `deployment_context`, `autonomy_level`, and `risk_appetite` are now free
  text at capture time. The `init` wizard never aborts on a multi-value or
  non-canonical answer. An LLM normalisation pass during `generate` resolves
  them to canonical enum values with a zero-LLM fast path and a graceful
  fallback to higher-risk defaults.
- `context.yaml` now has a two-section `project:` / `agent:` structure.
  Existing files from 0.1.0 are not auto-migrated; re-run `autogovern init`.

### Removed
- `data_categories` field removed from `ContextManifest`. The scanner-derived
  `governance.data_categories` (provenance-tracked, read from source) is the
  live value consumed by `generate`; the user-declared field was never read.

## [0.1.0] - 2026-07-18

Initial open-source release.

### Added
- CLI with seven commands: init, scan, generate, diff, check, explain, hook
  (with `hook install` and `hook run` subcommands)
- AgentProfile scanner with A2A AgentCard construction and provenance tracking
- Framework pack loader with section dependency graph
- Generation engine with incremental, idempotent regeneration
- Semver `doc_version`: regenerated documents bump major/minor/patch by the
  governance significance of the change; changelog entries record version
  bumps, significance, and materiality score
- Material change detection (heuristic, profile diff, semantic scoring)
- `governance/profile.lock` and `governance/context.lock`: code and context
  edits are both detected by `check` (autonomy and risk appetite changes
  score material deterministically)
- Vanilla mode: generate works without init, progressive enhancement
- Headless input: --profile flag on generate, check, diff
- Public library API: scan, generate_docs, check, load_profile
- Run manifests on every command, with provider token usage when reported
- Pre-commit hook: real heuristic pass printing `governance impact: yes/no`
  in under 500 ms, never blocks
- Forge-aware CI writers (GitHub, Forgejo, Bitbucket, generic)
- Provider-neutral GitHub Action; `--fix` mode commits regenerated docs
- Install scripts for POSIX and Windows
- Optional live-provider smoke test (`make smoke`, `AUTOGOVERN_SMOKE=1`)

### Fixed (post-build review hardening)
- `check` no longer fails on immaterial changes (dependency-only edits,
  renames): immaterial band passes silently per the spec
- Prompt changes now list their stale sections (dependency-graph mapping fix)
- `init` writes CI referencing the configured `api_key_env`, not the default
- `--profile` with a missing or invalid file exits cleanly
- `documents.changelog: false` is honoured
- `.env.example` uses the correct `AUTOGOVERN_*` variable names

### Notes
- Package name is `autogovern` everywhere (PyPI, docs, installers, CI templates)
- Runtime dependencies: typer, pydantic, pyyaml, httpx — nothing else
- Build process documents live in `docs/` (SPEC, BUILDPLAN, BUILDLOG)

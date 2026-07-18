---
title: "auto-govern - build plan"
created: 2026-07-17
updated: 2026-07-17
tags:
  - projects/auto-govern
source: SPEC.md
---

## How to use this plan

Execute the phases in order. Each phase has a **Build** list and a **Validate** gate. A phase is complete only when every validation passes **and** all previous phases still pass (`make check-all` runs the full suite). Do not start a phase before the previous gate is green. Where a validation names a fixture, use the fixtures created in Phase 3.

Global rules for the whole build:

- The spec (`SPEC.md`) is authoritative. If this plan and the spec conflict, the spec wins; note the conflict in `BUILDLOG.md`
- All tests mock the model provider. No test may call a live LLM. A separate optional smoke test (`make smoke`) runs live only when `AUTOGOVERN_SMOKE=1` and a provider is configured
- Every phase ends with a commit. Keep `BUILDLOG.md` at the repo root: one line per phase with date, phase number, and validation result
- Determinism is a feature: any test that passes intermittently is a failing test
- Apply the bundled `skills/project-setup` skill for Phase 0 (Python track: uv, src layout, gitleaks pre-commit, CI mirroring local gates, eval-shaped tests from the start)
- Apply the bundled `skills/ai-native-codebase-design` skill throughout: spec-anchored SDD (this plan and SPEC.md are the spec; acceptance criteria map to tests), deep modules with minimal interfaces, interface-first generation, and design-it-twice for the provider client, the pack loader, and the generation engine

## Phase 0 - scaffold

**Build**

- `pyproject.toml` (package name `auto-govern`, module `autogovern`, Python 3.12+, deps: typer, pydantic v2, pyyaml, jinja2, httpx)
- Package layout exactly as the spec's repository layout section
- Typer app in `cli.py` with stub commands: `init`, `scan`, `generate`, `diff`, `check`, `explain`, `hook`
- `Makefile` targets: `install`, `test`, `lint`, `check-all`
- Tooling: ruff for lint and format, pytest

**Validate**

- `pip install -e .` succeeds
- `autogovern --help` lists all seven commands; each stub exits 0 with a "not implemented" message
- `make check-all` runs and passes (lint plus an empty test suite placeholder)

## Phase 1 - data models

**Build**

- `AgentCard` model matching the A2A AgentCard schema (name, description, url, version, capabilities, skills, authentication, provider)
- `AgentProfile` = `AgentCard` fields plus `governance` extension block: model configuration, permissions surface, data categories observed, dependencies, prompt inventory. Every field carries provenance (source path, content hash)
- `ContextManifest` model with all wizard fields from the spec, with enum validation (autonomy_level, risk_appetite, deployment_context)
- `Config` model covering `model_provider` (api_base, model, api_key_env, temperature), watched-path globs, thresholds (defaults 80/20), document set toggles
- `RunManifest` model with all fields from the spec's observability section

**Validate**

- `pytest tests/test_models.py` passes: round-trip serialisation for every model, rejection tests for invalid enum values, missing required fields, and malformed provenance
- Each model exports JSON schema (`model_json_schema()`) without error; schemas written to `schemas/` by a `make schemas` target

## Phase 2 - config and provider client

**Build**

- Config loader for `.autogovern/config.yaml` with clear errors for missing or invalid fields
- Provider client: OpenAI-compatible chat completions over httpx, api_base and model from config, key read from the configured env var at call time, temperature 0, structured-JSON response helper, retry with backoff on 429/5xx
- Hard failure paths: missing key env var, unreachable endpoint (clean error, no partial state)

**Validate**

- `pytest tests/test_provider.py` passes with a mocked HTTP transport: correct request shape, key never logged, retry behaviour, JSON extraction
- `autogovern generate` on a repo with no config exits non-zero with a message naming the missing file and the `init` remedy
- Grep test: no source file writes the key value to disk or includes it in any log or manifest

## Phase 3 - fixture repos

**Build** (in `tests/fixtures/`)

- `fixture-basic/` - CLAUDE.md, README.md, `.mcp.json` with two tools, a prompt file, `pyproject.toml`. No AgentCard
- `fixture-carded/` - as basic, plus a valid `.well-known/agent.json`
- `fixture-plain/` - an ordinary Python project with no agent signals
- `fixture-profile.json` - a standalone valid AgentProfile for headless tests
- A fixture README documenting what each exists to prove

**Validate**

- All fixture files parse (JSON/YAML validity test)
- `fixture-profile.json` validates against the AgentProfile schema from Phase 1

## Phase 4 - scanner and AgentCard construction

**Build**

- Deterministic discovery: instruction files, README, MCP configs, tool schemas, model configuration, permission and env-var surface, dependency manifests, prompt globs (propose defaults, document them in the config reference)
- LLM summarisation step for free-text sources only, behind the provider client
- AgentCard construction when absent; write to `.well-known/agent.json` unless `--no-write-card`
- Provenance recording (path plus content hash) on every profile field
- `scan` command: human table output and `--json`

**Validate**

- `autogovern scan --json` on `fixture-basic` (mocked LLM) emits a schema-valid AgentProfile containing both MCP tools, the model configuration, and provenance on every field
- The same command writes a schema-valid AgentCard; on `fixture-carded` it parses the existing card instead and writes nothing
- On `fixture-plain`, scan exits 0 with an explicit "no agent signals found" result, not an empty profile
- Determinism: two scans of `fixture-basic` produce byte-identical output for all non-LLM fields
- Performance: scan of a generated 10k-file tree completes in under 5 s (`tests/test_perf.py`, generously bounded for CI)

## Phase 5 - init (config and context only)

**Build**

- Interactive wizard writing `.autogovern/config.yaml` and `.autogovern/context.yaml`
- `--defaults` non-interactive mode; `--from <file>` import with validation
- Provider settings captured here (api_base, model, key env var name); refuse to finish without them
- Hook and CI installation are Phase 10; leave clearly marked stubs

**Validate**

- `autogovern init --defaults` in a temp dir writes both files, valid against the Phase 1 models
- `init --from tests/fixtures/context-invalid.yaml` (create it) exits non-zero listing every invalid field
- Re-running init on an initialised repo prompts before overwriting (auto-answered in tests)

## Phase 6 - framework pack loader

**Build**

- Loader for `frameworks/pack.yaml`: files, style authority, verifier rubric, document feeds, scope notes, enterprise hooks
- Section reference resolver (`file.md#N` to heading text and content)
- Section dependency graph: document section → declared inputs (profile fields, context fields, pack sections)

**Validate**

- Loader resolves every reference in the bundled pack with zero unresolved warnings (`pytest tests/test_pack.py`)
- A test pack with a dangling reference fails loading with the exact bad reference named
- Graph query test: given "model configuration changed", the graph returns the system-card and inventory sections and nothing else

## Phase 7 - generation engine

**Build**

- Jinja2 templates per document, sections derived from the pack's artefact templates via `document_feeds`; engine templates for QUICKSTART, ATTENTION, CHANGELOG, and data-protection
- Section-level generation: each section prompt receives only its declared inputs; prompts embed the style authority rules
- Input-hash storage in frontmatter; regeneration only for sections whose input hash changed
- Frontmatter: doc_version, agent_version, generated, generator_version, input_hashes, framework_pack_version
- `governance/profile.lock` written on every generate
- Atomic writes: generation failure leaves no partial files

**Validate**

- `autogovern generate` on `fixture-basic` (mocked LLM) produces the full document set, the lockfile, and valid frontmatter everywhere
- **Idempotence gate**: a second `generate` immediately after produces zero git diff (acceptance criterion 4)
- Edit the fixture's model config, regenerate: only the sections the graph names are re-rendered (assert by LLM call count and untouched file mtimes)
- Style check: generated prompts contain the banned-constructions instruction block (snapshot test)

## Phase 8 - verifier and attention ledger

**Build**

- Verifier pass: per regenerated section, claims checked against declared inputs and provenance; rubric findings from the pack's verifier rubric (in-scope sections only); structured JSON result
- Unsupported claims removed from the section; gap written to `ATTENTION.md` with the missing init/scan input named
- Generation-time gaps (required input absent) also route to the ledger
- Ledger lifecycle: items carry stable ids; resolved items close on the next generate

**Validate**

- Mocked verifier returning one unsupported claim: claim absent from the final document, one open item in `ATTENTION.md` naming the resolving input (acceptance criterion 6, first half)
- Mocked verifier returning all-supported: ledger untouched
- Rubric findings appear in the run manifest, not in the documents

## Phase 9 - material change detection

**Build**

- Heuristic pass: watched-path glob match, no LLM, result object with matched paths
- Profile diff pass: rebuild profile, diff against `profile.lock`, field-level diff object
- Deterministic scoring rules: new/removed tool, permission scope change, autonomy change, new data category, model swap score material (>= 80) without an LLM
- Semantic scorer for the remainder (prompt content changes): profile diff in, 0-100 plus per-criterion reasoning out
- Band logic: >= 80 material, 21-79 advisory, <= 20 immaterial; thresholds from config

**Validate**

- Tool added to `fixture-basic`'s `.mcp.json`: profile diff detected, deterministic score >= 80, **zero LLM calls asserted**
- Unwatched file edited: heuristic pass negative, no profile rebuild, no LLM calls (acceptance criterion 3)
- Prompt text edited: semantic scorer invoked exactly once (mocked), band logic honoured for mocked scores of 15, 50, and 85
- `git log`-friendliness: lockfile diffs are line-stable (sorted keys, fixed formatting)

## Phase 10 - check, fix, diff, explain, hooks, CI writers

**Build**

- `check`: the five-step sequence from the spec; exit 0 current, exit 1 material-stale with score, stale section list, and remediation command; `--strict` also fails on open attention items and advisory scores; `--fix` regenerates stale sections plus lockfile in place
- `diff`: dry-run report of sections that would change and why
- `explain <doc>`: plain-language provenance and verification status per section
- Pre-commit hook (heuristic only, never blocks, no LLM) and `hook install`; init now installs it (`--no-hooks` opt-out)
- `init --local-enforce`: pre-push hook running full check
- Forge-aware CI writers: GitHub (`.github/workflows/`), Forgejo (`.forgejo/workflows/`), Bitbucket (`bitbucket-pipelines.yml` step), generic (printed command); `gh secret set` offer when available, printed instructions otherwise
- Global flags wired on every command: `--json`, `--config`, `--model`, `--strict`

**Validate**

- Full acceptance criterion 2 as an integration test: edit tool definition → `check` exits 1 with score and stale sections → `check --fix` regenerates → `check` exits 0
- `check --strict` exits 1 while the Phase 8 attention item is open, 0 once resolved (criterion 6, second half)
- Pre-commit hook on `fixture-basic` completes in under 500 ms and exits 0 for both impact outcomes (criterion 5)
- CI writer golden tests: generated workflow files for all three forges match checked-in goldens; remote-URL detection test per forge
- `--json` on check, scan, diff, and explain emits parseable JSON with a stable top-level schema

## Phase 11 - headless input and library surface

**Build**

- `--profile <file>` (and stdin) on `generate`, `check`, and `diff`: consume AgentProfile JSON, bypass scanning; lockfile path configurable for platform callers
- Public library API: `autogovern.generate_docs(...)`, `autogovern.check(...)`, `autogovern.scan(...)` with typed returns; CLI refactored to call these
- API stability test freezing the public function signatures

**Validate**

- `autogovern generate --profile tests/fixtures/fixture-profile.json --out <tmp>` produces the document set with no repo present
- A test script imports the library, runs check against the headless fixture, and receives a typed result without touching the CLI
- `check --profile` against a modified profile JSON returns the same verdict object as the repo path (parity test)

## Phase 12 - run manifests and observability

**Build**

- Run manifest written to `.autogovern/runs/<timestamp>.json` on every scan, generate, check, and diff: command, tool version, config snapshot minus secrets, input hashes, sections regenerated and why, model id, token counts, scores and reasoning, verifier results, attention items opened and closed
- `explain` upgraded to read manifests for its verification-status output

**Validate**

- Every command test from Phases 4-11 re-run with a manifest assertion: file exists, validates against the RunManifest schema, contains no secret values (grep for the fixture key)
- Token counts present when the mocked provider reports usage; null, not fabricated, when it does not

## Phase 13 - end-to-end, packaging, release readiness

**Build**

- One E2E test driving the full journey on a fresh temp repo: init --defaults → generate → idempotent regenerate → material edit → check fails → check --fix → check passes → manifests and changelog inspected
- README: install, quickstart (Journey B from the spec), config reference, CI setup per forge, headless usage
- `pre-commit-hooks.yaml` for the pre-commit framework; `action/` GitHub Action wrapping check and generate
- `install/install.sh` and `install/install.ps1` per the spec's distribution section (uv-first, user-local, idempotent, PATH check, prints `autogovern init` on success), plus a static install page under `site/` with tabbed commands
- Version 0.1.0, changelog, licence file (Apache-2.0), `make build` producing a wheel

**Validate**

- The E2E test passes in CI from a clean environment
- All seven acceptance criteria in SPEC.md pass, each mapped to a named test (`tests/test_acceptance.py` with one test per criterion)
- `pip install dist/*.whl` in a fresh venv, then `autogovern --help`, succeeds
- `sh install/install.sh` in a clean container (no uv, no auto-govern) ends with `autogovern --help` working and is safe to run a second time; `shellcheck install/install.sh` passes
- `make check-all` green; `make smoke` documented as the optional live-provider check

## Exit condition

The build is done when Phase 13's gate is green, `BUILDLOG.md` shows all fourteen phases passed in order, and a fresh clone can go from `pip install` to a fully generated, idempotent, enforced governance set on `fixture-basic` using only commands in the README.

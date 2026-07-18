---
title: "autogovern - build specification"
aliases:
  - Auto-govern spec
created: 2026-07-11
updated: 2026-07-11
tags:
  - governance/ai
  - projects/autogovern
source:
---

## Purpose

`autogovern` is a CLI that generates and maintains enterprise-grade governance documentation for AI agents, directly from the agent's codebase plus a small amount of organisational context. It hooks into the development workflow so that when an agent materially changes, its governance documentation is regenerated, versioned, and enforced before merge. The north star is end-to-end automation of agent governance **and security**: humans are involved only where verification genuinely cannot be automated, everything requiring human attention surfaces in exactly one place, and the enterprise tier culminates in a single fleet-wide console.

This specification covers the open-source core. Enterprise features (dynamic framework mapping, regulatory research, testing pipelines, observability triggers, doc platform publishing) are out of scope for the build but the architecture must leave clean seams for them, as described in the final section.

**Audience** - a coding agent implementing the tool end to end.

## Product summary

- **What it does** - reads an agent project, combines it with user-supplied organisational context, and produces a versioned set of governance documents using an LLM
- **How it runs** - as a CLI, a pre-commit hook, and a CI check
- **What it enforces** - governance docs must be current relative to the agent's material state before a PR can merge
- **Licence** - Apache-2.0, open-core model

## Technology decisions

| Area | Decision | Rationale |
|---|---|---|
| Language | Python 3.12+ | Ecosystem fit with agent tooling |
| CLI framework | Typer | Typed, minimal boilerplate |
| Data models | Pydantic v2 | Validation, JSON schema export |
| Model access | Provider-agnostic client | See below |
| Config format | YAML | Human-editable, diff-friendly |
| Packaging | `pyproject.toml`, published to PyPI as `auto-govern` | Standard |
| Hook distribution | `pre-commit` framework hook + GitHub Action | Meets developers where they are |

### Model access

The tool is completely model-agnostic. There is no default model and no bundled provider list. Configuration in `.autogovern/config.yaml`:

```yaml
model_provider:
  api_base: https://openrouter.ai/api/v1   # any OpenAI-compatible endpoint
  model: <user-chosen model id>
  api_key_env: OPENROUTER_API_KEY           # name of the env var holding the key
  temperature: 0
```

`init` requires the user to supply these values; the tool refuses to run generation without them. Keys are read from the named environment variable at runtime and never written to disk. Any endpoint speaking the OpenAI-compatible chat completions format works, which covers OpenRouter and effectively every hosted or self-hosted provider.

## Repository layout (of the tool itself)

```text
auto-govern/
  src/autogovern/
    cli.py              # Typer app, command definitions
    ingest/             # repo scanners and A2A card construction
    context/            # org context wizard and manifest models
    frameworks/         # bundled framework pack (from the agentic-governance skill)
    generate/           # doc generation engine, section dependency graph
    verify/             # verifier agent
    detect/             # material change detection (heuristic + semantic)
    hooks/              # pre-commit and CI entrypoints
    versioning/         # doc version stamping, changelog writer
    observability/      # run manifests
  templates/            # document templates (Jinja2 + Markdown)
  action/               # GitHub Action definition
  tests/
    fixtures/           # small fake agent repos used as known test inputs
```

## Inputs

### 1. Repo introspection and the AgentProfile

The `scan` stage builds the **AgentProfile**, the single structured representation of the agent that everything downstream consumes. The profile is anchored on the A2A AgentCard standard:

- If `.well-known/agent.json` exists, parse it as the base of the profile
- If it does not exist, **construct one** from the sources below and write it to `.well-known/agent.json` (default on, `--no-write-card` to disable). Emitting a standards-compliant AgentCard is a deliberate side benefit of running the tool
- The AgentProfile Pydantic model is a superset: the AgentCard fields plus a `governance` extension block covering what the card standard does not (model configuration, permissions surface, data categories observed in code, dependencies, prompt inventory)

Sources, in priority order:

- **Agent instruction files** - `CLAUDE.md`, `AGENTS.md`, `agent.md`, `.claude/` directory contents
- **README** - project purpose, usage, and stated limitations
- **Tool definitions** - MCP server configs (`.mcp.json`, `mcp.json`), tool schemas, function definitions discovered in source
- **Model configuration** - model names, providers, temperature, system prompts (files matching configured globs)
- **Permissions and secrets surface** - environment variable references, OAuth scopes, filesystem and network access implied by tool definitions
- **Dependency manifests** - `pyproject.toml`, `package.json`, `requirements.txt`

The scanner is deterministic where possible (file discovery, JSON/YAML parsing) and uses the LLM only to summarise free-text sources into structured fields. Every profile field records its provenance (file path plus content hash).

### 2. Organisational context manifest

`autogovern init` runs an interactive wizard and writes `.autogovern/context.yaml`. Fields:

- **organisation** - legal name and short name
- **sector** - e.g. financial services, healthcare
- **jurisdictions** - list, e.g. `[UK, EU]`
- **deployment_context** - internal, customer-facing, or third-party distributed
- **intended_users** - who interacts with the agent
- **autonomy_level** - human-in-the-loop, human-on-the-loop, or fully autonomous
- **oversight_model** - free text describing how humans intervene
- **data_categories** - personal data, special category, financial, none, etc.
- **risk_appetite** - conservative, balanced, or aggressive
- **strategy** - one paragraph on why the organisation is deploying this agent
- **owner** - accountable person or role
- **review_cadence** - e.g. quarterly

All fields validate against Pydantic models. The wizard accepts `--defaults` for non-interactive CI setup and `--from <file>` to import an existing manifest. The wizard is intentionally thorough: a complete init plus a thorough scan should leave nothing for humans to fill in later. **`init` also installs the pre-commit hook automatically** (`--no-hooks` to skip) and prints next steps.

**CI setup within init** - `init` detects the forge from the git remote and writes the matching CI configuration:

- **GitHub** - `.github/workflows/autogovern.yml`; offers `gh secret set <API_KEY_ENV>` if the `gh` CLI is authenticated, otherwise prints the settings path
- **Forgejo / Gitea** - same workflow syntax written to `.forgejo/workflows/`; secret created via repo settings (path printed)
- **Bitbucket** - a step appended to (or created in) `bitbucket-pipelines.yml` running `autogovern check --json`; key stored as a secured repository variable (settings path printed)
- **Other / none** - prints the single command to add to any CI system (`pip install auto-govern && autogovern check --json`) and the env var it needs

In every case the workflow maps the platform's secret store to the configured key env var. Keys are never written to the repo or to config files.

**Local enforcement fallback** - `init --local-enforce` additionally installs a **pre-push hook** that runs the full `check` (LLM included, using the developer's own environment key) and blocks the push while docs are stale. This gives teams without CI integration rights the complete workflow with no platform dependency. The pre-commit hook remains warning-only in all modes.

### 3. Framework pack

The pack ships **in this bundle** at `frameworks/`, built verbatim from the agentic-governance skill:

- `frameworks/pack.yaml` - the index: pack files, the style authority, and the **document feeds** mapping each generated document to the pack sections that supply it. The generation engine builds its section dependency graph from this mapping
- `frameworks/agentic-governance/` - the primary source content, copied unmodified: `governance-frameworks.md` (knowledge base: controls, risk vectors, testing methods, metrics, regulatory principles), `governance-artefacts.md` (**the authoritative section templates** - the register entry, risk-to-control mapping, agent/model card, deployment blueprint, monitoring/IR plan, and pre-deployment checklist), `ongoing-governance-runbook.md` (the perpetual-operation loop, reserved for the enterprise scheduled-drift seam), `formatting.md` (output production rules), and `skill-source.md` (the original SKILL.md, whose writing rules are the general style guide governing all generation prompts)
- `frameworks/agentic-business-case/` - supplementary content, copied unmodified and scoped by `pack.yaml`: `rubric.md` (the **verifier quality rubric** - its governance, realism, and cross-cutting sections give the verifier scoring criteria beyond claim-support checking: risks mapped one-to-one to actual capabilities, kill switch and logging present, strategic restraint named, numbers carrying stated assumptions) and `frameworks.md` (sections 3 and 4 - the 7-point agentic viability checklist and the rule of ten - feed the system card's intended-purpose justification; sections 9-16 duplicate the governance knowledge base and are out of scope, with the governance file authoritative on any conflict)

The generation engine treats the pack as data, never as code. This is the enterprise seam: the enterprise tier swaps in a larger, dynamically updated pack (EU AI Act, NIST AI RMF, ISO/IEC 42001) without touching the engine.

## Outputs - the document set

> **Status: subject to change.** The document set below is the working assumption, not final. Keep document definitions data-driven (templates plus `pack.yaml` wiring) so the set can be reshaped without engine changes.

Generated into `governance/` in the target repo. All documents are Markdown with YAML frontmatter carrying: `doc_version`, `agent_version`, `generated`, `generator_version`, `input_hashes` (map of source file to content hash), and `framework_pack_version`.

| Document | File | Content |
|---|---|---|
| Quickstart | `QUICKSTART.md` | One page. What was generated, how to read it, where human attention is needed. The only file a human must read |
| Attention ledger | `ATTENTION.md` | The single source of truth for anything requiring a human. Empty file means fully automated state |
| System card | `system-card.md` | Agent purpose, capabilities, tools, models, autonomy level, known limitations |
| Risk assessment | `risk-assessment.md` | Identified risks, likelihood and impact ratings, mitigations, residual risk, owner |
| Data protection summary | `data-protection.md` | Data categories processed, lawful basis considerations, retention, cross-border notes |
| Human oversight statement | `oversight.md` | Oversight model, intervention points, escalation paths |
| Model and tool inventory | `inventory.md` | Every model and tool with version, provider, and permissions surface |
| Testing and evaluation summary | `testing.md` | Current evals and their coverage; placeholder sections where none exist |
| Incident response plan | `incident-response.md` | Detection, containment, notification, and post-incident steps |
| Governance changelog | `CHANGELOG.md` | Append-only, one entry per regeneration, human-readable diff summary |

The document set is configurable in `.autogovern/config.yaml`; teams can disable documents that do not apply. `QUICKSTART.md` and `ATTENTION.md` cannot be disabled.

## Generation engine

- Each document is assembled from **sections**. A section declares its input dependencies (profile fields, context fields, framework pack sections) in the template. This declaration forms the **section dependency graph**
- Section content is generated by the LLM from a fixed prompt template plus only its declared inputs - never the whole repo. This is the primary token-efficiency mechanism
- Each rendered section stores a hash of its inputs in the document frontmatter. On regeneration, a section is re-rendered **only if its input hash changed**. Identifying which sections need regeneration is therefore deterministic and free: walk the dependency graph, compare hashes, collect the affected set. No LLM call is needed to decide what to regenerate
- Prompts instruct the model to write in the register defined by the framework pack's style authority (`frameworks/agentic-governance/skill-source.md`, writing rules section): plain declarative sentences, concrete thresholds and figures, no em-dashes, no contrastive negation, no significance inflation, no meta-signposting. The verifier pass also flags violations of these rules
- Section templates derive from `governance-artefacts.md` in the pack via the `document_feeds` mapping in `pack.yaml`. Where the spec's document set and the pack's artefact set differ (for example `data-protection.md` has no dedicated pack template in v1), the engine template fills the gap and the divergence is noted in `pack.yaml`

### Verification instead of human review tags

There are no inline human-review tags. The design position: if generated content needs routine human review, the init or scan stage was not thorough enough, and the fix is upstream. Instead:

- After generation, a **verifier agent** (second LLM pass, same provider config) checks every claim in each regenerated section against its declared inputs and provenance records, and scores the section against the in-scope criteria of the pack's verifier rubric (`frameworks/agentic-business-case/rubric.md`). It returns structured JSON: claim, supported/unsupported, source reference, and rubric findings
- Unsupported claims are removed and the underlying gap is written to `ATTENTION.md` with what is missing and which init/scan input would resolve it
- Missing required inputs discovered at generation time (for example the scanner finds PII handling but no data category was declared) also route to `ATTENTION.md`
- `autogovern check` reports the count of open attention items; a non-empty ledger is a warning by default and a failure with `--strict`

Humans interact with one file. Everything else is machine-verified.

## Observability

Every run writes a **run manifest** to `.autogovern/runs/<timestamp>.json`:

- Command, tool version, config snapshot (minus secrets)
- Input hashes consumed, sections regenerated and why (which hash changed)
- Model id, token counts, prompt template versions
- Materiality scores and per-criterion reasoning from detection
- Verifier results per section
- Attention items opened or closed

Run manifests are the audit trail and the future-proofing layer: verifier agents, review agents, and the enterprise observability stack all consume this format rather than parsing documents. Humans never read hashes; `autogovern explain <doc>` renders provenance and verification status for any document in plain language.

## Material change detection

Three stages, in `detect/`, ordered so that the expensive step runs as rarely as possible:

1. **Heuristic pass (fast, deterministic)** - a changed file matching the watched-path set flags a potential governance impact. Default watched paths: agent instruction files, prompt files, tool and MCP definitions, model configuration, permission or scope declarations, the A2A card, and dependency manifests. Configurable via globs in `.autogovern/config.yaml`. Runs in pre-commit
2. **Profile diff pass (CI, mostly deterministic)** - `scan` rebuilds the AgentProfile from the current code and diffs it against the committed **`governance/profile.lock`**, a frozen serialisation of the profile (AgentCard plus governance extension), analogous to a package lockfile. No diff means the agent is materially unchanged: pass in seconds with zero LLM calls. Certain field changes score deterministically without an LLM - a new tool, a widened permission scope, a changed autonomy level, or a new data category is material by definition
3. **Semantic pass (LLM, only when needed)** - profile diffs not resolved deterministically (for example prompt content changes) are scored 0-100 for materiality. The scorer receives the field-level profile diff, not raw git hunks, which keeps token use minimal and scoring precise. Score and per-criterion reasoning are returned as structured JSON

The lockfile doubles as the agent's governance history: `git log governance/profile.lock` lists every material change the agent has undergone, which is precisely the audit question

**Thresholds (Pareto bands, configurable):**

- **Score >= 80** - material. Documentation must be regenerated before merge
- **Score 21-79** - advisory. Logged in the run manifest and changelog; does not block
- **Score <= 20** - immaterial. Pass silently

The heuristic pass alone runs in pre-commit; the profile diff and semantic passes run in CI. `generate` and `scan` are responsible for writing an updated `profile.lock` whenever the profile changes.

## CLI commands

```bash
autogovern init          # wizard: config, context manifest, and hook install in one step
autogovern scan          # build and print the AgentProfile (writes AgentCard if absent)
autogovern generate      # full or incremental doc generation into governance/
autogovern diff          # show which sections would change and why, without writing
autogovern check         # CI gate: report stale docs; --fix regenerates in place
autogovern explain <doc> # plain-language provenance and verification status
autogovern hook install  # re-install hooks manually if needed
```

### How `check` works

`check` never crashes and a "failing" check is not an error - it is the gate doing its job. The sequence:

1. Rebuild the AgentProfile from the current code (`scan`)
2. Diff it against the committed `governance/profile.lock`
3. No diff: the agent is materially unchanged, exit 0, print `governance: current`. No LLM call
4. Diff: score it (deterministic rules first, semantic pass for the remainder). Score >= 80 means the docs no longer describe the agent: exit 1 with the score, the list of stale sections (from the dependency graph), and the exact remediation command
5. With `--fix`, skip the exit and regenerate the stale sections plus the updated lockfile immediately, ready to commit

In a fully automated pipeline, CI runs `check --fix` and commits the regenerated docs itself; no human is in the loop. In a gated pipeline, CI runs plain `check` and the failing status tells the developer to run `generate` locally.

### Global flags

Global flags are options accepted by **every** command, placed after the command name. They override the config file for that single run without changing it:

- `--json` - print machine-readable JSON instead of human-formatted output, so scripts and other agents can parse results
- `--config <path>` - use an alternate config file
- `--model <id>` - override the configured model for this run
- `--strict` - treat warnings (open attention items, advisory-band scores) as failures

Example: `autogovern check --json --strict` in CI.

## Versioning model

- Governance docs live in the target repo and version with git - no external state
- `doc_version` follows semver. The semantic pass classifies each regeneration: major (autonomy, permissions, or data category change), minor (tool or model change), patch (descriptive updates)
- `agent_version` is taken from the project's own version if discoverable, otherwise from the release flag
- `CHANGELOG.md` entries record: date, doc_version, agent_version, materiality score, changed sections, and a two-line human summary
- Release regeneration: `autogovern generate --release <version>` performs a full regeneration regardless of hashes and stamps the version

## Workflow integration

Layered triggers, from cheapest to most complete:

- **Init** - installs the pre-commit hook and writes the forge-appropriate CI configuration (GitHub, Forgejo, Bitbucket, or a generic command), with user confirmation
- **Pre-commit** - heuristic pass only. Prints `governance impact: yes/no` with the matched paths. Never blocks the commit and never calls the LLM. Purpose is developer awareness
- **Pre-push (optional, `--local-enforce`)** - full `check` from the developer's machine; blocks the push while docs are stale. The no-CI fallback
- **CI / PR gate** - `autogovern check` (or `check --fix` for full automation) runs the lockfile diff and, only when needed, the semantic pass as described above
- **Deploy gate (optional)** - a final `autogovern check --strict` before the deploy job, so nothing ships with stale documentation or open attention items. This gate is the seam AgentGuard extends in enterprise: same position in the pipeline, evaluation upgraded from doc currency to full policy-as-code criteria with suggested fixes
- **Release / tag** - full regeneration with version stamp and changelog entry
- **Scheduled (enterprise seam)** - drift checks driven by regulatory feeds and observability signals, where governance conditions change without a code change

## Library and automation surface

The OSS core stays CLI-first, with three integration paths:

- **Importable as a library** - the engine is normal Python code. Another Python program can `import autogovern` and call `generate_docs(...)` or `check(...)` directly as functions, in the same process, with no CLI involved. The CLI is a thin wrapper over these functions
- **Scriptable as an API** - because every command supports `--json`, any external system (a shell script, n8n, a CI job, another agent) can run the CLI as a subprocess and parse structured output. The CLI behaves like an API without running a server
- **Headless profile input** - `generate`, `check`, and `diff` accept `--profile <file>` (or stdin) to consume an AgentProfile JSON directly, bypassing repo scanning entirely. This is how low-code and no-code agent platforms integrate: the platform maps its internal agent record to the profile schema and calls auto-govern on each publish event, with the last-published profile serving as the lockfile equivalent. Outputs return as structured JSON for the platform to store and render

A `serve` command exposing a local REST endpoint is deferred to enterprise; the library boundary must be designed so adding it requires no engine changes.

## Distribution

The canonical package lives on PyPI (`pip install auto-govern`, or `pipx` / `uv tool install auto-govern` for isolated CLI installs). On top of that, ship the one-line installer pattern standard for dev tools:

- **`install/install.sh`** - POSIX shell installer served from the project website so users can run `curl -fsSL https://autogovern.dev/install.sh | sh`. The script: detects OS and architecture, installs `uv` if absent (user-local, no sudo), runs `uv tool install auto-govern`, verifies the binary is on PATH (appending the shell profile line if not), and finishes by printing the next step (`autogovern init`). Idempotent: safe to re-run, and re-running upgrades
- **`install/install.ps1`** - PowerShell equivalent for Windows (`irm https://autogovern.dev/install.ps1 | iex`), same behaviour
- **Install site** - a static page (GitHub Pages or Cloudflare Pages, custom domain) presenting tabbed install commands (curl, PowerShell, pip, pipx, uv) with copy buttons, serving the two scripts at stable URLs. The scripts are committed in the repo under `install/` and deployed from there, so they are reviewable and versioned like everything else
- **Integrity** - HTTPS only; publish SHA-256 checksums for the scripts alongside each release; the scripts install only from PyPI and never require sudo
- **Roadmap** - standalone binaries (PyInstaller) for environments without Python; an **npm wrapper package** built on those binaries (`npm install -g auto-govern`, plus pnpm and bun equivalents), following the pattern ruff, Biome, and esbuild use - a thin npm package whose platform-specific optional dependencies carry the prebuilt binary, giving JS-native teams their mainstream channel and filling the npm/pnpm/bun tabs on the install page; and a Homebrew tap, once adoption justifies them

## Non-functional requirements

- **Idempotence** - running `generate` twice in a row with no input changes produces an identical result: the second run writes nothing and `git diff` is empty
- **Offline failure mode** - if the model provider is unreachable, `check` still runs the heuristic pass and reports degraded mode; `generate` fails cleanly with no partial writes
- **No telemetry** - the OSS tool sends nothing anywhere except the user's configured model provider
- **Performance** - `scan` under 5 s on a 10k-file repo; heuristic pass under 500 ms
- **Testing** - unit tests for scanners and detection heuristics against fixture repos (small fake agent projects checked into `tests/fixtures/`, used as known inputs so tests are predictable); snapshot tests for template rendering; one end-to-end test with a mocked model provider

## Enterprise seams (do not build, do not block)

- **Framework pack interface** - packs are versioned data; the enterprise tier delivers signed, dynamically updated packs mapping EU AI Act, NIST AI RMF, and ISO/IEC 42001, applied selectively based on the scan and context manifest
- **Regulatory research agent** - watches regulatory sources, raises pack updates, and triggers regeneration when applicable obligations change
- **AgentGuard (working name) - policy enforcement and security layer** - the enterprise evolution of the OSS deploy gate. The enterprise defines its governance criteria as **policy-as-code** (required controls, permitted models and providers, permission ceilings, mandatory test evidence, data-category rules). At deployment time AgentGuard evaluates the agent's profile, generated documentation, and test evidence against those criteria and returns one of: pass, **halt with suggested fixes** (each failed criterion mapped to the concrete change or missing evidence that resolves it), or pass-with-conditions. It consumes the pre-deployment checklist (`testing.md`, fed by the pack's checklist template) as its evidence base, so the OSS pre-deployment testing story folds into this feature rather than existing alongside it. AgentGuard is also the future home of the **security console**: red-team campaign management, golden dataset regression, adversarial testing cadence, and attack-surface mapping, all recording results back into `testing.md` and the run manifests
- **Fleet console** - the single Palantir-style view of the whole agent fleet: every registered agent with its lockfile state, governance currency, AgentGuard verdict, attention items, drift signals, test coverage, and regulatory exposure, backed by the registry and the run-manifest stream. The console is a read of data the OSS core already emits; no agent-side changes required
- **Agent efficiency layer (placeholder name, roadmap)** - an optimisation engine built on the same data plane. Run manifests already record token counts and model ids per operation, and the lockfile records each agent's model and tool configuration; aggregated across the fleet, this identifies inefficiencies in models and harnesses (oversized models on simple tasks, bloated context, retry loops, missing caching) and proposes efficiency changes. Implementation goes through the tool's own safety pipeline: proposals land as PRs, pass the materiality gate, and are verified non-damaging by AgentGuard golden dataset regression before merge. Scope note: this layer modifies agent code rather than governance documents, so its design requires separate discussion before any build; it is recorded here as roadmap only
- **Observability triggers** - runtime signals (new tools appearing, permission escalation, drift) consuming and extending the run manifest format, feeding both AgentGuard re-evaluation and the fleet console
- **Publishing connectors** - push rendered documents to Notion, Confluence, SharePoint, Google Docs, GitBook, and Coda. OSS ships Markdown-in-repo only
- **Agent platform integration** - the `serve` REST mode packaged for enterprise agent-builder platforms: the platform calls the governance service on every publish event with the agent's profile JSON, receives materiality verdict and regenerated docs, and gates or completes the publish accordingly. Workspace-level context manifests are inherited by all agents on the platform
- **Attestation** - signed doc bundles and an audit registry
- **Hosted control plane** - enterprise runs as a cloud service handling packs, registry, research agent, and dashboards, while generation continues to run in the customer's own CI via the same CLI (customer code never leaves their environment; the CLI pulls signed packs and pushes attestations)

The only requirement on the OSS build is that packs, detection criteria, document definitions, and generation inputs are all data-driven and pluggable.

## Enterprise user journeys (context, not build scope)

Three personas illustrating how the same engine serves different enterprise setups. Included so the implementer understands which surfaces each journey depends on.

### Journey A - built their own agent platform

An enterprise platform team runs an internal harness UI where business users assemble agents from prebuilt components. No repos, no CI, agents live as database records.

1. Platform team maps their agent record schema to the AgentProfile schema (one-off integration, a few days)
2. An admin completes the workspace-level context manifest once; every agent inherits it
3. The platform backend calls the governance service (enterprise `serve` mode) on every publish event, sending the agent's profile JSON
4. The service diffs against the last-published profile, scores materiality, regenerates stale sections, and returns them
5. Publish is gated or auto-completed; docs render in a Governance tab per agent and sync to Confluence via a publishing connector
6. Runtime drift: agents acquiring tools or permissions not in their last-published profile raise attention items automatically

Surfaces used - headless profile input, `serve`, workspace context, publishing connectors, drift detection.

### Journey B - nothing yet

A development team builds agents in ordinary repos. No governance process exists; documentation is written by hand when someone remembers.

1. A developer runs `pip install auto-govern && autogovern init` on one agent repo; the wizard captures org context and installs hooks and CI config in one sitting
2. First `generate` produces the full document set and the AgentCard; the team reviews `QUICKSTART.md` once to understand what exists
3. CI runs in gated mode initially - developers see red checks with exact remediation commands and build the habit
4. After a few weeks the team switches to `check --fix` auto mode; documentation now maintains itself
5. The pattern is copied across further agent repos; org context is imported with `init --from`
6. Enterprise upgrade later adds signed framework packs (EU AI Act, ISO/IEC 42001), the regulatory research agent, and attestations - no workflow change for developers

Surfaces used - the entire OSS core as shipped. This journey is the adoption wedge and must require nothing beyond `init`.

### Journey C - on a managed agent platform (Vertex, Bedrock AgentCore, Claude managed agents)

An enterprise builds agents on a hyperscaler or vendor platform it does not control. Two sub-paths depending on how agents are defined:

**C1 - agents defined as code and deployed via IaC.** The agent's configuration (prompts, tools, model) lives in a repo and is deployed by Terraform, CDK, or the provider CLI. This collapses to the standard repo journey: the CI gate runs before the deploy step, so no agent version reaches the managed platform with stale documentation. No new surfaces required.

**C2 - agents built or modified in the provider console.** No repo captures the change, so a **provider connector** (enterprise) pulls agent definitions on a schedule or platform event via the provider's management API, maps them to profile JSON, and runs the headless check. Material changes made in the console trigger regeneration and, where the change bypassed change control entirely, an attention item. The lockfile lives in the enterprise registry rather than a repo.

Drift between C1 and C2 is itself a signal: a live agent whose console state diverges from its repo-defined profile is unauthorised change by definition, and surfaces as a high-priority attention item.

Surfaces used - standard CI gate (C1); headless input, provider connectors, enterprise registry, drift detection (C2).

## Acceptance criteria

1. `autogovern init && autogovern generate` on a fixture repo containing a `CLAUDE.md`, an MCP config, and a README produces the full document set with populated sections, a written AgentCard, correct frontmatter, and a run manifest
2. After editing a tool definition, `autogovern check` exits 1 and reports: materiality score, the stale sections (derived from the dependency graph), and the remediation command. `autogovern check --fix` regenerates those sections and a subsequent `check` exits 0
3. Editing an unwatched file (for example a test) leaves `check` exiting 0 with no LLM call
4. Two consecutive `generate` runs produce zero git diff
5. The pre-commit hook prints an impact flag in under 500 ms and never blocks
6. A verifier pass that finds an unsupported claim removes it and writes an item to `ATTENTION.md`; `check --strict` then exits 1 until resolved
7. The GitHub Action in `check --fix` mode commits regenerated docs with no human involvement

## Open decisions for the implementer

- Exact glob defaults for prompt file discovery - propose and document
- AgentCard field mapping where sources conflict (README vs instruction files) - propose a precedence rule
- Materiality criteria weights within the 80/20 bands - ship sensible defaults and expose them in config

# autogovern

Generate and maintain enterprise-grade governance documentation for AI agents, directly from the agent's codebase.

## Install

```bash
# With uv (recommended)
uv tool install autogovern

# With pipx
pipx install autogovern

# Or with pip
pip install autogovern
```

One-line installers (install `uv` first if needed, then the tool):

```bash
# POSIX (Linux/macOS)
curl -fsSL https://raw.githubusercontent.com/ashborn-systems/autogovern/main/install/install.sh | sh

# Windows (PowerShell)
irm https://raw.githubusercontent.com/ashborn-systems/autogovern/main/install/install.ps1 | iex
```

A hosted install page with copy-button tabs is on the roadmap; the scripts
above are committed in `install/` and work from any stable URL.

## Quickstart

### Vanilla mode (no init required)

```bash
export AUTOGOVERN_API_BASE=https://openrouter.ai/api/v1
export AUTOGOVERN_MODEL=anthropic/claude-3.5-sonnet
export AUTOGOVERN_API_KEY_ENV=OPENROUTER_API_KEY
export OPENROUTER_API_KEY=your-key-here

autogovern generate /path/to/agent-repo
```

Docs are generated into `governance/`. They are generic because no organisational context was provided. The more context you give it, the better the docs.

### Enhanced mode (with init)

```bash
autogovern init          # wizard: config, context, hooks, CI
autogovern scan          # build the AgentProfile and AgentCard
autogovern generate      # write the governance document set
autogovern check         # verify docs are current
```

`init` writes `.autogovern/config.yaml` (provider settings) and `.autogovern/context.yaml` (organisational context: risk appetite, oversight model, jurisdictions, owner). It also installs a pre-commit hook and writes forge-appropriate CI configuration.

## Commands

```bash
autogovern init          # wizard: config, context, hooks, CI
autogovern scan          # build and print the AgentProfile
autogovern generate      # full or incremental doc generation
autogovern diff          # show which sections would change and why
autogovern check         # CI gate: report stale docs; --fix regenerates
autogovern explain <doc> # plain-language provenance for a document
autogovern hook install  # re-install hooks manually
autogovern hook run      # heuristic impact check (pre-commit entrypoint)
```

### Global flags

The inspection and generation commands (`scan`, `generate`, `diff`, `check`,
`explain`) accept:

- `--json` — machine-readable JSON output
- `--config <path>` — alternate config file
- `--model <id>` — override the configured model for one run
- `--strict` — treat advisory scores as failures (`check` only)

### Headless mode

```bash
# Generate from a profile JSON without scanning a repo
autogovern generate --profile agent-profile.json

# Check against a headless profile
autogovern check --profile agent-profile.json
```

## Configuration

`.autogovern/config.yaml`:

```yaml
model_provider:
  api_base: https://openrouter.ai/api/v1
  model: <model-id>
  api_key_env: OPENROUTER_API_KEY
  temperature: 0
watched_paths:
  - CLAUDE.md
  - .mcp.json
  - prompts/**
  # ...
thresholds:
  material: 80
  immaterial: 20
documents:
  system-card: true
  risk-assessment: true
  # ...
```

The API key is read from the named environment variable at runtime and never written to disk.

## CI setup

`autogovern init` detects your forge from the git remote and writes CI configuration:

- **GitHub** — `.github/workflows/autogovern.yml`
- **Forgejo** — `.forgejo/workflows/autogovern.yml`
- **Bitbucket** — `bitbucket-pipelines.yml`
- **Other** — prints the command to add

In CI, run:

```bash
autogovern check --json --strict
```

For auto-fix mode (commits regenerated docs):

```bash
autogovern check --fix
git add governance/ && git commit -m "autogovern: regenerated docs"
```

## How it works

1. **Scan** reads the repo (instruction files, MCP configs, model config, dependencies, prompts) and builds an AgentProfile with provenance on every field.
2. **Generate** writes the governance document set from the profile plus the organisational context. Each section receives only its declared inputs (token-efficient). Incremental: only sections whose inputs changed are regenerated.
3. **Check** rebuilds the profile, diffs against `governance/profile.lock`, and scores the change. Material changes (new tool, model swap, autonomy change) are detected deterministically without an LLM. Prompt content changes go to a semantic scorer.
4. **Idempotent** — a second `generate` with no changes writes nothing.

## Documentation

- `docs/SPEC.md` — the full build specification
- `docs/BUILDPLAN.md` — the phased build plan
- `docs/BUILDLOG.md` — the build log, one line per phase

## Roadmap

- Hosted install page (tabbed install commands) on ashbornsystems.com
- Standalone binaries (PyInstaller) and an npm wrapper for JS-native teams
- Homebrew tap

## License

Apache-2.0

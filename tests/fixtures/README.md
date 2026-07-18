# Test fixtures

Small fake agent repos and data files used as known inputs so tests are
predictable. Each fixture exists to prove a specific behaviour of the scanner,
init, or generation engine.

## Repositories

### `fixture-basic/`

A representative agent repo with the standard signals a scanner must find:
- `CLAUDE.md` — agent instruction file
- `README.md` — project purpose, usage, and limitations
- `.mcp.json` — MCP config with **two tools** (`fetch_ticket`, `assign_ticket`)
- `prompts/system.md` — a prompt file
- `pyproject.toml` — dependency manifest (anthropic, httpx)

**No** `.well-known/agent.json` — proves the scanner constructs a card when
absent. Used by Phase 4 (scan writes a card), Phase 7 (generate), and the
acceptance criteria that require both MCP tools in the profile.

### `fixture-carded/`

Identical to `fixture-basic/` but **with** a valid `.well-known/agent.json`.
Proves the scanner parses an existing card instead of writing one. Used by
Phase 4 (scan reads, does not overwrite, the card).

### `fixture-plain/`

An ordinary Python project (`wordfreq`) with no agent signals — no
instruction files, no MCP config, no prompt files. Proves scan exits 0 with
"no agent signals found" rather than an empty profile. Used by Phase 4.

## Data files

### `fixture-profile.json`

A standalone valid `AgentProfile` for headless tests (Phase 11 `--profile`
input). Contains the full governance extension block with provenance on every
field. Validates against the Phase 1 `AgentProfile` schema.

### `context-invalid.yaml`

An invalid organisational context manifest where every field is wrong. Used by
Phase 5 (`init --from`) to prove init exits non-zero listing every invalid
field. Parseable as YAML (so the error is schema-level, not a parse failure).

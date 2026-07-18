# Build log

One line per phase: date, phase number, validation result. Detailed completion notes follow the summary line.

- 2026-07-18 — Phase 0 (scaffold) — PASS: `uv sync` succeeds, `autogovern --help` lists all seven commands, each stub exits 0 with "not implemented" message, `make check-all` green (ruff + mypy + 7 tests).

- 2026-07-18 — Phase 1 (data models) — PASS: `pytest tests/test_models.py` green (29 tests: round-trip for all models, rejection of invalid enums/missing fields/malformed provenance, JSON schema export); `make schemas` writes 24 schema files to `schemas/`; `make check-all` green (ruff + mypy + 36 tests).

  **Phase 1 completion notes:**

  Built `src/autogovern/models.py` (24 pydantic models), `tests/test_models.py` (29 tests), and `scripts/export_schemas.py`.

  Five primary models:
  1. **AgentCard** — faithful to the A2A AgentCard standard (name, description, url, version, capabilities, skills, authentication, provider). Sub-models: AgentProvider, AgentSkill, AgentCapabilities, AgentAuthentication.
  2. **AgentProfile** — superset of AgentCard plus a `governance` extension block. Every scanner-derived field carries provenance via a generic `ProvenancedField[T]` wrapper (PEP 695 type parameter syntax). Card-standard fields carry provenance through a `provenance: dict[str, Provenance]` map so the card serialises standards-compliant on its own. Sub-models: GovernanceExtension, ModelConfiguration, Permission, DataCategory, Dependency, PromptEntry.
  3. **ContextManifest** — all wizard fields with `StrEnum` validation for AutonomyLevel, RiskAppetite, DeploymentContext.
  4. **Config** — the `.autogovern/config.yaml` document: ModelProviderConfig, watched_paths (10 default globs), Thresholds (material=80, immaterial=20), documents (10 doc toggles; quickstart + attention always on).
  5. **RunManifest** — full observability record: command, tool_version, config_snapshot (minus secrets), input_hashes, sections_regenerated, model_id, token_counts, prompt_template_versions, materiality, verifier_results per section, attention_items.

  Design decisions:
  - PEP 695 `class ProvenancedField[T](BaseModel)` for the generic wrapper — clean, type-safe, mypy-happy on 3.12.
  - Kept AgentCard fields plain on AgentProfile (standards-compliant shape) with a side provenance dict, so the card serialises correctly when written to `.well-known/agent.json`.
  - QUICKSTART.md and ATTENTION.md default on; the generation engine will enforce non-disableable in Phase 7.

  Validation: ruff check clean, ruff format clean, mypy strict (12 files, no issues), pytest 36 passed (7 CLI + 29 models), `make schemas` writes 24 JSON files.

- 2026-07-18 — Phase 2 (config and provider client) — PASS: `pytest tests/test_provider.py` green (16 tests: request shape, key never logged, retry on 429/503/connection error, no retry on 400, JSON extraction, schema validation, hard failures); `autogovern generate` with no config exits 1 mentioning `init`; grep test confirms no source file persists the key; `make check-all` green (ruff + mypy + 68 tests).

  **Phase 2 completion notes:**

  Built `src/autogovern/config_loader.py`, `src/autogovern/provider.py`, `tests/test_provider.py`, `tests/test_secrets_discipline.py`. Wired `generate` command to the config loader.

  Config loader (`config_loader.py`):
  - `load_config(path=None) -> Config` reads `.autogovern/config.yaml`, validates against the Phase 1 Config model.
  - Clear errors: `ConfigNotFoundError` (mentions `init` remedy), `ConfigInvalidError` (YAML parse or schema validation failure with full detail).

  Provider client (`provider.py`) — a deep module, Design A from design-it-twice:
  - OpenAI-compatible chat completions over httpx.
  - `chat(messages, temperature=None) -> str` and `chat_json(messages, temperature=None, schema=None) -> Any`.
  - Key read from the configured env var (`api_key_env`) at call time via `os.environ.get`, never at construction.
  - Retry with exponential backoff on 429/5xx and transport errors; 4xx (except 429) not retried.
  - Structured-JSON helper validates against an optional pydantic model.
  - Hard failure paths: `MissingApiKeyError`, `ProviderUnreachableError`, `ProviderResponseError` (all clean, no partial state).

  Secrets discipline:
  - The key is never written to disk, logs, or manifests. The provider reads it at call time only.
  - `tests/test_secrets_discipline.py` (17 tests): static grep across source tree for forbidden patterns (logging the key, writing it to a file, storing in config_snapshot); confirms `os.environ.get` is called at call time not construction; confirms RunManifest.config_snapshot defaults empty; confirms `.env.example` has no real key values.

  Design decisions:
  - Chose Design A (single ProviderClient class) over Design B (split transport + JSON parser) — the JSON extraction is trivial and splitting it would be over-decomposition. The client is a deep module: simple interface, complex internals.
  - Retry uses exponential backoff (0.5s initial, 5s cap, 3 retries) with `time.sleep` — simple and deterministic for testing.
  - Injected `httpx.Client` with `MockTransport` in tests; no live LLM calls.

  Validation: ruff check clean, ruff format clean, mypy strict (14 files, no issues), pytest 68 passed (6 CLI + 29 models + 16 provider + 17 secrets).

- 2026-07-18 — Phase 3 (fixture repos) — PASS: `pytest tests/test_fixtures.py` green (7 tests: 4 JSON parse, 1 YAML parse, fixture-profile.json validates as AgentProfile, fixture-carded agent.json validates as AgentCard); `make check-all` green (ruff + mypy + 75 tests).

  **Phase 3 completion notes:**

  Audited and sealed the fixture set in `tests/fixtures/`, plus `tests/test_fixtures.py`. The fixture files were already present on disk from the prior session; this phase added the validation gate that proves them fit for purpose and guards them against regressions in later phases.

  Fixtures (each exists to prove a specific behaviour, documented in `tests/fixtures/README.md`):
  1. **`fixture-basic/`** — a representative agent repo: `CLAUDE.md`, `README.md`, `.mcp.json` with two tools (`fetch_ticket`, `assign_ticket`), `prompts/system.md`, `pyproject.toml` (anthropic, httpx). No `.well-known/agent.json` — proves the scanner constructs a card when absent.
  2. **`fixture-carded/`** — identical to basic but with a valid `.well-known/agent.json`. Proves the scanner parses an existing card instead of writing one.
  3. **`fixture-plain/`** — `wordfreq`, an ordinary Python project with no agent signals. Proves scan exits 0 with "no agent signals found" rather than an empty profile.
  4. **`fixture-profile.json`** — a standalone valid `AgentProfile` for headless tests (Phase 11 `--profile`). Carries the full governance extension block with provenance on every field.
  5. **`context-invalid.yaml`** — every field wrong. Parseable as YAML (so the Phase 5 init error is schema-level, not a parse failure) but fails `ContextManifest` validation with five field errors.

  Design decisions:
  - Dynamic discovery (`rglob`) for the parse tests, so fixtures added in later phases are automatically covered without editing the test.
  - Kept Phase 3 to parse + schema validity only. Behavioural assertions that depend on the scanner (e.g. "both MCP tools appear in the profile") belong to Phase 4, keeping the serial phase gates clean.
  - Empirically pre-validated the three load-bearing contracts before writing the test: `fixture-profile.json` → `AgentProfile`, the carded `agent.json` → `AgentCard`, and `context-invalid.yaml` → five `ContextManifest` errors. The test encodes those exact contracts.
  - Did not add a TOML parse check for the `pyproject.toml` fixtures; the Phase 3 gate names JSON/YAML only, and the scanner's manifest parsing is exercised by Phase 4.

  Validation: ruff check clean, ruff format clean, mypy strict (14 source files, no issues), pytest 75 passed (6 CLI + 29 models + 16 provider + 17 secrets + 7 fixtures).

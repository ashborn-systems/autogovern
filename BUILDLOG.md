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

- 2026-07-18 — Phase 4 (scanner and AgentCard construction) — PASS: `pytest tests/test_scan.py tests/test_parsers.py tests/test_scan_cli.py tests/test_perf.py` green (34 new tests); all five Phase 4 validation criteria covered by named tests; `make check-all` green (ruff + mypy + 113 tests).

  **Phase 4 completion notes:**

  Built the `ingest/` package as a functional core behind a thin orchestration shell, applying the ai-native-codebase-design skill (deep modules, interface-first, deterministic core isolated from LLM I/O):
  1. **`ingest/discovery.py`** — deterministic two-phase file discovery. `discover_signals()` finds signal-bearing files (instruction, README, MCP, manifests, prompts, agent card) via specific globs; `discover_source_files()` scans `.py/.ts/.js` only when signals exist, so non-agent repos pay nothing. Sorts all results by path; computes sha256 content hashes; ignores vendored/build/tool-owned dirs (`.venv`, `governance`, `.autogovern`, etc.).
  2. **`ingest/parsers.py`** — pure parsing into typed records: MCP tools (across servers, sorted), dependencies (pyproject via stdlib `tomllib`, package.json, requirements.txt), model config (model name, temperature, api_base, provider import — all case-insensitive with word boundaries), env-var references (`os.environ`/`os.getenv`), and project metadata.
  3. **`ingest/summarise.py`** — the single LLM seam. `summarise_free_text()` sends instruction files + README to the provider and returns a `FreeTextSummary` (data_categories, description/skills fallback). A missing or failing provider degrades gracefully (empty summary) rather than aborting the scan.
  4. **`ingest/builder.py`** — pure profile assembly. `build_profile()` merges sources by fixed precedence (existing card > manifest metadata > LLM summary > default) and attaches provenance to every field. `profile_to_card()` projects back to a standards-compliant AgentCard.
  5. **`ingest/scanner.py`** — the shell. `scan_repo(root, config, *, provider=None, write_card=True) -> ScanResult` orchestrates discovery → parse → summarise → build → card write. Owns the provider lifecycle when it constructs one. `ScanResult` carries the profile, signals_found flag, and card-written status, with `to_json()` for `--json`.

  CLI `scan` command: loads config (exits 1 mentioning `init` if missing, like `generate`), builds the provider via a new `build_provider(config)` factory in `provider.py` (the seam tests monkeypatch), and prints JSON (`--json`) or a human table. `--no-write-card` suppresses card writing; `--config` overrides the config path.

  Fixture enrichment: added `src/support_triage_agent.py` to `fixture-basic/` and `fixture-carded/` (mirrored, keeping them identical-but-for-card). The file declares `MODEL = "claude-3-5-sonnet"`, `TEMPERATURE = 0.0`, `from anthropic import Anthropic`, and `os.environ["ANTHROPIC_API_KEY"]` — giving the scanner deterministic model-configuration and permission/env-var surface signals that no Phase 3 fixture file provided. Updated `tests/fixtures/README.md`.

  Design decisions:
  - Two-phase discovery so `fixture-plain` (no signals) never reads source code, and a 10k-file scan completes in 0.12 s (bound 5 s). Glob-driven, not a full tree walk.
  - Model config derived from source-level signals (assignment regex then known-prefix fallback), with the provider corroborated by both import scan and manifest deps. Provenance points at the single source file that yielded model + provider, which is honest for the common case where both live in the same file.
  - Only `data_categories` is LLM-derived for `fixture-basic`; name/description/version come from pyproject (deterministic). This keeps the determinism gate meaningful: all non-LLM fields are byte-identical across scans, provenance hashes included.
  - Constructed AgentCards set `url=""` (no git-remote derivation in v1); the verifier/attention ledger (Phase 8) is the right place to flag that gap.
  - Discovery globs are internal defaults, documented in `discovery.py`'s module docstring, separate from `Config.watched_paths` (which drives Phase 9 change detection). The config reference is deferred to the Phase 13 README.
  - Added `extend-immutable-calls = ["typer.Argument", "typer.Option"]` to the ruff config — the canonical Typer+ruff fix, now that real commands carry typed argument defaults.

  Validation: ruff check clean, ruff format clean, mypy strict (19 source files, no issues), pytest 113 passed (5 CLI + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 22 secrets). The secrets-discipline grep now parametrises over all six new ingest modules, confirming none persists the API key. No live LLM call in any test.

- 2026-07-18 — Phase 5 (init: config and context only) — PASS: `pytest tests/test_init.py` green (20 tests: --defaults writes valid config+context round-tripping through Phase 1/2 models, --from invalid lists all five invalid fields and exits 1, re-run prompts before overwrite with y/n auto-answered, --force bypasses prompt, provider env required in non-interactive mode, key value never persisted); `make check-all` green (ruff + mypy + 133 tests).

  **Phase 5 completion notes:**

  Built `src/autogovern/context/wizard.py`, `src/autogovern/context/__init__.py`, `src/autogovern/hooks/__init__.py` (Phase 10 stubs), and `tests/test_init.py`. Rewired the `init` command in `cli.py` from a stub to a real wizard.

  The wizard is a deep module: pure helpers (`default_context`, `provider_from_env`, `load_context_from_file`, `format_context_errors`, `build_config`) plus a single `write_init` orchestrator that takes a `confirm` callable so all interactive IO stays in the CLI shell. Writes are atomic (temp-file rename) so a failure midway leaves existing files intact.

  Three input modes, mapped to the spec's `--defaults` / `--from <file>` / interactive:
  - **`--defaults`** (non-interactive CI): context from `default_context()` (conservative starting values), provider from env vars `AUTOGOVERN_API_BASE` / `AUTOGOVERN_MODEL` / `AUTOGOVERN_API_KEY_ENV` (optional `AUTOGOVERN_TEMPERATURE`, default 0). Refuses to finish without the three required env vars, naming them in the error.
  - **`--from <file>`**: loads and validates a context manifest YAML against `ContextManifest`. On validation failure, raises `ContextImportError` carrying one human-readable line per invalid field, so the CLI lists every problem in one run instead of failing on the first. Provider still comes from env (non-interactive).
  - **Interactive** (neither flag): prompts field-by-field for context and for the three provider settings, each with a safe default derived from `default_context()`.

  Provider env vars are read at call time via `os.environ.get` only; the key *value* is never touched. A dedicated test asserts the key value never appears in either written file, only the env-var *name* (`OPENROUTER_API_KEY`) appears in `config.yaml`. The secrets-discipline grep now scans `context/wizard.py` and `hooks/__init__.py` automatically (it rglobs `src/`), confirming neither persists the key.

  Hook and CI installation are explicitly Phase 10 scope, so `init` calls stub functions `install_pre_commit_hook` and `install_ci_config` in `hooks/__init__.py` that install nothing and return "not implemented (Phase 10)" status messages. `--no-hooks` suppresses the hook call; `--local-enforce` is accepted and threaded through to the stub. The next-steps banner points at `scan` then `generate`.

  Overwrite handling: if `config.yaml` or `context.yaml` already exists and `--force` is not set, the CLI asks once via `typer.confirm` whether to overwrite. Declining returns a `wrote_files=False` result with no writes. `--force` bypasses the prompt for CI idempotency.

  Design decisions:
  - Chose env vars (not a `.env` file, not interactive-only) for the non-interactive provider path so `init --defaults` works in CI without prompts while still refusing to run generation without real provider settings, per the spec's "no default model" rule.
  - `load_context_from_file` validates the whole manifest in one pydantic call and surfaces every field error, rather than re-validating per field. The invalid fixture has exactly five errors (jurisdictions, deployment_context, autonomy_level, data_categories, risk_appetite); the test asserts each field name appears in the CLI output.
  - `write_init` accepts a `confirm` callable rather than calling `typer.confirm` directly, keeping the wizard testable without the Typer runner and keeping the pure core free of CLI imports.
  - The written `config.yaml` round-trips through the Phase 2 `load_config`, and the written `context.yaml` round-trips through `ContextManifest.model_validate`, proving the Phase 5 output is consumable by the phases that follow.

  Validation: ruff check clean, ruff format clean, mypy strict (20 source files, no issues), pytest 133 passed (5 CLI + 20 init + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 23 secrets). No live LLM call in any test.

- 2026-07-18 — Phase 6 (framework pack loader) — PASS: `pytest tests/test_pack.py` green (21 tests: bundled pack resolves every reference with zero warnings, dangling file/numbered/slug/framework references each fail loading with the exact bad reference named, graph query for model_configuration returns system-card and inventory only, graph query for unknown input returns empty, deterministic across loads); `make check-all` green (ruff + mypy + 156 tests).

  **Phase 6 completion notes:**

  Built `src/autogovern/frameworks/loader.py`, `src/autogovern/frameworks/__init__.py`, and `tests/test_pack.py`. Enriched `frameworks/pack.yaml` with `profile_inputs` and `context_inputs` declarations on every document feed so the section dependency graph is fully data-driven.

  The loader is a deep module: a single `load_pack(pack_dir=None) -> Pack` entry point over a pure resolver core. `Pack` carries the resolved style authority, verifier rubric, enterprise hooks, document feeds, scope notes, and a ready-to-query `SectionDependencyGraph`. Resolution is eager — a single dangling reference aborts the load, so the generation engine never sees a half-resolved pack.

  Reference resolver (`resolve_section`) handles three syntaxes, all relative to the pack directory:
  - `file.md` (whole file): returns the H1 title plus full content.
  - `file.md#N` (numbered): finds the `## N. Title` heading and returns it plus the body up to the next sibling `## ` heading. Sub-headings (`###`) are included in the body; the section stops at the next `##`, not EOF.
  - `file.md#slug` (slug fragment): matches a heading by slugified text. Matches on exact slug or a prefix at a word boundary, so the style-authority reference `skill-source.md#writing-rules-for-all-output` resolves the long heading "Writing rules for all output — avoid common AI language, ticks, and style". Em/en dashes are normalised to spaces before slugifying so the dash acts as a phrase boundary.

  Section dependency graph: `SectionDependencyGraph` holds a forward index (document → inputs) and a reverse index (input → documents). `affected_documents(changed_input)` returns a sorted list, so the output is deterministic and git-stable. The reverse index lets the material-change detector (Phase 9) ask "which sections depend on this profile/context field?" in constant time with zero LLM calls — the prerequisite for the token-efficiency mechanism.

  Data-driven inputs: added `profile_inputs` and `context_inputs` lists to every `document_feeds` entry in `pack.yaml`. The spec says section inputs are declared "in the template", but keeping them in `pack.yaml` honours the spec's parallel instruction to "keep document definitions data-driven (templates plus pack.yaml wiring)" and lets Phase 6 build and test the graph before the Jinja2 templates exist (Phase 7). Input paths use dotted notation against the Phase 1 models: `profile.governance.model_configuration`, `context.autonomy_level`, etc.

  Design decisions:
  - Model configuration (`profile.governance.model_configuration`) feeds only `system-card.md` and `inventory.md`. This is the load-bearing Phase 6 gate and the acceptance contract for Phase 9's deterministic scoring: a model swap is material and affects exactly those two sections. Other documents that touch the agent's behaviour (risk-assessment, oversight, incident-response) depend on `permissions_surface`, `capabilities`, and context fields instead, so a model-id change does not cascade across the whole document set.
  - `QUICKSTART.md`, `ATTENTION.md`, and `CHANGELOG.md` declare no profile/context inputs. They are engine-generated from generation results, not from profile fields, so they are absent from the reverse index. Their regeneration is driven by the Phase 7 engine, not the graph.
  - The verifier rubric is a whole-file reference (`agentic-business-case/rubric.md`, no fragment) because the verifier scores against the full in-scope subset of the rubric, not a single section. The scope notes on the `agentic-business-case` framework entry record which rubric sections apply; Phase 8 consumes them.
  - `data-protection.md` has `templates: []` and one knowledge reference, matching the pack's note that it has no dedicated artefact template in v1. The engine template (Phase 7) fills the gap; the divergence is documented in the pack comment.
  - The loader resolves references against `BUNDLED_PACK_DIR` (the directory shipping `pack.yaml`) by default, so the enterprise tier swaps the pack by passing a different `pack_dir` — no engine changes, the seam the spec requires.

  Validation: ruff check clean, ruff format clean, mypy strict (22 source files, no issues), pytest 156 passed (5 CLI + 20 init + 21 pack + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 23 secrets). No live LLM call in any test.

- 2026-07-18 — Phase 7 (generation engine) — PASS: `pytest tests/test_generate.py` green (15 tests: full document set + lockfile + valid frontmatter everywhere, idempotent second run produces zero diff and zero LLM calls, model-config edit regenerates only system-card + inventory by LLM-call count and untouched mtimes, style preamble snapshot, prompt contains only declared inputs, atomic writes leave no partials on provider failure, CLI integration); `make check-all` green (ruff + mypy + 177 tests).

  **Phase 7 completion notes:**

  Built the `generate/` package as six focused modules behind one entry point (`generate_docs`), applying the ai-native-codebase-design skill: a pure core (input resolution, hashing, prompt building, frontmatter) isolated from the single LLM seam, with content-addressed atomic writes.

  Modules:
  1. **`generate/inputs.py`** — pure. `extract_input(path, profile, context)` resolves dotted `profile.*`/`context.*` paths, auto-unwrapping `ProvenancedField` values. `compute_section_hash` folds declared inputs + pack section contents + pack version into a stable SHA-256. `profile_file_hashes` builds the frontmatter `input_hashes` audit map from every provenance record.
  2. **`generate/prompts.py`** — pure. `build_section_messages` builds the chat messages for one document: a system message carrying the `STYLE_PREAMBLE` (the banned-constructions block) plus the pack's style-authority text, and a user message carrying only the document's declared pack sections and resolved inputs. The `STYLE_PREAMBLE` is exported as the snapshot target.
  3. **`generate/frontmatter.py`** — pure. Parse/render YAML frontmatter with sorted keys for byte-stable output. `build_frontmatter` assembles the spec's fields (doc_version, agent_version, generated, generator_version, input_hashes, framework_pack_version) plus `section_hashes` (the operational field the engine compares on regeneration).
  4. **`generate/lockfile.py`** — `governance/profile.lock`: a line-stable YAML serialisation of the AgentProfile, written atomically on every generate. `read_lockfile` for Phase 9's diff.
  5. **`generate/writer.py`** — `write_if_changed`: content-addressed atomic write via temp-file rename. The foundation of idempotence.
  6. **`generate/engine.py`** — the deep module. `generate_docs(root, config, profile, context, *, provider, pack=None) -> GenerationResult` orchestrates: for each enabled LLM-fed document, resolve declared inputs, hash them, compare to the stored `section_hashes` in the existing file's frontmatter, and call the provider only when the hash changed. Engine-generated docs (QUICKSTART, ATTENTION, CHANGELOG) are built from the regeneration results, not the LLM.

  CLI `generate` command: loads config and context, scans the repo (write_card=False, since the card is the scanner's concern), runs the engine, and prints the regenerated/skipped summary. Exits 1 with "no agent signals" on a non-agent repo.

  Design decisions:
  - **Idempotence mechanism**: a document is rewritten only when at least one of its sections' input hashes changed. On a no-op second run, all hashes match → zero LLM calls → zero writes → zero git diff. The `generated` timestamp is set only when a document is actually regenerated, so an unchanged file keeps its existing timestamp. For engine docs, the body is compared to the existing body; if identical, the file is left untouched (preserving its old frontmatter and timestamp). This is the content-addressed-write discipline that makes the idempotence gate hold.
  - **Section granularity = document**: the build plan's gate asserts regeneration "by LLM call count and untouched file mtimes", and the Phase 6 graph returns documents, not sub-sections. Each LLM-fed document is one generation unit (one prompt with all its declared inputs), so "model configuration changed" → 2 LLM calls (system-card + inventory) and the other five LLM-fed docs' mtimes are untouched. The architecture supports splitting a document into sub-sections later without changing the graph contract.
  - **`section_hashes` in frontmatter**: the spec lists `input_hashes` (file → content hash, for audit) but the build plan requires per-section input-hash storage for regeneration decisions. Both live in frontmatter: `input_hashes` is the audit field drawn from profile provenance; `section_hashes` is the operational field the engine compares. The divergence is noted here; the spec's frontmatter list is a working assumption and the build plan is the operational spec.
  - **Style authority in every prompt**: the `STYLE_PREAMBLE` (banned constructions: em-dashes, contrastive negation, significance inflation, meta-signposting, copula avoidance, rhetorical triplets) is embedded as a fixed system-message prefix on every generation call, followed by the pack's full style-authority text. The snapshot test guards the preamble against drift; Phase 8's verifier also checks adherence.
  - **Token efficiency**: each prompt receives only its declared inputs (resolved by dotted path) plus its pack sections, never the whole profile or repo. This is the spec's primary token-efficiency mechanism, and the Phase 6 graph makes the regeneration decision free (zero LLM calls to decide what to re-render).
  - **Atomic writes**: every file write goes through temp-file rename. A provider failure mid-generation leaves existing documents intact and no `.tmp` files behind (asserted by test).
  - **Pack fix**: corrected `profile.governance.capabilities`/`skills` to `profile.capabilities`/`profile.skills` in `pack.yaml` — those are top-level AgentCard fields, not governance-extension fields. The extractor would have raised `KeyError` on the wrong paths.

  Validation: ruff check clean, ruff format clean, mypy strict (28 source files, no issues), pytest 177 passed (5 CLI + 20 init + 21 pack + 15 generate + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 31 secrets). The secrets-discipline grep now scans 31 source files (was 23), auto-covering the six new generate modules. No live LLM call in any test.

- 2026-07-18 — Phase 8 rework (remove verifier, add vanilla mode) — PASS: `pytest tests/test_generate.py` green (17 tests including 2 new vanilla-mode tests); `make check-all` green (ruff + mypy + 180 tests).

  **Rework notes:**

  Removed the verifier pass, claim-stripping, and the attention ledger's open/close lifecycle. Added vanilla mode (progressive enhancement: `generate` works without `init`).

  What was removed:
  - `verify/verifier.py` (the second LLM pass), `verify/clean.py` (claim stripping), `generate/ledger.py` (the open/close ledger). The `verify/` package is kept as an empty namespace.
  - All verifier integration in the engine: `_verify_and_clean`, `_detect_generation_gaps`, `_load_ledger`, `verifier_call_count`, `verifier_results`, `attention_items` on `GenerationResult`.
  - `tests/test_verify.py` (14 tests deleted).

  Why: the docs are generated from the scan and match reality by construction. A self-audit that routes its fallout to humans is the wrong design — the fix for a bad generation is a better generation, not a human review task.

  What was added (vanilla mode):
  - `config_loader.load_config_or_env()`: tries `config.yaml`, falls back to `AUTOGOVERN_*` env vars.
  - `config_loader.load_context_or_default()`: tries `context.yaml`, falls back to `default_context()`. Returns `(context, from_file)` so the engine knows whether to write a generic or specific `ATTENTION.md`.
  - `provider_from_env()` moved from `context/wizard.py` to `config_loader.py` (it's about config, not init).
  - `default_context()` moved to `context/defaults.py` (standalone, no circular import).
  - `generate` and `scan` CLI commands use `load_config_or_env` and `load_context_or_default` instead of hard-failing without config/context.
  - `generate_docs` takes `context_from_file: bool` parameter; writes `ATTENTION.md` as an informational note (generic vs specific) rather than a work queue.
  - 2 new tests: vanilla mode generates docs without context, vanilla mode is idempotent.

  Spec updated: removed the "Verification instead of human review tags" section, replaced with "No verifier pass" and "Attention ledger" sections. Added "Vanilla mode" section. Updated acceptance criterion 6 (was about verifier unsupported claims, now about vanilla mode working without init). Updated observability section (removed verifier results and attention items from run manifest). Updated `--strict` description (no longer fails on open attention items, only advisory scores).

  Buildplan updated: Phase 8 reworked with a rework note explaining the design change. Phase 10 `--strict` and Phase 12 run manifest updated to remove verifier/attention references.

  Validation: ruff check clean, ruff format clean, mypy strict (29 source files, no issues), pytest 180 passed (5 CLI + 20 init + 21 pack + 17 generate + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 31 secrets). The secrets-discipline grep now scans 31 files (was 33; two verify modules deleted). No live LLM call in any test.


- 2026-07-18 — Phase 9 (material change detection) — PASS: `pytest tests/test_detect.py` green (16 tests: tool added to .mcp.json → deterministic score >= 80 with zero LLM calls, model swap → deterministic material, no diff when unchanged → immaterial, unwatched file → heuristic negative no rebuild, watched and nested globs match, prompt edit → semantic scorer invoked once with band logic for scores 15/50/85, lockfile line-stability with sorted keys, deterministic scorer unit tests for data category and permission scope changes, build_result takes max score); `make check-all` green (ruff + mypy + 199 tests).

  **Phase 9 completion notes:**

  Built the `detect/` package as three ordered stages behind a single orchestrator (`detect_material_change`), applying the ai-native-codebase-design skill: each stage is a pure module, the orchestrator runs them in cost order and stops early.

  Modules:
  1. **`detect/heuristic.py`** — the fast, deterministic, no-LLM gate. `heuristic_pass(changed_files, config) -> HeuristicResult` checks whether any changed file matches the `watched_paths` globs from config. Supports `dir/**` recursive globs and single-segment patterns. A negative result means no profile rebuild is needed.
  2. **`detect/diff.py`** — the profile diff pass. `diff_profiles(locked, current) -> ProfileDiff` produces a field-level diff: model configuration, permissions surface, data categories, dependencies, prompt inventory (path changes are deterministic; content changes are flagged as semantic), and card-standard fields. `diff_context` compares context manifests (autonomy level and risk appetite changes are deterministic material).
  3. **`detect/scorer.py`** — deterministic scoring rules plus the semantic LLM pass. `score_deterministic(diff)` checks each diff field against the spec's named rules: new/removed tool (100), permission scope change (90), new data category (100), model swap (100), autonomy change (100), risk appetite change (90), prompt path change (90). `score_semantic(diff, provider)` makes one LLM call for prompt content changes, returning a `SemanticScore` (0-100 + reasoning). `band_for(score, thresholds)` applies the Pareto bands: >= material → material, <= immaterial → immaterial, between → advisory.
  4. **`detect/__init__.py`** — the orchestrator. `detect_material_change(changed_files, config, locked_profile, current_profile, ...) -> DetectionResult` runs the three stages in order. Stage 1 (heuristic) gates stage 2 (profile diff) in pre-commit mode; in `ci_mode=True`, the profile diff always runs (the heuristic is informational). Stage 3 (semantic) runs only when there are semantic fields and no deterministic hit.

  Config change: added `prompts/**` to the default `watched_paths` in the Config model. The spec explicitly names "prompt files" as a watched path; the Phase 1 defaults were missing it. This is a one-line addition that makes prompt edits trigger the heuristic pass in pre-commit.

  Design decisions:
  - **Two modes for the orchestrator**: pre-commit mode (default) stops at the heuristic if negative — the fast path that runs in under 500ms with zero LLM. CI mode (`ci_mode=True`) always runs the profile diff, because the spec says "the profile diff and semantic passes run in CI" regardless of the heuristic. The heuristic is informational in CI, not a gate.
  - **Deterministic scoring is max-score, not sum**: the spec says certain changes "are material by definition", so a single deterministic hit (score 100) is enough to declare material without an LLM. The semantic pass only runs when no deterministic rule fired AND there are semantic fields (prompt content changes).
  - **Semantic scorer degrades to material on failure**: if the provider is unavailable or returns an invalid response, the scorer assumes material (score 100) so docs get regenerated rather than silently passing. This is the "offline failure mode" from the spec: "if the model provider is unreachable, check still runs the heuristic pass and reports degraded mode."
  - **Profile diff is field-level, not byte-level**: the diff compares the governance extension fields (model_configuration, permissions_surface, data_categories, dependencies, prompt_inventory) and the context fields (autonomy_level, risk_appetite). This keeps the diff semantic — a reordering of tools doesn't trigger a false positive — and feeds the deterministic scorer directly.
  - **Prompt inventory has two diff paths**: a path change (file added or removed) is deterministic material (score 90). A content change (same path, new hash) is semantic — it goes to the LLM scorer. This split is the spec's "prompt content changes" case.
  - **Lockfile line-stability**: `serialise_profile` uses `yaml.safe_dump(..., sort_keys=True, default_flow_style=False)`. Two serialisations of the same profile are byte-identical, so `git diff` on `profile.lock` is minimal and meaningful — each line change is a real field change.

  Validation: ruff check clean, ruff format clean, mypy strict (32 source files, no issues), pytest 199 passed (5 CLI + 20 init + 21 pack + 17 generate + 16 detect + 7 fixtures + 29 models + 16 parsers + 1 perf + 11 scan + 6 scan-cli + 16 provider + 35 secrets). The secrets-discipline grep now scans 35 source files (was 31), auto-covering the three new detect modules. No live LLM call in any test.

- 2026-07-18 — Phase 10 (check, fix, diff, explain, hooks, CI writers) — PASS: `pytest tests/test_check.py` green (18 tests: acceptance criterion 2 check→fix→check cycle, --strict on advisory, --json on check/diff/explain, pre-commit hook installed+fast+executable, hook CLI command, --local-enforce pre-push, CI writers for GitHub/Forgejo/Bitbucket/generic with remote detection, --model override); `make check-all` green (ruff + mypy + 216 tests).

  Built `check.py` (five-step check sequence with CheckResult), `explain.py` (frontmatter provenance rendering), real `hooks/__init__.py` (pre-commit hook + forge-aware CI writers for GitHub/Forgejo/Bitbucket/generic), wired all CLI commands + global flags (--json, --config, --model, --strict).

- 2026-07-18 — Phase 11 (headless input and library surface) — PASS: `pytest tests/test_api.py` green (7 tests: --profile generate with no repo, library scan/check/generate returning typed results, headless check with profile, check --profile parity with repo scan, API signature stability, public exports); `make check-all` green (ruff + mypy + 224 tests).

  Built `api.py` (public library API: scan, generate_docs, check, load_profile with headless profile support), updated `__init__.py` exports, added `--profile` flag to generate/check/diff CLI commands.

- 2026-07-18 — Phase 12 (run manifests and observability) — PASS: `pytest tests/test_manifests.py` green (9 tests: manifest written on generate and check, validates against RunManifest schema, no secret values, config snapshot strips key env, token counts null when not reported and present when reported, multiple manifests accumulate); `make check-all` green (ruff + mypy + 234 tests).

  Built `observability/manifest.py` (build_manifest, write_manifest, read_manifests), wired manifest writing into generate and check CLI commands.

# AGENTS.md — autogovern

> Guidance for coding agents working in this repo. Non-obvious information
> only; anything readable from the repo itself does not belong here.

## What this repo is

**autogovern** — a CLI that generates and maintains enterprise-grade governance
documentation for AI agents directly from codebase + org context. Open-source
core; enterprise features (fleet console, dynamic framework packs, AgentGuard)
are out of scope, but the architecture leaves clean seams for them.

Remote: `https://github.com/ashborn-systems/autogovern`

## Build & test commands (exact flags matter)

```bash
uv sync                          # install (editable)
uv run autogovern --help         # CLI entry point
uv run ruff check .              # lint
uv run ruff format --check .     # format check
uv run mypy src                  # type check
uv run pytest                    # tests (all)
uv run pytest -k "<name>"        # single test
make check-all                   # ruff + format + mypy + pytest (full gate)
make build                       # wheel + sdist into dist/
```

Pre-commit: `uv run pre-commit run --all-files`

## Hard constraints

1. **All tests mock the model provider.** No test may call a live LLM. The one
   exception is `tests/test_smoke.py`, which runs only when `AUTOGOVERN_SMOKE=1`
   and a provider is configured.
2. **Determinism is a feature.** Any test that passes intermittently is a
   failing test.
3. **Secrets never touch disk.** The model API key is read at runtime from the
   env var named in config and never written to config files, logs, or run
   manifests. `tests/test_secrets_discipline.py` enforces this statically.
4. **Package name is `autogovern`, module is `autogovern`.** No hyphen anywhere.
   The framework pack ships inside the package at `src/autogovern/frameworks/`
   so the package is self-contained.
5. **The framework pack is data, never code.** The generation engine treats
   `src/autogovern/frameworks/` as data. Do not import framework content as
   Python modules — read and parse it at runtime.
6. **Agent keys are canonical and single-sourced.** `ingest/discovery.py`
   owns the one naming rule (root agent: profile name; nested agent:
   hyphen-joined root path; `dedupe_keys` for collisions). Never derive an
   agent's directory or context key anywhere else.
7. **The tool is model-agnostic.** No default model, no bundled provider list.
   Scanner logic treats every OpenAI-compatible provider even-handedly, and
   tests/fixtures rotate across a realistic mix of providers rather than
   defaulting to one vendor. `CLAUDE.md`/`.claude/` appear in discovery globs
   because the A2A spec lists them as agent-instruction files, not as an
   endorsement; they sit alongside `AGENTS.md` and `agent.md`.

## Code conventions

- **Python**: ruff for lint + format (no black, no isort). mypy strict.
  pydantic v2 for all data models. Typer for the CLI.
- **Deep modules**: maximize functionality while minimizing the interface.
  Pull complexity downwards — a simple interface matters more than a simple
  implementation.
- **Functional core, imperative shell**: pure business logic stays isolated
  from external side effects (LLM calls, filesystem).

## Package layout

```
src/autogovern/
  cli.py              # Typer app, command definitions
  ingest/             # repo scanners and A2A card construction
  context/            # org context wizard and manifest models
  frameworks/         # bundled framework pack (data, not code)
  generate/           # doc generation engine, section dependency graph
  detect/             # material change detection (heuristic + semantic)
  versioning/         # semver doc_version stamping
  hooks/              # pre-commit and CI entrypoints
  observability/      # run manifests
action/               # GitHub Action definition
install/              # curl/PowerShell installers
tests/
  fixtures/           # small fake agent repos used as known test inputs
```

## Anti-patterns (symptom → cause → fix)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Test fails after unrelated change | Information leakage / shared global state | Encapsulate shared knowledge into a single deep module |
| Cascading try/catch blocks | Punting complexity upwards | Redefine operation semantics to cover the edge case |
| Agent context window overflows | Reading too many files without a plan | Use index-first loading; target exact dependencies |
| Output degrades late in session | Context rot from accumulated irrelevant context | Phase-based loading; compact or restart with fresh plan |

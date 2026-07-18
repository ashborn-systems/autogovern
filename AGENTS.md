# AGENTS.md — autogovern

> Tier 1 hot memory. Non-obvious information only. Anything an agent can read
> from the repo itself (dependency lists, obvious structure) does not belong here.

## What this repo is

**autogovern** — a CLI that generates and maintains enterprise-grade governance
documentation for AI agents directly from codebase + org context. Open-source core;
enterprise features (fleet console, dynamic framework mapping, AgentGuard) are out
of scope for this build but the architecture leaves clean seams for them.

Remote: `https://github.com/ashborn-systems/autogovern`

The spec (`SPEC.md`) and phased build plan (`BUILDPLAN.md`) live at the repo root.
The build log (`BUILDLOG.md`) records one line per phase. The framework pack ships
inside the package at `src/autogovern/frameworks/`.

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
make test                        # pytest only
make lint                        # ruff + mypy only
```

Pre-commit: `uv run pre-commit run --all-files`

## Hard constraints

1. **Spec is authoritative.** `SPEC.md` wins over BUILDPLAN.md on any conflict.
   If you find one, note it in `BUILDLOG.md`.
2. **All tests mock the model provider.** No test may call a live LLM. Smoke
   tests run only when `AUTOGOVERN_SMOKE=1` and a provider is configured.
3. **Determinism is a feature.** Any test that passes intermittently is a
   failing test.
4. **Secrets never touch disk.** `.env` is git-ignored; `.env.example` is
   committed. The model API key is read at runtime from the named env var and
   never written to config files, logs, or run manifests.
5. **Spec-anchored SDD.** No "vibe coding." The build plan and spec are the
   spec; acceptance criteria map to tests; code plus tests are the enforcement
   layer. Apply the `ai-native-codebase-design` skill throughout: deep modules
   with minimal interfaces, interface-first generation, and design-it-twice for
   the provider client, the pack loader, and the generation engine.
6. **Phase gates are serial.** A phase is complete only when every validation
   passes and all previous phases still pass. Do not start a phase before the
   previous gate is green. Every phase ends with a commit.
7. **Package name is `autogovern`, module is `autogovern`.** No hyphen anywhere.
   The framework pack ships inside the package at `src/autogovern/frameworks/`
   so the package is self-contained.
8. **The framework pack is data, never code.** The generation engine treats
   `src/autogovern/frameworks/` as data. Do not import framework content as
   Python modules — read and parse it at runtime.
9. **The tool is model-agnostic; do not anchor on one provider.** The spec
   mandates provider neutrality (no default model, no bundled provider list).
   Apply that to code and examples alike: scanner logic must treat every
   OpenAI-compatible provider even-handedly, and tests/fixtures must rotate
   across a realistic mix of open and closed-source providers rather than
   defaulting to Anthropic/Claude. `CLAUDE.md`/`.claude/` appear in discovery
   globs because the A2A spec lists them as agent-instruction files, not as
   an endorsement; they sit alongside `AGENTS.md` and `agent.md`.

## Code conventions

- **Python**: ruff for lint + format (no black, no isort). mypy strict.
  pydantic v2 for all data models. Config via pydantic-settings singleton —
  never scattered `os.getenv()`. Typer for the CLI.
- **Interface-first generation**: write docstrings/interface comments before
  the implementation body. If the comment is hard to write, redesign the
  interface.
- **Deep modules**: maximize functionality while minimizing the interface.
  Pull complexity downwards — it is more important for a module to have a
  simple interface than a simple implementation.
- **Functional core, imperative shell**: pure business logic stays isolated
  from external side effects (LLM calls, filesystem).

## Package layout

```
src/autogovern/
  cli.py              # Typer app, command definitions
  config.py           # pydantic-settings singleton
  ingest/             # repo scanners and A2A card construction
  context/            # org context wizard and manifest models
  frameworks/         # bundled framework pack (data, not code)
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

## Anti-patterns (symptom → cause → fix)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Test fails after unrelated change | Information leakage / shared global state | Encapsulate shared knowledge into a single deep module |
| Cascading try/catch blocks | Punting complexity upwards | Redefine operation semantics to cover the edge case |
| Agent context window overflows | Reading too many files without a plan | Use index-first loading; target exact dependencies |
| Output degrades late in session | Context rot from accumulated irrelevant context | Phase-based loading; compact or restart with fresh plan |
| Spec and code disagree | Spec drift — code changed without spec update | Update the spec in the same session as the change |

## Phase status

Phases 0-4 are complete. Next: Phase 5 — init (config and context wizard).
See `BUILDPLAN.md` and `BUILDLOG.md`.

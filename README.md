# autogovern

Generate and maintain enterprise-grade governance documentation for AI agents, directly from the agent's codebase plus a small amount of organisational context.

## Status

Phase 0 (scaffold) complete. The CLI has seven stub commands; real implementations arrive in Phases 1-13 per `BUILDPLAN.md`.

## Install

```bash
uv sync
```

## Usage

```bash
autogovern --help
```

Commands: `init`, `scan`, `generate`, `diff`, `check`, `explain`, `hook`.

## Development

```bash
make check-all    # ruff check + ruff format --check + mypy + pytest
make test         # pytest only
make lint         # ruff + mypy only
```

## Licence

Apache-2.0

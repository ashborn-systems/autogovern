"""Typer CLI application for autogovern.

Stub commands exit 0 with a "not implemented" message. The ``generate``
command is wired to the config loader so that running it without a config
file fails clearly (Phase 2 requirement). The ``scan`` command is fully
implemented in Phase 4.
"""

from __future__ import annotations

from pathlib import Path

import typer

from autogovern.config_loader import ConfigInvalidError, ConfigNotFoundError, load_config
from autogovern.ingest import ScanResult, scan_repo
from autogovern.models import Config
from autogovern.provider import build_provider

app = typer.Typer(
    name="autogovern",
    help="Generate and maintain governance documentation for AI agents.",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Wizard: config, context manifest, and hook install in one step."""
    typer.echo("init: not implemented (Phase 5)")


@app.command()
def scan(
    path: Path = typer.Argument(Path("."), help="Repository root to scan."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    no_write_card: bool = typer.Option(
        False, "--no-write-card", help="Do not write .well-known/agent.json."
    ),
    config: Path | None = typer.Option(None, "--config", help="Alternate config file."),
) -> None:
    """Build and print the AgentProfile (writes AgentCard if absent)."""
    cfg = _load_config_or_exit(config)
    provider = build_provider(cfg)
    try:
        result = scan_repo(path, cfg, provider=provider, write_card=not no_write_card)
    finally:
        provider.close()

    if json_output:
        typer.echo(result.to_json())
        return

    _print_scan_human(result)


@app.command()
def generate() -> None:
    """Full or incremental doc generation into governance/."""
    _load_config_or_exit(None)
    typer.echo("generate: not implemented (Phase 7)")


@app.command()
def diff() -> None:
    """Show which sections would change and why, without writing."""
    typer.echo("diff: not implemented (Phase 10)")


@app.command()
def check() -> None:
    """CI gate: report stale docs; --fix regenerates in place."""
    typer.echo("check: not implemented (Phase 10)")


@app.command()
def explain(
    doc: str = typer.Argument(help="Document to explain provenance and verification for."),
) -> None:
    """Plain-language provenance and verification status for a document."""
    typer.echo(f"explain {doc}: not implemented (Phase 10)")


@app.command()
def hook() -> None:
    """Re-install hooks manually if needed."""
    typer.echo("hook: not implemented (Phase 10)")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_config_or_exit(config: Path | None) -> Config:
    """Load config, exiting non-zero with the init remedy on failure."""
    try:
        return load_config(config)
    except ConfigNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except ConfigInvalidError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _print_scan_human(result: ScanResult) -> None:
    """Render a scan result as a human-readable summary table."""
    if not result.signals_found or result.profile is None:
        typer.echo(f"No agent signals found in {result.root}.")
        return

    profile = result.profile
    typer.echo(f"Agent: {profile.name} (v{profile.version})")
    if profile.description:
        typer.echo(profile.description)
    typer.echo("")

    gov = profile.governance
    mc = gov.model_configuration.value
    typer.echo(f"Model:          {mc.model} ({mc.provider})")

    tools = [p.detail.split(" — ")[0] for p in gov.permissions_surface.value if p.kind == "tool"]
    env_vars = [p.detail for p in gov.permissions_surface.value if p.kind == "env"]
    typer.echo(f"Tools:          {_join_or_none(tools)}")
    typer.echo(f"Env vars:       {_join_or_none(env_vars)}")

    deps = [d.name for d in gov.dependencies.value]
    typer.echo(f"Dependencies:   {_join_or_none(deps)}")

    prompts = [p.path for p in gov.prompt_inventory.value]
    typer.echo(f"Prompts:        {_join_or_none(prompts)}")

    categories = [c.value for c in gov.data_categories.value]
    typer.echo(f"Data categories: {_join_or_none(categories)}")

    typer.echo("")
    if result.card_written:
        typer.echo(f"AgentCard: written to {result.card_path}")
    elif result.card_path:
        typer.echo(f"AgentCard: found at {result.card_path}")
    else:
        typer.echo("AgentCard: not written (--no-write-card)")


def _join_or_none(items: list[str]) -> str:
    """Join a list for display, or 'none' when empty."""
    return ", ".join(items) if items else "none"


if __name__ == "__main__":
    app()

"""Typer CLI application for autogovern.

Stub commands exit 0 with a "not implemented" message. The ``generate``
command is wired to the config loader so that running it without a config
file fails clearly (Phase 2 requirement).
"""

import typer

from autogovern.config_loader import ConfigInvalidError, ConfigNotFoundError, load_config

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
def scan() -> None:
    """Build and print the AgentProfile (writes AgentCard if absent)."""
    typer.echo("scan: not implemented (Phase 4)")


@app.command()
def generate() -> None:
    """Full or incremental doc generation into governance/."""
    try:
        load_config()
    except ConfigNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except ConfigInvalidError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
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


if __name__ == "__main__":
    app()

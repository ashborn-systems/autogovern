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
from autogovern.context import (
    ContextImportError,
    InitResult,
    build_config,
    default_context,
    load_context_from_file,
    provider_from_env,
    write_init,
)
from autogovern.ingest import ScanResult, scan_repo
from autogovern.models import Config, ContextManifest, ModelProviderConfig
from autogovern.provider import build_provider

app = typer.Typer(
    name="autogovern",
    help="Generate and maintain governance documentation for AI agents.",
    no_args_is_help=True,
)


@app.command()
def init(
    defaults: bool = typer.Option(
        False, "--defaults", help="Non-interactive: provider from env vars, context from defaults."
    ),
    from_file: Path | None = typer.Option(
        None, "--from", help="Import context manifest from a YAML file."
    ),
    no_hooks: bool = typer.Option(False, "--no-hooks", help="Skip pre-commit hook installation."),
    local_enforce: bool = typer.Option(
        False, "--local-enforce", help="Also install the pre-push hook (Phase 10)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing config/context without prompting."
    ),
) -> None:
    """Wizard: config, context manifest, and hook install in one step."""
    root = Path.cwd()
    non_interactive = defaults or from_file is not None

    context = _resolve_context(from_file=from_file, defaults=defaults)
    provider = _resolve_provider(non_interactive)
    config = build_config(provider)

    try:
        result = write_init(
            root=root,
            config=config,
            context=context,
            force=force,
            no_hooks=no_hooks,
            local_enforce=local_enforce,
            confirm=typer.confirm,
        )
    except Exception as exc:  # pragma: no cover - defensive, write_init is pure
        typer.echo(f"init failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_init_result(result, context)


def _resolve_context(*, from_file: Path | None, defaults: bool) -> ContextManifest:
    """Return a validated ContextManifest from --from, --defaults, or prompts."""
    if from_file is not None:
        try:
            return load_context_from_file(from_file)
        except ContextImportError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    if defaults:
        return default_context()
    return _prompt_context()


def _resolve_provider(non_interactive: bool) -> ModelProviderConfig:
    """Provider from env vars, or interactive prompts when env is unset."""
    provider = provider_from_env()
    if provider is not None:
        return provider
    if non_interactive:
        typer.echo(
            "Non-interactive init requires provider settings. Set the "
            "AUTOGOVERN_API_BASE, AUTOGOVERN_MODEL, and AUTOGOVERN_API_KEY_ENV "
            "environment variables, or run init interactively.",
            err=True,
        )
        raise typer.Exit(code=1)
    return _prompt_provider()


def _prompt_provider() -> ModelProviderConfig:
    """Prompt for the three required provider settings."""
    api_base = typer.prompt(
        "Provider API base (OpenAI-compatible)", default="https://openrouter.ai/api/v1"
    )
    model = typer.prompt("Model id")
    api_key_env = typer.prompt("Env var name holding the API key", default="OPENROUTER_API_KEY")
    return ModelProviderConfig(api_base=api_base, model=model, api_key_env=api_key_env)


def _prompt_context() -> ContextManifest:
    """Interactive context wizard, field by field, with safe defaults."""
    base = default_context()
    organisation = typer.prompt("Organisation legal name", default=base.organisation)
    sector = typer.prompt("Sector", default=base.sector)
    jurisdictions_raw = typer.prompt(
        "Jurisdictions (comma-separated)", default=", ".join(base.jurisdictions)
    )
    jurisdictions = [j.strip() for j in jurisdictions_raw.split(",") if j.strip()]
    deployment_context = typer.prompt(
        "Deployment context (internal / customer-facing / third-party-distributed)",
        default=base.deployment_context.value,
    )
    intended_users = typer.prompt("Intended users", default=base.intended_users)
    autonomy_level = typer.prompt(
        "Autonomy level (human-in-the-loop / human-on-the-loop / fully-autonomous)",
        default=base.autonomy_level.value,
    )
    oversight_model = typer.prompt("Oversight model", default=base.oversight_model)
    data_categories_raw = typer.prompt(
        "Data categories (comma-separated: none, personal, special-category,"
        " financial, operational)",
        default=", ".join(c.value for c in base.data_categories),
    )
    data_categories = [d.strip() for d in data_categories_raw.split(",") if d.strip()]
    risk_appetite = typer.prompt(
        "Risk appetite (conservative / balanced / aggressive)",
        default=base.risk_appetite.value,
    )
    strategy = typer.prompt("Strategy (one paragraph)", default=base.strategy)
    owner = typer.prompt("Owner (accountable person or role)", default=base.owner)
    review_cadence = typer.prompt("Review cadence", default=base.review_cadence)

    try:
        return ContextManifest(
            organisation=organisation,
            sector=sector,
            jurisdictions=jurisdictions,
            deployment_context=deployment_context,
            intended_users=intended_users,
            autonomy_level=autonomy_level,
            oversight_model=oversight_model,
            data_categories=data_categories,
            risk_appetite=risk_appetite,
            strategy=strategy,
            owner=owner,
            review_cadence=review_cadence,
        )
    except Exception as exc:
        typer.echo(f"Invalid context input: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _print_init_result(result: InitResult, context: ContextManifest) -> None:
    if not result.wrote_files:
        typer.echo("init: no files written (existing config retained).")
        return
    typer.echo(f"init: wrote {result.config_path}")
    typer.echo(f"init: wrote {result.context_path}")
    if result.overwritten:
        typer.echo("init: overwrote existing files.")
    typer.echo(result.hook_message)
    typer.echo(result.ci_message)
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. autogovern scan      # build the AgentProfile and AgentCard")
    typer.echo("  2. autogovern generate  # write the governance document set")


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

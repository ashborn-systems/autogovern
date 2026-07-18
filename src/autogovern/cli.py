"""Typer CLI application for autogovern.

Seven commands: ``init``, ``scan``, ``generate``, ``diff``, ``check``,
``explain``, and ``hook`` (with ``install`` and ``run`` subcommands). The
CLI is a thin shell over the library API (:mod:`autogovern.api`) and the
package entry points; all interactive IO lives here.
"""

from __future__ import annotations

from pathlib import Path

import typer

from autogovern.api import check as check_lib
from autogovern.api import load_profile
from autogovern.config_loader import (
    ConfigInvalidError,
    ConfigNotFoundError,
    ContextInvalidError,
    load_config_or_env,
    load_context_or_default,
    provider_from_env,
)
from autogovern.context import (
    ContextImportError,
    InitResult,
    build_config,
    default_context,
    load_context_from_file,
    write_init,
)
from autogovern.explain import explain_document
from autogovern.generate import generate_docs
from autogovern.hooks import install_pre_commit_hook
from autogovern.ingest import ScanResult, scan_repo
from autogovern.models import AgentProfile, Config, ContextManifest, ModelProviderConfig
from autogovern.observability import build_manifest, write_manifest
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
        False, "--local-enforce", help="Also install the pre-push hook (full check)."
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
    model: str | None = typer.Option(None, "--model", help="Override the configured model."),
) -> None:
    """Build and print the AgentProfile (writes AgentCard if absent)."""
    cfg = _load_config_or_env_or_exit(config, model)
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
def generate(
    path: Path = typer.Argument(Path("."), help="Repository root to generate docs for."),
    config: Path | None = typer.Option(None, "--config", help="Alternate config file."),
    model: str | None = typer.Option(None, "--model", help="Override the configured model."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    profile_path: Path | None = typer.Option(
        None, "--profile", help="AgentProfile JSON file (headless mode)."
    ),
) -> None:
    """Full or incremental doc generation into governance/."""
    cfg = _load_config_or_env_or_exit(config, model)
    context, context_from_file = _load_context_or_default_or_exit()
    provider = build_provider(cfg)
    usage: dict[str, int | None] | None = None
    try:
        if profile_path is not None:
            profile = _load_profile_or_exit(profile_path)
        else:
            scan_result = scan_repo(path, cfg, provider=provider, write_card=False)
            if not scan_result.signals_found or scan_result.profile is None:
                typer.echo(f"No agent signals found in {path}. Nothing to generate.", err=True)
                raise typer.Exit(code=1)
            profile = scan_result.profile
        result = generate_docs(
            path,
            cfg,
            profile,
            context,
            provider=provider,
            context_from_file=context_from_file,
        )
        usage = provider.total_usage
    finally:
        provider.close()

    _write_generate_manifest(path, cfg, result, token_counts=usage)

    if json_output:
        import json as _json

        typer.echo(
            _json.dumps(
                {
                    "regenerated": result.regenerated,
                    "skipped": result.skipped,
                    "llm_calls": result.llm_call_count,
                }
            )
        )
        return

    if result.changed:
        typer.echo(f"generate: regenerated {len(result.regenerated)} document(s):")
        for doc in result.regenerated:
            typer.echo(f"  - {doc}")
        if result.skipped:
            typer.echo(f"({len(result.skipped)} unchanged, skipped)")
        if not context_from_file:
            typer.echo("")
            typer.echo("Note: running without a context manifest. Docs are generic.")
            typer.echo("Run `autogovern init` for specific governance docs.")
    else:
        typer.echo("generate: all documents up to date (nothing regenerated).")


@app.command()
def diff(
    path: Path = typer.Argument(Path("."), help="Repository root."),
    config: Path | None = typer.Option(None, "--config", help="Alternate config file."),
    model: str | None = typer.Option(None, "--model", help="Override the configured model."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    profile_path: Path | None = typer.Option(
        None, "--profile", help="AgentProfile JSON (headless mode)."
    ),
) -> None:
    """Show which sections would change and why, without writing."""
    cfg = _load_config_or_env_or_exit(config, model)
    context, context_from_file = _load_context_or_default_or_exit()
    provider = build_provider(cfg)
    try:
        profile = _load_profile_or_exit(profile_path) if profile_path is not None else None
        result = check_lib(
            path,
            cfg,
            context,
            provider=provider,
            strict=False,
            fix=False,
            context_from_file=context_from_file,
            profile=profile,
        )
    finally:
        provider.close()

    if json_output:
        import json as _json

        typer.echo(_json.dumps(result.to_dict()))
        return

    if result.current:
        typer.echo("diff: governance is current, no changes detected.")
    else:
        typer.echo(f"diff: score {result.score} ({result.band})")
        typer.echo(f"  changed fields: {', '.join(result.changed_fields)}")
        typer.echo(f"  stale sections: {', '.join(result.stale_sections)}")
        typer.echo(f"  remediation: {result.remediation}")


@app.command()
def check(
    path: Path = typer.Argument(Path("."), help="Repository root."),
    config: Path | None = typer.Option(None, "--config", help="Alternate config file."),
    model: str | None = typer.Option(None, "--model", help="Override the configured model."),
    strict: bool = typer.Option(False, "--strict", help="Treat advisory scores as failures."),
    fix: bool = typer.Option(False, "--fix", help="Regenerate stale sections in place."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    profile_path: Path | None = typer.Option(
        None, "--profile", help="AgentProfile JSON (headless mode)."
    ),
) -> None:
    """CI gate: report stale docs; --fix regenerates in place."""
    cfg = _load_config_or_env_or_exit(config, model)
    context, context_from_file = _load_context_or_default_or_exit()
    provider = build_provider(cfg)
    usage: dict[str, int | None] | None = None
    try:
        profile = _load_profile_or_exit(profile_path) if profile_path is not None else None
        result = check_lib(
            path,
            cfg,
            context,
            provider=provider,
            strict=strict,
            fix=fix,
            context_from_file=context_from_file,
            profile=profile,
        )
        usage = provider.total_usage
    finally:
        provider.close()

    _write_check_manifest(path, cfg, result, token_counts=usage)

    if json_output:
        import json as _json

        typer.echo(_json.dumps(result.to_dict()))
    elif result.current:
        typer.echo("check: governance is current.")
    elif result.fixed:
        typer.echo(
            f"check --fix: regenerated {len(result.stale_sections)} section(s), lockfile updated."
        )
    elif result.band == "immaterial":
        typer.echo(f"check: current (immaterial changes only, score {result.score}).")
    else:
        typer.echo(f"check: STALE (score {result.score}, {result.band})")
        typer.echo(f"  stale sections: {', '.join(result.stale_sections)}")
        typer.echo(f"  remediation: {result.remediation}")

    raise typer.Exit(code=result.exit_code)


@app.command()
def explain(
    doc: str = typer.Argument(help="Document name or path to explain."),
    config: Path | None = typer.Option(None, "--config", help="Alternate config file."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Plain-language provenance for a document."""
    governance_dir = Path("governance")
    result = explain_document(Path(doc), governance_dir)

    if json_output:
        import json as _json

        typer.echo(_json.dumps(result, default=str))
        return

    if "error" in result:
        typer.echo(str(result["error"]), err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Document: {result['document']}")
    typer.echo(f"Generated: {result['generated']}")
    typer.echo(f"Agent version: {result['agent_version']}")
    typer.echo(f"Generator: {result['generator_version']}")
    typer.echo(f"Framework pack: {result['framework_pack_version']}")
    typer.echo(f"Input files: {result['input_files']}")
    typer.echo(f"Body lines: {result['body_lines']}")


hook_app = typer.Typer(
    help="Manage git hooks.",
    no_args_is_help=True,
)
app.add_typer(hook_app, name="hook")


@hook_app.command("install")
def hook_install(
    local_enforce: bool = typer.Option(
        False, "--local-enforce", help="Also install the pre-push hook (full check)."
    ),
) -> None:
    """Install the pre-commit hook (warning-only heuristic, never blocks)."""
    msg = install_pre_commit_hook(Path.cwd(), local_enforce=local_enforce)
    typer.echo(msg)


@hook_app.command("run")
def hook_run(
    files: list[str] | None = typer.Argument(
        None, help="Changed files to check. Defaults to the staged file list."
    ),
    staged: bool = typer.Option(
        False, "--staged", help="Check the staged file list (explicit default)."
    ),
) -> None:
    """Heuristic governance-impact check: prints a flag, always exits 0.

    This is the pre-commit entrypoint: no LLM, no profile rebuild, no
    blocking. A positive result warns that governance docs may need
    regenerating; the commit always proceeds.
    """
    from autogovern.detect.heuristic import heuristic_pass

    changed = list(files) if files else _staged_files()
    result = heuristic_pass(changed, _watched_paths_for_hook())
    if result.matched:
        typer.echo("governance impact: yes")
        typer.echo(f"  matched: {', '.join(result.matched_paths)}")
        typer.echo("  docs may need regenerating; run `autogovern generate` before merge.")
    else:
        typer.echo("governance impact: no")


def _staged_files() -> list[str]:
    """The staged file list from git, or [] when git is unavailable."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _watched_paths_for_hook() -> list[str]:
    """Watched paths from config, falling back to the model defaults."""
    from autogovern.config_loader import load_config
    from autogovern.models import DEFAULT_WATCHED_PATHS

    try:
        return load_config().watched_paths
    except (ConfigNotFoundError, ConfigInvalidError):
        return list(DEFAULT_WATCHED_PATHS)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_config_or_env_or_exit(config: Path | None, model: str | None = None) -> Config:
    """Load config from disk or env vars, exiting non-zero if neither exists."""
    try:
        cfg = load_config_or_env(config)
    except ConfigNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except ConfigInvalidError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if model is not None:
        cfg = cfg.model_copy(
            update={"model_provider": cfg.model_provider.model_copy(update={"model": model})}
        )
    return cfg


def _load_profile_or_exit(profile_path: Path) -> AgentProfile:
    """Load a --profile JSON file, exiting cleanly on any read/parse error."""
    try:
        return load_profile(profile_path)
    except FileNotFoundError:
        typer.echo(f"Profile file not found: {profile_path}", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(f"Invalid AgentProfile in {profile_path}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _load_context_or_default_or_exit() -> tuple[ContextManifest, bool]:
    """Load context from disk, or fall back to defaults (vanilla mode)."""
    try:
        return load_context_or_default()
    except ContextInvalidError as exc:
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


def _write_generate_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
) -> None:
    """Write a run manifest for a generate command."""
    sections = [
        {"section": doc, "changed_input": "input hash changed"}
        for doc in getattr(result, "regenerated", [])
    ]
    manifest = build_manifest(
        command="generate",
        config=config,
        sections_regenerated=sections,
        model_id=config.model_provider.model,
        token_counts=token_counts,
        prompt_template_versions={"generation": "generation-1.0.0"},
    )
    write_manifest(root, manifest)


def _write_check_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
) -> None:
    """Write a run manifest for a check command."""
    detection = getattr(result, "detection", None)
    materiality = None
    if detection is not None and getattr(detection, "materiality", None) is not None:
        mat = detection.materiality
        materiality = {
            "score": mat.score,
            "band": mat.band,
            "criteria": [c.model_dump() for c in mat.criteria],
        }
    manifest = build_manifest(
        command="check",
        config=config,
        model_id=config.model_provider.model,
        token_counts=token_counts,
        materiality=materiality,
    )
    write_manifest(root, manifest)


if __name__ == "__main__":
    app()

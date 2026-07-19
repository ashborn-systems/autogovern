"""Typer CLI application for autogovern.

Seven commands: ``init``, ``scan``, ``generate``, ``diff``, ``check``,
``explain``, and ``hook`` (with ``install`` and ``run`` subcommands). The
CLI is a thin shell over the library API (:mod:`autogovern.api`) and the
package entry points; all interactive IO lives here.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

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
from autogovern.models import (
    AgentContext,
    AgentProfile,
    Config,
    ContextManifest,
    ModelProviderConfig,
    ProjectContext,
    RunManifest,
)
from autogovern.observability import build_manifest, write_manifest
from autogovern.provider import build_provider
from autogovern.tui import enable_plain
from autogovern.tui.activity import Stage, StageTracker
from autogovern.tui.panels import check_verdict, init_summary, summary_line
from autogovern.tui.status import print_status

app = typer.Typer(
    name="autogovern",
    help="Generate and maintain governance documentation for AI agents.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    plain: bool = typer.Option(
        False, "--plain", help="Force plain output (no colour, no spinners)."
    ),
) -> None:
    """autogovern: generate and maintain governance documentation for AI agents."""
    # Route all logger output to stderr so it never corrupts JSON on stdout.
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")
    if plain:
        enable_plain()
    if ctx.invoked_subcommand is None:
        print_status()
        raise typer.Exit()


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


def _print_context_preamble() -> None:
    """Print the per-agent scope clarification before the context wizard."""
    from rich.console import Console
    from rich.panel import Panel

    Console(stderr=True).print(
        Panel(
            "The next questions describe THIS agent specifically, not your\n"
            "whole organisation. Where a single value is asked, pick the one\n"
            "that best fits this agent.",
            title="Context for this agent",
            border_style="blue",
        )
    )


def _prompt_context() -> ContextManifest:
    """Interactive context wizard, field by field, with safe defaults.

    Project-level questions are asked first (true for the whole repo), then
    agent-level questions (specific to this agent). The three enum fields
    are free text; the LLM normalises them during generation.
    """
    base = default_context()

    _print_context_preamble()

    # --- Project-level (org-wide) ---
    typer.echo("")
    typer.echo("Project context (true for the whole repo):")
    organisation = typer.prompt("Organisation legal name", default=base.project.organisation)
    sector = typer.prompt("Sector", default=base.project.sector)
    jurisdictions_raw = typer.prompt(
        "Jurisdictions (comma-separated)", default=", ".join(base.project.jurisdictions)
    )
    jurisdictions = [j.strip() for j in jurisdictions_raw.split(",") if j.strip()]
    risk_appetite = typer.prompt(
        "Risk appetite for this project (conservative / balanced / aggressive)",
        default=base.project.risk_appetite,
    )
    owner = typer.prompt("Owner (accountable person or role)", default=base.project.owner)
    review_cadence = typer.prompt("Review cadence", default=base.project.review_cadence)
    strategy = typer.prompt("Strategy (one paragraph)", default=base.project.strategy)

    # --- Agent-level (this specific agent) ---
    typer.echo("")
    typer.echo("Agent context (describe THIS agent specifically):")
    deployment_context = typer.prompt(
        "Deployment context for this agent (internal / customer-facing / third-party-distributed)",
        default=base.agents.get("default", AgentContext()).deployment_context,
    )
    autonomy_level = typer.prompt(
        "Autonomy level for this agent (human-in-the-loop / human-on-the-loop / fully-autonomous)",
        default=base.agents.get("default", AgentContext()).autonomy_level,
    )
    intended_users = typer.prompt(
        "Intended users", default=base.agents.get("default", AgentContext()).intended_users
    )
    oversight_model = typer.prompt(
        "Oversight model", default=base.agents.get("default", AgentContext()).oversight_model
    )

    return ContextManifest(
        project=ProjectContext(
            organisation=organisation,
            sector=sector,
            jurisdictions=jurisdictions,
            risk_appetite=risk_appetite,
            owner=owner,
            review_cadence=review_cadence,
            strategy=strategy,
        ),
        agents={
            "default": AgentContext(
                deployment_context=deployment_context,
                autonomy_level=autonomy_level,
                intended_users=intended_users,
                oversight_model=oversight_model,
            )
        },
    )


def _print_init_result(result: InitResult, context: ContextManifest) -> None:
    if not result.wrote_files:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim

        get_console().print(dim("init: no files written (existing config retained)."))
        return
    init_summary(
        config_path=result.config_path,
        context_path=result.context_path,
        overwritten=result.overwritten,
        hook_message=result.hook_message,
        ci_message=result.ci_message,
    )


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
    import time

    start = time.time()
    tracker = StageTracker([Stage("scan", "Scan")]) if not json_output else None
    if tracker:
        tracker.start()
        tracker.begin("scan")
    try:
        result = scan_repo(path, cfg, provider=provider, write_card=not no_write_card)
        usage = provider.total_usage
        calls = provider.call_log
    finally:
        provider.close()
    elapsed = time.time() - start
    if tracker:
        if result.agents:
            first = result.agents[0]
            tools = [
                p.detail
                for p in first.profile.governance.permissions_surface.value
                if p.kind == "tool"
            ]
            deps = len(first.profile.governance.dependencies.value)
            tracker.complete(
                "scan", f"{len(result.agents)} agent(s) · {deps} deps · {len(tools)} tools"
            )
        else:
            tracker.complete("scan", "no signals")
        tracker.stop()

    if json_output:
        typer.echo(result.to_json())
        _write_scan_manifest(path, cfg, result, token_counts=usage, call_log=calls)
        return

    if not result.agents:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim

        get_console().print(dim(f"No agent signals found in {path}."))
        _write_scan_manifest(path, cfg, result, token_counts=usage, call_log=calls)
        return

    _print_scan_human(result)
    summary_line("scan", detail=f"{len(result.agents)} agent(s)", elapsed=elapsed)
    _write_scan_manifest(path, cfg, result, token_counts=usage, call_log=calls)


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
    from autogovern.observability import init_tracing
    from autogovern.observability import shutdown as tracing_shutdown
    from autogovern.observability import span as tracing_span

    init_tracing(cfg)
    usage: dict[str, int | None] | None = None
    import time

    start = time.time()
    tracker = (
        StageTracker([Stage("scan", "Scan"), Stage("generate", "Generate")])
        if not json_output
        else None
    )
    if tracker:
        tracker.start()
    try:
        if profile_path is not None:
            profile = _load_profile_or_exit(profile_path)
            from autogovern.ingest import ScannedAgent, ScanResult

            scan_result = ScanResult(
                agents=[
                    ScannedAgent(
                        name=profile.name,
                        root=".",
                        profile=profile,
                        card_written=False,
                        card_path=None,
                    )
                ],
                root=str(path),
            )
        else:
            if tracker:
                tracker.begin("scan")
            scan_result = scan_repo(path, cfg, provider=provider, write_card=False)
            if not scan_result.agents:
                if tracker:
                    tracker.complete("scan", "no signals")
                    tracker.stop()
                from autogovern.tui.console import get_console
                from autogovern.tui.states import dim

                get_console().print(dim(f"No agent signals found in {path}. Nothing to generate."))
                raise typer.Exit(code=1)
            if tracker:
                agent_names = ", ".join(a.name for a in scan_result.agents)
                tracker.complete("scan", f"{len(scan_result.agents)} agent(s): {agent_names}")
        if tracker:
            tracker.begin("generate")
        with tracing_span("generate", attributes={"agents": len(scan_result.agents)}):
            result = generate_docs(
                path,
                cfg,
                scan_result,
                context,
                provider=provider,
                context_from_file=context_from_file,
            )
        usage = provider.total_usage
    finally:
        provider.close()
        tracing_shutdown()
    elapsed = time.time() - start
    tokens = usage.get("total") if usage else None
    if tracker:
        if result.changed:
            tracker.complete("generate", f"{len(result.regenerated)} section(s) regenerated")
        else:
            tracker.complete("generate", "nothing regenerated")
        tracker.stop()

    _write_generate_manifest(path, cfg, result, token_counts=usage, call_log=provider.call_log)

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
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim, primary

        console = get_console()
        console.print(primary(f"generate: regenerated {len(result.regenerated)} document(s):"))
        for doc in result.regenerated:
            console.print(dim(f"  - {doc}"))
        if result.skipped:
            console.print(dim(f"({len(result.skipped)} unchanged, skipped)"))
        if not context_from_file:
            console.print("")
            console.print(dim("Note: running without a context manifest. Docs are generic."))
            console.print(dim("Run `autogovern init` for specific governance docs."))
    else:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim

        get_console().print(dim("generate: all documents up to date (nothing regenerated)."))

    detail = f"{len(result.regenerated)} section(s) regenerated" if result.changed else "up to date"
    summary_line("generate", detail=detail, tokens=tokens, elapsed=elapsed)


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
        usage = provider.total_usage
        calls = provider.call_log
    finally:
        provider.close()

    _write_diff_manifest(path, cfg, result, token_counts=usage, call_log=calls)

    if json_output:
        import json as _json

        typer.echo(_json.dumps(result.to_dict()))
        return

    if result.current:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import primary

        get_console().print(primary("diff: governance is current, no changes detected."))
    else:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim, primary

        console = get_console()
        console.print(primary(f"diff: score {result.score} ({result.band})"))
        console.print(dim(f"  changed fields: {', '.join(result.changed_fields)}"))
        console.print(dim(f"  stale sections: {', '.join(result.stale_sections)}"))
        console.print(dim(f"  remediation: {result.remediation}"))


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

    _write_check_manifest(path, cfg, result, token_counts=usage, call_log=provider.call_log)

    if json_output:
        import json as _json

        typer.echo(_json.dumps(result.to_dict()))
    else:
        criteria = None
        if hasattr(result, "criteria") and result.criteria:
            criteria = [c if isinstance(c, dict) else c.model_dump() for c in result.criteria]
        check_verdict(
            current=result.current,
            fixed=result.fixed,
            band=result.band,
            score=result.score,
            stale_sections=result.stale_sections,
            criteria=criteria,
            remediation=result.remediation,
        )

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
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim

        get_console().print(dim(str(result["error"])))
        raise typer.Exit(code=1)

    from autogovern.tui.console import get_console
    from autogovern.tui.states import dim, primary

    console = get_console()
    console.print(primary(f"Document: {result['document']}"))
    console.print(dim(f"Generated: {result['generated']}"))
    console.print(dim(f"Agent version: {result['agent_version']}"))
    console.print(dim(f"Generator: {result['generator_version']}"))
    console.print(dim(f"Framework pack: {result['framework_pack_version']}"))
    console.print(dim(f"Input files: {result['input_files']}"))
    console.print(dim(f"Body lines: {result['body_lines']}"))


@app.command()
def runs(
    latest: bool = typer.Option(False, "--latest", help="Show only the most recent run in detail."),
    limit: int = typer.Option(20, "--limit", help="Maximum number of runs to list."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List recent run manifests with token usage and materiality."""
    from autogovern.observability import load_recent_manifests

    root = Path.cwd()
    manifests = load_recent_manifests(root, limit=limit)

    if json_output:
        import json as _json

        typer.echo(_json.dumps([m.model_dump(mode="json") for m in manifests], indent=2))
        return

    if not manifests:
        from autogovern.tui.console import get_console
        from autogovern.tui.states import dim

        get_console().print(dim("No runs found. Run a command first."))
        return

    if latest:
        _print_run_detail(manifests[0])
        return

    _print_runs_table(manifests)


def _print_runs_table(manifests: list[RunManifest]) -> None:
    """Print a compact table of recent runs."""
    from autogovern.tui.console import get_console
    from autogovern.tui.states import dim, primary

    console = get_console()
    console.print(primary(f"Recent runs ({len(manifests)} shown)"))
    console.print("")
    for m in manifests:
        parts = [m.command]
        if m.sections_regenerated:
            parts.append(f"{len(m.sections_regenerated)} section(s)")
        if m.token_counts and m.token_counts.total:
            parts.append(f"{m.token_counts.total / 1000:.1f}k tokens")
        if m.materiality:
            parts.append(f"score {m.materiality.score}")
        if m.call_log:
            parts.append(f"{len(m.call_log)} LLM call(s)")
        console.print(dim("  · ".join(parts)))
    console.print("")
    console.print(dim("  Run 'autogovern runs --latest' for full detail."))


def _print_run_detail(manifest: RunManifest) -> None:
    """Print one run manifest in full detail."""
    from autogovern.tui.console import get_console
    from autogovern.tui.states import dim, primary

    console = get_console()
    console.print(primary(f"Run: {manifest.command}"))
    console.print(dim(f"  Tool version: {manifest.tool_version}"))
    if manifest.model_id:
        console.print(dim(f"  Model: {manifest.model_id}"))
    if manifest.token_counts:
        tc = manifest.token_counts
        console.print(
            dim(
                f"  Tokens: {tc.total or 0} total"
                f" ({tc.prompt or 0} prompt, {tc.completion or 0} completion)"
            )
        )
    if manifest.call_log:
        console.print("")
        console.print(dim("  Per-call breakdown:"))
        for call in manifest.call_log:
            label = call.label or "(unlabelled)"
            total = call.total or 0
            console.print(dim(f"    {label}: {total} tokens"))
    if manifest.normalisation:
        console.print("")
        norm = manifest.normalisation
        status = "fallback" if norm.fallback else ("LLM" if norm.used_llm else "direct")
        console.print(dim(f"  Normalisation: {status}"))
        if norm.fallback:
            console.print(dim("    (fell back to higher-risk defaults)"))
    if manifest.sections_regenerated:
        console.print("")
        console.print(dim("  Sections regenerated:"))
        for s in manifest.sections_regenerated:
            console.print(dim(f"    {s.section}: {s.changed_input}"))
    if manifest.materiality:
        console.print("")
        mat = manifest.materiality
        console.print(dim(f"  Materiality: {mat.score}/100 ({mat.band})"))
        for c in mat.criteria:
            console.print(dim(f"    {c.criterion}: {c.score} - {c.reasoning}"))


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
    """Render a scan result as a human-readable summary of all agents."""
    from autogovern.tui.console import get_console
    from autogovern.tui.states import dim, primary

    console = get_console()
    if not result.agents:
        console.print(dim(f"No agent signals found in {result.root}."))
        return

    console.print(primary(f"{len(result.agents)} agent(s) discovered"))
    console.print("")

    for agent in result.agents:
        profile = agent.profile
        console.print(primary(f"  {profile.name} (v{profile.version}) — root: {agent.root}"))
        if profile.description:
            console.print(dim(f"    {profile.description}"))

        gov = profile.governance
        mc = gov.model_configuration.value
        console.print(dim(f"    Model:          {mc.model} ({mc.provider})"))

        tools = [
            p.detail.split(" — ")[0] for p in gov.permissions_surface.value if p.kind == "tool"
        ]
        console.print(dim(f"    Tools:          {_join_or_none(tools)}"))

        deps = [d.name for d in gov.dependencies.value]
        console.print(dim(f"    Dependencies:   {_join_or_none(deps)}"))

        if agent.card_written:
            console.print(dim(f"    AgentCard: written to {agent.card_path}"))
        elif agent.card_path:
            console.print(dim(f"    AgentCard: found at {agent.card_path}"))
        console.print("")


def _join_or_none(items: list[str]) -> str:
    """Join a list for display, or 'none' when empty."""
    return ", ".join(items) if items else "none"


def _write_generate_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
    call_log: list[dict[str, Any]] | None = None,
) -> None:
    """Write a run manifest for a generate command."""
    sections = []
    reasons = getattr(result, "regeneration_reasons", {})
    for doc in getattr(result, "regenerated", []):
        sections.append(
            {
                "section": doc,
                "changed_input": reasons.get(doc, "input hash changed"),
            }
        )
    norm = None
    norm_obj = getattr(result, "normalisation", None)
    if norm_obj is not None:
        norm = {
            "used_llm": norm_obj.used_llm,
            "fallback": norm_obj.fallback,
            "fields": norm_obj.fields,
        }
    manifest = build_manifest(
        command="generate",
        config=config,
        sections_regenerated=sections,
        model_id=config.model_provider.model,
        token_counts=token_counts,
        call_log=call_log,
        normalisation=norm,
        prompt_template_versions={"generation": "generation-1.0.0"},
    )
    write_manifest(root, manifest)


def _write_check_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
    call_log: list[dict[str, Any]] | None = None,
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
        call_log=call_log,
        materiality=materiality,
    )
    write_manifest(root, manifest)


def _write_scan_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
    call_log: list[dict[str, Any]] | None = None,
) -> None:
    """Write a run manifest for a scan command."""
    signals = getattr(result, "signals_found", False)
    manifest = build_manifest(
        command="scan",
        config=config,
        model_id=config.model_provider.model,
        token_counts=token_counts,
        call_log=call_log,
        input_hashes={"signals_found": str(signals).lower()},
    )
    write_manifest(root, manifest)


def _write_diff_manifest(
    root: Path,
    config: Config,
    result: object,
    token_counts: dict[str, int | None] | None = None,
    call_log: list[dict[str, Any]] | None = None,
) -> None:
    """Write a run manifest for a diff command."""
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
        command="diff",
        config=config,
        model_id=config.model_provider.model,
        token_counts=token_counts,
        call_log=call_log,
        materiality=materiality,
    )
    write_manifest(root, manifest)


if __name__ == "__main__":
    app()

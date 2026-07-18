"""Init wizard: writes ``.autogovern/config.yaml`` and ``.autogovern/context.yaml``.

Phase 5 scope is config and context only. Hook and CI installation belong to
Phase 10 and are invoked through the stub functions in
:mod:`autogovern.hooks`, so the wizard calls them but they install nothing
yet.

The module is a deep one: a small set of pure helpers (default context,
provider-from-env, context-file import with structured errors) plus a single
:func:`write_init` orchestrator that takes a ``confirm`` callable so all
interactive IO lives in the CLI shell, not here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from autogovern.context.defaults import default_context
from autogovern.hooks import install_ci_config, install_pre_commit_hook
from autogovern.models import (
    Config,
    ContextManifest,
    ModelProviderConfig,
)

CONFIG_DIR = Path(".autogovern")
CONFIG_FILENAME = "config.yaml"
CONTEXT_FILENAME = "context.yaml"
CONFIG_FILE = CONFIG_DIR / CONFIG_FILENAME
CONTEXT_FILE = CONFIG_DIR / CONTEXT_FILENAME


# Environment variables for non-interactive provider configuration. The key
# itself is never read here; only the *name* of the env var holding it is
# captured into config.yaml.
class InitError(Exception):
    """Base class for init failures."""


class ContextImportError(InitError):
    """A ``--from`` context file failed validation.

    Carries one human-readable line per invalid field so the CLI can list
    every problem in one run rather than failing on the first.
    """

    def __init__(self, field_errors: list[str], *, source: Path) -> None:
        self.field_errors = field_errors
        self.source = source
        joined = "\n".join(f"  - {line}" for line in field_errors)
        super().__init__(f"Invalid context manifest at {source}:\n{joined}")


class ProviderConfigError(InitError):
    """Provider settings are missing in a non-interactive init."""


@dataclass
class InitResult:
    """Outcome of an init run, for the CLI to print and tests to assert."""

    config_path: Path
    context_path: Path
    wrote_files: bool
    overwritten: bool
    hook_message: str
    ci_message: str


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def load_context_from_file(path: Path) -> ContextManifest:
    """Load and validate a context manifest from a YAML file.

    Raises:
        ContextImportError: The file is missing, not valid YAML, or fails
            ``ContextManifest`` validation. Validation errors carry one line
            per invalid field.
    """
    if not path.is_file():
        raise ContextImportError([f"file not found: {path}"], source=path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContextImportError([f"not valid YAML: {exc}"], source=path) from exc
    if not isinstance(raw, dict):
        raise ContextImportError(["top level must be a YAML mapping"], source=path)
    try:
        return ContextManifest.model_validate(raw)
    except ValidationError as exc:
        raise ContextImportError(format_context_errors(exc), source=path) from exc


def format_context_errors(exc: ValidationError) -> list[str]:
    """Render a pydantic ValidationError as one line per invalid field."""
    lines: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        lines.append(f"{loc}: {err['msg']}")
    return lines


def build_config(provider: ModelProviderConfig) -> Config:
    """Build a Config from a provider, accepting all other defaults."""
    return Config(model_provider=provider)


# ---------------------------------------------------------------------------
# Write orchestration
# ---------------------------------------------------------------------------


def write_init(
    *,
    root: Path,
    config: Config,
    context: ContextManifest,
    force: bool = False,
    no_hooks: bool = False,
    local_enforce: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> InitResult:
    """Write config.yaml and context.yaml, invoke hook/CI stubs, return result.

    If either target file already exists and ``force`` is false, the caller's
    ``confirm`` callable is asked once whether to overwrite. A ``None`` or
    declining ``confirm`` means nothing is written and the returned
    :class:`InitResult` reports ``wrote_files=False``.

    Writes are atomic: a failure midway leaves any existing files intact.
    """
    config_path = root / CONFIG_FILE
    context_path = root / CONTEXT_FILE
    already_existed = config_path.exists() or context_path.exists()

    if (
        already_existed
        and not force
        and (
            confirm is None
            or not confirm(f"{CONFIG_FILE} and/or {CONTEXT_FILE} already exist. Overwrite?")
        )
    ):
        return InitResult(
            config_path=config_path,
            context_path=context_path,
            wrote_files=False,
            overwritten=False,
            hook_message="skipped (existing config retained)",
            ci_message="skipped (existing config retained)",
        )

    _atomic_write(config_path, _dump_config(config))
    _atomic_write(context_path, _dump_context(context))

    if no_hooks:
        hook_message = "skipped (--no-hooks)"
    else:
        hook_message = install_pre_commit_hook(root, local_enforce=local_enforce)
    ci_message = install_ci_config(root)

    return InitResult(
        config_path=config_path,
        context_path=context_path,
        wrote_files=True,
        overwritten=already_existed,
        hook_message=hook_message,
        ci_message=ci_message,
    )


def _dump_config(config: Config) -> str:
    return yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, default_flow_style=False)


def _dump_context(context: ContextManifest) -> str:
    return yaml.safe_dump(
        context.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path via a temp file rename so failures leave no partials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "CONTEXT_FILE",
    "ContextImportError",
    "InitError",
    "InitResult",
    "ProviderConfigError",
    "build_config",
    "default_context",
    "format_context_errors",
    "load_context_from_file",
    "write_init",
]

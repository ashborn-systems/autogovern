"""Config and context loading for autogovern.

Two modes:
- **Enhanced**: ``.autogovern/config.yaml`` and ``.autogovern/context.yaml``
  exist (written by ``init``). Docs are specific to the organisation.
- **Vanilla**: no config or context on disk. Provider settings come from env
  vars; context uses defaults. Docs are generic but still generated.

The key never touches this module. Only the *name* of the env var holding it
is captured into config.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from autogovern.context.defaults import default_context
from autogovern.models import Config, ContextManifest, ModelProviderConfig

CONFIG_PATH = Path(".autogovern/config.yaml")
CONTEXT_PATH = Path(".autogovern/context.yaml")

# Environment variables for vanilla-mode provider configuration. The key
# itself is never read here; only the name of the variable holding it.
ENV_API_BASE = "AUTOGOVERN_API_BASE"
ENV_MODEL = "AUTOGOVERN_MODEL"
ENV_API_KEY_ENV = "AUTOGOVERN_API_KEY_ENV"
ENV_TEMPERATURE = "AUTOGOVERN_TEMPERATURE"


class ConfigNotFoundError(FileNotFoundError):
    """Raised when no config is found on disk or in env vars."""


class ConfigInvalidError(ValueError):
    """Raised when the config file fails validation."""


class ContextNotFoundError(FileNotFoundError):
    """Raised when ``.autogovern/context.yaml`` is missing."""


class ContextInvalidError(ValueError):
    """Raised when the context file fails validation."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> Config:
    """Load and validate the autogovern config from disk.

    Raises:
        ConfigNotFoundError: The config file does not exist.
        ConfigInvalidError: The file is not valid YAML or fails validation.
    """
    config_path = path or CONFIG_PATH
    if not config_path.is_file():
        raise ConfigNotFoundError(
            f"Config file not found: {config_path}. Run `autogovern init`, or set "
            f"the {ENV_API_BASE}, {ENV_MODEL}, and {ENV_API_KEY_ENV} environment "
            f"variables for vanilla mode."
        )

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigInvalidError(f"Config file {config_path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigInvalidError(
            f"Config file {config_path} must contain a YAML mapping at the top level."
        )

    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigInvalidError(f"Config file {config_path} failed validation:\n{exc}") from exc


def provider_from_env() -> ModelProviderConfig | None:
    """Build a provider config from environment variables, or ``None``.

    Returns ``None`` if any required variable is unset. The API key value is
    never touched; only the name of the variable holding it is captured.
    """
    api_base = os.environ.get(ENV_API_BASE)
    model = os.environ.get(ENV_MODEL)
    api_key_env = os.environ.get(ENV_API_KEY_ENV)
    if not (api_base and model and api_key_env):
        return None
    raw_temp = os.environ.get(ENV_TEMPERATURE, "0")
    try:
        temperature = float(raw_temp)
    except ValueError:
        temperature = 0.0
    return ModelProviderConfig(
        api_base=api_base,
        model=model,
        api_key_env=api_key_env,
        temperature=temperature,
    )


def load_config_or_env(path: Path | None = None) -> Config:
    """Load config from disk, or fall back to env vars (vanilla mode).

    Tries ``config.yaml`` first. If not found, builds a Config from
    ``AUTOGOVERN_*`` env vars. If neither is available, raises
    :class:`ConfigNotFoundError` naming both remedies.
    """
    try:
        return load_config(path)
    except ConfigNotFoundError:
        provider = provider_from_env()
        if provider is not None:
            return Config(model_provider=provider)
        raise


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def load_context(path: Path | None = None) -> ContextManifest:
    """Load and validate the organisational context manifest from disk.

    Raises:
        ContextNotFoundError: The context file does not exist.
        ContextInvalidError: The file is not valid YAML or fails validation.
    """
    context_path = path or CONTEXT_PATH
    if not context_path.is_file():
        raise ContextNotFoundError(
            f"Context file not found: {context_path}. Running without one "
            f"produces generic docs; run `autogovern init` for specific output."
        )
    try:
        raw = yaml.safe_load(context_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContextInvalidError(f"Context file {context_path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContextInvalidError(
            f"Context file {context_path} must contain a YAML mapping at the top level."
        )
    try:
        return ContextManifest.model_validate(raw)
    except ValidationError as exc:
        raise ContextInvalidError(f"Context file {context_path} failed validation:\n{exc}") from exc


def load_context_or_default(path: Path | None = None) -> tuple[ContextManifest, bool]:
    """Load context from disk, or fall back to defaults (vanilla mode).

    Returns ``(context, from_file)`` where ``from_file`` is True when a real
    context manifest was loaded and False when defaults are being used. The
    flag lets the engine write an honest ATTENTION.md noting that docs are
    generic.
    """
    try:
        return load_context(path), True
    except ContextNotFoundError:
        return default_context(), False


__all__ = [
    "CONFIG_PATH",
    "CONTEXT_PATH",
    "ConfigInvalidError",
    "ConfigNotFoundError",
    "ContextInvalidError",
    "ContextNotFoundError",
    "ENV_API_BASE",
    "ENV_API_KEY_ENV",
    "ENV_MODEL",
    "ENV_TEMPERATURE",
    "load_config",
    "load_config_or_env",
    "load_context",
    "load_context_or_default",
    "provider_from_env",
]

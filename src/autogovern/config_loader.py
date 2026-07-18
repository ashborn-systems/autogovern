"""Config loader for ``.autogovern/config.yaml``.

All environment access for the model key flows through the provider client,
not here. This module reads only the on-disk config file and validates it
against the :class:`~autogovern.models.Config` model.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from autogovern.models import Config, ContextManifest

CONFIG_PATH = Path(".autogovern/config.yaml")
CONTEXT_PATH = Path(".autogovern/context.yaml")


class ConfigNotFoundError(FileNotFoundError):
    """Raised when ``.autogovern/config.yaml`` is missing."""


class ConfigInvalidError(ValueError):
    """Raised when the config file fails validation."""


class ContextNotFoundError(FileNotFoundError):
    """Raised when ``.autogovern/context.yaml`` is missing."""


class ContextInvalidError(ValueError):
    """Raised when the context file fails validation."""


def load_context(path: Path | None = None) -> ContextManifest:
    """Load and validate the organisational context manifest.

    Args:
        path: Optional explicit path. Defaults to ``.autogovern/context.yaml``
            in the current working directory.

    Returns:
        A validated :class:`ContextManifest`.

    Raises:
        ContextNotFoundError: The context file does not exist.
        ContextInvalidError: The file is not valid YAML or fails validation.
    """
    context_path = path or CONTEXT_PATH
    if not context_path.is_file():
        raise ContextNotFoundError(
            f"Context file not found: {context_path}. Run `autogovern init` to create it."
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


def load_config(path: Path | None = None) -> Config:
    """Load and validate the autogovern config.

    Args:
        path: Optional explicit path. Defaults to ``.autogovern/config.yaml``
            in the current working directory.

    Returns:
        A validated :class:`Config` instance.

    Raises:
        ConfigNotFoundError: The config file does not exist.
        ConfigInvalidError: The config file is not valid YAML or fails
            schema validation.
    """
    config_path = path or CONFIG_PATH
    if not config_path.is_file():
        raise ConfigNotFoundError(
            f"Config file not found: {config_path}. Run `autogovern init` to create it."
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


__all__ = [
    "CONFIG_PATH",
    "CONTEXT_PATH",
    "ConfigInvalidError",
    "ConfigNotFoundError",
    "ContextInvalidError",
    "ContextNotFoundError",
    "load_config",
    "load_context",
]

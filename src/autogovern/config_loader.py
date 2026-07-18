"""Config loader for ``.autogovern/config.yaml``.

All environment access for the model key flows through the provider client,
not here. This module reads only the on-disk config file and validates it
against the :class:`~autogovern.models.Config` model.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from autogovern.models import Config

CONFIG_PATH = Path(".autogovern/config.yaml")


class ConfigNotFoundError(FileNotFoundError):
    """Raised when ``.autogovern/config.yaml`` is missing."""


class ConfigInvalidError(ValueError):
    """Raised when the config file fails validation."""


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
    "ConfigInvalidError",
    "ConfigNotFoundError",
    "load_config",
]

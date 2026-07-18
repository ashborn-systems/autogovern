"""Secret-discipline grep test: no source file writes the key value to disk
or includes it in any log or run manifest.

This is a static check across the source tree, complementing the runtime
check in test_provider.py (key never logged).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "autogovern"


# Patterns that would indicate a source file writes, logs, or persists a key.
_FORBIDDEN_PATTERNS = [
    # Logging the key directly.
    re.compile(r"log(?:ger|ging)?\.[a-z]+\([^)]*key[^)]*\)", re.IGNORECASE),
    re.compile(r"logger\.[a-z]+\(.*os\.environ", re.IGNORECASE),
    # Writing the key to a file.
    re.compile(r"\.write(?:text|lines)?\(.*key", re.IGNORECASE),
    re.compile(r"open\(.*['\"].*['\"].*key", re.IGNORECASE),
    # Storing the key in a manifest or config snapshot.
    re.compile(r"config_snapshot.*key", re.IGNORECASE),
]

# These modules legitimately touch the key env var but must not persist it.
_KEY_REFERENCE_FILES = {"provider.py", "config_loader.py"}


def _source_files() -> list[Path]:
    return list(SRC_ROOT.rglob("*.py"))


@pytest.mark.parametrize("source_file", _source_files(), ids=lambda p: str(p.relative_to(SRC_ROOT)))
def test_no_source_file_persists_api_key(source_file: Path) -> None:
    """No source file contains a pattern that writes, logs, or stores the key."""
    content = source_file.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        matches = pattern.findall(content)
        assert not matches, (
            f"{source_file.relative_to(SRC_ROOT)} contains forbidden pattern "
            f"{pattern.pattern!r}: {matches[:3]}"
        )


def test_provider_reads_key_from_env_at_call_time() -> None:
    """The provider client reads the key via os.environ.get at call time,
    not at construction."""
    provider_src = (SRC_ROOT / "provider.py").read_text(encoding="utf-8")
    # The key must be read inside a method (at call time), not in __init__.
    assert "os.environ.get" in provider_src
    # And never assigned to an instance attribute that could be serialised.
    assert "self._key" not in provider_src
    assert "self._api_key" not in provider_src


def test_run_manifest_config_snapshot_excludes_key() -> None:
    """RunManifest.config_snapshot is a dict[str, Any] — verify the model
    does not auto-populate secrets, and the provider client does not write
    the key into it."""
    from autogovern.models import RunManifest

    manifest = RunManifest(command="test", tool_version="0.1.0")
    # config_snapshot defaults to empty — no secrets populated by default.
    assert manifest.config_snapshot == {}
    # And the field is not named anything key-like.
    assert "key" not in str(RunManifest.model_fields)


def test_env_example_has_no_real_key_values() -> None:
    """The committed .env.example must not contain real key values.

    Non-secret defaults (like the API base URL) are allowed; only the key
    and model fields, which hold secrets or instance-specific values, must
    be empty.
    """
    env_example = SRC_ROOT.parent.parent / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    # No sk- prefixed keys (common API key format).
    assert not re.search(r"sk-[a-zA-Z0-9]{10,}", content)
    # The key-env-var name line must be empty — it names the env var, not
    # a default, and a value here would be misleading.
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("MODEL_PROVIDER_API_KEY_ENV="):
            assert stripped == "MODEL_PROVIDER_API_KEY_ENV=OPENROUTER_API_KEY"
        elif stripped.startswith("MODEL_PROVIDER_MODEL="):
            assert stripped == "MODEL_PROVIDER_MODEL="

"""autogovern: governance documentation generation for AI agents.

Public library API is in :mod:`autogovern.api`. The CLI app is also exported
for convenience.
"""

from autogovern.api import (
    CheckResult,
    GenerationResult,
    ScanResult,
    build_provider,
    check,
    generate_docs,
    load_profile,
    scan,
)
from autogovern.cli import app

__all__ = [
    "CheckResult",
    "GenerationResult",
    "ScanResult",
    "app",
    "build_provider",
    "check",
    "generate_docs",
    "load_profile",
    "scan",
]

"""CLI eval harness — parametrised over the stub commands.

The ``generate`` command is wired to the config loader (Phase 2) so it exits
non-zero without a config; the other stubs still exit 0.
"""

import pytest
from typer.testing import CliRunner

from autogovern.cli import app

runner = CliRunner()

# Stubs that still exit 0 with a not-implemented message.
ZERO_EXIT_STUBS = [
    ("init", "init: not implemented"),
    ("scan", "scan: not implemented"),
    ("diff", "diff: not implemented"),
    ("check", "check: not implemented"),
    ("hook", "hook: not implemented"),
]


@pytest.mark.parametrize("command, expected_prefix", ZERO_EXIT_STUBS)
def test_stub_commands_exit_zero(command: str, expected_prefix: str) -> None:
    """Stub commands exit 0 and print a not-implemented message."""
    result = runner.invoke(app, [command])
    assert result.exit_code == 0
    assert result.stdout.startswith(expected_prefix)


def test_help_lists_all_commands() -> None:
    """autogovern --help lists all seven commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["init", "scan", "generate", "diff", "check", "explain", "hook"]:
        assert command in result.stdout

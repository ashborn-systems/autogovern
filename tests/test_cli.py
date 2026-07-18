"""CLI tests: the --help surface. All commands are implemented."""

from typer.testing import CliRunner

from autogovern.cli import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    """autogovern --help lists all seven commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["init", "scan", "generate", "diff", "check", "explain", "hook"]:
        assert command in result.stdout

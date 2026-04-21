"""Canopus CLI application root.

Defines the top-level Typer application, registers all command groups,
and exposes :func:`main` as the ``canopus`` console-script entry point.
"""

from __future__ import annotations

import typer

from canopus.cli.commands.chat import chat
from canopus.cli.commands.doctor import doctor
from canopus.cli.commands.profile import profile_app
from canopus.cli.commands.run_cmd import run_prompt
from canopus.cli.commands.version_cmd import version

app = typer.Typer(
    name="canopus",
    help=(
        "[bold cyan]Canopus[/bold cyan] — "
        "CLI-native personal AI assistant runtime.\n\n"
        "Run [bold]canopus --help[/bold] on any sub-command for details."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
)

# -----------------------------------------------------------------------
# Sub-applications (command groups)
# -----------------------------------------------------------------------
app.add_typer(profile_app, name="profile")

# -----------------------------------------------------------------------
# Top-level commands
# -----------------------------------------------------------------------
app.command("chat")(chat)
app.command("run")(run_prompt)
app.command("doctor")(doctor)
app.command("version")(version)


def main() -> None:
    """Entry point for the ``canopus`` console script."""
    app()

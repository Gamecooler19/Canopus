"""Canopus CLI application root.

Defines the top-level Typer application, registers all command groups,
and exposes :func:`main` as the ``canopus`` console-script entry point.
"""

from __future__ import annotations

import typer

from canopus.capabilities.native.register import register_all as _register_native
from canopus.cli.commands.capability import capability_app
from canopus.cli.commands.chat import chat
from canopus.cli.commands.doctor import doctor
from canopus.cli.commands.profile import profile_app
from canopus.cli.commands.run_cmd import run_prompt
from canopus.cli.commands.trace import trace_app
from canopus.cli.commands.version_cmd import version

# Register all native capabilities at import time so that CLI commands,
# the reasoning pipeline, and tests all see the same populated registry.
_register_native()

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
app.add_typer(capability_app, name="capability")
app.add_typer(trace_app, name="trace")

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

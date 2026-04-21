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
from canopus.cli.commands.plugin import plugin_app
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
app.add_typer(plugin_app, name="plugin")

# -----------------------------------------------------------------------
# Top-level commands
# -----------------------------------------------------------------------
app.command("chat")(chat)
app.command("run")(run_prompt)
app.command("doctor")(doctor)
app.command("version")(version)


def _bootstrap_plugins() -> None:
    """Discover and load legacy plugins from the configured plugins directory.

    Called once at startup before the CLI app dispatches to a command.
    A failure here must never crash the CLI — errors are silently recorded
    in the plugin manager and surfaced via ``canopus plugin doctor``.
    """
    from canopus.capabilities.registry import registry
    from canopus.core.config import load_config
    from canopus.plugins.legacy.manager import initialize

    try:
        config = load_config()
        initialize(plugins_dir=config.paths.plugins_dir, registry=registry)
    except Exception:
        # Don't crash the CLI if plugin bootstrap fails.
        # Failures are inspectable via `canopus plugin doctor`.
        pass


def main() -> None:
    """Entry point for the ``canopus`` console script."""
    _bootstrap_plugins()
    app()

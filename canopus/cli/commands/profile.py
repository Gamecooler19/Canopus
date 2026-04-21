"""``canopus profile`` — sub-commands for managing runtime profiles."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from canopus.core.config import load_config
from canopus.core.errors import ProfileNotFoundError
from canopus.core.profiles import ProfileLoader, ProfileSettings

console = Console()
profile_app = typer.Typer(help="Manage Canopus runtime profiles.")


@profile_app.command("list")
def profile_list() -> None:
    """List all available profiles (built-in and user-defined)."""
    config = load_config()
    loader = ProfileLoader(profiles_dir=config.paths.profiles_dir)
    profiles = loader.list_all()

    console.print(
        Panel.fit("[bold cyan]Available Profiles[/bold cyan]", border_style="cyan")
    )
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Display Name")
    table.add_column("Source", style="dim", no_wrap=True)
    table.add_column("Description")

    for profile in profiles:
        active_marker = " [green]●[/green]" if profile.name == config.active_profile else ""
        table.add_row(
            profile.name + active_marker,
            profile.display_name,
            profile.source,
            profile.description,
        )

    console.print(table)
    console.print(f"\n[dim]Active profile: {config.active_profile}[/dim]")


@profile_app.command("show")
def profile_show(
    name: str | None = typer.Argument(
        None,
        help="Profile name to show. Defaults to the currently active profile.",
    ),
) -> None:
    """Show detailed settings for a profile."""
    config = load_config()
    target_name = name or config.active_profile
    loader = ProfileLoader(profiles_dir=config.paths.profiles_dir)

    try:
        profile = loader.load(target_name)
    except ProfileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from None

    _render_profile(profile, is_active=(target_name == config.active_profile))


# ---------------------------------------------------------------------------
# Internal rendering helper
# ---------------------------------------------------------------------------


def _render_profile(profile: ProfileSettings, *, is_active: bool) -> None:
    """Render a profile's full settings to the terminal."""
    active_label = "  [green](active)[/green]" if is_active else ""
    console.print(
        Panel.fit(
            f"[bold]{profile.display_name}[/bold]{active_label}\n"
            f"[dim]{profile.description}[/dim]",
            title=f"[bold cyan]{profile.name}[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))

    table.add_row("[dim]Source[/dim]", profile.source)

    # Model routing
    mr = profile.model_routing
    local_str = (
        f"{mr.local_provider}/{mr.local_model}"
        if mr.local_provider
        else "[dim]not configured[/dim]"
    )
    remote_str = (
        f"{mr.remote_provider}/{mr.remote_model}"
        if mr.remote_provider
        else "[dim]not configured[/dim]"
    )
    table.add_row(
        "[dim]Prefer local[/dim]",
        "[green]yes[/green]" if mr.prefer_local else "no",
    )
    table.add_row("[dim]Local model[/dim]", local_str)
    table.add_row("[dim]Remote model[/dim]", remote_str)
    table.add_row(
        "[dim]Fallback to remote[/dim]",
        "[yellow]yes[/yellow]" if mr.fallback_to_remote else "no",
    )

    # Network
    net = profile.network
    table.add_row(
        "[dim]Network access[/dim]",
        "[green]allowed[/green]" if net.allow_network else "[red]blocked[/red]",
    )

    # Memory
    mem = profile.memory
    table.add_row(
        "[dim]Memory[/dim]",
        "[green]enabled[/green]" if mem.enabled else "disabled",
    )

    # Feature flags
    table.add_row(
        "[dim]MCP tools[/dim]",
        "[green]enabled[/green]" if profile.mcp_enabled else "disabled",
    )
    table.add_row(
        "[dim]Tracing[/dim]",
        "[green]enabled[/green]" if profile.tracing_enabled else "disabled",
    )

    console.print(table)

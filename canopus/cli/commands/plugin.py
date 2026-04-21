"""``canopus plugin`` — sub-commands for inspecting and managing legacy plugins."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from canopus.plugins.legacy.manager import PluginManager, get_manager
from canopus.plugins.legacy.models import PluginStatus

console = Console()
plugin_app = typer.Typer(help="Inspect and manage legacy plugins.")

# Status icons used across commands
_STATUS_ICON: dict[PluginStatus, str] = {
    PluginStatus.LOADED: "[green]✓ loaded[/green]",
    PluginStatus.PARTIAL: "[yellow]⚠ partial[/yellow]",
    PluginStatus.INVALID: "[red]✗ invalid[/red]",
    PluginStatus.ERRORED: "[red]✗ errored[/red]",
    PluginStatus.SKIPPED: "[dim]— skipped[/dim]",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_manager() -> PluginManager:
    """Return the global manager or print a helpful message and exit."""
    manager = get_manager()
    if manager is None:
        console.print(
            "[yellow]Plugin manager is not initialized.[/yellow] "
            "This can happen when running commands outside the normal "
            "[cyan]canopus[/cyan] entrypoint. Run [bold]canopus plugin list[/bold] "
            "from the CLI to ensure plugins are loaded."
        )
        raise typer.Exit(1)
    return manager


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@plugin_app.command("list")
def plugin_list(
    status: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status: loaded, partial, invalid, errored, skipped.",
    ),
) -> None:
    """List all discovered plugins and their status."""
    manager = _require_manager()
    records = manager.get_records()

    if status:
        try:
            wanted = PluginStatus(status.lower())
        except ValueError:
            console.print(
                f"[red]Unknown status {status!r}.[/red] "
                f"Valid values: {', '.join(s.value for s in PluginStatus)}"
            )
            raise typer.Exit(1) from None
        records = [r for r in records if r.status == wanted]

    console.print(
        Panel.fit("[bold cyan]Canopus Plugins[/bold cyan]", border_style="cyan")
    )
    console.print(f"[dim]Plugin directory: {manager.plugins_dir}[/dim]")
    console.print()

    if not records:
        console.print("[dim]No plugins found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Plugin", style="cyan", no_wrap=True, min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Version", style="dim", min_width=8)
    table.add_column("Capabilities", min_width=8)
    table.add_column("File")

    for record in records:
        cap_count = str(len(record.capability_names)) if record.capability_names else "—"
        version = record.meta.version if record.meta else "—"
        table.add_row(
            record.name,
            _STATUS_ICON.get(record.status, record.status),
            version,
            cap_count,
            record.file_name,
        )

    console.print(table)
    loaded = sum(
        1 for r in records if r.status in (PluginStatus.LOADED, PluginStatus.PARTIAL)
    )
    failed = sum(
        1 for r in records if r.status in (PluginStatus.INVALID, PluginStatus.ERRORED)
    )
    console.print(
        f"\n[dim]{len(records)} plugin(s) discovered — "
        f"[green]{loaded} loaded[/green], [red]{failed} failed[/red][/dim]"
    )


@plugin_app.command("inspect")
def plugin_inspect(
    name: str = typer.Argument(..., help="Plugin name to inspect."),
) -> None:
    """Show detailed information about a specific plugin."""
    manager = _require_manager()
    record = manager.get_record(name)

    if record is None:
        console.print(f"[red]Plugin not found:[/red] {name!r}")
        console.print(
            "Run [bold]canopus plugin list[/bold] to see available plugins."
        )
        raise typer.Exit(1)

    # Header panel
    status_str = _STATUS_ICON.get(record.status, record.status)
    description = record.meta.description if record.meta else "—"
    author = record.meta.author if record.meta else "—"
    version = record.meta.version if record.meta else "—"
    tags_str = ", ".join(record.meta.tags) if record.meta and record.meta.tags else "—"

    console.print(
        Panel(
            f"[bold]Name:[/bold]        {record.name}\n"
            f"[bold]Status:[/bold]      {status_str}\n"
            f"[bold]Description:[/bold] {description}\n"
            f"[bold]Version:[/bold]     {version}\n"
            f"[bold]Author:[/bold]      {author}\n"
            f"[bold]Tags:[/bold]        {tags_str}\n"
            f"[bold]File:[/bold]        {record.path}",
            title=f"[bold cyan]Plugin: {record.name}[/bold cyan]",
            border_style="cyan",
        )
    )

    # Capabilities
    if record.capability_names:
        console.print()
        console.print(Rule("[bold]Capabilities[/bold]"))
        from canopus.capabilities.registry import registry

        for cap_name in record.capability_names:
            try:
                spec = registry.get(cap_name)
                perms = (
                    ", ".join(p.value for p in spec.permissions)
                    if spec.permissions
                    else "none"
                )
                console.print(
                    f"  [cyan]{spec.name}[/cyan]\n"
                    f"    {spec.description}\n"
                    f"    [dim]side_effects={spec.side_effect_level.value}  "
                    f"permissions={perms}[/dim]"
                )
            except Exception:
                console.print(f"  [dim]{cap_name} (spec unavailable)[/dim]")
    else:
        console.print("\n[dim]No capabilities registered.[/dim]")

    # Error
    if record.error:
        console.print()
        console.print(Rule("[bold red]Error[/bold red]"))
        console.print(f"[red]{record.error}[/red]")

    # Warnings
    if record.warnings:
        console.print()
        console.print(Rule("[bold yellow]Warnings[/bold yellow]"))
        for w in record.warnings:
            console.print(f"  [yellow]⚠ {w}[/yellow]")


@plugin_app.command("doctor")
def plugin_doctor() -> None:
    """Summarize plugin health: loaded, failed, warnings."""
    manager = _require_manager()
    records = manager.get_records()

    console.print(
        Panel.fit("[bold cyan]Plugin Doctor[/bold cyan]", border_style="cyan")
    )
    console.print(f"[dim]Directory: {manager.plugins_dir}[/dim]")
    console.print()

    total = len(records)
    loaded_recs = manager.get_loaded()
    failed_recs = manager.get_failed()
    skipped_recs = manager.get_skipped()
    warned_recs = [r for r in loaded_recs if r.warnings]

    # Summary table
    table = Table(show_header=False, box=None)
    table.add_column(style="dim", min_width=18)
    table.add_column()
    table.add_row("Total discovered", str(total))
    table.add_row("Loaded (ok)", f"[green]{len(loaded_recs)}[/green]")
    table.add_row("Failed", f"[red]{len(failed_recs)}[/red]")
    table.add_row("Skipped", str(len(skipped_recs)))
    table.add_row("With warnings", f"[yellow]{len(warned_recs)}[/yellow]")
    console.print(table)
    console.print()

    if not records:
        console.print(
            "[dim]No plugins found. "
            f"Drop .py plugin files into {manager.plugins_dir} to get started.[/dim]"
        )
        return

    # Show failed plugins
    if failed_recs:
        console.print(Rule("[red]Failed Plugins[/red]"))
        for record in failed_recs:
            console.print(
                f"  [red]✗[/red] [cyan]{record.name}[/cyan] "
                f"([dim]{record.file_name}[/dim])  [{record.status}]"
            )
            if record.error:
                # Indent the error block
                for line in record.error.splitlines()[:5]:
                    console.print(f"    [red]{line}[/red]")
        console.print()

    # Show warnings
    if warned_recs:
        console.print(Rule("[yellow]Plugins with Warnings[/yellow]"))
        for record in warned_recs:
            console.print(
                f"  [yellow]⚠[/yellow] [cyan]{record.name}[/cyan] "
                f"— {len(record.warnings)} warning(s)"
            )
            for w in record.warnings:
                console.print(f"    [yellow]{w}[/yellow]")
        console.print()

    # Health verdict
    if not failed_recs and not warned_recs:
        console.print("[green]All plugins loaded successfully.[/green]")
    elif failed_recs:
        console.print(
            f"[red]{len(failed_recs)} plugin(s) failed to load.[/red] "
            "Run [bold]canopus plugin inspect <name>[/bold] for details."
        )
    else:
        console.print(
            f"[yellow]{len(warned_recs)} plugin(s) loaded with warnings.[/yellow]"
        )

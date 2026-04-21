"""``canopus capability`` — sub-commands for inspecting registered capabilities."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from canopus.capabilities.registry import registry

console = Console()
capability_app = typer.Typer(help="Inspect registered capabilities.")


@capability_app.command("list")
def capability_list(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    transport: str | None = typer.Option(
        None, "--transport", help="Filter by transport (native, legacy_plugin, mcp)."
    ),
) -> None:
    """List all registered capabilities."""
    caps = registry.list_all()

    if tag:
        caps = [c for c in caps if tag in c.tags]
    if transport:
        caps = [c for c in caps if c.transport == transport]

    console.print(
        Panel.fit("[bold cyan]Registered Capabilities[/bold cyan]", border_style="cyan")
    )
    console.print()

    if not caps:
        console.print("[dim]No capabilities match the given filters.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Name", style="cyan", no_wrap=True, min_width=24)
    table.add_column("Transport", style="dim", min_width=12)
    table.add_column("Side Effects", min_width=12)
    table.add_column("Permissions", min_width=16)
    table.add_column("Description")

    for cap in caps:
        perms = ", ".join(p.value for p in cap.permissions) if cap.permissions else "—"
        table.add_row(
            cap.name,
            cap.transport,
            cap.side_effect_level.value,
            perms,
            cap.description,
        )

    console.print(table)
    console.print(f"\n[dim]{len(caps)} capability(ies) listed.[/dim]")

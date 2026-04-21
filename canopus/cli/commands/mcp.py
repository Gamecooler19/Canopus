"""``canopus mcp`` — sub-commands for inspecting MCP servers and their tools."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from canopus.plugins.mcp.manager import McpManager, get_manager
from canopus.plugins.mcp.models import McpServerStatus

console = Console()
mcp_app = typer.Typer(help="Inspect and manage MCP server connections.")

# Status display strings for each server status
_STATUS_LABEL: dict[McpServerStatus, str] = {
    McpServerStatus.CONNECTED: "[green]connected[/green]",
    McpServerStatus.PARTIAL: "[yellow]partial[/yellow]",
    McpServerStatus.FAILED: "[red]failed[/red]",
    McpServerStatus.DISABLED: "[dim]disabled[/dim]",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_manager() -> McpManager:
    """Return the global MCP manager or print a message and exit."""
    manager = get_manager()
    if manager is None:
        console.print(
            "[yellow]MCP manager is not initialized.[/yellow] "
            "This can happen when running commands outside the normal "
            "[cyan]canopus[/cyan] entrypoint."
        )
        raise typer.Exit(1)
    return manager


# ---------------------------------------------------------------------------
# canopus mcp list
# ---------------------------------------------------------------------------


@mcp_app.command("list")
def mcp_list(
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by status: connected, partial, failed, disabled.",
    ),
) -> None:
    """List all configured MCP servers and their connection status."""
    manager = _require_manager()
    records = manager.get_records()

    # Apply optional status filter
    if status is not None:
        try:
            filter_status = McpServerStatus(status.lower())
        except ValueError:
            valid = ", ".join(s.value for s in McpServerStatus)
            console.print(f"[red]Unknown status filter {status!r}. Valid: {valid}[/red]")
            raise typer.Exit(1) from None
        records = [r for r in records if r.status == filter_status]

    console.print(Panel.fit("[bold cyan]Canopus MCP Servers[/bold cyan]"))

    if not records:
        console.print("\n[dim]No MCP servers found.[/dim]\n")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Transport")
    table.add_column("Status")
    table.add_column("Tools", justify="right")
    table.add_column("Description")

    for record in records:
        status_label = _STATUS_LABEL.get(record.status, record.status.value)
        table.add_row(
            record.name,
            record.transport,
            status_label,
            str(len(record.tool_names)),
            record.description or "[dim]—[/dim]",
        )

    console.print(table)

    connected = len(manager.get_connected())
    failed = len(manager.get_failed())
    disabled = len(manager.get_disabled())

    console.print(
        f"\n[dim]Total: {len(records)} server(s) — "
        f"{connected} connected, {failed} failed, {disabled} disabled[/dim]"
    )


# ---------------------------------------------------------------------------
# canopus mcp inspect
# ---------------------------------------------------------------------------


@mcp_app.command("inspect")
def mcp_inspect(
    name: str = typer.Argument(..., help="MCP server name to inspect."),
) -> None:
    """Show detailed information about a specific MCP server."""
    manager = _require_manager()
    record = manager.get_record(name)

    if record is None:
        console.print(f"[red]MCP server {name!r} not found.[/red]")
        raise typer.Exit(1)

    status_label = _STATUS_LABEL.get(record.status, record.status.value)

    summary = (
        f"[bold]Name:[/bold]        {record.name}\n"
        f"[bold]Transport:[/bold]   {record.transport}\n"
        f"[bold]Status:[/bold]      {status_label}\n"
        f"[bold]Enabled:[/bold]     {'yes' if record.enabled else 'no'}\n"
        f"[bold]Description:[/bold] {record.description or '—'}"
    )
    console.print(
        Panel(
            summary,
            title=f"[bold cyan]MCP Server: {record.name}[/bold cyan]",
            border_style="cyan",
        )
    )

    if record.error:
        console.print(f"\n[red][bold]Error:[/bold] {record.error}[/red]")

    if record.tool_names:
        console.print(Rule("[bold]Registered Tools[/bold]"))
        # Look up full specs from the capability registry if available
        try:
            from canopus.capabilities.registry import registry
            tool_table = Table(show_header=True, header_style="bold")
            tool_table.add_column("Capability Name", style="cyan")
            tool_table.add_column("Description")
            tool_table.add_column("Tags")
            for cap_name in sorted(record.tool_names):
                try:
                    spec = registry.get(cap_name)
                    tool_table.add_row(
                        cap_name,
                        spec.description,
                        ", ".join(spec.tags) or "[dim]—[/dim]",
                    )
                except Exception:
                    tool_table.add_row(cap_name, "[dim]—[/dim]", "[dim]—[/dim]")
            console.print(tool_table)
        except Exception:
            for cap_name in sorted(record.tool_names):
                console.print(f"  [cyan]{cap_name}[/cyan]")
    else:
        console.print("\n[dim]No tools registered for this server.[/dim]")

    if record.warnings:
        console.print(Rule("[bold yellow]Warnings[/bold yellow]"))
        for warning in record.warnings:
            console.print(f"  [yellow]⚠[/yellow]  {warning}")


# ---------------------------------------------------------------------------
# canopus mcp doctor
# ---------------------------------------------------------------------------


@mcp_app.command("doctor")
def mcp_doctor() -> None:
    """Summarize MCP server health: connectivity, tool counts, and failures."""
    manager = _require_manager()
    records = manager.get_records()

    connected = manager.get_connected()
    failed = manager.get_failed()
    disabled = manager.get_disabled()

    console.print(Panel.fit("[bold cyan]MCP Server Health Report[/bold cyan]"))

    # Summary table
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Label", style="bold")
    summary_table.add_column("Value")
    summary_table.add_row("Total configured", str(len(records)))
    summary_table.add_row("[green]Connected[/green]", str(len(connected)))
    summary_table.add_row("[red]Failed[/red]", str(len(failed)))
    summary_table.add_row("[dim]Disabled[/dim]", str(len(disabled)))
    total_tools = sum(len(r.tool_names) for r in records)
    summary_table.add_row("Total tools registered", str(total_tools))
    console.print(summary_table)

    # Failed servers detail
    if failed:
        console.print(Rule("[bold red]Failed Servers[/bold red]"))
        for record in failed:
            console.print(f"\n  [red][bold]{record.name}[/bold][/red] ({record.transport})")
            if record.error:
                console.print(f"    Error: {record.error}")

    # Partial servers with warnings
    partial = [r for r in connected if r.warnings]
    if partial:
        console.print(Rule("[bold yellow]Servers with Warnings[/bold yellow]"))
        for record in partial:
            console.print(f"\n  [yellow][bold]{record.name}[/bold][/yellow]")
            for warning in record.warnings:
                console.print(f"    ⚠  {warning}")

    # Health verdict
    console.print()
    if not records:
        console.print("[dim]No MCP servers configured.[/dim]")
    elif not failed and not partial:
        console.print("[green][bold]All MCP servers healthy.[/bold][/green]")
    elif failed:
        console.print(
            f"[red][bold]{len(failed)} server(s) failed.[/bold][/red] "
            "Run [cyan]canopus mcp inspect <name>[/cyan] for details."
        )
    else:
        console.print(
            f"[yellow][bold]{len(partial)} server(s) have warnings.[/bold][/yellow]"
        )

"""``canopus capability`` — sub-commands for inspecting and invoking capabilities."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.executor import CapabilityExecutor
from canopus.capabilities.registry import registry
from canopus.core.errors import CapabilityError

console = Console()
capability_app = typer.Typer(help="Inspect and invoke registered capabilities.")


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


@capability_app.command("invoke")
def capability_invoke(
    name: str = typer.Argument(..., help="Capability name to invoke."),
    input_json: str = typer.Option(
        "{}",
        "--input-json",
        "-i",
        help="JSON object of inputs forwarded to the capability handler.",
    ),
    pretty: bool = typer.Option(True, "--pretty/--raw", help="Pretty-print JSON output."),
) -> None:
    """Invoke a capability directly by name.

    Useful for testing native and plugin capabilities without going through
    the full reasoning pipeline.

    Examples::

        canopus capability invoke system.now
        canopus capability invoke filesystem.list_dir --input-json '{"path": "."}'
        canopus capability invoke hello.greet --input-json '{"name": "Alice"}'
    """
    # ── Parse input ───────────────────────────────────────────────────────
    try:
        inputs: dict[str, Any] = json.loads(input_json)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid --input-json:[/red] {exc}")
        raise typer.Exit(1) from None

    if not isinstance(inputs, dict):
        console.print("[red]--input-json must be a JSON object (dict), not a list or scalar.[/red]")
        raise typer.Exit(1)

    # ── Verify capability exists ──────────────────────────────────────────
    try:
        spec = registry.get(name)
    except CapabilityError:
        console.print(f"[red]Capability not found:[/red] {name!r}")
        console.print("Run [bold]canopus capability list[/bold] to see registered capabilities.")
        raise typer.Exit(1) from None

    # ── Build minimal context ─────────────────────────────────────────────
    from canopus.core.profiles import builtin_profiles
    profile = builtin_profiles().get("local-private")
    if profile is None:
        console.print("[red]Could not load default profile.[/red]")
        raise typer.Exit(1)

    ctx = CapabilityContext(profile=profile)

    # ── Invoke ────────────────────────────────────────────────────────────
    executor = CapabilityExecutor(registry)
    result = executor.invoke(name, inputs, ctx)

    # ── Display result ────────────────────────────────────────────────────
    status_color = "green" if result.success else "red"
    status_label = "success" if result.success else "failed"
    latency_str = f"{result.latency_ms:.1f} ms" if result.latency_ms else "—"

    console.print(
        Panel(
            f"[bold]Capability:[/bold] {spec.name}\n"
            f"[bold]Transport:[/bold]  {spec.transport}\n"
            f"[bold]Status:[/bold]     [{status_color}]{status_label}[/{status_color}]\n"
            f"[bold]Latency:[/bold]    {latency_str}",
            title="[bold cyan]Capability Invoke[/bold cyan]",
            border_style="cyan",
        )
    )

    if result.success:
        output_json = json.dumps(result.data, indent=2 if pretty else None, default=str)
        console.print("\n[bold]Output:[/bold]")
        if pretty:
            console.print(Syntax(output_json, "json", theme="monokai"))
        else:
            console.print(output_json)
    else:
        console.print(f"\n[red][bold]Error:[/bold] {result.error}[/red]")
        raise typer.Exit(1)

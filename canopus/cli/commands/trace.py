"""``canopus trace`` — sub-commands for inspecting execution traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from canopus.core.config import load_config

console = Console()
trace_app = typer.Typer(help="Inspect Canopus execution traces.")


@trace_app.command("show")
def trace_show(
    run_id: str = typer.Argument(..., help="Run ID or prefix to display."),
    events: bool = typer.Option(True, "--events/--no-events", help="Show trace events."),
) -> None:
    """Show a human-readable summary of an execution trace."""
    config = load_config()
    traces_dir = config.paths.traces_dir

    trace_path = _resolve_trace(traces_dir, run_id)
    if trace_path is None:
        console.print(f"[red]No trace found matching run ID:[/red] {run_id}")
        raise typer.Exit(1)

    try:
        data: dict[str, Any] = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not read trace:[/red] {exc}")
        raise typer.Exit(1) from exc

    _render_trace(data, show_events=events)


@trace_app.command("list")
def trace_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum traces to show."),
) -> None:
    """List recent execution traces."""
    config = load_config()
    traces_dir = config.paths.traces_dir

    if not traces_dir.exists():
        console.print("[dim]No traces directory found.[/dim]")
        return

    trace_files = sorted(traces_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    trace_files = trace_files[:limit]

    if not trace_files:
        console.print("[dim]No traces found.[/dim]")
        return

    console.print(
        Panel.fit("[bold cyan]Recent Execution Traces[/bold cyan]", border_style="cyan")
    )
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Run ID (prefix)", style="cyan", no_wrap=True, min_width=10)
    table.add_column("Mode", min_width=8)
    table.add_column("Profile", min_width=14)
    table.add_column("Started", min_width=20)
    table.add_column("Duration", min_width=10)
    table.add_column("Outcome")

    for path in trace_files:
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        run_id = data.get("run_id", "?")[:8]
        mode = data.get("mode", "?")
        profile = data.get("profile_name", "?")
        started = data.get("started_at", "?")[:19].replace("T", " ")
        duration = data.get("duration_ms")
        duration_str = f"{duration:.0f} ms" if duration else "—"
        error = data.get("error")
        summary = data.get("result_summary", "")
        outcome = "[red]ERROR[/red]" if error else (summary or "[green]ok[/green]")

        table.add_row(run_id, mode, profile, started, duration_str, outcome)

    console.print(table)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_trace(traces_dir: Path, run_id_prefix: str) -> Path | None:
    """Find a trace file whose name starts with *run_id_prefix*."""
    if not traces_dir.exists():
        return None

    # Exact match first
    exact = traces_dir / f"{run_id_prefix}.json"
    if exact.exists():
        return exact

    # Prefix match
    matches = list(traces_dir.glob(f"{run_id_prefix}*.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Return the most recently modified one
        return max(matches, key=lambda p: p.stat().st_mtime)

    return None


def _render_trace(data: dict[str, Any], *, show_events: bool) -> None:
    """Render a trace dict to the terminal."""
    run_id = data.get("run_id", "?")
    mode = data.get("mode", "?")
    profile = data.get("profile_name", "?")
    request = data.get("request") or "—"
    started = data.get("started_at", "?")[:19].replace("T", " ")
    duration = data.get("duration_ms")
    duration_str = f"{duration:.0f} ms" if duration else "—"
    provider = data.get("model_provider") or "—"
    model = data.get("model_name") or "—"
    error = data.get("error")
    summary = data.get("result_summary") or "—"

    status_color = "red" if error else "green"
    status_label = "FAILED" if error else "OK"

    console.print(
        Panel(
            f"[bold]Run ID:[/bold]  {run_id}\n"
            f"[bold]Mode:[/bold]    {mode}\n"
            f"[bold]Profile:[/bold] {profile}\n"
            f"[bold]Started:[/bold] {started}\n"
            f"[bold]Duration:[/bold] {duration_str}\n"
            f"[bold]Provider:[/bold] {provider} / {model}\n"
            f"[bold]Status:[/bold]  [{status_color}]{status_label}[/{status_color}]",
            title="[bold cyan]Trace Summary[/bold cyan]",
            border_style="cyan",
        )
    )

    console.print(f"\n[bold]Request:[/bold] {request}")
    console.print(f"[bold]Result:[/bold]  {summary}\n")

    if error:
        console.print(f"[red][bold]Error:[/bold] {error}[/red]\n")

    if show_events:
        event_list: list[dict[str, Any]] = data.get("events", [])
        if event_list:
            console.print("[bold]Events:[/bold]")
            table = Table(show_header=True, header_style="bold", show_lines=False)
            table.add_column("#", style="dim", min_width=3)
            table.add_column("Timestamp", style="dim", min_width=20)
            table.add_column("Event Type", style="cyan", min_width=28)
            table.add_column("Data")

            for i, ev in enumerate(event_list, start=1):
                ts = ev.get("timestamp", "")[:19].replace("T", " ")
                ev_type = ev.get("event_type", "?")
                ev_data = ev.get("data", {})
                data_str = ", ".join(f"{k}={v!r}" for k, v in ev_data.items()) or "—"
                table.add_row(str(i), ts, ev_type, data_str)

            console.print(table)

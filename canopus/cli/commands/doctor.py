"""``canopus doctor`` — system health check and diagnostic summary."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from canopus.core.config import load_config
from canopus.core.profiles import ProfileLoader, builtin_profiles

console = Console()


def doctor() -> None:
    """Run a system health check and display a diagnostic summary."""
    config = load_config()
    paths = config.paths
    paths.ensure_all()

    console.print(
        Panel.fit("[bold cyan]Canopus Doctor[/bold cyan]", border_style="cyan")
    )
    console.print()

    # Each check is (passed: bool, label: str, detail: str)
    checks: list[tuple[bool, str, str]] = []

    # ----------------------------------------------------------------
    # Directory checks
    # ----------------------------------------------------------------
    dir_checks = [
        (paths.config_dir, "Config directory"),
        (paths.profiles_dir, "Profiles directory"),
        (paths.traces_dir, "Traces directory"),
        (paths.logs_dir, "Logs directory"),
        (paths.memory_dir, "Memory directory"),
        (paths.plugins_dir, "Plugins directory"),
        (paths.workflows_dir, "Workflows directory"),
        (paths.cache_dir, "Cache directory"),
    ]
    for directory, label in dir_checks:
        checks.append((directory.exists(), label, str(directory)))

    # ----------------------------------------------------------------
    # Config file
    # ----------------------------------------------------------------
    config_file_exists = paths.config_file.exists()
    detail = str(paths.config_file)
    if not config_file_exists:
        detail += "  [dim](not found — using defaults)[/dim]"
    checks.append((config_file_exists, "Config file", detail))

    # ----------------------------------------------------------------
    # Active profile
    # ----------------------------------------------------------------
    loader = ProfileLoader(profiles_dir=paths.profiles_dir)
    try:
        active = loader.load(config.active_profile)
        checks.append((
            True,
            "Active profile",
            f"{active.name}  ({active.display_name})  [dim][{active.source}][/dim]",
        ))
    except Exception as exc:
        checks.append((False, "Active profile", str(exc)))

    # ----------------------------------------------------------------
    # Built-in profile inventory
    # ----------------------------------------------------------------
    builtin_count = len(builtin_profiles())
    checks.append((True, "Built-in profiles", f"{builtin_count} available"))

    # ----------------------------------------------------------------
    # Render
    # ----------------------------------------------------------------
    table = Table(show_header=False, box=None, padding=(0, 1))
    pass_count = 0
    for ok, label, detail_text in checks:
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        table.add_row(icon, f"[dim]{label}[/dim]", detail_text)
        if ok:
            pass_count += 1

    console.print(table)
    console.print()

    total = len(checks)
    if pass_count == total:
        console.print(f"[green]All {total} checks passed.[/green]")
    else:
        failed = total - pass_count
        console.print(
            f"[yellow]{pass_count}/{total} checks passed.[/yellow]  "
            f"[red]{failed} issue(s) found.[/red]"
        )

"""``canopus version`` — display version and runtime information."""

from __future__ import annotations

import platform

from rich.console import Console
from rich.table import Table

from canopus import __version__

console = Console()


def version() -> None:
    """Display Canopus version and runtime environment information."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]Canopus[/bold cyan]", f"v{__version__}")
    table.add_row("[dim]Python[/dim]", platform.python_version())
    table.add_row("[dim]Platform[/dim]", platform.platform())
    table.add_row("[dim]Architecture[/dim]", platform.machine())
    console.print(table)

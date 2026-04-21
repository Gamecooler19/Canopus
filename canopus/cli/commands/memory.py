"""``canopus memory`` — CLI command group for the memory subsystem."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from canopus.memory.models import MemoryKind, MemoryQuery, MemoryRecord
from canopus.memory.service import MemoryService, get_service

memory_app = typer.Typer(
    name="memory",
    help="Inspect and manage the Canopus memory store.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_service() -> MemoryService:
    """Return the global MemoryService or exit with an error."""
    svc = get_service()
    if svc is None:
        console.print("[red]Memory service is not initialised.[/red]")
        console.print("[dim]Try running 'canopus memory list' after starting canopus.[/dim]")
        raise typer.Exit(1)
    return svc


def _render_record(record: MemoryRecord) -> None:
    """Print a single memory record as a rich Panel."""
    tag_str = ", ".join(record.tags) if record.tags else "[dim]none[/dim]"
    meta_str = str(record.metadata) if record.metadata else "[dim]{}[/dim]"
    body = (
        f"[bold]ID:[/bold]         {record.id}\n"
        f"[bold]Kind:[/bold]       {record.kind}\n"
        f"[bold]Source:[/bold]     {record.source}\n"
        f"[bold]Importance:[/bold] {record.importance:.2f}\n"
        f"[bold]Tags:[/bold]       {tag_str}\n"
        f"[bold]Session:[/bold]    {record.session_id or '[dim]—[/dim]'}\n"
        f"[bold]Run:[/bold]        {record.run_id or '[dim]—[/dim]'}\n"
        f"[bold]Created:[/bold]    {record.created_at.isoformat()}\n"
        f"[bold]Updated:[/bold]    {record.updated_at.isoformat()}\n"
        f"[bold]Metadata:[/bold]   {meta_str}\n"
        f"\n{record.content}"
    )
    console.print(
        Panel(body, title="[bold cyan]Memory[/bold cyan]", border_style="cyan")
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@memory_app.command("add")
def memory_add(
    content: str = typer.Argument(..., help="Text content of the memory to store."),
    kind: str = typer.Option(
        "fact", "--kind", "-k", help="Memory category (conversation/fact/summary/system)."
    ),
    tags: str = typer.Option(
        "", "--tags", "-t", help="Comma-separated tags (e.g. 'python,design')."
    ),
    importance: float = typer.Option(
        0.5, "--importance", "-i", min=0.0, max=1.0, help="Importance (0.0–1.0)."
    ),
    source: str = typer.Option("user", "--source", "-s", help="Source label."),
) -> None:
    """Store a new memory record manually.

    Example::

        canopus memory add "Prefer SQLite over Postgres" --kind fact --tags "db,design"
    """
    svc = _require_service()
    try:
        kind_enum = MemoryKind(kind)
    except ValueError:
        console.print(f"[red]Unknown kind:[/red] {kind!r}")
        raise typer.Exit(1) from None
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    record = MemoryRecord(
        content=content,
        kind=kind_enum,
        tags=tag_list,
        source=source,
        importance=importance,
    )
    svc.remember(record)
    console.print(f"[green]Stored memory[/green] [dim]{record.id}[/dim]")


@memory_app.command("list")
def memory_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum records to show."),
    kind: str = typer.Option(
        "", "--kind", "-k",
        help="Filter by kind (conversation/fact/summary/system)."
    ),
    source: str = typer.Option("", "--source", "-s", help="Filter by source."),
) -> None:
    """List recent memory records.

    Example::

        canopus memory list --limit 10 --kind fact
    """
    svc = _require_service()

    kind_filter: MemoryKind | None = None
    if kind:
        try:
            kind_filter = MemoryKind(kind)
        except ValueError:
            console.print(f"[red]Unknown kind:[/red] {kind!r}")
            raise typer.Exit(1) from None

    records = svc.list_recent(
        limit=limit,
        kind=kind_filter,
        source=source or None,
    )

    if not records:
        console.print("[dim]No memory records found.[/dim]")
        return

    table = Table(title="Memory Records", border_style="cyan", show_lines=False)
    table.add_column("ID", style="dim", no_wrap=True, max_width=12)
    table.add_column("Kind", no_wrap=True)
    table.add_column("Source", no_wrap=True)
    table.add_column("Imp.", no_wrap=True, justify="right")
    table.add_column("Created", no_wrap=True)
    table.add_column("Content preview", overflow="ellipsis")

    for rec in records:
        preview = rec.content.replace("\n", " ")[:60]
        table.add_row(
            rec.id[:8],
            rec.kind.value,
            rec.source,
            f"{rec.importance:.2f}",
            rec.created_at.strftime("%Y-%m-%d %H:%M"),
            preview,
        )

    console.print(table)
    console.print(f"[dim]{len(records)} record(s) shown.[/dim]")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search text."),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results."),
    kind: str = typer.Option("", "--kind", "-k", help="Filter by kind."),
) -> None:
    """Search memories by text.

    Full-text search using FTS5. Supports prefix search (``hello*``),
    boolean operators (``AND``, ``OR``, ``NOT``), and phrase search.

    Example::

        canopus memory search "SQLite design decision" --limit 5
    """
    svc = _require_service()

    kinds: list[MemoryKind] = []
    if kind:
        try:
            kinds = [MemoryKind(kind)]
        except ValueError:
            console.print(f"[red]Unknown kind:[/red] {kind!r}")
            raise typer.Exit(1) from None

    mem_query = MemoryQuery(text=query, limit=limit, kinds=kinds)
    records = svc.search(mem_query)

    if not records:
        console.print(f"[dim]No memories matched {query!r}.[/dim]")
        return

    table = Table(title=f"Search: {query!r}", border_style="cyan")
    table.add_column("ID", style="dim", no_wrap=True, max_width=12)
    table.add_column("Kind")
    table.add_column("Imp.", justify="right")
    table.add_column("Created")
    table.add_column("Content preview", overflow="ellipsis")

    for rec in records:
        preview = rec.content.replace("\n", " ")[:70]
        table.add_row(
            rec.id[:8],
            rec.kind.value,
            f"{rec.importance:.2f}",
            rec.created_at.strftime("%Y-%m-%d %H:%M"),
            preview,
        )

    console.print(table)
    console.print(f"[dim]{len(records)} result(s).[/dim]")


@memory_app.command("inspect")
def memory_inspect(
    memory_id: str = typer.Argument(..., help="Full or prefix of a memory ID."),
) -> None:
    """Show full details of a single memory record.

    *memory_id* can be the full UUID or the first 8 characters.

    Example::

        canopus memory inspect abc12345
    """
    from canopus.core.errors import MemoryNotFoundError

    svc = _require_service()

    # Try exact match first, then prefix search
    record: MemoryRecord | None = None
    try:
        record = svc.get(memory_id)
    except MemoryNotFoundError:
        # Attempt prefix match via list_recent (linear scan is fine for CLI)
        candidates = svc.list_recent(limit=1000)
        matches = [r for r in candidates if r.id.startswith(memory_id)]
        if len(matches) == 1:
            record = matches[0]
        elif len(matches) > 1:
            console.print(
                f"[yellow]Ambiguous prefix:[/yellow] {memory_id!r} matches "
                f"{len(matches)} records. Use a longer prefix or full ID."
            )
            raise typer.Exit(1) from None

    if record is None:
        console.print(f"[red]No memory found with ID or prefix:[/red] {memory_id!r}")
        raise typer.Exit(1)

    _render_record(record)


@memory_app.command("forget")
def memory_forget(
    memory_id: str = typer.Argument(..., help="Full memory ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a memory record permanently.

    Example::

        canopus memory forget <id> --yes
    """
    from canopus.core.errors import MemoryNotFoundError

    svc = _require_service()

    # Verify exists first
    try:
        record = svc.get(memory_id)
    except MemoryNotFoundError:
        console.print(f"[red]Memory not found:[/red] {memory_id!r}")
        raise typer.Exit(1) from None

    if not yes:
        preview = record.content[:60].replace("\n", " ")
        confirmed = typer.confirm(f"Delete memory {memory_id[:8]!r} ({preview!r})?")
        if not confirmed:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    try:
        svc.forget(memory_id)
        console.print(f"[green]Deleted memory[/green] [dim]{memory_id[:8]}[/dim]")
    except MemoryNotFoundError:
        console.print(f"[red]Memory not found:[/red] {memory_id!r}")
        raise typer.Exit(1) from None

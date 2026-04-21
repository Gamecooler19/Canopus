"""``canopus workflow`` — CLI command group for workflow management.

Commands:

- ``workflow list``      — list discovered workflows
- ``workflow inspect``   — show full definition of a named workflow
- ``workflow run``       — run a workflow with optional input values
- ``workflow validate``  — check a workflow definition for errors
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from canopus.workflows.loader import WorkflowLoader

workflow_app = typer.Typer(
    name="workflow",
    help="Discover, inspect, and execute reusable workflows.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_workflows_dir() -> Path:
    """Return the configured workflows directory from the application config."""
    from canopus.core.config import load_config

    return load_config().paths.workflows_dir


def _get_loader() -> WorkflowLoader:
    from canopus.workflows.loader import WorkflowLoader

    return WorkflowLoader(_get_workflows_dir())


def _parse_inputs(raw: list[str]) -> dict[str, str]:
    """Parse a list of ``key=value`` strings into a dict.

    Args:
        raw: List of strings like ``["path=/tmp", "limit=5"]``.

    Returns:
        Dict of parsed key/value pairs.

    Raises:
        :class:`typer.BadParameter`: If any item is not in ``key=value`` form.
    """
    result: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise typer.BadParameter(
                f"Input {item!r} is not in 'key=value' format.",
                param_hint="--input",
            )
        key, _, value = item.partition("=")
        result[key.strip()] = value
    return result


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@workflow_app.command("list")
def workflow_list() -> None:
    """List all workflows found in the workflows directory.

    Shows the workflow name, description, and tags for each discovered
    workflow. The directory is ``~/.canopus/workflows/`` by default and
    can be overridden in the application configuration.

    Example::

        canopus workflow list
    """
    from canopus.workflows.models import WorkflowDef

    loader = _get_loader()
    workflows: list[WorkflowDef] = loader.load_all()

    if not workflows:
        console.print("[dim]No workflows found.[/dim]")
        console.print(
            f"[dim]Add YAML files to [bold]{_get_workflows_dir()}[/bold].[/dim]"
        )
        return

    table = Table(
        title="[bold cyan]Workflows[/bold cyan]",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Name", style="bold cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")
    table.add_column("Steps", justify="right")

    for wf in sorted(workflows, key=lambda w: w.name):
        tag_str = ", ".join(wf.tags) if wf.tags else "—"
        table.add_row(
            wf.name,
            wf.description or "—",
            tag_str,
            str(len(wf.steps)),
        )

    console.print(table)


@workflow_app.command("inspect")
def workflow_inspect(
    name: Annotated[str, typer.Argument(help="Name of the workflow to inspect.")],
) -> None:
    """Show the full definition of a workflow.

    Displays all steps, inputs, and metadata for the named workflow.

    Example::

        canopus workflow inspect directory_summary
    """
    from canopus.workflows.errors import WorkflowNotFoundError

    loader = _get_loader()
    try:
        wf = loader.load(name)
    except WorkflowNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Error loading workflow:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Header
    header = (
        f"[bold]Name:[/bold]        {wf.name}\n"
        f"[bold]Description:[/bold] {wf.description or '—'}\n"
        f"[bold]Tags:[/bold]        {', '.join(wf.tags) if wf.tags else '—'}\n"
        f"[bold]Source:[/bold]      {wf.source_path}"
    )
    console.print(Panel(header, title="[bold cyan]Workflow[/bold cyan]", border_style="cyan"))

    # Inputs
    if wf.inputs:
        input_table = Table(
            title="[bold]Inputs[/bold]",
            show_header=True,
            border_style="dim",
        )
        input_table.add_column("Name", style="bold")
        input_table.add_column("Required", justify="center")
        input_table.add_column("Default")
        input_table.add_column("Description")
        for inp in wf.inputs:
            input_table.add_row(
                inp.name,
                "[green]yes[/green]" if inp.required else "[dim]no[/dim]",
                inp.default or "—",
                inp.description or "—",
            )
        console.print(input_table)

    # Steps
    step_table = Table(
        title="[bold]Steps[/bold]",
        show_header=True,
        border_style="dim",
    )
    step_table.add_column("#", justify="right", style="dim")
    step_table.add_column("ID", style="bold cyan")
    step_table.add_column("Kind", style="bold")
    step_table.add_column("On Failure")
    step_table.add_column("Description")
    for i, step in enumerate(wf.steps, start=1):
        step_table.add_row(
            str(i),
            step.id,
            str(step.kind),
            step.on_failure,
            step.description or "—",
        )
    console.print(step_table)


@workflow_app.command("validate")
def workflow_validate(
    name: Annotated[str, typer.Argument(help="Name of the workflow to validate.")],
) -> None:
    """Validate a workflow definition and report any errors.

    Exits with code 0 if the workflow is valid, 1 if there are errors.

    Example::

        canopus workflow validate directory_summary
    """
    loader = _get_loader()
    errors = loader.validate(name)

    if not errors:
        console.print(f"[green]Workflow [bold]{name}[/bold] is valid.[/green]")
        return

    console.print(f"[red]Workflow [bold]{name}[/bold] has validation errors:[/red]")
    for err in errors:
        console.print(f"  [dim]•[/dim] {err}")
    raise typer.Exit(1)


@workflow_app.command("run")
def workflow_run(
    name: Annotated[str, typer.Argument(help="Name of the workflow to run.")],
    inputs: Annotated[
        list[str] | None,
        typer.Option(
            "--input",
            "-i",
            help="Input value as 'key=value'. Repeat for multiple inputs.",
        ),
    ] = None,
    profile_name: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="Profile to use for model routing and permissions.",
        ),
    ] = "local-private",
) -> None:
    """Run a workflow with optional input values.

    Input values are supplied as ``--input key=value`` pairs. They map to
    the ``inputs:`` declared in the workflow YAML.

    Example::

        canopus workflow run directory_summary --input path=/home/user/notes

        canopus workflow run memory_brief --input query="recent Python decisions"
    """
    from canopus.capabilities.registry import registry
    from canopus.core.profiles import ProfileLoader
    from canopus.memory.service import get_service
    from canopus.models.router import ModelRouter
    from canopus.workflows.engine import WorkflowEngine
    from canopus.workflows.errors import WorkflowNotFoundError, WorkflowValidationError

    # Parse inputs
    try:
        parsed_inputs = _parse_inputs(inputs or [])
    except typer.BadParameter as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Load workflow
    loader = _get_loader()
    try:
        wf = loader.load(name)
    except WorkflowNotFoundError as exc:
        console.print(f"[red]Workflow not found:[/red] {name}")
        console.print(f"[dim]{exc}[/dim]")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Error loading workflow:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Resolve profile
    try:
        profile = ProfileLoader().load(profile_name)
    except Exception as exc:
        console.print(f"[red]Profile error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Resolve model provider
    try:
        provider = ModelRouter().get_provider(profile)
    except Exception as exc:
        console.print(f"[red]Model provider error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Build and run the engine
    engine = WorkflowEngine(
        registry=registry,
        provider=provider,
        memory_service=get_service(),
    )

    console.print(
        f"[bold cyan]Running workflow:[/bold cyan] {wf.name} "
        f"[dim]({len(wf.steps)} steps)[/dim]"
    )

    try:
        result = engine.run(wf, inputs=parsed_inputs, profile=profile)
    except WorkflowValidationError as exc:
        console.print(f"[red]Validation error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Runtime error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Render step results
    for step_result in result.step_results:
        icon = {
            "completed": "[green]✓[/green]",
            "failed": "[red]✗[/red]",
            "skipped": "[dim]⊘[/dim]",
        }.get(str(step_result.status), "?")
        ms = f"{step_result.latency_ms:.0f}ms" if step_result.latency_ms else "—"
        console.print(
            f"  {icon} [bold]{step_result.step_id}[/bold] "
            f"[dim]({step_result.kind})[/dim] "
            f"[dim]{ms}[/dim]"
        )
        if step_result.error:
            console.print(f"     [red]{step_result.error}[/red]")

    # Render summary
    status_color = {
        "completed": "green",
        "failed": "red",
        "partial": "yellow",
    }.get(str(result.status), "white")

    total_ms = f"{result.latency_ms:.0f}ms" if result.latency_ms else "—"
    summary = f"[{status_color}]Status:[/{status_color}] {result.status}  |  Time: {total_ms}"
    if result.error:
        summary += f"\n[red]Error:[/red] {result.error}"

    console.print(Panel(summary, title="[bold]Run Summary[/bold]", border_style="dim"))

    # Print final output if available
    if result.final_output:
        console.print(
            Panel(
                result.final_output,
                title="[bold cyan]Output[/bold cyan]",
                border_style="cyan",
            )
        )

    if result.status == "failed":
        raise typer.Exit(1)

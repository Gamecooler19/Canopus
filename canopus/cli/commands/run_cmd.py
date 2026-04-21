"""``canopus run <prompt>`` — one-shot prompt execution through the reasoning pipeline."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from canopus.core.runtime import RequestMode, create_session
from canopus.core.tracing import TraceWriter
from canopus.memory.models import MemoryContext
from canopus.memory.service import get_service
from canopus.reasoning.pipeline import run_pipeline
from canopus.reasoning.types import ReflectionOutcome

console = Console()


def run_prompt(
    prompt: str = typer.Argument(..., help="The task or question to execute."),
) -> None:
    """Execute a one-shot prompt through the reasoning pipeline.

    Creates a runtime session, classifies intent, invokes the configured
    model provider (or EchoProvider in demo mode), and displays the final
    response. A structured JSON trace is written on completion.
    """
    session = create_session(mode=RequestMode.RUN, request=prompt)
    writer = TraceWriter.from_session(session)
    writer.trace.add_event("session.started")
    writer.trace.add_event("request.received", {"text": prompt})

    # ----------------------------------------------------------------
    # Header
    # ----------------------------------------------------------------
    console.print(
        Panel(
            f"[bold]Run[/bold]  [dim]{session.run_id[:8]}[/dim]\n"
            f"Profile: [green]{session.profile.display_name}[/green]",
            title="[bold cyan]Canopus[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print(f"\n[bold]Request:[/bold] {prompt}\n")

    # ----------------------------------------------------------------
    # Memory context
    # ----------------------------------------------------------------
    memory_svc = get_service()
    mem_ctx: MemoryContext | None = None
    if memory_svc is not None:
        try:
            mem_ctx = memory_svc.build_context(prompt)
        except Exception:
            pass  # memory failure must not interrupt execution

    # ----------------------------------------------------------------
    # Reasoning pipeline
    # ----------------------------------------------------------------
    error_msg: str | None = None
    result_summary: str

    try:
        reflection = run_pipeline(prompt, session.profile, writer=writer, memory_context=mem_ctx)

        intent_label = reflection.execution.plan.intent.value
        confidence = reflection.execution.plan.intent_confidence
        provider = reflection.execution.provider_name
        model = reflection.execution.model_name
        latency = reflection.execution.latency_ms

        console.print(
            f"[dim]Intent:[/dim]   {intent_label}  "
            f"[dim](confidence {confidence:.0%})[/dim]"
        )
        console.print(f"[dim]Provider:[/dim] {provider} / {model}")
        if latency is not None:
            console.print(f"[dim]Latency:[/dim]  {latency:.1f} ms")
        console.print()

        console.print(Rule(style="dim"))
        if reflection.outcome == ReflectionOutcome.VALID:
            console.print(reflection.final_response)
        else:
            console.print(f"[yellow]{reflection.final_response}[/yellow]")
            for issue in reflection.issues:
                console.print(f"  [dim]• {issue}[/dim]")
        console.print(Rule(style="dim"))

        result_summary = f"outcome={reflection.outcome} intent={intent_label}"

        # Store the exchange in memory (best-effort; never crashes run)
        if memory_svc is not None and reflection.outcome == ReflectionOutcome.VALID:
            try:
                memory_svc.remember_exchange(
                    user_input=prompt,
                    assistant_response=reflection.final_response,
                    run_id=session.run_id,
                    session_id=session.session_id,
                )
            except Exception:
                pass

    except Exception as exc:
        error_msg = str(exc)
        result_summary = f"error: {error_msg}"
        console.print(f"\n[red]Error:[/red] {error_msg}")

    # ----------------------------------------------------------------
    # Finalise session + trace
    # ----------------------------------------------------------------
    session.finalize()
    trace_path = writer.close(error=error_msg, result_summary=result_summary)
    console.print(f"\n[dim]Trace: {trace_path}[/dim]")

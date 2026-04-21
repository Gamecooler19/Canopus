"""``canopus chat`` — interactive conversational session."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

from canopus import __version__
from canopus.core.runtime import RequestMode, create_session
from canopus.core.tracing import TraceWriter
from canopus.memory.service import get_service
from canopus.reasoning.pipeline import run_pipeline
from canopus.reasoning.types import ReflectionOutcome

console = Console()


def chat() -> None:
    """Start an interactive chat session with Canopus.

    Creates a session runtime and enters a read–respond loop driven by the
    reasoning pipeline. Type ``exit`` or ``quit`` to end the session, or
    press Ctrl-C at any time. A trace is written when the session exits.
    """
    session = create_session(mode=RequestMode.CHAT)
    writer = TraceWriter.from_session(session)
    writer.trace.add_event("session.started")
    memory_svc = get_service()

    console.print(
        Panel.fit(
            f"[bold cyan]Canopus Chat[/bold cyan]  v{__version__}\n"
            f"Profile: [green]{session.profile.display_name}[/green]"
            f"  [dim](session {session.session_id[:8]})[/dim]\n\n"
            "[dim]Type your message and press Enter. "
            "Type [bold]exit[/bold] or press Ctrl‑C to quit.[/dim]",
            border_style="cyan",
        )
    )

    turn = 0
    try:
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                break

            stripped = user_input.strip()
            if not stripped:
                continue
            if stripped.lower() in {"exit", "quit", "bye"}:
                break

            turn += 1
            writer.trace.add_event("request.received", {"turn": turn, "text": stripped})

            # Build memory context for this turn (best-effort)
            mem_ctx = None
            if memory_svc is not None:
                try:
                    mem_ctx = memory_svc.build_context(stripped)
                except Exception:
                    pass

            try:
                reflection = run_pipeline(
                    stripped, session.profile, writer=writer, memory_context=mem_ctx
                )
                provider = reflection.execution.provider_name
                model = reflection.execution.model_name
                intent = reflection.execution.plan.intent.value

                console.print(
                    f"\n[bold]Canopus[/bold]  "
                    f"[dim]{intent} · {provider}/{model}[/dim]"
                )
                console.print(Rule(style="dim"))
                if reflection.outcome == ReflectionOutcome.VALID:
                    console.print(reflection.final_response)
                else:
                    console.print(f"[yellow]{reflection.final_response}[/yellow]")
                console.print(Rule(style="dim"))

                writer.trace.add_event(
                    "response.generated",
                    {
                        "turn": turn,
                        "outcome": reflection.outcome,
                        "intent": intent,
                    },
                )

                # Store this exchange in memory (best-effort)
                if memory_svc is not None and reflection.outcome == ReflectionOutcome.VALID:
                    try:
                        memory_svc.remember_exchange(
                            user_input=stripped,
                            assistant_response=reflection.final_response,
                            session_id=session.session_id,
                        )
                    except Exception:
                        pass

            except Exception as exc:
                console.print(f"[red]Error:[/red] {exc}")
                writer.trace.add_event("error", {"turn": turn, "message": str(exc)})

    except KeyboardInterrupt:
        pass
    finally:
        session.finalize()
        trace_path = writer.close(result_summary=f"chat session ended after {turn} turns")
        console.print(f"\n[dim]Session ended. Trace: {trace_path}[/dim]")

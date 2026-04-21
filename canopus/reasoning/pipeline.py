"""Reasoning pipeline orchestrator.

:func:`run_pipeline` is the single entry point that CLI commands call.  It
wires together the :class:`~canopus.reasoning.planner.Planner`,
:class:`~canopus.reasoning.executor.Executor`, and
:class:`~canopus.reasoning.reflector.Reflector` into a coherent
planner → executor → reflector flow and emits structured trace events at
each stage.

Keeping this orchestration separate from both the CLI layer and the
individual reasoning components means:

- CLI code stays thin (no business logic).
- Each reasoning stage remains independently testable.
- The pipeline boundary is a clear integration point for future enhancements
  (retries, multi-step planning, capability dispatch, …).
"""

from __future__ import annotations

from canopus.core.profiles import ProfileSettings
from canopus.core.tracing import TraceWriter
from canopus.memory.models import MemoryContext
from canopus.models.base import ModelProvider
from canopus.models.router import ModelRouter
from canopus.reasoning.executor import Executor
from canopus.reasoning.planner import Planner
from canopus.reasoning.reflector import Reflector
from canopus.reasoning.types import ReflectionResult


def run_pipeline(
    request: str,
    profile: ProfileSettings,
    *,
    writer: TraceWriter | None = None,
    provider: ModelProvider | None = None,
    memory_context: MemoryContext | None = None,
) -> ReflectionResult:
    """Run the full planner → executor → reflector pipeline for *request*.

    Args:
        request: The raw user input string.
        profile: The active profile, used to select a provider if *provider*
            is not supplied explicitly.
        writer: Optional :class:`~canopus.core.tracing.TraceWriter` to receive
            structured reasoning-stage events.
        provider: Override the provider selected by the router. Primarily
            useful in tests.
        memory_context: Optional pre-assembled memory context from the memory
            subsystem. When supplied, the rendered prompt block is injected
            into the user prompt before the model call.

    Returns:
        A :class:`~canopus.reasoning.types.ReflectionResult` containing the
        final response and full execution metadata.
    """
    # ----------------------------------------------------------------
    # Provider selection
    # ----------------------------------------------------------------
    resolved_provider = provider or ModelRouter().get_provider(profile)

    if writer:
        writer.trace.add_event(
            "provider.selected",
            {
                "provider": resolved_provider.provider_name,
                "model": resolved_provider.model_name,
            },
        )
        # Populate top-level trace fields for quick filtering/display
        writer.trace.model_provider = resolved_provider.provider_name
        writer.trace.model_name = resolved_provider.model_name

    # ----------------------------------------------------------------
    # Planning
    # ----------------------------------------------------------------
    planner = Planner()
    plan = planner.plan(request)

    if writer:
        writer.trace.add_event(
            "plan.created",
            {
                "intent": plan.intent,
                "confidence": plan.intent_confidence,
                "summary": plan.summary,
                "steps": [s.description for s in plan.steps],
                "requires_capabilities": plan.requires_capabilities,
            },
        )

    # ----------------------------------------------------------------
    # Memory context injection
    # ----------------------------------------------------------------
    memory_block = ""
    if memory_context is not None:
        memory_block = memory_context.as_prompt_block()
        if writer and memory_block:
            writer.trace.add_event(
                "memory.context_injected",
                {
                    "records": memory_context.total_found,
                    "truncated": memory_context.truncated,
                },
            )

    # ----------------------------------------------------------------
    # Execution
    # ----------------------------------------------------------------
    executor = Executor(resolved_provider)
    execution = executor.execute(plan, request, writer=writer, memory_block=memory_block)

    if writer:
        event_data: dict[str, object] = {
            "provider": execution.provider_name,
            "model": execution.model_name,
            "latency_ms": execution.latency_ms,
            "prompt_tokens": execution.prompt_tokens,
            "completion_tokens": execution.completion_tokens,
        }
        if execution.capability_name:
            event_data["capability"] = execution.capability_name
        writer.trace.add_event("execution.completed", event_data)

    # ----------------------------------------------------------------
    # Reflection
    # ----------------------------------------------------------------
    reflector = Reflector()
    reflection = reflector.reflect(execution)

    if writer:
        writer.trace.add_event(
            "reflection.completed",
            {
                "outcome": reflection.outcome,
                "issues": reflection.issues,
                "retry_count": reflection.retry_count,
            },
        )

    return reflection

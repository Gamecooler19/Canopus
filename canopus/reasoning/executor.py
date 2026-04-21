"""Plan executor — dispatches capability calls or model provider calls.

The :class:`Executor` is responsible for:

1. Checking whether any plan step targets a registered capability.
2. If so, routing through the :class:`~canopus.capabilities.executor.CapabilityExecutor`.
3. Otherwise, building a model request from the plan and calling the provider.
4. Wrapping the response in a typed :class:`~canopus.reasoning.types.ExecutionResult`.

The executor is deliberately thin: it does not retry, it does not validate,
and it does not interpret the response. Those responsibilities belong to the
:class:`~canopus.reasoning.reflector.Reflector`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.executor import CapabilityExecutor
from canopus.capabilities.registry import registry as _global_registry
from canopus.models.base import ModelProvider, ModelRequest
from canopus.reasoning.prompts.templates import build_prompt
from canopus.reasoning.types import ExecutionResult, Plan

if TYPE_CHECKING:
    from canopus.capabilities.registry import CapabilityRegistry
    from canopus.core.profiles import ProfileSettings
    from canopus.core.tracing import TraceWriter


class Executor:
    """Runs a :class:`~canopus.reasoning.types.Plan` through a capability or model provider.

    If any plan step has ``capability_name`` set, the first matching step is
    dispatched through the :class:`~canopus.capabilities.executor.CapabilityExecutor`.
    All other plans fall through to the model provider path.

    Args:
        provider: The :class:`~canopus.models.base.ModelProvider` to use for
            generation. Injected externally so the executor remains
            provider-agnostic.
        capability_registry: Optional registry override; defaults to the
            global registry.

    Usage::

        executor = Executor(provider)
        result = executor.execute(plan, original_request="hello")
    """

    def __init__(
        self,
        provider: ModelProvider,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._cap_registry = capability_registry or _global_registry
        self._cap_executor = CapabilityExecutor(self._cap_registry)

    def execute(
        self,
        plan: Plan,
        original_request: str,
        *,
        writer: TraceWriter | None = None,
        memory_block: str = "",
    ) -> ExecutionResult:
        """Execute *plan* via a capability or a model provider.

        Checks plan steps for capability routing first; falls back to the
        model provider if no capability step is found.

        Args:
            plan: The planner-produced execution plan.
            original_request: The verbatim user input.
            writer: Optional trace writer forwarded to capability context.
            memory_block: Pre-formatted memory context string from
                :meth:`~canopus.memory.models.MemoryContext.as_prompt_block`.
                Injected into the model prompt when the model path is taken.

        Returns:
            An :class:`~canopus.reasoning.types.ExecutionResult`.
        """
        # ── Capability path ───────────────────────────────────────────────
        for step in plan.steps:
            if step.capability_name and self._cap_registry.contains(step.capability_name):
                return self._execute_capability(
                    plan=plan,
                    capability_name=step.capability_name,
                    inputs=step.capability_inputs,
                    writer=writer,
                )

        # ── Model provider path ───────────────────────────────────────────
        return self._execute_model(plan, original_request, memory_block=memory_block)

    # ------------------------------------------------------------------
    # Internal execution paths
    # ------------------------------------------------------------------

    def _execute_capability(
        self,
        plan: Plan,
        capability_name: str,
        inputs: dict[str, Any],
        writer: TraceWriter | None,
    ) -> ExecutionResult:
        """Invoke a registered capability and wrap the result."""

        # Build a minimal CapabilityContext (profile accessed via provider if needed)
        # We create a minimal context; the pipeline passes writer for tracing.
        ctx = CapabilityContext(
            profile=_get_dummy_profile(),  # replaced below if needed
            writer=writer,
        )

        result = self._cap_executor.invoke(capability_name, inputs, ctx)

        # Format the output as a readable string for the reflector
        raw_response = _format_capability_output(capability_name, result.data, result.error)

        return ExecutionResult(
            plan=plan,
            raw_response=raw_response,
            provider_name="capability",
            model_name=capability_name,
            latency_ms=result.latency_ms,
            capability_name=capability_name,
        )

    def _execute_model(
        self, plan: Plan, original_request: str, *, memory_block: str = ""
    ) -> ExecutionResult:
        """Invoke the model provider and wrap the response."""
        system_prompt, user_prompt = build_prompt(
            plan, original_request, memory_block=memory_block
        )

        model_request = ModelRequest(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        response = self._provider.complete(model_request)

        return ExecutionResult(
            plan=plan,
            raw_response=response.text,
            provider_name=response.provider_name,
            model_name=response.model_name,
            latency_ms=response.latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_capability_output(name: str, data: dict[str, Any], error: str | None) -> str:
    """Produce a human-readable string from a capability's output dict."""
    if error:
        return f"Capability {name!r} failed: {error}"

    if name == "system.now":
        return (
            f"Current time: {data.get('local_time', '?')} "
            f"({data.get('timezone', 'UTC')})\n"
            f"Date: {data.get('local_date', '?')}\n"
            f"UTC: {data.get('utc_iso', '?')}"
        )

    if name == "filesystem.read_text":
        size = data.get("size_bytes", 0)
        content = data.get("content", "")
        return f"File: {data.get('path', '?')} ({size:,} bytes)\n\n{content}"

    if name == "filesystem.list_dir":
        path = data.get("path", "?")
        entries: list[dict[str, Any]] = data.get("entries", [])
        truncated: bool = data.get("truncated", False)
        lines = [f"Directory: {path}", f"{len(entries)} entries:"]
        for e in entries:
            if e.get("type") == "directory":
                lines.append(f"  [{e['name']}/]")
            else:
                size = e.get("size_bytes")
                size_str = f" ({size:,} B)" if size is not None else ""
                lines.append(f"  {e['name']}{size_str}")
        if truncated:
            lines.append("  … (output truncated)")
        return "\n".join(lines)

    # Generic fallback
    return "\n".join(f"{k}: {v}" for k, v in data.items())


def _get_dummy_profile() -> ProfileSettings:
    """Return a minimal dummy ProfileSettings for context construction.

    The capability context profile is only consulted by handlers that
    need network/permission checks. All native capabilities in Phase 3
    ignore it. This will be replaced with real profile injection in Phase 7.
    """
    from canopus.core.profiles import builtin_profiles

    return builtin_profiles()["local-private"]


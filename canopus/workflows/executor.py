"""Workflow step executor — dispatches individual steps to the right subsystem.

:class:`StepExecutor` is the step-level dispatcher. The engine calls it once
per step and gets a :class:`~canopus.workflows.models.StepResult` back.

Each step kind is routed to an internal ``_execute_*`` method that uses the
existing Canopus subsystems:

- ``capability`` → :class:`~canopus.capabilities.executor.CapabilityExecutor`
- ``model``      → model provider via :meth:`~canopus.models.base.ModelProvider.complete`
- ``memory_search`` → :class:`~canopus.memory.service.MemoryService`
- ``output``     → template resolution only
- ``set_var``    → template resolution only

No subsystem logic is duplicated here. This module is intentionally thin —
all it does is dispatch.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.executor import CapabilityExecutor
from canopus.core.errors import CapabilityError
from canopus.memory.models import MemoryQuery
from canopus.models.base import ModelRequest
from canopus.workflows.errors import WorkflowStepError
from canopus.workflows.models import StepResult, StepStatus, WorkflowStepDef, WorkflowStepKind

if TYPE_CHECKING:
    from canopus.workflows.context import WorkflowContext


class StepExecutor:
    """Dispatches a single workflow step to the appropriate subsystem.

    Args:
        ctx: The mutable workflow execution context.
    """

    def __init__(self, ctx: WorkflowContext) -> None:
        self._ctx = ctx

    def execute(self, step: WorkflowStepDef) -> StepResult:
        """Execute *step* and return a structured result.

        Never raises. All failures are captured in the returned :class:`StepResult`
        with ``status="failed"`` so the engine can decide whether to abort.

        Args:
            step: The step definition to execute.

        Returns:
            A :class:`~canopus.workflows.models.StepResult`.
        """
        start = time.monotonic()
        try:
            output = self._dispatch(step)
            latency_ms = (time.monotonic() - start) * 1_000
            return StepResult(
                step_id=step.id,
                kind=step.kind,
                status=StepStatus.COMPLETED,
                output=output,
                latency_ms=latency_ms,
            )
        except WorkflowStepError as exc:
            latency_ms = (time.monotonic() - start) * 1_000
            return StepResult(
                step_id=step.id,
                kind=step.kind,
                status=StepStatus.FAILED,
                error=exc.reason,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1_000
            return StepResult(
                step_id=step.id,
                kind=step.kind,
                status=StepStatus.FAILED,
                error=str(exc),
                latency_ms=latency_ms,
            )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Route the step to the correct handler."""
        match step.kind:
            case WorkflowStepKind.CAPABILITY:
                return self._execute_capability(step)
            case WorkflowStepKind.MODEL:
                return self._execute_model(step)
            case WorkflowStepKind.MEMORY_SEARCH:
                return self._execute_memory_search(step)
            case WorkflowStepKind.OUTPUT:
                return self._execute_output(step)
            case WorkflowStepKind.SET_VAR:
                return self._execute_set_var(step)
            case _:
                raise WorkflowStepError(step.id, f"unknown step kind {step.kind!r}")

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------

    def _execute_capability(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Invoke a registered capability."""
        cap_name = step.capability
        if not cap_name:
            raise WorkflowStepError(step.id, "missing 'capability' field")

        # Resolve template expressions in inputs
        raw_inputs: dict[str, Any] = step.inputs or {}
        try:
            resolved_inputs = self._ctx.resolve_dict(raw_inputs)
        except Exception as exc:
            raise WorkflowStepError(step.id, f"input template error: {exc}") from exc

        executor = CapabilityExecutor(self._ctx.registry)
        cap_ctx = CapabilityContext(
            profile=self._ctx.profile,
            writer=self._ctx.writer,
        )
        try:
            result = executor.invoke(cap_name, resolved_inputs, cap_ctx)
        except CapabilityError as exc:
            raise WorkflowStepError(step.id, str(exc)) from exc

        if not result.success:
            raise WorkflowStepError(
                step.id, result.error or "capability returned failure"
            )

        output = dict(result.data)
        # Convenience: add a top-level "text" key with a formatted summary
        if "text" not in output:
            output["text"] = _dict_to_text(output)
        return output

    def _execute_model(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Run a model generation step."""
        if not step.prompt:
            raise WorkflowStepError(step.id, "missing 'prompt' field")

        try:
            resolved_prompt = self._ctx.resolve(step.prompt)
        except Exception as exc:
            raise WorkflowStepError(step.id, f"prompt template error: {exc}") from exc

        request = ModelRequest(prompt=resolved_prompt)
        try:
            response = self._ctx.provider.complete(request)
        except Exception as exc:
            raise WorkflowStepError(step.id, f"model provider error: {exc}") from exc

        return {
            "text": response.text,
            "provider": response.provider_name,
            "model": response.model_name,
            "latency_ms": response.latency_ms,
        }

    def _execute_memory_search(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Retrieve memory records for this step."""
        svc = self._ctx.memory_service
        if svc is None:
            raise WorkflowStepError(
                step.id, "memory service is not initialised — run 'canopus memory' first"
            )

        query_text = ""
        if step.query:
            try:
                query_text = self._ctx.resolve(step.query)
            except Exception as exc:
                raise WorkflowStepError(
                    step.id, f"query template error: {exc}"
                ) from exc

        q = MemoryQuery(text=query_text, limit=10)
        records = svc.search(q)

        # Build the context object for downstream template use
        from canopus.memory.models import MemoryContext

        mem_ctx = MemoryContext(
            records=records,
            query_text=query_text,
            total_found=len(records),
        )
        block = mem_ctx.as_prompt_block()

        return {
            "records": [r.model_dump(mode="json") for r in records],
            "count": len(records),
            "block": block,
            "text": block,
        }

    def _execute_output(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Resolve the final output value."""
        value = step.value or ""
        try:
            resolved = self._ctx.resolve(value) if value else ""
        except Exception as exc:
            raise WorkflowStepError(
                step.id, f"output template error: {exc}"
            ) from exc
        return {"text": resolved}

    def _execute_set_var(self, step: WorkflowStepDef) -> dict[str, Any]:
        """Resolve and store a workflow variable."""
        value = step.value or ""
        try:
            resolved = self._ctx.resolve(value) if value else ""
        except Exception as exc:
            raise WorkflowStepError(
                step.id, f"value template error: {exc}"
            ) from exc
        return {"value": resolved, "text": resolved}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dict_to_text(data: dict[str, Any]) -> str:
    """Convert a capability output dict to a compact text summary."""
    parts: list[str] = []
    for k, v in data.items():
        if isinstance(v, list):
            parts.append(f"{k}: {len(v)} items")
        elif isinstance(v, dict):
            parts.append(f"{k}: (dict)")
        else:
            parts.append(f"{k}: {v}")
    return "\n".join(parts) if parts else ""

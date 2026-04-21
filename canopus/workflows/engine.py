"""Workflow engine — orchestrates multi-step workflow execution.

:class:`WorkflowEngine` is the top-level orchestrator. It:

1. Validates user-supplied inputs against the workflow's ``inputs`` declarations.
2. Resolves default values for optional inputs.
3. Builds a :class:`~canopus.workflows.context.WorkflowContext`.
4. Iterates over the ordered list of steps, calling
   :class:`~canopus.workflows.executor.StepExecutor`.
5. Applies ``on_failure`` policy (``"abort"`` or ``"continue"``) on step failure.
6. Emits trace events for observability.
7. Collects the final ``output`` step value into
   :attr:`~canopus.workflows.models.WorkflowResult.final_output`.
8. Returns a fully populated :class:`~canopus.workflows.models.WorkflowResult`.

Usage::

    engine = WorkflowEngine(registry=registry, provider=provider)
    result = engine.run(workflow_def, inputs={"path": "/tmp/notes"}, profile=profile)
    print(result.final_output)
"""

from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING, Any

from canopus.workflows.context import WorkflowContext
from canopus.workflows.errors import WorkflowValidationError
from canopus.workflows.executor import StepExecutor
from canopus.workflows.models import (
    StepResult,
    StepStatus,
    WorkflowDef,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStepKind,
)

if TYPE_CHECKING:
    from canopus.capabilities.registry import CapabilityRegistry
    from canopus.core.profiles import ProfileSettings
    from canopus.core.tracing import TraceWriter
    from canopus.memory.service import MemoryService
    from canopus.models.base import ModelProvider


class WorkflowEngine:
    """Orchestrates the execution of a :class:`~canopus.workflows.models.WorkflowDef`.

    Args:
        registry: Capability registry used by capability steps.
        provider: Model provider used by model steps.
        memory_service: Optional memory service for memory_search steps.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        provider: ModelProvider,
        *,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._registry = registry
        self._provider = provider
        self._memory_service = memory_service

    def run(
        self,
        workflow: WorkflowDef,
        inputs: dict[str, Any] | None = None,
        profile: ProfileSettings | None = None,
        *,
        writer: TraceWriter | None = None,
    ) -> WorkflowResult:
        """Execute *workflow* and return a structured result.

        Args:
            workflow: The parsed and validated workflow definition.
            inputs: User-supplied input values. Merged with declared defaults.
            profile: Runtime profile. Defaults to a minimal default profile.
            writer: Optional trace writer. When supplied, workflow lifecycle
                events are emitted to the trace.

        Returns:
            A :class:`~canopus.workflows.models.WorkflowResult` describing
            the full execution outcome.
        """
        started_at = datetime.datetime.now(datetime.UTC)
        start_mono = time.monotonic()

        resolved_inputs = self._resolve_inputs(workflow, inputs or {})

        if profile is None:
            profile = _default_profile()

        ctx = WorkflowContext(
            workflow=workflow,
            inputs=resolved_inputs,
            profile=profile,
            registry=self._registry,
            provider=self._provider,
            memory_service=self._memory_service,
            writer=writer,
        )

        # Emit workflow.started
        if writer:
            writer.trace.add_event(
                "workflow.started",
                {
                    "workflow_name": workflow.name,
                    "run_id": ctx.run_id,
                    "inputs": {k: str(v) for k, v in resolved_inputs.items()},
                },
            )

        result = WorkflowResult(
            workflow_name=workflow.name,
            run_id=ctx.run_id,
            inputs=resolved_inputs,
            started_at=started_at,
        )

        executor = StepExecutor(ctx)
        final_output: str | None = None
        failed = False

        for step in workflow.steps:
            if writer:
                writer.trace.add_event(
                    "workflow.step.started",
                    {"step_id": step.id, "kind": str(step.kind)},
                )

            step_result: StepResult = executor.execute(step)

            if step_result.status == StepStatus.COMPLETED:
                ctx.record_step_output(step.effective_output_key, step_result.output)
                if step.kind == WorkflowStepKind.OUTPUT:
                    final_output = step_result.output.get("text")

                if writer:
                    writer.trace.add_event(
                        "workflow.step.completed",
                        {
                            "step_id": step.id,
                            "latency_ms": step_result.latency_ms,
                        },
                    )
            else:
                failed = True
                if writer:
                    writer.trace.add_event(
                        "workflow.step.failed",
                        {
                            "step_id": step.id,
                            "error": step_result.error,
                        },
                    )
                if step.on_failure == "abort":
                    result.step_results.append(step_result)
                    result.status = WorkflowStatus.FAILED
                    result.error = (
                        f"Step {step.id!r} failed: {step_result.error}"
                    )
                    break

            result.step_results.append(step_result)

        # Determine overall status
        if result.status != WorkflowStatus.FAILED:
            if failed:
                result.status = WorkflowStatus.PARTIAL
            else:
                result.status = WorkflowStatus.COMPLETED

        completed_at = datetime.datetime.now(datetime.UTC)
        latency_ms = (time.monotonic() - start_mono) * 1_000

        result.completed_at = completed_at
        result.latency_ms = latency_ms
        result.final_output = final_output

        if writer:
            writer.trace.add_event(
                "workflow.completed",
                {
                    "workflow_name": workflow.name,
                    "run_id": ctx.run_id,
                    "status": str(result.status),
                    "latency_ms": latency_ms,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Input resolution
    # ------------------------------------------------------------------

    def _resolve_inputs(
        self,
        workflow: WorkflowDef,
        supplied: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge supplied inputs with declared defaults and validate required ones.

        Args:
            workflow: Workflow definition with input declarations.
            supplied: User-supplied key/value pairs.

        Returns:
            Fully resolved inputs dict.

        Raises:
            :class:`~canopus.workflows.errors.WorkflowValidationError`: If a
                required input is missing and has no default.
        """
        resolved: dict[str, Any] = {}
        for decl in workflow.inputs:
            if decl.name in supplied:
                resolved[decl.name] = supplied[decl.name]
            elif decl.default is not None:
                resolved[decl.name] = decl.default
            elif decl.required:
                raise WorkflowValidationError(
                    workflow.name,
                    f"required input {decl.name!r} was not provided",
                )
        # Pass through any undeclared inputs silently
        for k, v in supplied.items():
            if k not in resolved:
                resolved[k] = v
        return resolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_profile() -> ProfileSettings:
    """Return the built-in local-private ProfileSettings as the workflow default."""
    from canopus.core.profiles import ProfileLoader

    return ProfileLoader().load("local-private")

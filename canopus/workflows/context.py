"""Workflow execution context.

:class:`WorkflowContext` is the mutable state object that lives for the
duration of a single workflow run. It holds:

- The resolved workflow inputs
- The accumulated step outputs (used for template resolution)
- The workflow definition and run ID
- References to the profile, trace writer, capability registry, model provider,
  and memory service that the executor needs

The context is threaded through the executor so no global state is accessed
directly during execution.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from canopus.workflows.templating import resolve, resolve_dict

if TYPE_CHECKING:
    from canopus.capabilities.registry import CapabilityRegistry
    from canopus.core.profiles import ProfileSettings
    from canopus.core.tracing import TraceWriter
    from canopus.memory.service import MemoryService
    from canopus.models.base import ModelProvider
    from canopus.workflows.models import WorkflowDef


class WorkflowContext:
    """Mutable execution state for a single workflow run.

    Args:
        workflow: The parsed workflow definition.
        inputs: Resolved user-supplied inputs.
        profile: Active runtime profile.
        registry: Capability registry for capability steps.
        provider: Model provider for model steps.
        memory_service: Memory service for memory_search steps. May be ``None``
            if the memory subsystem is not initialised.
        writer: Trace writer. May be ``None`` in test contexts.
    """

    def __init__(
        self,
        workflow: WorkflowDef,
        inputs: dict[str, Any],
        profile: ProfileSettings,
        registry: CapabilityRegistry,
        provider: ModelProvider,
        *,
        memory_service: MemoryService | None = None,
        writer: TraceWriter | None = None,
    ) -> None:
        self.workflow = workflow
        self.inputs: dict[str, Any] = inputs
        self.profile = profile
        self.registry = registry
        self.provider = provider
        self.memory_service = memory_service
        self.writer = writer
        self.run_id: str = str(uuid.uuid4())

        # step_id → {"output": dict[str, Any]}
        self._step_outputs: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Step output management
    # ------------------------------------------------------------------

    def record_step_output(self, step_id: str, output: dict[str, Any]) -> None:
        """Store the output of a completed step for template resolution.

        Args:
            step_id: The step's ``id`` field.
            output: The structured output dict from the step executor.
        """
        self._step_outputs[step_id] = {"output": output}

    def get_step_output(self, step_id: str) -> dict[str, Any]:
        """Return the output dict for a previously executed step.

        Args:
            step_id: The step's ``id`` field.

        Returns:
            The output dict, or an empty dict if the step has no output yet.
        """
        step = self._step_outputs.get(step_id)
        if step is None:
            return {}
        output = step.get("output", {})
        if not isinstance(output, dict):
            return {}
        return output

    def completed_step_ids(self) -> list[str]:
        """Return IDs of steps that have recorded output, in order."""
        return list(self._step_outputs.keys())

    # ------------------------------------------------------------------
    # Template resolution
    # ------------------------------------------------------------------

    @property
    def _template_data(self) -> dict[str, Any]:
        return {"inputs": self.inputs, "steps": self._step_outputs}

    def resolve(self, template: str) -> str:
        """Resolve a template string against the current context.

        Args:
            template: String that may contain ``{{ inputs.x }}`` or
                ``{{ steps.y.z }}`` expressions.

        Returns:
            The resolved string.

        Raises:
            :class:`~canopus.workflows.errors.WorkflowTemplatingError`: On failure.
        """
        return resolve(template, self._template_data)

    def resolve_dict(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Resolve all string values in *mapping* against the current context.

        Args:
            mapping: A key/value dict whose string values may contain templates.

        Returns:
            A new dict with templates resolved.
        """
        return resolve_dict(mapping, self._template_data)

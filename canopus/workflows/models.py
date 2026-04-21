"""Typed models for the workflow subsystem.

The public contract for workflow definitions, step specifications, and
execution results. All I/O with the YAML files goes through these models.

Key types:
- :class:`WorkflowStepKind` — enumeration of supported step types
- :class:`WorkflowStepDef` — a single step definition as parsed from YAML
- :class:`WorkflowDef` — a complete workflow definition
- :class:`StepResult` — outcome of executing one step
- :class:`WorkflowResult` — complete outcome of a workflow run
"""

from __future__ import annotations

import datetime
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class WorkflowStepKind(StrEnum):
    """Supported step types in a workflow definition.

    Attributes:
        CAPABILITY: Invoke a registered capability by name.
        MODEL: Run a generation step through the model router.
        MEMORY_SEARCH: Retrieve memory context for this workflow run.
        OUTPUT: Mark the final output of the workflow.
        SET_VAR: Assign a value to a workflow variable (no external call).
    """

    CAPABILITY = "capability"
    MODEL = "model"
    MEMORY_SEARCH = "memory_search"
    OUTPUT = "output"
    SET_VAR = "set_var"


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------


class WorkflowStepDef(BaseModel):
    """Definition of a single workflow step, as parsed from YAML.

    Attributes:
        id: Unique step identifier within the workflow. Used in template
            references: ``{{ steps.<id>.output }}``.
        kind: The type of step — determines which executor handles it.
        description: Human-readable description shown in ``workflow inspect``.
        capability: For ``capability`` steps — the registered capability name.
        prompt: For ``model`` steps — the prompt text (may contain templates).
        query: For ``memory_search`` steps — the search query (may contain templates).
        value: For ``set_var`` steps — the value to assign (may contain templates).
        inputs: For ``capability`` steps — key/value inputs (values may contain templates).
        on_failure: What to do if this step fails. ``"abort"`` (default) stops
            the workflow; ``"continue"`` records the failure and proceeds.
        output_key: Override the key name used to store this step's result
            in the workflow context. Defaults to the step ``id``.
    """

    id: str
    kind: WorkflowStepKind
    description: str = ""
    capability: str | None = None
    prompt: str | None = None
    query: str | None = None
    value: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    on_failure: Literal["abort", "continue"] = "abort"
    output_key: str | None = None

    @model_validator(mode="after")
    def _validate_step_fields(self) -> WorkflowStepDef:
        """Ensure required fields are present for each step kind."""
        if self.kind == WorkflowStepKind.CAPABILITY and not self.capability:
            raise ValueError(
                f"Step {self.id!r}: 'capability' is required for kind 'capability'"
            )
        if self.kind == WorkflowStepKind.MODEL and not self.prompt:
            raise ValueError(
                f"Step {self.id!r}: 'prompt' is required for kind 'model'"
            )
        return self

    @property
    def effective_output_key(self) -> str:
        """The context key under which this step's result is stored."""
        return self.output_key or self.id


# ---------------------------------------------------------------------------
# Workflow definition
# ---------------------------------------------------------------------------


class WorkflowInputDef(BaseModel):
    """Declaration of a single workflow input parameter.

    Attributes:
        name: Parameter name, referenced in templates as ``{{ inputs.<name> }}``.
        description: Human-readable hint for the CLI ``--input`` option.
        required: Whether the workflow refuses to run without this input.
        default: Default value when the input is not supplied.
    """

    name: str
    description: str = ""
    required: bool = False
    default: str | None = None


class WorkflowDef(BaseModel):
    """Complete parsed workflow definition.

    Loaded from a YAML file under ``~/.canopus/workflows/`` (or the examples
    directory during development).

    Attributes:
        name: Unique workflow identifier, matching the file stem.
        description: Short human-readable description.
        tags: Free-form labels for filtering/discovery.
        inputs: Declared input parameters.
        steps: Ordered list of step definitions.
        source_path: Absolute path to the YAML file that produced this definition.
    """

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    inputs: list[WorkflowInputDef] = Field(default_factory=list)
    steps: list[WorkflowStepDef] = Field(default_factory=list)
    source_path: str = ""

    @model_validator(mode="after")
    def _validate_step_ids(self) -> WorkflowDef:
        """Ensure all step IDs are unique within the workflow."""
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(
                    f"Workflow {self.name!r}: duplicate step id {step.id!r}"
                )
            seen.add(step.id)
        return self


# ---------------------------------------------------------------------------
# Execution result types
# ---------------------------------------------------------------------------


class StepStatus(StrEnum):
    """Outcome of a single step execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepResult(BaseModel):
    """Outcome of executing one workflow step.

    Attributes:
        step_id: The ``id`` of the step definition.
        kind: The step kind that produced this result.
        status: Whether the step completed, failed, or was skipped.
        output: The step's output value. Shape depends on the step kind:
            - ``capability``: the capability's ``data`` dict
            - ``model``: ``{"text": "<generated text>"}``
            - ``memory_search``: ``{"records": [...], "block": "<prompt block>"}``
            - ``output``: ``{"text": "<resolved text>"}``
            - ``set_var``: ``{"value": "<resolved value>"}``
        error: Error message when ``status == "failed"``.
        latency_ms: Wall-clock time for this step.
    """

    step_id: str
    kind: WorkflowStepKind
    status: StepStatus = StepStatus.COMPLETED
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float | None = None


class WorkflowStatus(StrEnum):
    """Overall outcome of a workflow run."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class WorkflowResult(BaseModel):
    """Complete outcome of a single workflow execution.

    Attributes:
        workflow_name: Name of the workflow that was executed.
        run_id: UUID for this specific run.
        status: Overall outcome.
        step_results: Results for each step in execution order.
        inputs: The resolved inputs the workflow was called with.
        final_output: The value of the last ``output`` step, if any.
        error: Top-level error message for catastrophic failures.
        started_at: UTC timestamp when execution began.
        completed_at: UTC timestamp when execution finished.
        latency_ms: Total wall-clock execution time.
    """

    workflow_name: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    step_results: list[StepResult] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    final_output: str | None = None
    error: str | None = None
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    completed_at: datetime.datetime | None = None
    latency_ms: float | None = None

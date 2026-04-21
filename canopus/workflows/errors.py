"""Exception hierarchy for the workflow subsystem.

All exceptions extend :class:`~canopus.core.errors.WorkflowError` and carry
structured fields so callers can react to specific failure modes without
parsing error strings.

Exception types:

- :class:`WorkflowNotFoundError`: No workflow with the given name was found.
- :class:`WorkflowLoadError`: A workflow YAML file could not be read or parsed.
- :class:`WorkflowValidationError`: A workflow definition is structurally invalid.
- :class:`WorkflowStepError`: A single step failed during execution.
- :class:`WorkflowTemplatingError`: A ``{{ ... }}`` expression could not be resolved.
"""

from __future__ import annotations

from canopus.core.errors import WorkflowError


class WorkflowNotFoundError(WorkflowError):
    """Raised when no workflow with the requested name exists.

    Args:
        name: The name that was looked up.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Workflow not found: {name!r}")


class WorkflowLoadError(WorkflowError):
    """Raised when a workflow file cannot be read or its YAML is malformed.

    Args:
        path: Path to the workflow file.
        reason: Human-readable explanation of the failure.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot load workflow from {path!r}: {reason}")


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow definition fails schema or semantic validation.

    Args:
        name: The workflow name (may be derived from the file stem).
        reason: Human-readable explanation of the validation failure.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Workflow {name!r} is invalid: {reason}")


class WorkflowStepError(WorkflowError):
    """Raised when a single step fails during execution.

    Args:
        step_id: The ``id`` of the step that failed.
        reason: Human-readable explanation of the failure.
    """

    def __init__(self, step_id: str, reason: str) -> None:
        self.step_id = step_id
        self.reason = reason
        super().__init__(f"Step {step_id!r} failed: {reason}")


class WorkflowTemplatingError(WorkflowError):
    """Raised when a ``{{ ... }}`` template expression cannot be resolved.

    Args:
        template: The full template expression that failed, e.g. ``{{ inputs.x }}``.
        reason: Human-readable explanation of why the expression failed.
    """

    def __init__(self, template: str, reason: str) -> None:
        self.template = template
        self.reason = reason
        super().__init__(f"Template error in {template!r}: {reason}")

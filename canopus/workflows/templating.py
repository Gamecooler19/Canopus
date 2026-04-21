"""Workflow template resolution.

Resolves ``{{ ... }}`` expressions in workflow step strings against the
current workflow context (inputs and prior step outputs).

Supported expressions:
- ``{{ inputs.<name> }}``        — a named workflow input value
- ``{{ steps.<step_id>.output }}`` — the ``output`` dict of a prior step
- ``{{ steps.<step_id>.text }}``   — shorthand for ``steps.<id>.output.text``
- ``{{ steps.<step_id>.<key> }}``  — any key inside the step's output dict

The resolver is intentionally deterministic and sandboxed. It does not
evaluate arbitrary Python — only pre-defined path lookups. This makes
templates safe to use with model-generated inputs as values.

Usage::

    ctx_data = {
        "inputs": {"path": "/home/user/notes"},
        "steps": {
            "list_dir": {"output": {"entries": [...], "text": "3 files"}},
        },
    }
    resolved = resolve("List files in {{ inputs.path }}", ctx_data)
    # → "List files in /home/user/notes"
"""

from __future__ import annotations

import re
from typing import Any

from canopus.workflows.errors import WorkflowTemplatingError

# Matches {{ ... }} with optional surrounding whitespace inside the braces.
_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def resolve(template: str, data: dict[str, Any]) -> str:
    """Resolve all ``{{ ... }}`` template expressions in *template*.

    Args:
        template: A string that may contain zero or more template expressions.
        data: The resolution data dictionary with ``"inputs"`` and ``"steps"``
            sub-dictionaries matching the context structure.

    Returns:
        The resolved string with all ``{{ ... }}`` replaced by their values.

    Raises:
        :class:`~canopus.workflows.errors.WorkflowTemplatingError`: If an
            expression cannot be resolved.
    """

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        return str(_resolve_expr(expr, data, original=match.group(0)))

    return _TEMPLATE_RE.sub(_replace, template)


def resolve_dict(
    mapping: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    """Resolve all string values in *mapping* that contain template expressions.

    Non-string values are passed through unchanged.

    Args:
        mapping: Key/value dict whose string values may contain templates.
        data: Resolution data (same shape as :func:`resolve`).

    Returns:
        A new dict with all string values resolved.
    """
    return {
        k: resolve(v, data) if isinstance(v, str) else v
        for k, v in mapping.items()
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_expr(expr: str, data: dict[str, Any], *, original: str) -> Any:
    """Resolve a single dot-path expression.

    Supported path roots:
    - ``inputs.<name>``
    - ``steps.<step_id>.output`` → the full output dict
    - ``steps.<step_id>.<key>``  → a key inside the step output dict
    - ``steps.<step_id>``        → the step output dict directly

    Args:
        expr: The expression text (without braces), e.g. ``"inputs.path"``.
        data: The context data dictionary.
        original: The original ``{{ ... }}`` expression for error messages.

    Returns:
        The resolved value.

    Raises:
        :class:`~canopus.workflows.errors.WorkflowTemplatingError`: On resolution failure.
    """
    parts = expr.split(".", maxsplit=2)

    if not parts:
        raise WorkflowTemplatingError(original, "empty expression")

    root = parts[0]

    # inputs.<name>
    if root == "inputs":
        if len(parts) < 2:
            raise WorkflowTemplatingError(
                original, "inputs reference requires a field name: 'inputs.<name>'"
            )
        field = parts[1]
        inputs: dict[str, Any] = data.get("inputs", {})
        if field not in inputs:
            raise WorkflowTemplatingError(
                original, f"input {field!r} is not defined"
            )
        return inputs[field]

    # steps.<step_id> or steps.<step_id>.<key>
    if root == "steps":
        if len(parts) < 2:
            raise WorkflowTemplatingError(
                original, "steps reference requires a step id: 'steps.<id>'"
            )
        step_id = parts[1]
        steps: dict[str, Any] = data.get("steps", {})
        if step_id not in steps:
            raise WorkflowTemplatingError(
                original,
                f"step {step_id!r} has not produced output yet "
                f"(available: {sorted(steps.keys())})",
            )
        step_output: dict[str, Any] = steps[step_id].get("output", {})

        if len(parts) == 2:
            # Return the entire output dict
            return step_output

        key = parts[2]
        if key == "output":
            return step_output
        # Look inside the output dict
        if key not in step_output:
            raise WorkflowTemplatingError(
                original,
                f"step {step_id!r} output has no key {key!r} "
                f"(available: {sorted(step_output.keys())})",
            )
        return step_output[key]

    raise WorkflowTemplatingError(
        original,
        f"unknown template root {root!r} — supported: 'inputs', 'steps'",
    )

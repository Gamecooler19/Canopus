"""Shared type models for the Canopus reasoning pipeline.

These types flow through the planner → executor → reflector stages and are
the primary data contracts between them. Keeping them in a single module
avoids circular imports and makes the pipeline easy to reason about.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


class IntentCategory(StrEnum):
    """High-level classification of user request intent.

    Attributes:
        CONVERSATIONAL: Open-ended chat or greeting — no specific action needed.
        INFORMATIONAL: Question or summarisation — requires knowledge retrieval.
        ACTION_ORIENTED: Task the assistant should *perform* — may require
            capabilities, permissions, or external tools.
    """

    CONVERSATIONAL = "conversational"
    INFORMATIONAL = "informational"
    ACTION_ORIENTED = "action_oriented"


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """A single step within an execution plan.

    Attributes:
        index: Zero-based position in the plan step list.
        description: Human-readable description of what this step does.
        capability_name: When set, the executor should invoke this registered
            capability instead of calling the model provider. The string must
            match a key in the capability registry.
        capability_inputs: Optional inputs to forward to the capability handler.
    """

    index: int
    description: str
    capability_name: str | None = None
    capability_inputs: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """Structured plan produced by the :class:`~canopus.reasoning.planner.Planner`.

    Attributes:
        intent: Classified intent category.
        intent_confidence: Confidence score in [0, 1] from the classifier.
        summary: Short human-readable plan summary for tracing/display.
        steps: Ordered list of execution steps.
        requires_capabilities: ``True`` when the plan requires registered
            capabilities beyond pure language generation.
        system_prompt_key: Key used by the prompt builder to select the
            appropriate system prompt variant.
    """

    intent: IntentCategory
    intent_confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    steps: list[PlanStep]
    requires_capabilities: bool = False
    system_prompt_key: str = "default"


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """Output of the :class:`~canopus.reasoning.executor.Executor` stage.

    Attributes:
        plan: The plan that was executed.
        raw_response: Verbatim text returned by the model provider, or a
            formatted string representation of a capability's output.
        provider_name: Name of the provider that generated the response.
        model_name: Specific model used (``"capability"`` when a capability
            handled the request instead of a model).
        latency_ms: End-to-end generation latency reported by the provider.
        prompt_tokens: Tokens consumed by the prompt, if available.
        completion_tokens: Tokens generated, if available.
        capability_name: When the response came from a capability rather than
            a model, this holds the capability's registered name.
    """

    plan: Plan
    raw_response: str
    provider_name: str
    model_name: str
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    capability_name: str | None = None


# ---------------------------------------------------------------------------
# Reflection result
# ---------------------------------------------------------------------------


class ReflectionOutcome(StrEnum):
    """Outcome determined by the :class:`~canopus.reasoning.reflector.Reflector`.

    Attributes:
        VALID: Response is acceptable and ready for the user.
        NEEDS_RETRY: Response is deficient but a retry is warranted.
        FAILED: Response is unusable and no retry will be attempted.
    """

    VALID = "valid"
    NEEDS_RETRY = "needs_retry"
    FAILED = "failed"


class ReflectionResult(BaseModel):
    """Final output of the reasoning pipeline, ready for CLI rendering.

    Attributes:
        execution: The :class:`ExecutionResult` that was evaluated.
        outcome: Whether the response is valid, needs retry, or failed.
        issues: List of problems detected (empty when outcome is VALID).
        final_response: The response string to present to the user. This is
            the raw response when valid, or a fallback message otherwise.
        retry_count: How many retries were performed before reaching this result.
    """

    execution: ExecutionResult
    outcome: ReflectionOutcome
    issues: list[str]
    final_response: str
    retry_count: int = 0

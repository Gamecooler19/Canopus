"""Plan executor — invokes a model provider against a planner-produced plan.

The :class:`Executor` is responsible for:

1. Building the model request from the plan and the original user request.
2. Invoking the selected provider.
3. Wrapping the raw provider response in a typed :class:`~canopus.reasoning.types.ExecutionResult`.

The executor is deliberately thin: it does not retry, it does not validate, and
it does not interpret the response. Those responsibilities belong to the
:class:`~canopus.reasoning.reflector.Reflector`.
"""

from __future__ import annotations

from canopus.models.base import ModelProvider, ModelRequest
from canopus.reasoning.prompts.templates import build_prompt
from canopus.reasoning.types import ExecutionResult, Plan


class Executor:
    """Runs a :class:`~canopus.reasoning.types.Plan` through a model provider.

    Args:
        provider: The :class:`~canopus.models.base.ModelProvider` to use for
            generation. Injected externally so the executor itself remains
            provider-agnostic.

    Usage::

        executor = Executor(provider)
        result = executor.execute(plan, original_request="hello")
    """

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    def execute(self, plan: Plan, original_request: str) -> ExecutionResult:
        """Execute *plan* by invoking the model provider.

        Builds a :class:`~canopus.models.base.ModelRequest` from the plan
        and original request, calls the provider, and returns a structured
        :class:`~canopus.reasoning.types.ExecutionResult`.

        Args:
            plan: The planner-produced execution plan.
            original_request: The verbatim user input, forwarded to the
                prompt builder for context.

        Returns:
            An :class:`~canopus.reasoning.types.ExecutionResult` containing
            the provider's raw response and metadata.
        """
        system_prompt, user_prompt = build_prompt(plan, original_request)

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

"""EchoProvider — deterministic local provider for development and testing.

:class:`EchoProvider` satisfies the :class:`~canopus.models.base.ModelProvider`
Protocol without calling any external service. It is used as the automatic
fallback when no real provider is configured in the active profile.

This makes the full pipeline (planner → executor → reflector) runnable and
testable from day one without an LLM backend.
"""

from __future__ import annotations

import time

from canopus.models.base import ModelRequest, ModelResponse

_PROVIDER_NAME = "echo"
_MODEL_NAME = "echo-1.0"


class EchoProvider:
    """Deterministic model provider for development and offline use.

    Generates a structured response that demonstrates the pipeline is working
    without making any external calls.  Every invocation is instant and
    reproducible, which makes this provider valuable for unit tests.

    Attributes:
        provider_name: Always ``"echo"``.
        model_name: Always ``"echo-1.0"``.
    """

    @property
    def provider_name(self) -> str:
        return _PROVIDER_NAME

    @property
    def model_name(self) -> str:
        return _MODEL_NAME

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a structured echo response.

        The response body acknowledges the request and indicates that a real
        provider must be configured for AI-generated answers.

        Args:
            request: The model request to process.

        Returns:
            A :class:`~canopus.models.base.ModelResponse` with deterministic
            content and timing metadata.
        """
        start = time.monotonic()
        text = self._build_response(request)
        latency_ms = (time.monotonic() - start) * 1_000

        return ModelResponse(
            text=text,
            provider_name=_PROVIDER_NAME,
            model_name=_MODEL_NAME,
            prompt_tokens=len(request.prompt.split()),
            completion_tokens=len(text.split()),
            latency_ms=latency_ms,
            finish_reason="stop",
        )

    def is_available(self) -> bool:
        """Always available — no external dependencies."""
        return True

    @staticmethod
    def _build_response(request: ModelRequest) -> str:
        """Produce a coherent demo response for the given request."""
        prompt_preview = (
            request.prompt[:120] + "…"
            if len(request.prompt) > 120
            else request.prompt
        )
        lines = [
            "Running in echo/demo mode — no model provider is configured.",
            "",
            f'Your request: "{prompt_preview}"',
            "",
            "To enable real AI responses, configure a provider in your active profile:",
            "  • Local:  set local_provider = \"ollama\" and local_model in your profile",
            "  • Remote: set remote_provider = \"openai\" and a remote_model",
            "",
            "Run `canopus profile show` to inspect your current configuration.",
        ]
        if request.system_prompt:
            lines += [
                "",
                f"[System context received: {len(request.system_prompt)} chars]",
            ]
        return "\n".join(lines)

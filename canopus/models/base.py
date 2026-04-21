"""Model provider abstraction: request/response types and the ModelProvider Protocol.

All model providers — whether local (Ollama, llama.cpp) or remote (OpenAI,
Anthropic) — must implement :class:`ModelProvider`. Keeping this as a
``Protocol`` rather than a base class means adapters can live outside this
package without inheriting from it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ModelRequest(BaseModel):
    """Structured input sent to a model provider.

    Args:
        prompt: The main user-facing prompt text.
        system_prompt: Optional system/instruction context prepended to the
            conversation. Providers that do not support system prompts should
            incorporate it into the main prompt.
        max_tokens: Maximum number of tokens the provider may generate.
        temperature: Sampling temperature — higher values increase randomness.
    """

    prompt: str
    system_prompt: str | None = None
    max_tokens: int = 1024
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ModelResponse(BaseModel):
    """Structured output returned by a model provider.

    Attributes:
        text: The generated text content.
        provider_name: Stable identifier for the provider (e.g. ``"echo"``,
            ``"ollama"``, ``"openai"``).
        model_name: Specific model used (e.g. ``"llama3.2:3b"``).
        prompt_tokens: Number of tokens in the prompt, if reported.
        completion_tokens: Number of tokens generated, if reported.
        latency_ms: Wall-clock generation time in milliseconds.
        finish_reason: Termination reason from the provider
            (``"stop"``, ``"length"``, …).
    """

    text: str
    provider_name: str
    model_name: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    finish_reason: str | None = None


# ---------------------------------------------------------------------------
# Provider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelProvider(Protocol):
    """Structural interface for all model providers.

    Any class that implements these four members satisfies the protocol —
    no explicit inheritance required.
    """

    @property
    def provider_name(self) -> str:
        """Stable identifier for the provider (e.g. ``"echo"``, ``"ollama"``)."""
        ...

    @property
    def model_name(self) -> str:
        """Active model identifier within this provider."""
        ...

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Generate a completion for the given request.

        Args:
            request: Structured prompt plus generation parameters.

        Returns:
            A :class:`ModelResponse` containing the generated text and
            provider metadata.
        """
        ...

    def is_available(self) -> bool:
        """Return ``True`` if this provider can currently accept requests.

        Implementations should perform a lightweight liveness check (e.g. a
        connectivity ping for remote providers). This must not raise.
        """
        ...

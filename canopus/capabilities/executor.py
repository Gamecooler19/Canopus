"""Capability executor — the deterministic dispatch layer for capability calls.

:class:`CapabilityExecutor` is the single execution path for all capabilities,
regardless of whether they originate from native code, a legacy plugin, or an
MCP adapter. It:

1. Looks up the spec and handler in the registry.
2. Invokes the handler with validated input.
3. Records timing and outcome.
4. Returns a typed :class:`~canopus.capabilities.specs.CapabilityResult`.

No reasoning logic lives here — the executor is a pure dispatcher.
"""

from __future__ import annotations

import time
from typing import Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.registry import CapabilityRegistry
from canopus.capabilities.specs import CapabilityResult
from canopus.core.errors import CapabilityError


class CapabilityExecutor:
    """Dispatches capability invocations through the registry.

    Args:
        registry: The :class:`~canopus.capabilities.registry.CapabilityRegistry`
            to look up handlers from.

    Usage::

        executor = CapabilityExecutor(registry)
        result = executor.invoke("system.now", {}, ctx)
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def invoke(
        self,
        name: str,
        inputs: dict[str, Any],
        ctx: CapabilityContext,
    ) -> CapabilityResult:
        """Invoke a capability by name.

        Args:
            name: Registered capability name, e.g. ``"system.now"``.
            inputs: Raw input dict, forwarded to the handler.
            ctx: Runtime context including trace writer and profile.

        Returns:
            A :class:`~canopus.capabilities.specs.CapabilityResult` describing
            the outcome regardless of success or failure.
        """
        spec = self._registry.get(name)  # raises CapabilityError if missing
        handler = self._registry.get_handler(name)

        # Emit a pre-execution trace event
        if ctx.writer:
            ctx.writer.trace.add_event(
                "capability.invoked",
                {
                    "capability": name,
                    "transport": spec.transport,
                    "side_effect_level": spec.side_effect_level,
                    # Log only keys, never values (values may contain sensitive data)
                    "input_keys": sorted(inputs.keys()),
                },
            )

        start = time.monotonic()
        try:
            output: dict[str, Any] = handler(inputs, ctx)
            latency_ms = (time.monotonic() - start) * 1_000

            if ctx.writer:
                ctx.writer.trace.add_event(
                    "capability.succeeded",
                    {"capability": name, "latency_ms": latency_ms},
                )

            return CapabilityResult(
                capability_name=name,
                success=True,
                data=output,
                latency_ms=latency_ms,
            )

        except CapabilityError:
            raise  # let the caller see registry/contract errors directly
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1_000
            error_msg = str(exc)

            if ctx.writer:
                ctx.writer.trace.add_event(
                    "capability.failed",
                    {"capability": name, "error": error_msg, "latency_ms": latency_ms},
                )

            return CapabilityResult(
                capability_name=name,
                success=False,
                error=error_msg,
                latency_ms=latency_ms,
            )

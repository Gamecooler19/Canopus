"""Capability specification models.

A :class:`CapabilitySpec` is the static metadata contract that every
capability — native, legacy plugin, or MCP — must provide. The rest of
the system (planner, executor, registry, policy layer) operates on specs
rather than on implementation objects directly.

:class:`CapabilityResult` is the uniform output container returned by any
capability execution, regardless of transport.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from canopus.security.permissions import ConfirmationPolicy, Permission, SideEffectLevel


class CapabilitySpec(BaseModel):
    """Static metadata for a single capability.

    This is the normalized descriptor that all capability sources
    (``native``, ``legacy_plugin``, ``mcp``) expose to the rest of the
    system. The planner uses this for discovery; the policy layer uses it
    for permission checks; the CLI uses it for display.

    Attributes:
        name: Dot-namespaced unique identifier, e.g. ``"system.now"``.
        description: Short human-readable description of what this capability does.
        tags: Free-form category labels used for search and filtering.
        permissions: Set of :class:`~canopus.security.permissions.Permission`
            tokens required for execution.
        side_effect_level: How disruptive execution is to external state.
        confirmation_policy: When human confirmation must be obtained.
        transport: Where this capability is implemented.
        examples: Optional list of example invocation phrases for the planner.
    """

    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    permissions: list[Permission] = Field(default_factory=list)
    side_effect_level: SideEffectLevel = SideEffectLevel.NONE
    confirmation_policy: ConfirmationPolicy = ConfirmationPolicy.NEVER
    transport: Literal["native", "legacy_plugin", "mcp"] = "native"
    examples: list[str] = Field(default_factory=list)


class CapabilityResult(BaseModel):
    """Uniform output from any capability execution.

    Attributes:
        capability_name: The :attr:`CapabilitySpec.name` that produced this result.
        success: Whether execution succeeded.
        data: Structured output data. Shape depends on the capability.
        error: Error message when ``success`` is ``False``.
        latency_ms: Execution wall time in milliseconds.
    """

    capability_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float | None = None

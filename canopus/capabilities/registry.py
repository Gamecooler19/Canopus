"""Capability registry — the normalized catalog of all available capabilities.

The :class:`CapabilityRegistry` stores :class:`~canopus.capabilities.specs.CapabilitySpec`
objects and callable implementations side by side. It is transport-agnostic:
native code, legacy plugins, and MCP adapters all register through the same
interface so the rest of the system never needs to know the origin.

The global singleton :data:`registry` is created here and populated by
``canopus/capabilities/native/`` modules at import time. CLI commands and
the reasoning pipeline import this singleton directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from canopus.capabilities.specs import CapabilitySpec
from canopus.core.errors import CapabilityError

# Type alias for the raw callable an implementation provides
CapabilityHandler = Callable[..., Any]


class CapabilityRegistry:
    """Thread-safe, in-process registry for all capabilities.

    Each entry is a (:class:`CapabilitySpec`, callable) pair. The callable
    is the implementation that the :class:`~canopus.capabilities.executor.CapabilityExecutor`
    will invoke.

    Usage::

        registry = CapabilityRegistry()
        registry.register(spec, handler)

        spec = registry.get("system.now")
        all_specs = registry.list_all()
    """

    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}
        self._handlers: dict[str, CapabilityHandler] = {}

    def register(
        self,
        spec: CapabilitySpec,
        handler: CapabilityHandler,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register a capability.

        Args:
            spec: Metadata describing the capability.
            handler: Callable that implements the capability. It must accept
                a single ``dict[str, Any]`` argument (the input payload) and
                return a ``dict[str, Any]`` result.
            overwrite: When ``True``, silently replace an existing registration
                with the same name. When ``False`` (default), raise
                :class:`~canopus.core.errors.CapabilityError` on collision.

        Raises:
            :class:`~canopus.core.errors.CapabilityError`: If the name is
                already registered and *overwrite* is ``False``.
        """
        if spec.name in self._specs and not overwrite:
            raise CapabilityError(
                f"Capability {spec.name!r} is already registered. "
                "Pass overwrite=True to replace it."
            )
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> CapabilitySpec:
        """Return the spec for a registered capability.

        Args:
            name: Dot-namespaced capability name, e.g. ``"system.now"``.

        Returns:
            The :class:`~canopus.capabilities.specs.CapabilitySpec`.

        Raises:
            :class:`~canopus.core.errors.CapabilityError`: If *name* is not
                registered.
        """
        if name not in self._specs:
            raise CapabilityError(f"Capability {name!r} is not registered.")
        return self._specs[name]

    def get_handler(self, name: str) -> CapabilityHandler:
        """Return the implementation callable for a registered capability.

        Raises:
            :class:`~canopus.core.errors.CapabilityError`: If *name* is not
                registered.
        """
        if name not in self._handlers:
            raise CapabilityError(f"Capability {name!r} is not registered.")
        return self._handlers[name]

    def list_all(self) -> list[CapabilitySpec]:
        """Return all registered capability specs, sorted by name."""
        return sorted(self._specs.values(), key=lambda s: s.name)

    def contains(self, name: str) -> bool:
        """Return ``True`` if *name* is registered."""
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------

#: The application-wide capability registry. Import and use this directly.
registry: CapabilityRegistry = CapabilityRegistry()

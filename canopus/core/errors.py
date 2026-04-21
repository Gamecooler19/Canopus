"""Exception hierarchy for all Canopus subsystems.

Each subsystem raises its own typed exception so callers can handle failures
at the appropriate level of granularity. All exceptions inherit from
:class:`CanopusError` so callers can catch the whole family with a single
``except CanopusError`` clause if needed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class CanopusError(Exception):
    """Base exception for all Canopus errors."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigError(CanopusError):
    """Raised when configuration is invalid or cannot be loaded."""


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class ProfileError(CanopusError):
    """Raised when a profile fails validation or cannot be loaded."""


class ProfileNotFoundError(ProfileError):
    """Raised when a named profile does not exist in any source."""

    def __init__(self, name: str) -> None:
        self.profile_name = name
        super().__init__(f"Profile not found: {name!r}")


# ---------------------------------------------------------------------------
# Session runtime
# ---------------------------------------------------------------------------


class CanopusRuntimeError(CanopusError):
    """Raised when the session runtime encounters an unrecoverable error."""


class SessionError(CanopusRuntimeError):
    """Raised when session creation or lifecycle management fails."""


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


class TracingError(CanopusError):
    """Raised when the trace subsystem fails to write or read trace data."""


# ---------------------------------------------------------------------------
# Capabilities and plugins
# ---------------------------------------------------------------------------


class CapabilityError(CanopusError):
    """Raised when capability registration or invocation fails."""


class PluginError(CanopusError):
    """Raised when a plugin cannot be discovered, loaded, or executed."""


class McpError(CanopusError):
    """Raised when an MCP server or tool operation fails."""


# ---------------------------------------------------------------------------
# Policy and safety
# ---------------------------------------------------------------------------


class PolicyError(CanopusError):
    """Raised when an action is denied by the active policy layer."""


class PermissionDeniedError(PolicyError):
    """Raised when a required permission has not been granted."""

    def __init__(self, permission: str, capability: str | None = None) -> None:
        self.permission = permission
        self.capability = capability
        msg = f"Permission denied: {permission!r}"
        if capability:
            msg += f" (required by capability {capability!r})"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class MemoryError(CanopusError):
    """Raised when the memory subsystem fails to read, write, or query records."""


class MemoryStoreError(MemoryError):
    """Raised when the memory store cannot initialize or perform I/O."""


class MemoryNotFoundError(MemoryError):
    """Raised when a memory record with the given ID does not exist."""

    def __init__(self, memory_id: str) -> None:
        self.memory_id = memory_id
        super().__init__(f"Memory record not found: {memory_id!r}")


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


class WorkflowError(CanopusError):
    """Raised when workflow parsing or execution fails."""

"""Typed data models for the MCP plugin subsystem.

These types describe the internal representation of MCP servers and tools
as seen by the manager, adapter, and CLI. MCP server *configuration* lives
in :class:`~canopus.core.config.McpServerConfig`.

Key types:
- :class:`McpToolSpec` — normalized tool definition returned by a transport
- :class:`McpServerStatus` — lifecycle state of a configured MCP server
- :class:`McpServerRecord` — full snapshot of a server after initialization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


@dataclass
class McpToolSpec:
    """A single tool as declared by an MCP server.

    This is the normalized internal representation produced by a transport's
    ``list_tools()`` call. It mirrors the contract of
    :class:`~canopus.plugins.legacy.models.PluginCapabilityDef` so both
    subsystems can feed into the same adapter/registry pipeline.

    Attributes:
        name: Tool name without server prefix, e.g. ``"echo"``. The adapter
            constructs the full capability name as ``"<server>.<tool>"``.
        description: Short human-readable description of what the tool does.
        tags: Free-form category labels.
        permissions: Permission token strings (e.g. ``"fs.read"``).
        side_effect_level: One of ``"none"``, ``"low"``, ``"medium"``, ``"high"``.
        confirmation_policy: One of ``"never"``, ``"smart"``, ``"always"``.
        examples: Example invocation phrases for the planner.
    """

    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    side_effect_level: str = "none"
    confirmation_policy: str = "never"
    examples: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Server status
# ---------------------------------------------------------------------------


class McpServerStatus(StrEnum):
    """Lifecycle state of a configured MCP server after initialization.

    Attributes:
        CONNECTED: Server initialized successfully and all tools registered.
        PARTIAL: Server connected but some tools failed to normalize/register.
        FAILED: Server could not be connected or all tools failed.
        DISABLED: Server is present in config but ``enabled=False``.
    """

    CONNECTED = "connected"
    PARTIAL = "partial"
    FAILED = "failed"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Server record
# ---------------------------------------------------------------------------


class McpServerRecord(BaseModel):
    """Full snapshot of an MCP server after the manager has processed it.

    Stored in :class:`~canopus.plugins.mcp.manager.McpManager` and exposed
    to CLI commands. Contains enough information to diagnose failures without
    re-running initialization.

    Attributes:
        name: Server identifier (from config).
        transport: Transport type string (from config).
        description: Human-readable description (from config).
        enabled: Whether the server was enabled in config.
        status: Initialization outcome.
        tool_names: Fully-qualified capability names registered for this
            server, e.g. ``["mock.echo", "mock.word_count"]``.
        error: Top-level error message when status is ``FAILED``.
        warnings: Per-tool warnings when status is ``PARTIAL``.
    """

    name: str
    transport: str
    description: str = ""
    enabled: bool = True
    status: McpServerStatus = McpServerStatus.DISABLED
    tool_names: list[str] = Field(default_factory=list)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)

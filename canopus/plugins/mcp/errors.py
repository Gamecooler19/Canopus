"""Exception hierarchy for the MCP plugin subsystem.

All MCP errors inherit from :class:`~canopus.core.errors.McpError` so callers
can catch the whole family with a single clause, while specific subclasses
allow fine-grained handling where useful.
"""

from __future__ import annotations

from canopus.core.errors import McpError


class McpConnectionError(McpError):
    """Raised when an MCP server cannot be connected to or initialized.

    This covers transport-level failures: subprocess launch failures, protocol
    handshake errors, or transport-not-implemented conditions.
    """

    def __init__(self, server_name: str, reason: str) -> None:
        self.server_name = server_name
        self.reason = reason
        super().__init__(f"MCP server {server_name!r} connection failed: {reason}")


class McpToolCallError(McpError):
    """Raised when an MCP tool invocation fails at the transport level.

    This is distinct from a tool returning an error result — it indicates
    a communication failure, unexpected response format, or unknown tool name.
    """

    def __init__(self, server_name: str, tool_name: str, reason: str) -> None:
        self.server_name = server_name
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(
            f"MCP tool {tool_name!r} on server {server_name!r} failed: {reason}"
        )


class McpToolAdapterError(McpError):
    """Raised when an MCP tool definition cannot be normalized into a capability.

    Examples:
    - Unknown permission string declared in tool metadata
    - Invalid side-effect level or confirmation policy
    """

    def __init__(self, server_name: str, tool_name: str | None, reason: str) -> None:
        self.server_name = server_name
        self.tool_name = tool_name
        self.reason = reason
        label = tool_name or "<unnamed>"
        super().__init__(
            f"MCP server {server_name!r} tool {label!r} cannot be adapted: {reason}"
        )

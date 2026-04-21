"""MCP transport protocol and type definitions.

A transport is the communication channel between Canopus and an MCP server.
All transports implement the same :class:`McpTransport` protocol, allowing the
:class:`~canopus.plugins.mcp.client.McpClient` and
:class:`~canopus.plugins.mcp.manager.McpManager` to be transport-agnostic.

Currently implemented transports:
- :mod:`~canopus.plugins.mcp.transports.mock` — in-process mock (development/testing)
- :mod:`~canopus.plugins.mcp.transports.stdio` — stub for future external processes

Adding a new transport is as simple as creating a class that satisfies the
:class:`McpTransport` protocol and adding its constructor call in
:func:`~canopus.plugins.mcp.manager.create_transport`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from canopus.plugins.mcp.models import McpToolSpec


@runtime_checkable
class McpTransport(Protocol):
    """Protocol that every MCP transport must satisfy.

    The manager creates one transport per server and passes it to an
    :class:`~canopus.plugins.mcp.client.McpClient`. The client delegates all
    communication to the transport so the rest of the system never sees
    transport-specific details.
    """

    def list_tools(self) -> list[McpToolSpec]:
        """Return all tools exposed by this MCP server.

        Raises:
            :class:`~canopus.plugins.mcp.errors.McpConnectionError`: If the
                server cannot be reached or the tool list cannot be retrieved.
        """
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a named tool and return its result.

        Args:
            name: Tool name without server prefix (e.g. ``"echo"``).
            arguments: Raw input payload forwarded to the tool implementation.

        Returns:
            Structured result dict. Shape is tool-specific.

        Raises:
            :class:`~canopus.plugins.mcp.errors.McpToolCallError`: If the
                tool cannot be called or returns an error.
        """
        ...

    def close(self) -> None:
        """Release any resources held by this transport.

        Should be idempotent — calling ``close()`` multiple times must not
        raise an error.
        """
        ...

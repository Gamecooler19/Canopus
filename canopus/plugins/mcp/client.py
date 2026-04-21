"""MCP client — thin wrapper around a transport with error normalization.

:class:`McpClient` is the stable interface between the
:class:`~canopus.plugins.mcp.manager.McpManager` and the capability adapter.
It holds the transport, applies the server name prefix to error messages, and
provides the two operations the system needs: ``list_tools`` and ``call_tool``.

The adapter captures a client reference in its handler closure so that MCP
tool calls follow the same code path as native and legacy-plugin calls:

    registry.get_handler("mock.echo")(inputs, ctx)
        → client.call_tool("echo", inputs)
            → transport.call_tool("echo", inputs)
"""

from __future__ import annotations

from typing import Any

from canopus.plugins.mcp.errors import McpConnectionError, McpToolCallError
from canopus.plugins.mcp.models import McpToolSpec
from canopus.plugins.mcp.transports import McpTransport


class McpClient:
    """Wraps a transport and exposes a clean interface for the manager and adapter.

    Args:
        server_name: Identifier of the MCP server (used in error messages and
            as the capability name prefix).
        transport: Transport implementation to delegate to.
    """

    def __init__(self, server_name: str, transport: McpTransport) -> None:
        self._server_name = server_name
        self._transport = transport

    @property
    def server_name(self) -> str:
        """The name of the MCP server this client connects to."""
        return self._server_name

    def list_tools(self) -> list[McpToolSpec]:
        """Return all tools exposed by the connected server.

        Returns:
            List of :class:`~canopus.plugins.mcp.models.McpToolSpec` objects.

        Raises:
            :class:`~canopus.plugins.mcp.errors.McpConnectionError`: If the
                transport cannot retrieve the tool list.
        """
        try:
            return self._transport.list_tools()
        except McpConnectionError:
            raise
        except Exception as exc:
            raise McpConnectionError(
                self._server_name,
                f"list_tools() failed: {exc}",
            ) from exc

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a named tool and return its result.

        Args:
            name: Tool name without server prefix (e.g. ``"echo"``).
            arguments: Raw input dict forwarded to the tool.

        Returns:
            Structured result dict (tool-specific shape).

        Raises:
            :class:`~canopus.plugins.mcp.errors.McpToolCallError`: If the
                tool cannot be invoked or the transport signals an error.
        """
        try:
            return self._transport.call_tool(name, arguments)
        except McpToolCallError:
            raise
        except Exception as exc:
            raise McpToolCallError(
                self._server_name, name, str(exc)
            ) from exc

    def close(self) -> None:
        """Release transport resources. Safe to call multiple times."""
        try:
            self._transport.close()
        except Exception:
            # Suppress errors on close — the process may already be gone.
            pass

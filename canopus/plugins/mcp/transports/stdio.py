"""Stdio-based MCP transport — stub for future external MCP process support.

:class:`StdioMcpTransport` is a placeholder that satisfies the
:class:`~canopus.plugins.mcp.transports.McpTransport` protocol but raises
:class:`~canopus.plugins.mcp.errors.McpConnectionError` on every call until
the transport is implemented.

This stub exists to make the architecture forward-compatible: the manager,
adapter, and CLI code already treat it as a real transport. Once the stdio
protocol implementation is added, only this module needs to change.

How to implement this in a future phase:
1. Launch ``self._command`` as a subprocess with stdin/stdout pipes.
2. Send JSON-RPC ``initialize`` and ``tools/list`` requests over stdin.
3. Parse the JSON-RPC responses to populate the tool list.
4. For ``call_tool``, send a ``tools/call`` JSON-RPC request and read the result.
5. On ``close()``, send a ``shutdown`` notification and terminate the process.

Refer to the MCP specification for the precise wire format.
"""

from __future__ import annotations

from typing import Any

from canopus.plugins.mcp.errors import McpConnectionError
from canopus.plugins.mcp.models import McpToolSpec

_NOT_IMPLEMENTED_REASON = (
    "Stdio MCP transport is not yet implemented. "
    "Use transport=\"mock\" for local development or contribute the stdio "
    "implementation to canopus/plugins/mcp/transports/stdio.py."
)


class StdioMcpTransport:
    """Placeholder stdio transport for external MCP server processes.

    All methods raise :class:`~canopus.plugins.mcp.errors.McpConnectionError`
    until this transport is implemented.

    Args:
        server_name: Name of the server being connected to (used in errors).
        command: Path to the MCP server executable.
        args: Additional CLI arguments for the server process.
        env: Extra environment variables to pass to the process.
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._server_name = server_name
        self._command = command
        self._args = args or []
        self._env = env or {}

    def list_tools(self) -> list[McpToolSpec]:
        raise McpConnectionError(self._server_name, _NOT_IMPLEMENTED_REASON)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise McpConnectionError(self._server_name, _NOT_IMPLEMENTED_REASON)

    def close(self) -> None:
        # Nothing to clean up for an unstarted process.
        pass

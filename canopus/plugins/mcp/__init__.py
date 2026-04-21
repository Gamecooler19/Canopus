"""MCP plugin subsystem for Canopus.

This package implements MCP (Model Context Protocol) server support as a
first-class capability source alongside native capabilities and legacy plugins.
MCP tools are normalized into the central capability registry so the rest of
the system (planner, executor, CLI) never needs to care about their origin.

Public API
----------
The most commonly used symbols are re-exported here for convenience:

- :class:`McpManager` — server lifecycle and capability registration
- :func:`initialize` — create and populate the global manager at startup
- :func:`get_manager` — retrieve the current global manager
- :func:`reset_for_testing` — reset the singleton for test isolation
- :class:`McpServerRecord` — per-server status snapshot
- :class:`McpServerStatus` — server lifecycle states
- :class:`McpToolSpec` — normalized tool definition from a transport

Transport strategy
------------------
All communication with MCP servers goes through the
:class:`~canopus.plugins.mcp.transports.McpTransport` protocol.
Currently supported transports:

- ``"mock"`` — in-process mock for development and testing
- ``"stdio"`` — stub; planned for future external MCP process support

See :mod:`canopus.plugins.mcp.transports` for the protocol definition and
:mod:`canopus.plugins.mcp.manager.create_transport` for the factory.
"""

from __future__ import annotations

from canopus.plugins.mcp.manager import (
    McpManager,
    get_manager,
    initialize,
    reset_for_testing,
)
from canopus.plugins.mcp.models import McpServerRecord, McpServerStatus, McpToolSpec

__all__ = [
    "McpManager",
    "McpServerRecord",
    "McpServerStatus",
    "McpToolSpec",
    "get_manager",
    "initialize",
    "reset_for_testing",
]

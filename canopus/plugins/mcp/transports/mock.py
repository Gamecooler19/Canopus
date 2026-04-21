"""In-process mock MCP transport for development and testing.

:class:`MockMcpTransport` exposes three deterministic, side-effect-free tools
without starting any external process. It is the reference implementation of
the :class:`~canopus.plugins.mcp.transports.McpTransport` protocol and the
default path for ``transport = "mock"`` server configs.

Exposed tools:
- ``echo``       — return the input text unchanged
- ``word_count`` — count words, characters, and lines in text
- ``now``        — return the current UTC timestamp
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from canopus.plugins.mcp.errors import McpToolCallError
from canopus.plugins.mcp.models import McpToolSpec

# ---------------------------------------------------------------------------
# Static tool registry for the mock server
# ---------------------------------------------------------------------------

_MOCK_TOOLS: list[McpToolSpec] = [
    McpToolSpec(
        name="echo",
        description="Return the input text unchanged.",
        tags=["text", "utility", "mock"],
        examples=["echo this back", "repeat after me"],
    ),
    McpToolSpec(
        name="word_count",
        description="Count words, characters, and lines in the provided text.",
        tags=["text", "analysis", "mock"],
        examples=["how many words are in this?", "word count for my text"],
    ),
    McpToolSpec(
        name="now",
        description="Return the current UTC timestamp as an ISO-8601 string.",
        tags=["time", "utility", "mock"],
        examples=["what time is it?", "current timestamp"],
    ),
]


# ---------------------------------------------------------------------------
# Transport implementation
# ---------------------------------------------------------------------------


class MockMcpTransport:
    """In-process MCP transport with three deterministic tools.

    This transport never starts an external process. All tool calls execute
    directly in Python, making it suitable for unit tests, local development,
    and integration demos.

    Usage::

        transport = MockMcpTransport()
        tools = transport.list_tools()
        result = transport.call_tool("echo", {"text": "hello"})
    """

    # The mock server identifies itself with this name in error messages.
    SERVER_NAME = "mock"

    def list_tools(self) -> list[McpToolSpec]:
        """Return the three built-in mock tools."""
        return list(_MOCK_TOOLS)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to the named tool handler.

        Args:
            name: One of ``"echo"``, ``"word_count"``, or ``"now"``.
            arguments: Input payload (tool-specific).

        Returns:
            Dict result from the tool.

        Raises:
            :class:`~canopus.plugins.mcp.errors.McpToolCallError`: If *name*
                is not a known mock tool.
        """
        if name == "echo":
            return self._echo(arguments)
        if name == "word_count":
            return self._word_count(arguments)
        if name == "now":
            return self._now()
        raise McpToolCallError(
            self.SERVER_NAME, name, f"Unknown mock tool: {name!r}"
        )

    def close(self) -> None:
        """No-op — mock transport holds no external resources."""

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _echo(self, args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text", ""))
        return {"text": text}

    def _word_count(self, args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text", ""))
        lines = text.splitlines()
        words = text.split() if text.strip() else []
        return {
            "words": len(words),
            "characters": len(text),
            "lines": len(lines),
            "non_empty_lines": sum(1 for line in lines if line.strip()),
        }

    def _now(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "utc_iso": now.isoformat(),
            "unix_timestamp": now.timestamp(),
        }

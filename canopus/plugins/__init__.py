"""canopus.plugins — extensibility layer for Canopus.

Implements two complementary capability sources:

- **Legacy plugins**: single Python files dropped into ``~/.canopus/plugins/``.
  See :mod:`canopus.plugins.legacy`.

- **MCP servers**: MCP-protocol servers configured in ``config.toml``.
  See :mod:`canopus.plugins.mcp`.

Both sources normalize their tools/capabilities into the central
:class:`~canopus.capabilities.registry.CapabilityRegistry`.
"""

from canopus.plugins.legacy import (
    PluginManager,
    get_manager,
    initialize,
)
from canopus.plugins.mcp import (
    McpManager,
    McpServerRecord,
    McpServerStatus,
)
from canopus.plugins.mcp import (
    get_manager as get_mcp_manager,
)
from canopus.plugins.mcp import (
    initialize as initialize_mcp,
)

__all__ = [
    # Legacy
    "PluginManager",
    "get_manager",
    "initialize",
    # MCP
    "McpManager",
    "McpServerRecord",
    "McpServerStatus",
    "get_mcp_manager",
    "initialize_mcp",
]

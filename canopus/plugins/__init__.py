"""canopus.plugins — extensibility layer for Canopus.

Currently implements the legacy file-based plugin subsystem.
Future phases will add MCP adapter support here.
"""

from canopus.plugins.legacy import (
    PluginManager,
    get_manager,
    initialize,
)

__all__ = ["PluginManager", "get_manager", "initialize"]

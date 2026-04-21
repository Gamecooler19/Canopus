"""canopus.plugins.legacy — the legacy file-based plugin subsystem.

Drop a ``.py`` file into ``~/.canopus/plugins/`` and Canopus will discover,
validate, load it, and register its capabilities into the central registry.

See ``docs/plugin-contract.md`` for the full plugin authoring contract.
"""

from canopus.plugins.legacy.adapter import adapt
from canopus.plugins.legacy.loader import PluginLoadResult, load_plugin
from canopus.plugins.legacy.manager import (
    PluginManager,
    get_manager,
    initialize,
    reset_for_testing,
)
from canopus.plugins.legacy.models import (
    PluginCapabilityDef,
    PluginMeta,
    PluginRecord,
    PluginStatus,
)

__all__ = [
    "PluginCapabilityDef",
    "PluginLoadResult",
    "PluginManager",
    "PluginMeta",
    "PluginRecord",
    "PluginStatus",
    "adapt",
    "get_manager",
    "initialize",
    "load_plugin",
    "reset_for_testing",
]

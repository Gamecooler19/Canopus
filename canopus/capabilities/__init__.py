"""canopus.capabilities — normalized capability layer.

All capabilities — native, legacy plugin, and MCP — share this interface.
The global :data:`~canopus.capabilities.registry.registry` singleton is the
single source of truth for what the system can do at runtime.
"""

from canopus.capabilities.executor import CapabilityExecutor
from canopus.capabilities.registry import CapabilityRegistry, registry
from canopus.capabilities.specs import CapabilityResult, CapabilitySpec

__all__ = [
    "CapabilityExecutor",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilitySpec",
    "registry",
]

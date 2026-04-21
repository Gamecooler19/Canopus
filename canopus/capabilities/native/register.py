"""Native capability registration.

Calling :func:`register_all` populates the global
:data:`~canopus.capabilities.registry.registry` with all built-in native
capabilities. This function is idempotent — registering the same capability
twice (``overwrite=True``) is safe and used for test isolation.

New native capabilities should be added here alongside their module imports.
"""

from __future__ import annotations

from canopus.capabilities.native import filesystem_list, filesystem_read, system_now
from canopus.capabilities.registry import registry


def register_all(*, overwrite: bool = False) -> None:
    """Register all native capabilities into the global registry.

    Args:
        overwrite: When ``True``, re-register even if already present.
            Useful in tests that reset registry state.
    """
    _entries = [
        (system_now.SPEC, system_now.handler),
        (filesystem_read.SPEC, filesystem_read.handler),
        (filesystem_list.SPEC, filesystem_list.handler),
    ]
    for spec, handler in _entries:
        if not registry.contains(spec.name) or overwrite:
            registry.register(spec, handler, overwrite=overwrite)

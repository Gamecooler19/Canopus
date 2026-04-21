"""Exception hierarchy for the legacy plugin subsystem.

All plugin errors inherit from :class:`~canopus.core.errors.PluginError` so
callers can catch the whole family with a single clause. Specific subclasses
allow fine-grained handling where useful.

Design note: these errors describe problems in *plugin code*, not in the
loading machinery itself. The loader catches lower-level exceptions (e.g.
``ImportError``) and wraps them in the appropriate subclass.
"""

from __future__ import annotations

from canopus.core.errors import PluginError


class PluginImportError(PluginError):
    """Raised when a plugin file cannot be imported.

    This typically indicates a syntax error, a missing dependency, or a
    runtime exception during module-level execution.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.plugin_path = path
        self.reason = reason
        super().__init__(f"Cannot import plugin {path!r}: {reason}")


class PluginValidationError(PluginError):
    """Raised when a plugin file is discovered but fails contract validation.

    Examples:
    - Missing ``PLUGIN_META``
    - ``PLUGIN_META`` is missing required fields (``name``, ``description``)
    - Missing ``capabilities`` function
    - ``capabilities()`` returns a non-list value
    """

    def __init__(self, plugin_name: str, reason: str) -> None:
        self.plugin_name = plugin_name
        self.reason = reason
        super().__init__(f"Plugin {plugin_name!r} failed validation: {reason}")


class PluginCapabilityDefError(PluginError):
    """Raised when a single capability definition inside a plugin is invalid.

    The plugin itself may still be partially loaded — only the offending
    capability definition is skipped.
    """

    def __init__(self, plugin_name: str, cap_name: str | None, reason: str) -> None:
        self.plugin_name = plugin_name
        self.capability_name = cap_name
        self.reason = reason
        label = cap_name or "<unnamed>"
        super().__init__(
            f"Plugin {plugin_name!r} capability {label!r} is invalid: {reason}"
        )

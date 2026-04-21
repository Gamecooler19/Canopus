"""Typed data models for the legacy plugin subsystem.

These are the internal representations used by the loader, adapter, and
manager. Plugin *authors* never import from this module — the contract
they implement is plain Python dicts (see :doc:`/docs/plugin-contract`).

Key types:
- :class:`PluginMeta` — validated metadata from ``PLUGIN_META``
- :class:`PluginCapabilityDef` — validated per-capability definition from ``capabilities()``
- :class:`PluginStatus` — lifecycle state of a discovered plugin
- :class:`PluginRecord` — full snapshot of a plugin after discovery/load
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------


class PluginMeta(BaseModel):
    """Validated metadata extracted from a plugin's ``PLUGIN_META`` dict.

    Attributes:
        name: Unique identifier for this plugin. Recommended to be a short
            slug, e.g. ``"browser"`` or ``"text_tools"``.
        description: Human-readable explanation of what the plugin does.
        version: Plugin version string (free-form). Defaults to ``"0.1.0"``.
        author: Plugin author name or contact.
        tags: Free-form labels for search and discovery.
    """

    name: str
    description: str
    version: str = "0.1.0"
    author: str = ""
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-capability definition
# ---------------------------------------------------------------------------


@dataclass
class PluginCapabilityDef:
    """A single capability as declared by a plugin's ``capabilities()`` function.

    This is an *internal* type produced by the adapter after validating the
    raw dict returned by the plugin. It is never seen by plugin authors.

    Attributes:
        name: Dot-namespaced capability name, e.g. ``"text_tools.upper"``.
        description: Short description of what the capability does.
        handler: Callable that implements the capability. Must accept
            ``(inputs: dict, ctx: Any) -> dict``.
        tags: Category labels.
        permissions: Permission tokens declared as strings (e.g. ``"fs.read"``).
        side_effect_level: One of ``"none"``, ``"low"``, ``"medium"``, ``"high"``.
        confirmation_policy: One of ``"never"``, ``"smart"``, ``"always"``.
        examples: Example phrases that would route to this capability.
    """

    name: str
    description: str
    handler: Any  # Callable[[dict, Any], dict] — can't annotate callable here
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    side_effect_level: str = "none"
    confirmation_policy: str = "never"
    examples: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plugin lifecycle state
# ---------------------------------------------------------------------------


class PluginStatus(StrEnum):
    """Current state of a discovered plugin.

    Attributes:
        LOADED: Successfully imported and all capabilities registered.
        PARTIAL: Imported but some capability definitions were skipped due
            to validation errors. At least one capability was registered.
        INVALID: Plugin file fails contract validation (no load attempted).
        ERRORED: Plugin file caused a runtime exception during load.
        SKIPPED: File was found in the plugins directory but deliberately
            skipped (e.g. not a ``.py`` file, or a private ``_`` file).
    """

    LOADED = "loaded"
    PARTIAL = "partial"
    INVALID = "invalid"
    ERRORED = "errored"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Plugin record — full snapshot
# ---------------------------------------------------------------------------


class PluginRecord(BaseModel):
    """Complete snapshot of a discovered plugin after the load attempt.

    This is the primary output from the loader and the primary data type
    consumed by the manager and CLI commands.

    Attributes:
        name: Plugin name from ``PLUGIN_META``, or the stem of the file if
            metadata could not be read.
        file_name: Filename including ``.py`` extension.
        path: Absolute path to the plugin file.
        status: Lifecycle state after the load attempt.
        meta: Validated metadata. ``None`` if the plugin is INVALID/ERRORED.
        capability_names: Names of capabilities successfully registered.
        error: Primary failure message (for INVALID/ERRORED plugins).
        warnings: Non-fatal issues such as skipped capability definitions.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str
    file_name: str
    path: Path
    status: PluginStatus
    meta: PluginMeta | None = None
    capability_names: list[str] = Field(default_factory=list)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)

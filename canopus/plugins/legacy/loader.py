"""Legacy plugin file loader.

:func:`load_plugin` is the sole public entry point. It accepts a ``Path`` to
a ``.py`` file and returns a :class:`PluginLoadResult` regardless of whether
the load succeeded or failed. The caller never needs to catch exceptions from
this function — all failures are encoded in the result.

Security note
-------------
This module executes arbitrary Python code from the user's own
``~/.canopus/plugins/`` directory. This is intentional and equivalent to the
trust level given to installed Python packages. Plugin files should never be
loaded from untrusted sources.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from canopus.plugins.legacy.errors import (
    PluginCapabilityDefError,
    PluginImportError,
    PluginValidationError,
)
from canopus.plugins.legacy.models import (
    PluginCapabilityDef,
    PluginMeta,
    PluginRecord,
    PluginStatus,
)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class PluginLoadResult:
    """Output of a single plugin load attempt.

    Attributes:
        record: Status snapshot describing the outcome.
        capability_defs: Validated capability definitions ready for the adapter.
            Empty when the load failed or the plugin declared no capabilities.
    """

    record: PluginRecord
    capability_defs: list[PluginCapabilityDef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_plugin(path: Path) -> PluginLoadResult:
    """Load a single legacy plugin from *path*.

    The function never raises. All failures are captured in the returned
    :class:`PluginLoadResult`.

    Args:
        path: Absolute path to a ``.py`` plugin file.

    Returns:
        :class:`PluginLoadResult` describing the outcome.
    """
    stem = path.stem
    warnings: list[str] = []

    # ── Step 1: import the module ─────────────────────────────────────────
    try:
        module = _import_module(path)
    except PluginImportError as exc:
        record = PluginRecord(
            name=stem,
            file_name=path.name,
            path=path,
            status=PluginStatus.ERRORED,
            error=str(exc),
        )
        return PluginLoadResult(record=record)

    # ── Step 2: extract and validate PLUGIN_META ──────────────────────────
    raw_meta = getattr(module, "PLUGIN_META", None)
    if raw_meta is None:
        record = PluginRecord(
            name=stem,
            file_name=path.name,
            path=path,
            status=PluginStatus.INVALID,
            error="Missing 'PLUGIN_META' attribute. "
            "Add PLUGIN_META = {'name': '...', 'description': '...'} to your plugin.",
        )
        return PluginLoadResult(record=record)

    try:
        meta = _parse_meta(raw_meta, stem)
    except PluginValidationError as exc:
        record = PluginRecord(
            name=stem,
            file_name=path.name,
            path=path,
            status=PluginStatus.INVALID,
            error=str(exc),
        )
        return PluginLoadResult(record=record)

    plugin_name = meta.name

    # ── Step 3: extract capabilities ──────────────────────────────────────
    caps_fn = getattr(module, "capabilities", None)
    if caps_fn is None:
        record = PluginRecord(
            name=plugin_name,
            file_name=path.name,
            path=path,
            status=PluginStatus.INVALID,
            meta=meta,
            error="Missing 'capabilities' function. "
            "Add def capabilities(): return [...] to your plugin.",
        )
        return PluginLoadResult(record=record)

    if not callable(caps_fn):
        record = PluginRecord(
            name=plugin_name,
            file_name=path.name,
            path=path,
            status=PluginStatus.INVALID,
            meta=meta,
            error="'capabilities' must be a callable function.",
        )
        return PluginLoadResult(record=record)

    try:
        raw_caps = caps_fn()
    except Exception:
        tb = traceback.format_exc()
        record = PluginRecord(
            name=plugin_name,
            file_name=path.name,
            path=path,
            status=PluginStatus.ERRORED,
            meta=meta,
            error=f"capabilities() raised an exception:\n{tb}",
        )
        return PluginLoadResult(record=record)

    if not isinstance(raw_caps, list):
        record = PluginRecord(
            name=plugin_name,
            file_name=path.name,
            path=path,
            status=PluginStatus.INVALID,
            meta=meta,
            error=f"capabilities() must return a list, got {type(raw_caps).__name__!r}.",
        )
        return PluginLoadResult(record=record)

    # ── Step 4: validate individual capability definitions ────────────────
    valid_defs: list[PluginCapabilityDef] = []
    for i, raw_def in enumerate(raw_caps):
        try:
            cap_def = _parse_capability_def(raw_def, plugin_name, index=i)
            valid_defs.append(cap_def)
        except PluginCapabilityDefError as exc:
            warnings.append(str(exc))

    # ── Step 5: build the final record ───────────────────────────────────
    if not valid_defs and raw_caps:
        # Declared capabilities but all were invalid
        status = PluginStatus.INVALID
        error: str | None = (
            "All capability definitions were invalid. Check warnings for details."
        )
    elif valid_defs and warnings:
        status = PluginStatus.PARTIAL
        error = None
    else:
        status = PluginStatus.LOADED
        error = None

    record = PluginRecord(
        name=plugin_name,
        file_name=path.name,
        path=path,
        status=status,
        meta=meta,
        capability_names=[d.name for d in valid_defs],
        error=error,
        warnings=warnings,
    )
    return PluginLoadResult(record=record, capability_defs=valid_defs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _import_module(path: Path) -> types.ModuleType:
    """Import a plugin file as a Python module.

    Uses ``importlib.util.spec_from_file_location`` to load the module
    without adding it to the package hierarchy. The module *is* added to
    ``sys.modules`` under a namespaced key so that closures and method
    references inside the module remain valid for the lifetime of the
    process.

    Raises:
        :class:`~canopus.plugins.legacy.errors.PluginImportError`: On any
            import or execution failure.
    """
    module_key = f"_canopus_plugin_{path.stem}"
    path_str = str(path)

    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        raise PluginImportError(path_str, "importlib could not create a module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        # Remove stale entry from sys.modules so re-loading is clean
        sys.modules.pop(module_key, None)
        raise PluginImportError(path_str, str(exc)) from exc

    return module


def _parse_meta(raw: Any, fallback_name: str) -> PluginMeta:
    """Parse and validate a ``PLUGIN_META`` value.

    Accepts either a plain ``dict`` or an already-constructed
    :class:`~canopus.plugins.legacy.models.PluginMeta` instance.

    Raises:
        :class:`~canopus.plugins.legacy.errors.PluginValidationError`: On
            validation failure.
    """
    if isinstance(raw, PluginMeta):
        return raw

    if not isinstance(raw, dict):
        raise PluginValidationError(
            fallback_name,
            f"PLUGIN_META must be a dict or PluginMeta, got {type(raw).__name__!r}.",
        )

    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise PluginValidationError(
            fallback_name,
            "PLUGIN_META must include a non-empty 'name' string.",
        )

    description = raw.get("description")
    if not description or not isinstance(description, str):
        raise PluginValidationError(
            name,
            "PLUGIN_META must include a non-empty 'description' string.",
        )

    try:
        return PluginMeta(
            name=name,
            description=description,
            version=raw.get("version", "0.1.0"),
            author=raw.get("author", ""),
            tags=raw.get("tags", []),
        )
    except Exception as exc:
        raise PluginValidationError(name, str(exc)) from exc


def _parse_capability_def(
    raw: Any,
    plugin_name: str,
    *,
    index: int,
) -> PluginCapabilityDef:
    """Parse and validate a single capability definition dict.

    Raises:
        :class:`~canopus.plugins.legacy.errors.PluginCapabilityDefError`:
            On validation failure.
    """
    label = f"item[{index}]"

    if not isinstance(raw, dict):
        raise PluginCapabilityDefError(
            plugin_name, None,
            f"{label} must be a dict, got {type(raw).__name__!r}",
        )

    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise PluginCapabilityDefError(
            plugin_name, None,
            f"{label} must include a non-empty 'name' string",
        )

    description = raw.get("description")
    if not description or not isinstance(description, str):
        raise PluginCapabilityDefError(
            plugin_name, name,
            "must include a non-empty 'description' string",
        )

    handler = raw.get("handler")
    if handler is None:
        raise PluginCapabilityDefError(
            plugin_name, name, "must include a 'handler' callable"
        )
    if not callable(handler):
        raise PluginCapabilityDefError(
            plugin_name, name,
            f"'handler' must be callable, got {type(handler).__name__!r}",
        )

    return PluginCapabilityDef(
        name=name,
        description=description,
        handler=handler,
        tags=raw.get("tags", []),
        permissions=raw.get("permissions", []),
        side_effect_level=raw.get("side_effect_level", "none"),
        confirmation_policy=raw.get("confirmation_policy", "never"),
        examples=raw.get("examples", []),
    )

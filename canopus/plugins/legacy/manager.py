"""Legacy plugin manager — discovery, loading, and capability registration.

The :class:`PluginManager` is the central service for the legacy plugin
subsystem. It:

1. Scans a directory for ``.py`` plugin files.
2. Delegates per-file loading to :func:`~canopus.plugins.legacy.loader.load_plugin`.
3. Adapts valid capabilities via :func:`~canopus.plugins.legacy.adapter.adapt`.
4. Registers adapted capabilities into the global
   :class:`~canopus.capabilities.registry.CapabilityRegistry`.
5. Keeps a :class:`~canopus.plugins.legacy.models.PluginRecord` for every
   discovered file so CLI commands can inspect status, errors, and warnings.

One bad plugin must not break startup. All per-plugin errors are captured and
surfaced via :meth:`PluginManager.get_records` — not raised to the caller.

Module-level singleton
----------------------
:func:`initialize` creates and populates the global manager.
:func:`get_manager` retrieves it (or ``None`` before initialization).
CLI commands and tests call :func:`get_manager` rather than constructing
:class:`PluginManager` directly.
"""

from __future__ import annotations

from pathlib import Path

from canopus.capabilities.registry import CapabilityRegistry
from canopus.core.errors import CapabilityError
from canopus.plugins.legacy.adapter import adapt
from canopus.plugins.legacy.errors import PluginCapabilityDefError
from canopus.plugins.legacy.loader import load_plugin
from canopus.plugins.legacy.models import PluginRecord, PluginStatus

# ---------------------------------------------------------------------------
# Manager class
# ---------------------------------------------------------------------------


class PluginManager:
    """Discovers, validates, and loads legacy plugins from a directory.

    Args:
        plugins_dir: Path to the directory containing ``.py`` plugin files.
            Typically ``~/.canopus/plugins/``.
        registry: The capability registry to register plugin capabilities into.

    Usage::

        manager = PluginManager(plugins_dir=config.paths.plugins_dir, registry=registry)
        manager.discover_and_load()

        for record in manager.get_loaded():
            print(record.name, record.capability_names)
    """

    def __init__(self, plugins_dir: Path, registry: CapabilityRegistry) -> None:
        self._plugins_dir = plugins_dir
        self._registry = registry
        self._records: dict[str, PluginRecord] = {}  # keyed by plugin name

    # ------------------------------------------------------------------
    # Discovery and loading
    # ------------------------------------------------------------------

    def discover_and_load(self) -> list[PluginRecord]:
        """Scan the plugins directory and load every valid plugin.

        Files are processed in sorted order for deterministic loading. A
        plugin that fails import or validation is recorded but does not
        prevent other plugins from loading.

        Returns:
            All :class:`~canopus.plugins.legacy.models.PluginRecord` objects
            produced by this run (same as :meth:`get_records`).
        """
        self._records.clear()

        if not self._plugins_dir.exists():
            return []

        plugin_files = sorted(
            p for p in self._plugins_dir.glob("*.py") if _is_candidate(p)
        )

        seen_names: set[str] = set()

        for path in plugin_files:
            result = load_plugin(path)
            record = result.record

            # ── Duplicate plugin name detection ───────────────────────────
            if record.name in seen_names:
                record = record.model_copy(
                    update={
                        "status": PluginStatus.SKIPPED,
                        "error": (
                            f"Duplicate plugin name {record.name!r}. "
                            "A plugin with this name was already loaded. "
                            "Rename this plugin's PLUGIN_META name to avoid conflicts."
                        ),
                        "capability_names": [],
                    }
                )
                # Store under a disambiguated key so we don't silently lose it
                key = f"{record.name}__{record.file_name}"
                self._records[key] = record
                continue

            seen_names.add(record.name)

            # ── Register capabilities ─────────────────────────────────────
            registered: list[str] = []
            new_warnings = list(record.warnings)

            for cap_def in result.capability_defs:
                try:
                    spec, handler = adapt(cap_def, record.name)
                    self._registry.register(spec, handler)
                    registered.append(spec.name)
                except PluginCapabilityDefError as exc:
                    new_warnings.append(str(exc))
                except CapabilityError as exc:
                    # Duplicate capability name in the registry
                    new_warnings.append(
                        f"Capability {cap_def.name!r} skipped: {exc}"
                    )

            # Update status if some capabilities failed to register
            final_status = _compute_final_status(record.status, registered, new_warnings)
            record = record.model_copy(
                update={
                    "capability_names": registered,
                    "warnings": new_warnings,
                    "status": final_status,
                }
            )

            self._records[record.name] = record

        return list(self._records.values())

    # ------------------------------------------------------------------
    # Record access
    # ------------------------------------------------------------------

    def get_records(self) -> list[PluginRecord]:
        """Return all plugin records sorted by plugin name."""
        return sorted(self._records.values(), key=lambda r: r.name)

    def get_record(self, name: str) -> PluginRecord | None:
        """Return the record for a plugin by name, or ``None``."""
        return self._records.get(name)

    def get_loaded(self) -> list[PluginRecord]:
        """Return fully or partially loaded plugin records."""
        return [
            r for r in self._records.values()
            if r.status in (PluginStatus.LOADED, PluginStatus.PARTIAL)
        ]

    def get_failed(self) -> list[PluginRecord]:
        """Return INVALID and ERRORED plugin records."""
        return [
            r for r in self._records.values()
            if r.status in (PluginStatus.INVALID, PluginStatus.ERRORED)
        ]

    def get_skipped(self) -> list[PluginRecord]:
        """Return SKIPPED plugin records (e.g. duplicate name conflicts)."""
        return [r for r in self._records.values() if r.status == PluginStatus.SKIPPED]

    @property
    def plugins_dir(self) -> Path:
        """The directory being managed."""
        return self._plugins_dir


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: PluginManager | None = None


def initialize(
    plugins_dir: Path,
    registry: CapabilityRegistry,
) -> PluginManager:
    """Create the global :class:`PluginManager` and load all plugins.

    Safe to call multiple times — each call replaces the previous manager.
    This means each call re-scans and re-loads from disk.

    Args:
        plugins_dir: Directory to scan for ``.py`` plugin files.
        registry: Target capability registry.

    Returns:
        The newly created and loaded :class:`PluginManager`.
    """
    global _manager
    _manager = PluginManager(plugins_dir=plugins_dir, registry=registry)
    _manager.discover_and_load()
    return _manager


def get_manager() -> PluginManager | None:
    """Return the global :class:`PluginManager` if initialized, else ``None``."""
    return _manager


def reset_for_testing() -> None:
    """Reset global manager state.  **Only for use in tests.**"""
    global _manager
    _manager = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_candidate(path: Path) -> bool:
    """Return ``True`` if *path* looks like a plugin file we should attempt to load."""
    name = path.stem
    # Skip private/dunder files and __init__
    if name.startswith("_"):
        return False
    return True


def _compute_final_status(
    loader_status: PluginStatus,
    registered: list[str],
    warnings: list[str],
) -> PluginStatus:
    """Determine the final status after capability registration."""
    if loader_status in (PluginStatus.INVALID, PluginStatus.ERRORED):
        return loader_status

    if not registered and warnings:
        return PluginStatus.INVALID

    if registered and warnings:
        return PluginStatus.PARTIAL

    return PluginStatus.LOADED

"""Application configuration loading and filesystem path management.

This module defines:
- :class:`AppPaths` — all data directories under ``~/.canopus/``
- :class:`TracingSettings` — tracing sub-configuration
- :class:`AppConfig` — root configuration model
- :func:`load_config` — load config from disk with fallback to defaults
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from canopus.core.errors import ConfigError


class AppPaths(BaseModel):
    """Resolved filesystem paths for all Canopus data directories.

    All paths are rooted under ``root`` (default: ``~/.canopus``).
    Use :meth:`ensure_all` to create every directory before first use.
    """

    root: Path = Field(default_factory=lambda: Path.home() / ".canopus")

    # ------------------------------------------------------------------
    # Directory properties
    # ------------------------------------------------------------------

    @property
    def config_dir(self) -> Path:
        """``<root>/config/``"""
        return self.root / "config"

    @property
    def profiles_dir(self) -> Path:
        """``<root>/config/profiles/``"""
        return self.root / "config" / "profiles"

    @property
    def policies_dir(self) -> Path:
        """``<root>/config/policies/``"""
        return self.root / "config" / "policies"

    @property
    def secrets_file(self) -> Path:
        """``<root>/config/secrets.toml``"""
        return self.root / "config" / "secrets.toml"

    @property
    def plugins_dir(self) -> Path:
        """``<root>/plugins/``"""
        return self.root / "plugins"

    @property
    def memory_dir(self) -> Path:
        """``<root>/memory/``"""
        return self.root / "memory"

    @property
    def traces_dir(self) -> Path:
        """``<root>/traces/``"""
        return self.root / "traces"

    @property
    def workflows_dir(self) -> Path:
        """``<root>/workflows/``"""
        return self.root / "workflows"

    @property
    def cache_dir(self) -> Path:
        """``<root>/cache/``"""
        return self.root / "cache"

    @property
    def logs_dir(self) -> Path:
        """``<root>/logs/``"""
        return self.root / "logs"

    @property
    def config_file(self) -> Path:
        """``<root>/config/config.toml`` — main application config file."""
        return self.root / "config" / "config.toml"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def ensure_all(self) -> None:
        """Create all required directories if they do not already exist."""
        directories = [
            self.config_dir,
            self.profiles_dir,
            self.policies_dir,
            self.plugins_dir,
            self.memory_dir,
            self.traces_dir,
            self.workflows_dir,
            self.cache_dir,
            self.logs_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


class TracingSettings(BaseModel):
    """Configuration for the execution tracing subsystem."""

    enabled: bool = True
    max_trace_files: int = 1000


class AppConfig(BaseModel):
    """Root application configuration.

    Loaded from ``~/.canopus/config/config.toml`` when it exists, otherwise
    defaults are used. The ``paths`` field is always resolved from the
    runtime environment — it is not read from the TOML file.
    """

    active_profile: str = "local-private"
    tracing: TracingSettings = Field(default_factory=TracingSettings)
    paths: AppPaths = Field(default_factory=AppPaths)


def load_config(paths: AppPaths | None = None) -> AppConfig:
    """Load application configuration from disk with fallback to defaults.

    Args:
        paths: Override the default :class:`AppPaths`. Uses ``~/.canopus``
            by default. The ``paths`` value is always injected into the
            returned config — it is never taken from the TOML file itself.

    Returns:
        A fully resolved :class:`AppConfig`, with defaults where values
        are absent from the config file.

    Raises:
        :class:`~canopus.core.errors.ConfigError`: If the config file
            exists but cannot be parsed.
    """
    resolved_paths = paths or AppPaths()
    config_file = resolved_paths.config_file

    if not config_file.exists():
        return AppConfig(paths=resolved_paths)

    try:
        with config_file.open("rb") as fh:
            raw: dict[str, Any] = tomllib.load(fh)
    except Exception as exc:
        raise ConfigError(
            f"Failed to parse config file {config_file}: {exc}"
        ) from exc

    # Paths are always resolved from runtime — never from the TOML file.
    raw.pop("paths", None)

    return AppConfig(paths=resolved_paths, **raw)

"""Shared pytest fixtures for Canopus tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from canopus.core.config import AppConfig, AppPaths


@pytest.fixture
def tmp_canopus_paths(tmp_path: Path) -> AppPaths:
    """Return :class:`AppPaths` rooted in a temporary directory.

    All directories are created eagerly so tests can write files without
    extra setup.
    """
    paths = AppPaths(root=tmp_path / "canopus")
    paths.ensure_all()
    return paths


@pytest.fixture
def tmp_config(tmp_canopus_paths: AppPaths) -> AppConfig:
    """Return an :class:`AppConfig` backed by a temporary directory.

    Uses the ``local-private`` built-in profile (the default active profile).
    """
    return AppConfig(paths=tmp_canopus_paths)


@pytest.fixture
def patched_config(tmp_config: AppConfig):  # type: ignore[no-untyped-def]
    """Patch load_config in every module that calls it directly.

    CLI commands call ``load_config()`` from their own module scope.
    We also patch it in ``canopus.core.runtime`` which is called by the
    ``run`` and ``chat`` commands via ``create_session``.
    """
    with (
        patch("canopus.core.runtime.load_config", return_value=tmp_config),
        patch("canopus.cli.commands.doctor.load_config", return_value=tmp_config),
        patch("canopus.cli.commands.profile.load_config", return_value=tmp_config),
    ):
        yield tmp_config

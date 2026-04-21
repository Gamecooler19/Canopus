"""canopus.storage — local persistence layer.

This package provides low-level storage primitives used by other subsystems
(currently: the memory subsystem). All storage is local-first by default —
no cloud backend is required.

Modules:
    :mod:`canopus.storage.sqlite` — helpers for creating and managing SQLite
    databases with WAL mode, connection pooling, and schema migration support.
"""

from __future__ import annotations

"""canopus.memory — local-first memory subsystem.

This package provides the full memory layer for Canopus:

- :class:`~canopus.memory.models.MemoryRecord` — typed memory record model
- :class:`~canopus.memory.models.MemoryKind` — memory category enumeration
- :class:`~canopus.memory.models.MemoryQuery` — retrieval query parameters
- :class:`~canopus.memory.models.MemoryContext` — assembled context for the pipeline
- :class:`~canopus.memory.store.MemoryStore` — SQLite-backed persistence
- :class:`~canopus.memory.retrieval.MemoryRetriever` — FTS + recency-ranked retrieval
- :class:`~canopus.memory.context_builder.ContextBuilder` — prompt-ready context assembly
- :class:`~canopus.memory.service.MemoryService` — high-level service (primary entry point)

The recommended entry point for external callers is :func:`initialize` and :func:`get_service`.
"""

from __future__ import annotations

from canopus.memory.context_builder import ContextBuilder
from canopus.memory.models import MemoryContext, MemoryKind, MemoryQuery, MemoryRecord
from canopus.memory.retrieval import MemoryRetriever
from canopus.memory.service import (
    MemoryService,
    get_service,
    initialize,
    reset_for_testing,
)
from canopus.memory.store import MemoryStore

__all__ = [
    "ContextBuilder",
    "MemoryContext",
    "MemoryKind",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryRetriever",
    "MemoryService",
    "MemoryStore",
    "get_service",
    "initialize",
    "reset_for_testing",
]

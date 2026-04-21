"""Memory service — primary public interface for the memory subsystem.

:class:`MemoryService` is the only object external callers (CLI, reasoning
pipeline, integration points) should interact with. It wires together the
store, retriever, and context builder and exposes a focused, stable API.

Lifecycle:
- Call :meth:`open` before use (or use as a context manager).
- Call :meth:`close` when done.

Module-level singleton
----------------------
:func:`get_service` returns the current global service (or ``None`` if not
yet initialised).
:func:`initialize` creates the singleton, opens the store, and returns the
service.
:func:`reset_for_testing` destroys the singleton for test isolation.
"""

from __future__ import annotations

from pathlib import Path

from canopus.memory.context_builder import ContextBuilder
from canopus.memory.models import (
    MemoryContext,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
)
from canopus.memory.retrieval import MemoryRetriever
from canopus.memory.store import MemoryStore


class MemoryService:
    """High-level interface for all memory subsystem operations.

    Args:
        db_path: Path to the SQLite database file.
        max_context_records: Default maximum records assembled into context.
        recency_weight: Default recency factor used in retrieval scoring.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        max_context_records: int = 8,
        recency_weight: float = 0.3,
    ) -> None:
        self._store = MemoryStore(db_path)
        self._retriever = MemoryRetriever(self._store)
        self._builder = ContextBuilder(
            self._retriever,
            max_records=max_context_records,
            recency_weight=recency_weight,
        )
        self._open = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the underlying store and run pending migrations."""
        self._store.open()
        self._open = True

    def close(self) -> None:
        """Close the underlying store. Safe to call multiple times."""
        self._store.close()
        self._open = False

    def __enter__(self) -> MemoryService:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new memory record and return it.

        Args:
            record: The record to store. The ``id`` field is auto-generated
                if not supplied.

        Returns:
            The stored record (same object, for chaining convenience).
        """
        self._store.insert(record)
        return record

    def remember_exchange(
        self,
        *,
        user_input: str,
        assistant_response: str,
        session_id: str | None = None,
        run_id: str | None = None,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Store a user/assistant exchange as a conversation memory record.

        This is the primary integration point for ``canopus run`` and
        ``canopus chat``.

        Args:
            user_input: The raw user request.
            assistant_response: The assistant's final response text.
            session_id: Session ID, if available.
            run_id: Run ID, if available.
            importance: Relative importance score (0.0–1.0).
            tags: Optional additional tags.

        Returns:
            The created and stored :class:`~canopus.memory.models.MemoryRecord`.
        """
        content = f"User: {user_input}\nAssistant: {assistant_response}"
        record = MemoryRecord(
            kind=MemoryKind.CONVERSATION,
            content=content,
            tags=tags or [],
            source="conversation",
            importance=importance,
            session_id=session_id,
            run_id=run_id,
        )
        self._store.insert(record)
        return record

    def forget(self, memory_id: str) -> None:
        """Delete a memory record by ID.

        Args:
            memory_id: ID of the record to remove.

        Raises:
            :class:`~canopus.core.errors.MemoryNotFoundError`: If not found.
        """
        self._store.delete(memory_id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord:
        """Retrieve a single record by ID.

        Args:
            memory_id: The unique identifier.

        Returns:
            The matching record.

        Raises:
            :class:`~canopus.core.errors.MemoryNotFoundError`: If not found.
        """
        return self._store.get(memory_id)

    def list_recent(
        self,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
        source: str | None = None,
    ) -> list[MemoryRecord]:
        """Return recently created records, newest first.

        Args:
            limit: Maximum number of results.
            kind: Filter to a specific memory kind.
            source: Filter to a specific source.

        Returns:
            List of records.
        """
        return self._store.list_recent(limit=limit, kind=kind, source=source)

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Run a retrieval query and return ranked results.

        Args:
            query: Retrieval parameters.

        Returns:
            Ranked list of matching records.
        """
        return self._retriever.retrieve(query)

    def build_context(self, request: str) -> MemoryContext:
        """Assemble a bounded memory context for *request*.

        This is the primary integration point for the reasoning pipeline.

        Args:
            request: The user request string used as the retrieval query.

        Returns:
            A :class:`~canopus.memory.models.MemoryContext` ready for prompt injection.
        """
        return self._builder.build(request)

    def build_recent_context(self, *, limit: int = 5) -> MemoryContext:
        """Return a context of the most recent memories.

        Args:
            limit: Maximum number of records.

        Returns:
            A :class:`~canopus.memory.models.MemoryContext`.
        """
        return self._builder.build_recent(limit=limit)

    def count(self) -> int:
        """Return the total number of stored memory records."""
        return self._store.count()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: MemoryService | None = None


def initialize(db_path: Path, **kwargs: object) -> MemoryService:
    """Create and open the global :class:`MemoryService`.

    Args:
        db_path: Path to the SQLite database file.
        **kwargs: Forwarded to :class:`MemoryService.__init__`.

    Returns:
        The initialised service.
    """
    global _service
    svc = MemoryService(db_path, **kwargs)  # type: ignore[arg-type]
    svc.open()
    _service = svc
    return svc


def get_service() -> MemoryService | None:
    """Return the global :class:`MemoryService`, or ``None`` if not initialised."""
    return _service


def reset_for_testing() -> None:
    """Destroy the global singleton. For test isolation only."""
    global _service
    if _service is not None:
        try:
            _service.close()
        except Exception:
            pass
    _service = None

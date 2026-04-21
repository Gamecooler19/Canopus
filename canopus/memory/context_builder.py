"""Memory context builder.

:class:`ContextBuilder` assembles a :class:`~canopus.memory.models.MemoryContext`
from a user request and the current memory store. The result is designed to
be injected into the reasoning pipeline before the planner runs.

Design rules:
- Context assembly logic lives here, not in the retrieval or CLI layers.
- Output size is bounded by a configurable character budget.
- The interface is clean: one request string in, one MemoryContext out.
- Future phases can enrich this with semantic retrieval without changing callers.
"""

from __future__ import annotations

from canopus.memory.models import MemoryContext, MemoryQuery, MemoryRecord
from canopus.memory.retrieval import MemoryRetriever


class ContextBuilder:
    """Build a bounded, ranked memory context for a request string.

    Args:
        retriever: An initialised :class:`~canopus.memory.retrieval.MemoryRetriever`.
        max_records: Hard cap on the number of records included in the context.
        recency_weight: Passed to the retriever's scoring function.
    """

    def __init__(
        self,
        retriever: MemoryRetriever,
        *,
        max_records: int = 8,
        recency_weight: float = 0.3,
    ) -> None:
        self._retriever = retriever
        self._max_records = max_records
        self._recency_weight = recency_weight

    def build(self, request: str) -> MemoryContext:
        """Retrieve and assemble context relevant to *request*.

        Args:
            request: The raw user input string that will be used as the
                full-text search query.

        Returns:
            A :class:`~canopus.memory.models.MemoryContext` with ranked
            records and a rendered prompt block ready for injection.
        """
        query = MemoryQuery(
            text=request,
            limit=self._max_records * 2,  # over-fetch, then trim
            recency_weight=self._recency_weight,
        )
        candidates: list[MemoryRecord] = self._retriever.retrieve(query)

        total_found = len(candidates)
        records = candidates[: self._max_records]
        truncated = total_found > self._max_records

        return MemoryContext(
            records=records,
            query_text=request,
            truncated=truncated,
            total_found=total_found,
        )

    def build_recent(self, *, limit: int = 5) -> MemoryContext:
        """Return a context of the most recent memories (no text query).

        Useful for session preamble injection where there is no specific
        query yet.

        Args:
            limit: Maximum number of records to include.

        Returns:
            A :class:`~canopus.memory.models.MemoryContext`.
        """
        records = self._retriever.retrieve_recent(limit=limit)
        return MemoryContext(
            records=records,
            query_text="",
            truncated=False,
            total_found=len(records),
        )

"""Memory retrieval layer.

:class:`MemoryRetriever` sits above :class:`~canopus.memory.store.MemoryStore`
and provides higher-level retrieval that combines:

- Full-text search (FTS5) for text queries
- Recency-aware scoring
- Kind / tag / source filtering
- Deduplication

The retrieval strategy in this phase is deliberately **lexical + metadata**
(no vector embeddings). This is sufficient for most practical use-cases and
is easy to reason about. Future phases can slot in a semantic retrieval layer
behind the same interface without rewriting callers.

Design rule: this module must not contain any persistence logic. All SQL
lives in :class:`~canopus.memory.store.MemoryStore`.
"""

from __future__ import annotations

import datetime

from canopus.memory.models import MemoryKind, MemoryQuery, MemoryRecord
from canopus.memory.store import MemoryStore


class MemoryRetriever:
    """Retrieve and rank memory records for a given query.

    Args:
        store: An already-open :class:`~canopus.memory.store.MemoryStore`.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Execute a retrieval query and return a ranked result list.

        Combines FTS and recency scoring:

        1. If *query.text* is non-empty, run FTS5 search for candidates.
        2. Otherwise fall back to a recency-ordered list_recent query.
        3. Apply any remaining tag/kind filters.
        4. Re-rank results by a combined importance + recency score.
        5. Truncate to *query.limit*.

        Args:
            query: Retrieval parameters from :class:`~canopus.memory.models.MemoryQuery`.

        Returns:
            Ranked and filtered list of :class:`~canopus.memory.models.MemoryRecord`,
            most relevant first.
        """
        kind_filter = query.kinds[0] if len(query.kinds) == 1 else None
        fetch_limit = max(query.limit * 3, 60)  # over-fetch for re-ranking

        if query.text.strip():
            candidates = self._store.search_fts(
                query.text,
                limit=fetch_limit,
                kind=kind_filter,
                source=query.source,
                min_importance=query.min_importance,
            )
        else:
            candidates = self._store.list_recent(
                limit=fetch_limit,
                kind=kind_filter,
                source=query.source,
                session_id=query.session_id,
            )

        # Apply filters that the store query could not handle
        if len(query.kinds) > 1:
            kind_set = {k.value for k in query.kinds}
            candidates = [r for r in candidates if r.kind.value in kind_set]
        if query.session_id and not query.text:
            # list_recent already filters by session_id; skip when FTS is active
            pass
        elif query.session_id and query.text:
            candidates = [r for r in candidates if r.session_id == query.session_id]
        if query.tags:
            tag_set = set(query.tags)
            candidates = [r for r in candidates if tag_set & set(r.tags)]
        if query.min_importance > 0.0 and not query.text:
            candidates = [r for r in candidates if r.importance >= query.min_importance]

        # Rank
        now = datetime.datetime.now(datetime.UTC)
        scored = [
            (self._score(r, now, query.recency_weight), r)
            for r in candidates
        ]
        scored.sort(key=lambda t: t[0], reverse=True)

        return [r for _, r in scored[: query.limit]]

    def retrieve_recent(
        self,
        *,
        limit: int = 10,
        kind: MemoryKind | None = None,
        source: str | None = None,
    ) -> list[MemoryRecord]:
        """Convenience wrapper: return the most recent records.

        Args:
            limit: Maximum number of results. Defaults to 10.
            kind: Filter by memory kind.
            source: Filter by source string.

        Returns:
            Records newest-first.
        """
        return self._store.list_recent(limit=limit, kind=kind, source=source)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score(
        record: MemoryRecord,
        now: datetime.datetime,
        recency_weight: float,
    ) -> float:
        """Compute a combined relevance score.

        Score = (1 - recency_weight) * importance
              + recency_weight * recency_factor

        The recency factor is a simple exponential decay keyed on the
        number of days since creation (half-life ≈ 7 days).

        Args:
            record: The memory record to score.
            now: Current time reference for age calculation.
            recency_weight: How much recency contributes (0.0–1.0).

        Returns:
            Float score in roughly [0.0, 1.0].
        """
        # Ensure both timestamps are timezone-aware for subtraction
        created = record.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.UTC)

        age_days = max(0.0, (now - created).total_seconds() / 86400)
        recency = 2 ** (-age_days / 7.0)  # half-life = 7 days

        importance_score = record.importance
        return (1.0 - recency_weight) * importance_score + recency_weight * recency

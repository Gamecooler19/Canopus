"""Memory store — SQLite-backed persistence layer for memory records.

:class:`MemoryStore` provides the low-level read/write interface for
:class:`~canopus.memory.models.MemoryRecord` objects. It owns the schema and
all SQL; the retrieval and context layers sit above it.

Schema summary:
- ``memories``        — main record table
- ``memories_fts``    — FTS5 virtual table over ``content`` column

Usage::

    store = MemoryStore(db_path=Path("~/.canopus/memory/memory.db"))
    store.open()

    record = MemoryRecord(content="Decided to use SQLite for storage.")
    store.insert(record)

    rows = store.list_recent(limit=10)
    store.close()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canopus.core.errors import MemoryNotFoundError
from canopus.memory.models import MemoryKind, MemoryRecord
from canopus.storage.sqlite import SqliteStore

# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS memories (
            id          TEXT    PRIMARY KEY,
            kind        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            tags        TEXT    NOT NULL DEFAULT '[]',
            source      TEXT    NOT NULL DEFAULT 'user',
            importance  REAL    NOT NULL DEFAULT 0.5,
            session_id  TEXT,
            run_id      TEXT,
            metadata    TEXT    NOT NULL DEFAULT '{}',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memories_kind       ON memories(kind);
        CREATE INDEX IF NOT EXISTS idx_memories_source     ON memories(source);
        CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
        CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            content='memories',
            content_rowid='rowid',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
              VALUES('delete', old.rowid, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
              VALUES('delete', old.rowid, old.content);
            INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
        END;
        """,
    ),
]


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class MemoryStore:
    """SQLite-backed persistence for :class:`~canopus.memory.models.MemoryRecord`.

    Args:
        db_path: Path to the SQLite database file. Created automatically
            along with all parent directories on first :meth:`open`.
    """

    def __init__(self, db_path: Path) -> None:
        self._store = SqliteStore(db_path)
        self._open = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the database and run pending schema migrations.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        self._store.open()
        self._store.migrate(_MIGRATIONS)
        self._open = True

    def close(self) -> None:
        """Close the database connection. Safe to call multiple times."""
        self._store.close()
        self._open = False

    def __enter__(self) -> MemoryStore:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, record: MemoryRecord) -> None:
        """Persist a new memory record.

        Args:
            record: The record to insert. Its ``id`` must be unique.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: If the insert fails.
        """
        self._store.execute(
            """
            INSERT INTO memories
              (id, kind, content, tags, source, importance,
               session_id, run_id, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._to_row(record),
        )

    def update_content(self, memory_id: str, new_content: str) -> None:
        """Replace the content of an existing record.

        Args:
            memory_id: ID of the record to update.
            new_content: New content string.

        Raises:
            :class:`~canopus.core.errors.MemoryNotFoundError`: If the ID is unknown.
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        existing = self.get(memory_id)  # raises MemoryNotFoundError if absent
        existing.content = new_content
        existing.touch()
        self._store.execute(
            "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
            (new_content, existing.updated_at.isoformat(), memory_id),
        )

    def delete(self, memory_id: str) -> None:
        """Remove a memory record by ID.

        Args:
            memory_id: ID of the record to delete.

        Raises:
            :class:`~canopus.core.errors.MemoryNotFoundError`: If the ID is unknown.
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        self.get(memory_id)  # raises MemoryNotFoundError if absent
        self._store.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord:
        """Retrieve a single record by ID.

        Args:
            memory_id: The unique identifier.

        Returns:
            The matching :class:`~canopus.memory.models.MemoryRecord`.

        Raises:
            :class:`~canopus.core.errors.MemoryNotFoundError`: If not found.
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        row = self._store.query_one("SELECT * FROM memories WHERE id = ?", (memory_id,))
        if row is None:
            raise MemoryNotFoundError(memory_id)
        return self._from_row(row)

    def list_recent(
        self,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
        source: str | None = None,
        session_id: str | None = None,
    ) -> list[MemoryRecord]:
        """Return recently created records in reverse-chronological order.

        Args:
            limit: Maximum number of results.
            kind: Filter to a specific memory kind.
            source: Filter to a specific source string.
            session_id: Filter to a specific session.

        Returns:
            List of records, newest first.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind.value)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        sql = f"SELECT * FROM memories {where} ORDER BY created_at DESC LIMIT ?"
        rows = self._store.query(sql, tuple(params))
        return [self._from_row(r) for r in rows]

    def search_fts(
        self,
        query: str,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
        source: str | None = None,
        min_importance: float = 0.0,
    ) -> list[MemoryRecord]:
        """Full-text search over the ``content`` field.

        Uses FTS5 ``MATCH`` syntax. The FTS result set is then filtered by
        the optional ``kind``/``source``/``min_importance`` conditions.

        Args:
            query: FTS5 query string. Supports prefix search (``hello*``),
                boolean operators (``AND``, ``OR``, ``NOT``), and phrase
                search (``"hello world"``).
            limit: Maximum number of results.
            kind: Narrow results to a specific memory kind.
            source: Narrow results to a specific source string.
            min_importance: Only return records with importance ≥ this value.

        Returns:
            Matching records, ordered by FTS5 rank (best match first).

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O or FTS failure.
        """
        match_clause = "m.rowid IN (SELECT rowid FROM memories_fts WHERE content MATCH ?)"
        conditions: list[str] = [match_clause]
        params: list[Any] = [query]

        if kind is not None:
            conditions.append("m.kind = ?")
            params.append(kind.value)
        if source is not None:
            conditions.append("m.source = ?")
            params.append(source)
        if min_importance > 0.0:
            conditions.append("m.importance >= ?")
            params.append(min_importance)

        where = " AND ".join(conditions)
        params.append(limit)
        sql = (
            f"SELECT m.* FROM memories m "
            f"WHERE {where} "
            f"ORDER BY m.importance DESC, m.created_at DESC "
            f"LIMIT ?"
        )
        rows = self._store.query(sql, tuple(params))
        return [self._from_row(r) for r in rows]

    def count(self) -> int:
        """Return the total number of stored memory records.

        Returns:
            Integer count.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On I/O failure.
        """
        row = self._store.query_one("SELECT COUNT(*) AS n FROM memories")
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_row(record: MemoryRecord) -> tuple[Any, ...]:
        return (
            record.id,
            record.kind.value,
            record.content,
            json.dumps(record.tags),
            record.source,
            record.importance,
            record.session_id,
            record.run_id,
            json.dumps(record.metadata),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            kind=MemoryKind(row["kind"]),
            content=row["content"],
            tags=json.loads(row["tags"]),
            source=row["source"],
            importance=float(row["importance"]),
            session_id=row.get("session_id"),
            run_id=row.get("run_id"),
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

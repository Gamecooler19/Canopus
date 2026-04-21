"""SQLite storage helper for Canopus local databases.

Provides :class:`SqliteStore`, a thin wrapper around the stdlib
``sqlite3`` module that adds:

- WAL-mode for better concurrent read performance
- Auto-creation of the database file and parent directory
- A simple migration system keyed by integer version numbers
- A :meth:`execute` / :meth:`query` interface that returns typed rows
- Full-text search (FTS5) table creation helpers

The design deliberately avoids an ORM.  Raw SQL keeps the schema
transparent and the dependency footprint minimal.

Usage::

    store = SqliteStore(Path("~/.canopus/memory/memory.db").expanduser())
    store.open()
    store.migrate([
        (1, "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY)"),
    ])
    rows = store.query("SELECT * FROM records WHERE id = ?", ("abc",))
    store.close()
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from canopus.core.errors import MemoryStoreError


class SqliteStore:
    """Managed SQLite connection with WAL mode and schema migration support.

    This class is *not* thread-safe by default. Each thread/task that needs
    database access should create its own :class:`SqliteStore` instance
    pointing at the same file — SQLite's WAL mode handles concurrent access.

    Args:
        db_path: Absolute path to the ``.db`` file. The parent directory
            is created automatically if it does not exist.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database file and configure the connection.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: If the database
                cannot be opened.
        """
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"Cannot open database at {self._db_path}: {exc}") from exc

    def close(self) -> None:
        """Close the connection if open. Safe to call multiple times."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            finally:
                self._conn = None

    def __enter__(self) -> SqliteStore:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate(self, migrations: list[tuple[int, str]]) -> None:
        """Apply pending schema migrations in version order.

        Each migration is a ``(version, sql)`` tuple. Migrations are applied
        only if the stored ``user_version`` pragma is below *version*.
        Migrations run in ascending order and are committed atomically.

        Args:
            migrations: Ordered list of ``(version, sql)`` pairs. *sql* may
                contain multiple statements separated by semicolons.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: If a migration
                statement fails or if the store is not open.
        """
        conn = self._require_conn()
        current_version: int = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, sql in sorted(migrations, key=lambda t: t[0]):
            if version <= current_version:
                continue
            try:
                conn.executescript(sql)
                conn.execute(f"PRAGMA user_version={version}")
                conn.commit()
            except sqlite3.Error as exc:
                raise MemoryStoreError(
                    f"Migration v{version} failed: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Execute a DML statement (INSERT, UPDATE, DELETE) and commit.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params: Positional parameters bound to the placeholders.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On SQL error.
        """
        conn = self._require_conn()
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise MemoryStoreError(f"Execute failed: {exc}") from exc

    def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        """Execute a DML statement for each params tuple in *params_seq*.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params_seq: Sequence of parameter tuples.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On SQL error.
        """
        conn = self._require_conn()
        try:
            conn.executemany(sql, params_seq)
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise MemoryStoreError(f"Executemany failed: {exc}") from exc

    def query(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        """Execute a SELECT statement and return all rows as dicts.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params: Positional parameters.

        Returns:
            A list of ``{column: value}`` dicts. Empty list if no rows match.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On SQL error.
        """
        conn = self._require_conn()
        try:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"Query failed: {exc}") from exc

    def query_one(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        """Execute a SELECT statement and return the first row or ``None``.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params: Positional parameters.

        Returns:
            A ``{column: value}`` dict for the first row, or ``None``.

        Raises:
            :class:`~canopus.core.errors.MemoryStoreError`: On SQL error.
        """
        conn = self._require_conn()
        try:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"Query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # FTS helpers
    # ------------------------------------------------------------------

    def create_fts_table(
        self,
        fts_table: str,
        content_table: str,
        content_column: str,
        *,
        tokenize: str = "unicode61",
    ) -> None:
        """Create an FTS5 content table linked to *content_table*.

        Args:
            fts_table: Name of the FTS virtual table to create.
            content_table: The real table that provides row content.
            content_column: The column in *content_table* indexed by FTS.
            tokenize: FTS5 tokenizer. Defaults to ``"unicode61"``.
        """
        conn = self._require_conn()
        sql = (
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table} USING fts5("
            f"  {content_column},"
            f"  content={content_table!r},"
            f"  content_rowid='rowid',"
            f"  tokenize={tokenize!r}"
            f")"
        )
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.Error as exc:
            raise MemoryStoreError(f"FTS table creation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise MemoryStoreError("Store is not open. Call open() first.")
        return self._conn

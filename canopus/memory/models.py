"""Memory record models.

Defines the typed data contracts used throughout the memory subsystem.

Key types:
- :class:`MemoryKind` — enumeration of memory record categories
- :class:`MemoryRecord` — a single persisted memory entry
- :class:`MemoryQuery` — parameters for a retrieval query
- :class:`MemoryContext` — assembled context passed to the reasoning pipeline
"""

from __future__ import annotations

import datetime
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MemoryKind(StrEnum):
    """Category of a memory record.

    Attributes:
        CONVERSATION: A recorded user/assistant exchange from ``chat`` or ``run``.
        FACT: A discrete factual statement stored explicitly by the user.
        SUMMARY: A condensed summary of a session or topic.
        SYSTEM: Internal bookkeeping records (session metadata, etc.).
    """

    CONVERSATION = "conversation"
    FACT = "fact"
    SUMMARY = "summary"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Core record
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """A single persisted memory entry.

    Attributes:
        id: Unique identifier (UUID4 string). Auto-generated if not supplied.
        kind: The category of memory, used for filtering and retrieval.
        content: The main text body of the memory. This is the field that
            full-text search runs against.
        tags: Free-form labels for filtering (e.g. ``["canopus", "plugin"]``).
        source: Where this memory originated, e.g. ``"chat"``, ``"run"``,
            ``"user"`` (manual ``canopus memory add``).
        importance: Relative importance, 0.0–1.0. Used in ranking. Default 0.5.
        session_id: The session that produced this record, if applicable.
        run_id: The run that produced this record, if applicable.
        metadata: Arbitrary structured payload for subsystem-specific data.
            Must be JSON-serialisable.
        created_at: UTC timestamp of creation (set automatically).
        updated_at: UTC timestamp of last update (set automatically on write).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: MemoryKind = MemoryKind.CONVERSATION
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str = "user"
    importance: float = 0.5
    session_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    model_config = {"frozen": False}

    def touch(self) -> None:
        """Update ``updated_at`` to now (UTC)."""
        self.updated_at = datetime.datetime.now(datetime.UTC)


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------


class MemoryQuery(BaseModel):
    """Parameters that control a memory retrieval operation.

    Attributes:
        text: Full-text search query. Empty string disables text filtering.
        kinds: Restrict results to these memory kinds. Empty = all kinds.
        tags: Require records to have at least one of these tags. Empty = no tag filter.
        source: Restrict results to this source string. ``None`` = no filter.
        session_id: Restrict to a specific session. ``None`` = no filter.
        limit: Maximum number of records to return. Defaults to 20.
        min_importance: Minimum importance threshold, 0.0–1.0. Default 0.0.
        recency_weight: Factor (0.0–1.0) that boosts recently created records
            in the result ranking. 0.0 = no recency boost, 1.0 = pure recency.
    """

    text: str = ""
    kinds: list[MemoryKind] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    session_id: str | None = None
    limit: int = 20
    min_importance: float = 0.0
    recency_weight: float = 0.3


# ---------------------------------------------------------------------------
# Context assembly output
# ---------------------------------------------------------------------------


class MemoryContext(BaseModel):
    """Assembled memory context ready for injection into the reasoning pipeline.

    Attributes:
        records: Retrieved and ranked memory records (most relevant first).
        query_text: The original query text used to build this context.
        truncated: ``True`` if the full result set was trimmed to fit the limit.
        total_found: Total number of records matched before truncation.
    """

    records: list[MemoryRecord]
    query_text: str
    truncated: bool = False
    total_found: int = 0

    def as_prompt_block(self, *, max_chars: int = 4000) -> str:
        """Render records as a compact text block for prompt injection.

        Args:
            max_chars: Soft character budget for the entire block. Records are
                included in order until the budget is exhausted.

        Returns:
            A formatted multi-line string, or an empty string if there are
            no records.
        """
        if not self.records:
            return ""

        lines: list[str] = ["[Memory context]"]
        used = len(lines[0])
        for i, rec in enumerate(self.records, 1):
            snippet = rec.content.strip()
            tag_str = f"  tags={rec.tags}" if rec.tags else ""
            line = f"{i}. [{rec.kind}] {snippet}{tag_str}"
            if used + len(line) > max_chars:
                lines.append(f"… ({self.total_found - i + 1} more not shown)")
                break
            lines.append(line)
            used += len(line)

        return "\n".join(lines)

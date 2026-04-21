"""Structured execution tracing for Canopus sessions.

Every meaningful Canopus invocation writes a JSON trace file to
``~/.canopus/traces/<run_id>.json``.  Traces capture:

- Session metadata (IDs, mode, profile, timestamps)
- A chronological list of typed events
- The final outcome and any error

The design is intentionally extensible: future phases add model invocation
events, capability call events, policy decisions, and token/latency metrics
without changing the storage format.

Usage::

    session = create_session(RequestMode.RUN, request="hello")
    writer = TraceWriter.from_session(session)

    writer.trace.add_event("request.received", {"text": "hello"})
    # ... do work ...
    writer.close(result_summary="done")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from canopus.core.errors import TracingError

if TYPE_CHECKING:
    from canopus.core.runtime import SessionRuntime


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------


class TraceEvent(BaseModel):
    """A single timestamped event within an execution trace.

    ``event_type`` follows a dot-namespaced convention, e.g.
    ``"session.started"``, ``"model.invoked"``, ``"capability.failed"``.
    ``data`` holds structured payload specific to the event type.
    """

    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trace model
# ---------------------------------------------------------------------------


class ExecutionTrace(BaseModel):
    """Complete execution record for a single Canopus session.

    Serialised to JSON and written to disk by :class:`TraceWriter`. Consumers
    can parse this file for debugging, auditing, or replay.
    """

    run_id: str
    session_id: str
    mode: str
    profile_name: str
    request: str | None

    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None

    # Populated by the reasoning pipeline once a provider is selected.
    model_provider: str | None = None
    model_name: str | None = None

    events: list[TraceEvent] = Field(default_factory=list)

    error: str | None = None
    result_summary: str | None = None

    def add_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Append a timestamped event to the trace.

        Args:
            event_type: Dot-namespaced event identifier.
            data: Optional structured payload for this event.
        """
        self.events.append(
            TraceEvent(event_type=event_type, data=data or {})
        )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class TraceWriter:
    """Serialises an :class:`ExecutionTrace` to a JSON file on disk.

    Obtain an instance via :meth:`from_session`, accumulate events via
    ``writer.trace.add_event(…)``, then call :meth:`close` to finalise and
    persist the trace.

    :meth:`close` is idempotent — calling it multiple times returns the same
    path without rewriting the file.
    """

    def __init__(self, trace: ExecutionTrace, trace_path: Path) -> None:
        self._trace = trace
        self._trace_path = trace_path
        self._closed = False

    @classmethod
    def from_session(cls, session: SessionRuntime) -> TraceWriter:
        """Construct a :class:`TraceWriter` from a live :class:`SessionRuntime`.

        Initialises the :class:`ExecutionTrace` with all session metadata so
        callers only need to add domain-specific events.
        """
        trace = ExecutionTrace(
            run_id=session.run_id,
            session_id=session.session_id,
            mode=str(session.mode),
            profile_name=session.profile.name,
            request=session.request,
            started_at=session.started_at,
        )
        return cls(trace=trace, trace_path=session.trace_path)

    @property
    def trace(self) -> ExecutionTrace:
        """The live trace being assembled."""
        return self._trace

    def close(
        self,
        error: str | None = None,
        result_summary: str | None = None,
    ) -> Path:
        """Finalise the trace and write it to disk.

        Sets ``completed_at``, ``duration_ms``, appends a ``trace.closed``
        event, then serialises the full trace as indented JSON.

        Args:
            error: Error message if the session failed.
            result_summary: Short plain-text summary of the outcome.

        Returns:
            The :class:`Path` where the trace was written.

        Raises:
            :class:`~canopus.core.errors.TracingError`: If the file cannot
                be written.
        """
        if self._closed:
            return self._trace_path

        now = datetime.now(UTC)
        self._trace.completed_at = now
        self._trace.duration_ms = (now - self._trace.started_at).total_seconds() * 1000
        self._trace.error = error
        self._trace.result_summary = result_summary
        self._trace.add_event("trace.closed")

        try:
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._trace.model_dump(mode="json")
            self._trace_path.write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            raise TracingError(
                f"Failed to write trace to {self._trace_path}: {exc}"
            ) from exc

        self._closed = True
        return self._trace_path

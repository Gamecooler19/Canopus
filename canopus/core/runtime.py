"""Session runtime model and lifecycle management.

The :class:`SessionRuntime` is the execution boundary for a single Canopus
invocation. Every command (``run``, ``chat``, ``doctor``, …) creates one
session, which carries identifiers, timing, profile, and configuration
throughout the request lifecycle.

:func:`create_session` is the primary factory function used by CLI commands.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from canopus.core.config import AppConfig, load_config
from canopus.core.errors import CanopusRuntimeError
from canopus.core.profiles import ProfileLoader, ProfileSettings

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RequestMode(StrEnum):
    """The operational mode of a Canopus session."""

    CHAT = "chat"
    RUN = "run"
    DOCTOR = "doctor"
    PROFILE = "profile"
    VERSION = "version"
    VOICE = "voice"
    WORKFLOW = "workflow"


# ---------------------------------------------------------------------------
# Session model
# ---------------------------------------------------------------------------


class SessionRuntime(BaseModel):
    """Execution context for a single Canopus invocation.

    Carries all the state needed to process a request and produce a trace:
    unique identifiers, timestamps, active profile, and resolved paths.

    This model is intentionally kept serialisation-friendly so it can be
    embedded in trace payloads or forwarded to sub-processes in future phases.

    Attributes:
        run_id: UUID identifying this specific invocation.
        session_id: UUID for the conversation-level session. In Phase 1
            ``session_id == run_id``; future phases will allow multiple
            ``run_id`` values to share a ``session_id`` across a conversation.
        mode: The :class:`RequestMode` for this invocation.
        profile: The active :class:`ProfileSettings` snapshot.
        request: The raw user request string, if applicable.
        started_at: UTC timestamp when the session was created.
        completed_at: UTC timestamp set by :meth:`finalize`.
        trace_path: Absolute path where the JSON trace will be written.
    """

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: RequestMode
    profile: ProfileSettings
    request: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    trace_path: Path

    model_config = {"arbitrary_types_allowed": True}

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> float | None:
        """Wall-clock duration in milliseconds, or ``None`` before :meth:`finalize`."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds() * 1000

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """Record the session end timestamp."""
        self.completed_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_session(
    mode: RequestMode,
    request: str | None = None,
    config: AppConfig | None = None,
) -> SessionRuntime:
    """Create and initialise a new :class:`SessionRuntime`.

    Loads configuration and the active profile, ensures all data directories
    exist, generates a unique ``run_id``, and resolves the trace output path.

    Args:
        mode: Operational mode for this session.
        request: Raw user request string, if applicable.
        config: Pre-loaded :class:`AppConfig`. If ``None``, loaded from disk.

    Returns:
        A fully initialised :class:`SessionRuntime` ready for use.

    Raises:
        :class:`~canopus.core.errors.CanopusRuntimeError`: If the active
            profile cannot be loaded.
    """
    resolved_config = config or load_config()
    resolved_config.paths.ensure_all()

    loader = ProfileLoader(profiles_dir=resolved_config.paths.profiles_dir)
    try:
        profile = loader.load(resolved_config.active_profile)
    except Exception as exc:
        raise CanopusRuntimeError(
            f"Failed to load profile {resolved_config.active_profile!r}: {exc}"
        ) from exc

    run_id = str(uuid.uuid4())
    trace_path = resolved_config.paths.traces_dir / f"{run_id}.json"

    return SessionRuntime(
        run_id=run_id,
        # session_id == run_id in Phase 1; future phases add conversation continuity
        session_id=run_id,
        mode=mode,
        profile=profile,
        request=request,
        trace_path=trace_path,
    )

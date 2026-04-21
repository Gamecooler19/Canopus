"""Invocation context passed to capability handlers at execution time.

A :class:`CapabilityContext` carries all the runtime information a handler
might need beyond its raw input: trace writer, active profile, and future
policy hooks. Handlers that need none of this can ignore it — it is always
available but never mandatory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canopus.core.profiles import ProfileSettings
    from canopus.core.tracing import TraceWriter


class CapabilityContext:
    """Runtime context injected into capability handler calls.

    Attributes:
        profile: The active runtime profile. Handlers may consult this for
            permission grants or network-access policies.
        writer: Optional trace writer. Handlers should call
            ``writer.trace.add_event(...)`` to record capability-internal
            events when useful.
    """

    def __init__(
        self,
        profile: ProfileSettings,
        writer: TraceWriter | None = None,
    ) -> None:
        self.profile = profile
        self.writer = writer

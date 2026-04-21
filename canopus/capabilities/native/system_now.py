"""``system.now`` — returns current local and UTC timestamp metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.specs import CapabilitySpec
from canopus.security.permissions import ConfirmationPolicy, Permission, SideEffectLevel

SPEC = CapabilitySpec(
    name="system.now",
    description="Returns the current local date, time, UTC time, and timezone name.",
    tags=["system", "time", "clock", "datetime"],
    permissions=[Permission.SYSTEM_INFO],
    side_effect_level=SideEffectLevel.NONE,
    confirmation_policy=ConfirmationPolicy.NEVER,
    transport="native",
    examples=[
        "what time is it",
        "what is today's date",
        "current time",
        "what day is it",
    ],
)


def handler(inputs: dict[str, Any], ctx: CapabilityContext) -> dict[str, Any]:
    """Return current timestamp metadata.

    The *inputs* dict is intentionally unused — this capability takes no
    parameters. It is kept in the signature for consistency with the
    handler contract.
    """
    now_utc = datetime.now(UTC)
    now_local = datetime.now(UTC).astimezone()  # system local tz
    local_tz_name = now_local.tzname() or "local"

    return {
        "utc_iso": now_utc.isoformat(),
        "local_iso": now_local.isoformat(),
        "local_date": now_local.strftime("%A, %d %B %Y"),
        "local_time": now_local.strftime("%H:%M:%S"),
        "timezone": local_tz_name,
        "unix_timestamp": int(now_utc.timestamp()),
    }

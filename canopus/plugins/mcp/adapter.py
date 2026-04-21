"""MCP adapter — normalize MCP tool definitions into capability registry entries.

The adapter is the boundary between the MCP world (McpToolSpec, McpClient) and
the capability world (CapabilitySpec, CapabilityHandler). After adaptation the
rest of the system treats MCP-backed capabilities identically to native
capabilities and legacy plugin capabilities. The only visible difference is
``spec.transport == "mcp"``.

The adapter pattern mirrors :mod:`canopus.plugins.legacy.adapter` intentionally
— both adapters feed into the same registry and execution path.
"""

from __future__ import annotations

from typing import Any

from canopus.capabilities.registry import CapabilityHandler
from canopus.capabilities.specs import CapabilitySpec
from canopus.plugins.mcp.client import McpClient
from canopus.plugins.mcp.errors import McpToolAdapterError
from canopus.plugins.mcp.models import McpToolSpec
from canopus.security.permissions import (
    ConfirmationPolicy,
    Permission,
    SideEffectLevel,
)


def adapt(
    tool_spec: McpToolSpec,
    server_name: str,
    client: McpClient,
) -> tuple[CapabilitySpec, CapabilityHandler]:
    """Convert an :class:`McpToolSpec` into a capability registry entry.

    The resulting capability name is ``"<server_name>.<tool_name>"``, matching
    the namespacing convention used by legacy plugins.

    Args:
        tool_spec: Tool definition returned by the transport's ``list_tools()``.
        server_name: Owning server's name, used as the capability namespace.
        client: Connected :class:`McpClient` whose ``call_tool`` method becomes
            the capability handler.

    Returns:
        A ``(CapabilitySpec, handler)`` pair ready for
        :meth:`~canopus.capabilities.registry.CapabilityRegistry.register`.

    Raises:
        :class:`~canopus.plugins.mcp.errors.McpToolAdapterError`: If an
            invalid permission, side-effect level, or confirmation policy
            string is encountered.
    """
    permissions = _parse_permissions(tool_spec.permissions, server_name, tool_spec.name)
    side_effect_level = _parse_side_effect(
        tool_spec.side_effect_level, server_name, tool_spec.name
    )
    confirmation_policy = _parse_confirmation(
        tool_spec.confirmation_policy, server_name, tool_spec.name
    )

    cap_name = f"{server_name}.{tool_spec.name}"

    spec = CapabilitySpec(
        name=cap_name,
        description=tool_spec.description,
        tags=tool_spec.tags,
        permissions=permissions,
        side_effect_level=side_effect_level,
        confirmation_policy=confirmation_policy,
        transport="mcp",
        examples=tool_spec.examples,
    )

    # Capture tool name in closure; client reference is also captured.
    tool_name = tool_spec.name
    _client = client

    def handler(inputs: dict[str, Any], ctx: object) -> dict[str, Any]:
        return _client.call_tool(tool_name, inputs)

    return spec, handler


# ---------------------------------------------------------------------------
# Enum parsing helpers (mirrors canopus.plugins.legacy.adapter)
# ---------------------------------------------------------------------------


def _parse_permissions(
    raw: list[str],
    server_name: str,
    tool_name: str,
) -> list[Permission]:
    result: list[Permission] = []
    for perm_str in raw:
        try:
            result.append(Permission(perm_str))
        except ValueError:
            raise McpToolAdapterError(
                server_name, tool_name, f"Unknown permission: {perm_str!r}"
            ) from None
    return result


def _parse_side_effect(
    raw: str,
    server_name: str,
    tool_name: str,
) -> SideEffectLevel:
    try:
        return SideEffectLevel(raw)
    except ValueError:
        raise McpToolAdapterError(
            server_name,
            tool_name,
            f"Unknown side_effect_level: {raw!r}. "
            f"Valid values: {[e.value for e in SideEffectLevel]}",
        ) from None


def _parse_confirmation(
    raw: str,
    server_name: str,
    tool_name: str,
) -> ConfirmationPolicy:
    try:
        return ConfirmationPolicy(raw)
    except ValueError:
        raise McpToolAdapterError(
            server_name,
            tool_name,
            f"Unknown confirmation_policy: {raw!r}. "
            f"Valid values: {[e.value for e in ConfirmationPolicy]}",
        ) from None

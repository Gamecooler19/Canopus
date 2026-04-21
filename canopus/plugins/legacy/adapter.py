"""Legacy plugin adapter — normalise plugin capability defs into registry entries.

The adapter is the boundary between the plugin world (dict-based contracts,
arbitrary callables) and the capability world (typed :class:`CapabilitySpec`
objects + registry handlers).

After adaptation, the rest of the system treats a plugin capability identically
to a native capability. The only visible difference is
``spec.transport == "legacy_plugin"``.
"""

from __future__ import annotations

from typing import Any

from canopus.capabilities.registry import CapabilityHandler
from canopus.capabilities.specs import CapabilitySpec
from canopus.plugins.legacy.errors import PluginCapabilityDefError
from canopus.plugins.legacy.models import PluginCapabilityDef
from canopus.security.permissions import (
    ConfirmationPolicy,
    Permission,
    SideEffectLevel,
)


def adapt(
    cap_def: PluginCapabilityDef,
    plugin_name: str,
) -> tuple[CapabilitySpec, CapabilityHandler]:
    """Convert a validated :class:`PluginCapabilityDef` into a registry entry.

    Args:
        cap_def: Validated capability definition produced by the loader.
        plugin_name: The owning plugin's name, used for error messages.

    Returns:
        A ``(CapabilitySpec, handler)`` pair ready to be passed to
        :meth:`~canopus.capabilities.registry.CapabilityRegistry.register`.

    Raises:
        :class:`~canopus.plugins.legacy.errors.PluginCapabilityDefError`: If
            an invalid permission or side-effect string is encountered.
    """
    permissions = _parse_permissions(cap_def.permissions, plugin_name, cap_def.name)
    side_effect_level = _parse_side_effect(
        cap_def.side_effect_level, plugin_name, cap_def.name
    )
    confirmation_policy = _parse_confirmation(
        cap_def.confirmation_policy, plugin_name, cap_def.name
    )

    spec = CapabilitySpec(
        name=cap_def.name,
        description=cap_def.description,
        tags=cap_def.tags,
        permissions=permissions,
        side_effect_level=side_effect_level,
        confirmation_policy=confirmation_policy,
        transport="legacy_plugin",
        examples=cap_def.examples,
    )

    # Wrap the plugin's raw handler to ensure it always receives two arguments
    # (inputs: dict, ctx: CapabilityContext) matching the registry contract.
    raw_handler = cap_def.handler

    def handler(inputs: dict[str, Any], ctx: object) -> dict[str, Any]:
        return raw_handler(inputs, ctx)  # type: ignore[no-any-return]

    return spec, handler


# ---------------------------------------------------------------------------
# Enum parsing helpers
# ---------------------------------------------------------------------------


def _parse_permissions(
    raw: list[str],
    plugin_name: str,
    cap_name: str,
) -> list[Permission]:
    """Convert string permission tokens to :class:`~canopus.security.permissions.Permission` enums.

    Unknown strings are accepted as-is via ``Permission(value)`` if they exist;
    otherwise a :class:`~canopus.plugins.legacy.errors.PluginCapabilityDefError`
    is raised.
    """
    result: list[Permission] = []
    for token in raw:
        try:
            result.append(Permission(token))
        except ValueError:
            raise PluginCapabilityDefError(
                plugin_name,
                cap_name,
                f"Unknown permission token {token!r}. "
                f"Valid values: {[p.value for p in Permission]}",
            ) from None
    return result


def _parse_side_effect(
    raw: str,
    plugin_name: str,
    cap_name: str,
) -> SideEffectLevel:
    try:
        return SideEffectLevel(raw)
    except ValueError:
        raise PluginCapabilityDefError(
            plugin_name,
            cap_name,
            f"Unknown side_effect_level {raw!r}. "
            f"Valid values: {[s.value for s in SideEffectLevel]}",
        ) from None


def _parse_confirmation(
    raw: str,
    plugin_name: str,
    cap_name: str,
) -> ConfirmationPolicy:
    try:
        return ConfirmationPolicy(raw)
    except ValueError:
        raise PluginCapabilityDefError(
            plugin_name,
            cap_name,
            f"Unknown confirmation_policy {raw!r}. "
            f"Valid values: {[c.value for c in ConfirmationPolicy]}",
        ) from None

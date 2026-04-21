"""MCP manager — server initialization, tool loading, and capability registration.

:class:`McpManager` is the central service for the MCP subsystem. It:

1. Takes a list of :class:`~canopus.core.config.McpServerConfig` objects.
2. Creates an :class:`~canopus.plugins.mcp.client.McpClient` for each enabled server.
3. Calls ``list_tools()`` on the client to retrieve the tool inventory.
4. Adapts each tool via :func:`~canopus.plugins.mcp.adapter.adapt`.
5. Registers the resulting capabilities in the global
   :class:`~canopus.capabilities.registry.CapabilityRegistry`.
6. Keeps a :class:`~canopus.plugins.mcp.models.McpServerRecord` per server
   so CLI commands can inspect status, errors, and warnings.

One bad server must not break initialization. All per-server errors are
captured in the record and surfaced via ``canopus mcp doctor`` — not raised
to the caller.

Module-level singleton
----------------------
:func:`initialize` creates and populates the global manager.
:func:`get_manager` retrieves it (or ``None`` before initialization).
:func:`reset_for_testing` resets the singleton for test isolation.
"""

from __future__ import annotations

from canopus.capabilities.registry import CapabilityRegistry
from canopus.core.config import McpServerConfig
from canopus.core.errors import CapabilityError
from canopus.plugins.mcp.adapter import adapt
from canopus.plugins.mcp.client import McpClient
from canopus.plugins.mcp.errors import McpConnectionError, McpToolAdapterError
from canopus.plugins.mcp.models import McpServerRecord, McpServerStatus
from canopus.plugins.mcp.transports import McpTransport

# ---------------------------------------------------------------------------
# Manager class
# ---------------------------------------------------------------------------


class McpManager:
    """Initializes configured MCP servers and registers their tools.

    Args:
        server_configs: List of server definitions from :class:`~canopus.core.config.AppConfig`.
        registry: The capability registry to register MCP tools into.
    """

    def __init__(
        self,
        server_configs: list[McpServerConfig],
        registry: CapabilityRegistry,
    ) -> None:
        self._configs = server_configs
        self._registry = registry
        self._records: dict[str, McpServerRecord] = {}

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize_all(self) -> list[McpServerRecord]:
        """Initialize every configured server and return all records.

        Servers are processed in configuration order. A server that fails
        to connect or whose all tools fail to register does not prevent
        subsequent servers from loading.

        Returns:
            All :class:`~canopus.plugins.mcp.models.McpServerRecord` objects
            produced by this run (same as :meth:`get_records`).
        """
        self._records.clear()
        for config in self._configs:
            record = self._load_server(config)
            self._records[config.name] = record
        return list(self._records.values())

    def _load_server(self, config: McpServerConfig) -> McpServerRecord:
        """Load a single server and return its record. Never raises."""
        if not config.enabled:
            return McpServerRecord(
                name=config.name,
                transport=config.transport,
                description=config.description,
                enabled=False,
                status=McpServerStatus.DISABLED,
            )

        # ── Create transport and client ───────────────────────────────────
        try:
            transport = create_transport(config)
            client = McpClient(config.name, transport)
            tools = client.list_tools()
        except McpConnectionError as exc:
            return McpServerRecord(
                name=config.name,
                transport=config.transport,
                description=config.description,
                enabled=True,
                status=McpServerStatus.FAILED,
                error=str(exc),
            )
        except Exception as exc:
            return McpServerRecord(
                name=config.name,
                transport=config.transport,
                description=config.description,
                enabled=True,
                status=McpServerStatus.FAILED,
                error=f"Unexpected error during initialization: {exc}",
            )

        # ── Register tools ────────────────────────────────────────────────
        registered: list[str] = []
        warnings: list[str] = []

        for tool_spec in tools:
            try:
                spec, handler = adapt(tool_spec, config.name, client)
                self._registry.register(spec, handler)
                registered.append(spec.name)
            except McpToolAdapterError as exc:
                warnings.append(str(exc))
            except CapabilityError as exc:
                # Duplicate capability name in the registry
                warnings.append(
                    f"Tool {tool_spec.name!r} skipped: {exc}"
                )
            except Exception as exc:
                warnings.append(
                    f"Tool {tool_spec.name!r} registration failed unexpectedly: {exc}"
                )

        # ── Determine final status ────────────────────────────────────────
        if registered and not warnings:
            status = McpServerStatus.CONNECTED
        elif registered:
            status = McpServerStatus.PARTIAL
        else:
            # No tools registered at all
            status = McpServerStatus.FAILED
            if not warnings:
                warnings.append("Server exposed no tools.")

        return McpServerRecord(
            name=config.name,
            transport=config.transport,
            description=config.description,
            enabled=True,
            status=status,
            tool_names=registered,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Record access
    # ------------------------------------------------------------------

    def get_records(self) -> list[McpServerRecord]:
        """Return all server records, sorted by server name."""
        return sorted(self._records.values(), key=lambda r: r.name)

    def get_record(self, name: str) -> McpServerRecord | None:
        """Return the record for a server by name, or ``None``."""
        return self._records.get(name)

    def get_connected(self) -> list[McpServerRecord]:
        """Return records for servers that connected successfully (including partial)."""
        return [
            r for r in self._records.values()
            if r.status in (McpServerStatus.CONNECTED, McpServerStatus.PARTIAL)
        ]

    def get_failed(self) -> list[McpServerRecord]:
        """Return records for servers that failed to connect."""
        return [
            r for r in self._records.values()
            if r.status == McpServerStatus.FAILED
        ]

    def get_disabled(self) -> list[McpServerRecord]:
        """Return records for servers that are disabled in config."""
        return [
            r for r in self._records.values()
            if r.status == McpServerStatus.DISABLED
        ]


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------


def create_transport(config: McpServerConfig) -> McpTransport:
    """Instantiate the correct transport for a server config.

    Args:
        config: Server configuration specifying ``transport``, ``command``,
            ``args``, and ``env``.

    Returns:
        A ready-to-use transport instance.

    Raises:
        :class:`~canopus.plugins.mcp.errors.McpConnectionError`: If the
            transport type is unknown or if required fields are missing.
    """
    from canopus.plugins.mcp.transports.mock import MockMcpTransport
    from canopus.plugins.mcp.transports.stdio import StdioMcpTransport

    if config.transport == "mock":
        return MockMcpTransport()

    if config.transport == "stdio":
        command = config.command
        if not command:
            raise McpConnectionError(
                config.name,
                "Stdio transport requires a 'command' field in config.",
            )
        return StdioMcpTransport(
            server_name=config.name,
            command=command,
            args=config.args,
            env=config.env,
        )

    raise McpConnectionError(
        config.name,
        f"Unknown transport type: {config.transport!r}. "
        "Supported types: 'mock', 'stdio'.",
    )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: McpManager | None = None


def initialize(
    server_configs: list[McpServerConfig],
    registry: CapabilityRegistry,
) -> McpManager:
    """Create and initialize the global :class:`McpManager`.

    Replaces any previously initialized manager. Call this once at startup
    (typically from :func:`canopus.cli.app._bootstrap_mcp`).

    Args:
        server_configs: List of server configs from :class:`~canopus.core.config.AppConfig`.
        registry: The capability registry to register MCP tools into.

    Returns:
        The newly created and initialized manager.
    """
    global _manager
    _manager = McpManager(server_configs=server_configs, registry=registry)
    _manager.initialize_all()
    return _manager


def get_manager() -> McpManager | None:
    """Return the global :class:`McpManager`, or ``None`` if not initialized."""
    return _manager


def reset_for_testing() -> None:
    """Reset the global manager to ``None``.

    For use in tests only. Production code must not call this.
    """
    global _manager
    _manager = None

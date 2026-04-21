"""Tests for Phase 4B: MCP foundation and adapter layer.

Covers:
- MCP error types
- MCP config model (McpServerConfig validation)
- MCP tool spec and server record models
- MockMcpTransport (list_tools, call_tool, edge cases)
- StdioMcpTransport (stub behaviour)
- McpClient (error normalization)
- MCP adapter (spec normalization, permission/enum parsing)
- McpManager (happy path, disabled servers, failed servers, duplicate tools)
- Manager singleton (initialize, get_manager, reset_for_testing)
- create_transport factory (mock, stdio, unknown)
- CLI: canopus mcp list / inspect / doctor
- End-to-end: invoking an MCP capability through the general capability path
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from canopus.capabilities.registry import CapabilityRegistry
from canopus.core.config import McpServerConfig
from canopus.plugins.mcp.adapter import adapt
from canopus.plugins.mcp.client import McpClient
from canopus.plugins.mcp.errors import (
    McpConnectionError,
    McpToolAdapterError,
    McpToolCallError,
)
from canopus.plugins.mcp.manager import (
    McpManager,
    create_transport,
    get_manager,
    initialize,
    reset_for_testing,
)
from canopus.plugins.mcp.models import McpServerRecord, McpServerStatus, McpToolSpec
from canopus.plugins.mcp.transports import McpTransport
from canopus.plugins.mcp.transports.mock import MockMcpTransport
from canopus.plugins.mcp.transports.stdio import StdioMcpTransport

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_mcp_manager_after_each():
    """Ensure the global MCP manager is cleared between tests."""
    yield
    reset_for_testing()


def _mock_config(
    name: str = "mock",
    enabled: bool = True,
    transport: str = "mock",
    description: str = "Test mock server",
) -> McpServerConfig:
    return McpServerConfig(
        name=name,
        enabled=enabled,
        transport=transport,
        description=description,
    )


# ---------------------------------------------------------------------------
# MCP error types
# ---------------------------------------------------------------------------


class TestMcpErrors:
    def test_mcp_connection_error(self) -> None:
        err = McpConnectionError("my-server", "timeout")
        assert "my-server" in str(err)
        assert "timeout" in str(err)
        assert err.server_name == "my-server"
        assert err.reason == "timeout"

    def test_mcp_tool_call_error(self) -> None:
        err = McpToolCallError("srv", "echo", "bad response")
        assert "srv" in str(err)
        assert "echo" in str(err)
        assert "bad response" in str(err)

    def test_mcp_tool_adapter_error(self) -> None:
        err = McpToolAdapterError("srv", "my_tool", "unknown permission")
        assert "srv" in str(err)
        assert "my_tool" in str(err)
        assert "unknown permission" in str(err)

    def test_mcp_tool_adapter_error_no_tool_name(self) -> None:
        err = McpToolAdapterError("srv", None, "bad value")
        assert "<unnamed>" in str(err)


# ---------------------------------------------------------------------------
# MCP config model
# ---------------------------------------------------------------------------


class TestMcpServerConfig:
    def test_defaults(self) -> None:
        cfg = McpServerConfig(name="test")
        assert cfg.enabled is True
        assert cfg.transport == "mock"
        assert cfg.command is None
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.description == ""

    def test_full_config(self) -> None:
        cfg = McpServerConfig(
            name="my-server",
            enabled=False,
            transport="stdio",
            command="/usr/local/bin/my-mcp",
            args=["--verbose"],
            env={"FOO": "bar"},
            description="A test server.",
        )
        assert cfg.enabled is False
        assert cfg.command == "/usr/local/bin/my-mcp"
        assert cfg.args == ["--verbose"]
        assert cfg.env == {"FOO": "bar"}

    def test_name_required(self) -> None:
        with pytest.raises(ValueError):
            McpServerConfig()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# MCP models
# ---------------------------------------------------------------------------


class TestMcpToolSpec:
    def test_minimal(self) -> None:
        spec = McpToolSpec(name="echo", description="Echo text.")
        assert spec.tags == []
        assert spec.permissions == []
        assert spec.side_effect_level == "none"
        assert spec.confirmation_policy == "never"
        assert spec.examples == []

    def test_full(self) -> None:
        spec = McpToolSpec(
            name="upload",
            description="Upload a file.",
            tags=["file", "network"],
            permissions=["fs.read", "network.http"],
            side_effect_level="medium",
            confirmation_policy="smart",
            examples=["upload this file"],
        )
        assert spec.permissions == ["fs.read", "network.http"]
        assert spec.side_effect_level == "medium"


class TestMcpServerRecord:
    def test_defaults(self) -> None:
        record = McpServerRecord(name="srv", transport="mock")
        assert record.tool_names == []
        assert record.error is None
        assert record.warnings == []
        assert record.status == McpServerStatus.DISABLED

    def test_status_values(self) -> None:
        assert McpServerStatus.CONNECTED == "connected"
        assert McpServerStatus.PARTIAL == "partial"
        assert McpServerStatus.FAILED == "failed"
        assert McpServerStatus.DISABLED == "disabled"


# ---------------------------------------------------------------------------
# MockMcpTransport
# ---------------------------------------------------------------------------


class TestMockMcpTransport:
    def test_satisfies_protocol(self) -> None:
        t = MockMcpTransport()
        assert isinstance(t, McpTransport)

    def test_list_tools_returns_three_tools(self) -> None:
        t = MockMcpTransport()
        tools = t.list_tools()
        assert len(tools) == 3
        names = {tool.name for tool in tools}
        assert names == {"echo", "word_count", "now"}

    def test_echo_returns_input(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("echo", {"text": "hello world"})
        assert result == {"text": "hello world"}

    def test_echo_empty_input(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("echo", {})
        assert result == {"text": ""}

    def test_word_count_basic(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("word_count", {"text": "one two three"})
        assert result["words"] == 3
        assert result["characters"] == 13
        assert result["lines"] == 1

    def test_word_count_multiline(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("word_count", {"text": "line one\nline two\n"})
        assert result["lines"] == 2
        assert result["non_empty_lines"] == 2

    def test_word_count_empty(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("word_count", {"text": ""})
        assert result["words"] == 0
        assert result["characters"] == 0

    def test_now_returns_iso_timestamp(self) -> None:
        t = MockMcpTransport()
        result = t.call_tool("now", {})
        assert "utc_iso" in result
        assert "unix_timestamp" in result
        # Should be parseable
        from datetime import datetime
        dt = datetime.fromisoformat(result["utc_iso"])
        assert dt.tzinfo is not None

    def test_unknown_tool_raises_tool_call_error(self) -> None:
        t = MockMcpTransport()
        with pytest.raises(McpToolCallError, match="Unknown mock tool"):
            t.call_tool("nonexistent", {})

    def test_close_is_noop(self) -> None:
        t = MockMcpTransport()
        t.close()  # Must not raise


# ---------------------------------------------------------------------------
# StdioMcpTransport
# ---------------------------------------------------------------------------


class TestStdioMcpTransport:
    def test_list_tools_raises(self) -> None:
        t = StdioMcpTransport("my-srv", command="./server")
        with pytest.raises(McpConnectionError, match="not yet implemented"):
            t.list_tools()

    def test_call_tool_raises(self) -> None:
        t = StdioMcpTransport("my-srv", command="./server")
        with pytest.raises(McpConnectionError, match="not yet implemented"):
            t.call_tool("echo", {})

    def test_close_is_safe(self) -> None:
        t = StdioMcpTransport("my-srv", command="./server")
        t.close()  # Must not raise


# ---------------------------------------------------------------------------
# McpClient
# ---------------------------------------------------------------------------


class TestMcpClient:
    def test_server_name_property(self) -> None:
        client = McpClient("mock", MockMcpTransport())
        assert client.server_name == "mock"

    def test_list_tools_delegates(self) -> None:
        client = McpClient("mock", MockMcpTransport())
        tools = client.list_tools()
        assert len(tools) == 3

    def test_call_tool_delegates(self) -> None:
        client = McpClient("mock", MockMcpTransport())
        result = client.call_tool("echo", {"text": "hi"})
        assert result == {"text": "hi"}

    def test_call_tool_wraps_generic_exception(self) -> None:
        class BrokenTransport:
            def list_tools(self) -> list[McpToolSpec]:
                return []

            def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError("connection reset")

            def close(self) -> None:
                pass

        client = McpClient("broken", BrokenTransport())  # type: ignore[arg-type]
        with pytest.raises(McpToolCallError, match="connection reset"):
            client.call_tool("echo", {})

    def test_list_tools_wraps_generic_exception(self) -> None:
        class BrokenTransport:
            def list_tools(self) -> list[McpToolSpec]:
                raise OSError("pipe broken")

            def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return {}

            def close(self) -> None:
                pass

        client = McpClient("broken", BrokenTransport())  # type: ignore[arg-type]
        with pytest.raises(McpConnectionError, match="pipe broken"):
            client.list_tools()

    def test_close_suppresses_errors(self) -> None:
        class FailingTransport:
            def list_tools(self) -> list[McpToolSpec]:
                return []

            def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                return {}

            def close(self) -> None:
                raise RuntimeError("close failed")

        client = McpClient("bad", FailingTransport())  # type: ignore[arg-type]
        client.close()  # Must not raise


# ---------------------------------------------------------------------------
# MCP adapter
# ---------------------------------------------------------------------------


class TestMcpAdapter:
    def _make_spec(self, **kwargs: Any) -> McpToolSpec:
        defaults: dict[str, Any] = {"name": "echo", "description": "Echo text."}
        defaults.update(kwargs)
        return McpToolSpec(**defaults)

    def _make_client(self) -> McpClient:
        return McpClient("testserver", MockMcpTransport())

    def test_adapt_produces_correct_spec(self) -> None:
        tool = self._make_spec()
        spec, handler = adapt(tool, "testserver", self._make_client())
        assert spec.name == "testserver.echo"
        assert spec.transport == "mcp"
        assert spec.description == "Echo text."

    def test_adapt_namespaces_tool_name(self) -> None:
        tool = self._make_spec(name="word_count")
        spec, _ = adapt(tool, "myserver", self._make_client())
        assert spec.name == "myserver.word_count"

    def test_adapt_permissions_parsed(self) -> None:
        tool = self._make_spec(permissions=["fs.read", "network.http"])
        spec, _ = adapt(tool, "s", self._make_client())
        from canopus.security.permissions import Permission
        assert Permission.FS_READ in spec.permissions
        assert Permission.NETWORK_HTTP in spec.permissions

    def test_adapt_invalid_permission_raises(self) -> None:
        tool = self._make_spec(permissions=["bad.permission"])
        with pytest.raises(McpToolAdapterError, match="Unknown permission"):
            adapt(tool, "s", self._make_client())

    def test_adapt_side_effect_level(self) -> None:
        from canopus.security.permissions import SideEffectLevel
        tool = self._make_spec(side_effect_level="high")
        spec, _ = adapt(tool, "s", self._make_client())
        assert spec.side_effect_level == SideEffectLevel.HIGH

    def test_adapt_invalid_side_effect_raises(self) -> None:
        tool = self._make_spec(side_effect_level="catastrophic")
        with pytest.raises(McpToolAdapterError, match="Unknown side_effect_level"):
            adapt(tool, "s", self._make_client())

    def test_adapt_confirmation_policy(self) -> None:
        from canopus.security.permissions import ConfirmationPolicy
        tool = self._make_spec(confirmation_policy="always")
        spec, _ = adapt(tool, "s", self._make_client())
        assert spec.confirmation_policy == ConfirmationPolicy.ALWAYS

    def test_adapt_handler_calls_client(self) -> None:
        tool = self._make_spec(name="echo")
        client = McpClient("mock", MockMcpTransport())
        _, handler = adapt(tool, "mock", client)
        result = handler({"text": "hello"}, None)
        assert result == {"text": "hello"}

    def test_adapt_tags_preserved(self) -> None:
        tool = self._make_spec(tags=["a", "b"])
        spec, _ = adapt(tool, "s", self._make_client())
        assert spec.tags == ["a", "b"]

    def test_adapt_examples_preserved(self) -> None:
        tool = self._make_spec(examples=["do the echo thing"])
        spec, _ = adapt(tool, "s", self._make_client())
        assert spec.examples == ["do the echo thing"]


# ---------------------------------------------------------------------------
# create_transport factory
# ---------------------------------------------------------------------------


class TestCreateTransport:
    def test_mock_transport(self) -> None:
        cfg = McpServerConfig(name="test", transport="mock")
        t = create_transport(cfg)
        assert isinstance(t, MockMcpTransport)

    def test_stdio_transport(self) -> None:
        cfg = McpServerConfig(name="test", transport="stdio", command="./srv")
        t = create_transport(cfg)
        assert isinstance(t, StdioMcpTransport)

    def test_stdio_without_command_raises(self) -> None:
        cfg = McpServerConfig(name="test", transport="stdio")
        with pytest.raises(McpConnectionError, match="command"):
            create_transport(cfg)

    def test_unknown_transport_raises(self) -> None:
        cfg = McpServerConfig(name="test", transport="websocket")
        with pytest.raises(McpConnectionError, match="Unknown transport"):
            create_transport(cfg)


# ---------------------------------------------------------------------------
# McpManager
# ---------------------------------------------------------------------------


class TestMcpManager:
    def test_empty_configs_loads_nothing(self) -> None:
        reg = CapabilityRegistry()
        manager = McpManager(server_configs=[], registry=reg)
        records = manager.initialize_all()
        assert records == []

    def test_mock_server_connects_and_registers_tools(self) -> None:
        reg = CapabilityRegistry()
        manager = McpManager(server_configs=[_mock_config()], registry=reg)
        manager.initialize_all()
        assert len(manager.get_connected()) == 1
        record = manager.get_record("mock")
        assert record is not None
        assert record.status == McpServerStatus.CONNECTED
        assert "mock.echo" in record.tool_names
        assert "mock.word_count" in record.tool_names
        assert "mock.now" in record.tool_names

    def test_tools_registered_in_capability_registry(self) -> None:
        reg = CapabilityRegistry()
        manager = McpManager(server_configs=[_mock_config()], registry=reg)
        manager.initialize_all()
        assert reg.contains("mock.echo")
        assert reg.contains("mock.word_count")
        assert reg.contains("mock.now")
        spec = reg.get("mock.echo")
        assert spec.transport == "mcp"

    def test_disabled_server_not_connected(self) -> None:
        reg = CapabilityRegistry()
        cfg = _mock_config(enabled=False)
        manager = McpManager(server_configs=[cfg], registry=reg)
        manager.initialize_all()
        assert len(manager.get_connected()) == 0
        assert len(manager.get_disabled()) == 1
        record = manager.get_record("mock")
        assert record is not None
        assert record.status == McpServerStatus.DISABLED
        assert len(reg) == 0

    def test_failed_server_does_not_stop_good_server(self) -> None:
        reg = CapabilityRegistry()
        good_cfg = _mock_config(name="good", transport="mock")
        bad_cfg = McpServerConfig(name="bad", transport="stdio")  # missing command
        manager = McpManager(server_configs=[bad_cfg, good_cfg], registry=reg)
        manager.initialize_all()
        assert manager.get_record("good") is not None
        assert manager.get_record("good").status == McpServerStatus.CONNECTED  # type: ignore[union-attr]
        assert manager.get_record("bad") is not None
        assert manager.get_record("bad").status == McpServerStatus.FAILED  # type: ignore[union-attr]
        assert reg.contains("good.echo")

    def test_failed_server_has_error_message(self) -> None:
        reg = CapabilityRegistry()
        bad_cfg = McpServerConfig(name="bad", transport="stdio")
        manager = McpManager(server_configs=[bad_cfg], registry=reg)
        manager.initialize_all()
        record = manager.get_record("bad")
        assert record is not None
        assert record.error is not None

    def test_duplicate_tool_name_second_is_warned(self) -> None:
        reg = CapabilityRegistry()
        # Two servers with the same tool name "echo" would produce "srv1.echo" and "srv2.echo"
        # — these don't conflict. Real conflict would require overlapping namespaces.
        # Force a conflict by pre-registering "mock.echo" in the registry.
        from canopus.capabilities.specs import CapabilitySpec
        from canopus.security.permissions import ConfirmationPolicy, SideEffectLevel
        pre_spec = CapabilitySpec(
            name="mock.echo",
            description="Pre-existing",
            transport="native",
            side_effect_level=SideEffectLevel.NONE,
            confirmation_policy=ConfirmationPolicy.NEVER,
        )
        reg.register(pre_spec, lambda inputs, ctx: {})

        cfg = _mock_config()
        manager = McpManager(server_configs=[cfg], registry=reg)
        manager.initialize_all()
        record = manager.get_record("mock")
        assert record is not None
        # mock.echo could not be re-registered
        assert "mock.echo" not in record.tool_names
        # Other tools should still be registered
        assert "mock.word_count" in record.tool_names
        # Status should be PARTIAL (some tools registered, some not)
        assert record.status == McpServerStatus.PARTIAL

    def test_get_records_sorted_by_name(self) -> None:
        reg = CapabilityRegistry()
        configs = [
            _mock_config(name="zebra"),
            _mock_config(name="alpha"),
        ]
        manager = McpManager(server_configs=configs, registry=reg)
        manager.initialize_all()
        names = [r.name for r in manager.get_records()]
        assert names == ["alpha", "zebra"]

    def test_get_record_unknown_returns_none(self) -> None:
        reg = CapabilityRegistry()
        manager = McpManager(server_configs=[], registry=reg)
        manager.initialize_all()
        assert manager.get_record("ghost") is None

    def test_multiple_mock_servers_namespaced_separately(self) -> None:
        reg = CapabilityRegistry()
        configs = [
            _mock_config(name="alpha"),
            _mock_config(name="beta"),
        ]
        manager = McpManager(server_configs=configs, registry=reg)
        manager.initialize_all()
        assert reg.contains("alpha.echo")
        assert reg.contains("beta.echo")
        assert reg.contains("alpha.word_count")
        assert reg.contains("beta.word_count")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestMcpManagerSingleton:
    def test_initialize_creates_global_manager(self) -> None:
        assert get_manager() is None
        reg = CapabilityRegistry()
        manager = initialize(server_configs=[], registry=reg)
        assert get_manager() is manager

    def test_reset_clears_manager(self) -> None:
        reg = CapabilityRegistry()
        initialize(server_configs=[], registry=reg)
        assert get_manager() is not None
        reset_for_testing()
        assert get_manager() is None

    def test_initialize_twice_replaces_manager(self) -> None:
        reg = CapabilityRegistry()
        m1 = initialize(server_configs=[], registry=reg)
        m2 = initialize(server_configs=[], registry=reg)
        assert get_manager() is m2
        assert m1 is not m2


# ---------------------------------------------------------------------------
# CLI: canopus mcp list
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_manager_with_mock(patched_config):  # type: ignore[no-untyped-def]
    """Initialize a global MCP manager with one mock server."""
    from canopus.capabilities.native.register import register_all
    from canopus.capabilities.registry import registry as global_reg
    register_all(overwrite=True)
    manager = initialize(
        server_configs=[_mock_config()],
        registry=global_reg,
    )
    yield manager
    # Teardown: remove registered MCP tool capabilities from the global registry
    for record in manager.get_records():
        for cap_name in record.tool_names:
            global_reg.unregister(cap_name)


class TestMcpListCLI:
    def test_mcp_list_shows_servers(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "list"])
        assert result.exit_code == 0, result.output
        assert "mock" in result.output

    def test_mcp_list_shows_transport(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "list"])
        assert result.exit_code == 0, result.output
        assert "mock" in result.output

    def test_mcp_list_no_manager_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "list"])
        assert result.exit_code != 0

    def test_mcp_list_filter_by_status(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "list", "--status", "connected"])
        assert result.exit_code == 0, result.output
        assert "mock" in result.output

    def test_mcp_list_filter_invalid_status(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "list", "--status", "unknown_status"])
        assert result.exit_code != 0


class TestMcpInspectCLI:
    def test_mcp_inspect_shows_server(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "inspect", "mock"])
        assert result.exit_code == 0, result.output
        assert "mock" in result.output
        assert "mock.echo" in result.output
        assert "mock.word_count" in result.output

    def test_mcp_inspect_unknown_server_exits_nonzero(
        self, patched_config, mcp_manager_with_mock
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "inspect", "ghost"])
        assert result.exit_code != 0

    def test_mcp_inspect_failed_server_shows_error(self, patched_config) -> None:
        from canopus.capabilities.native.register import register_all
        from canopus.capabilities.registry import registry as global_reg
        register_all(overwrite=True)
        # A stdio server without a command will fail
        bad_cfg = McpServerConfig(name="broken", transport="stdio")
        initialize(server_configs=[bad_cfg], registry=global_reg)

        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "inspect", "broken"])
        assert result.exit_code == 0, result.output
        assert "broken" in result.output
        assert "Error" in result.output or "error" in result.output


class TestMcpDoctorCLI:
    def test_mcp_doctor_all_healthy(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "doctor"])
        assert result.exit_code == 0, result.output
        assert "healthy" in result.output.lower() or "connected" in result.output.lower()

    def test_mcp_doctor_shows_failure(self, patched_config) -> None:
        from canopus.capabilities.native.register import register_all
        from canopus.capabilities.registry import registry as global_reg
        register_all(overwrite=True)
        bad_cfg = McpServerConfig(name="broken", transport="stdio")
        initialize(server_configs=[bad_cfg], registry=global_reg)

        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "doctor"])
        assert result.exit_code == 0, result.output
        assert "failed" in result.output.lower() or "broken" in result.output

    def test_mcp_doctor_no_manager_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["mcp", "doctor"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# End-to-end: invoking MCP capability through the general capability path
# ---------------------------------------------------------------------------


class TestMcpCapabilityInvoke:
    def test_invoke_mock_echo_via_registry(self, mcp_manager_with_mock) -> None:
        from canopus.capabilities.context import CapabilityContext
        from canopus.capabilities.executor import CapabilityExecutor
        from canopus.capabilities.registry import registry
        from canopus.core.profiles import builtin_profiles

        executor = CapabilityExecutor(registry)
        ctx = CapabilityContext(profile=builtin_profiles()["local-private"])
        result = executor.invoke("mock.echo", {"text": "hello mcp"}, ctx)
        assert result.success
        assert result.data == {"text": "hello mcp"}
        assert result.capability_name == "mock.echo"

    def test_invoke_mock_word_count_via_registry(self, mcp_manager_with_mock) -> None:
        from canopus.capabilities.context import CapabilityContext
        from canopus.capabilities.executor import CapabilityExecutor
        from canopus.capabilities.registry import registry
        from canopus.core.profiles import builtin_profiles

        executor = CapabilityExecutor(registry)
        ctx = CapabilityContext(profile=builtin_profiles()["local-private"])
        result = executor.invoke("mock.word_count", {"text": "one two three four"}, ctx)
        assert result.success
        assert result.data["words"] == 4

    def test_invoke_mock_now_via_registry(self, mcp_manager_with_mock) -> None:
        from canopus.capabilities.context import CapabilityContext
        from canopus.capabilities.executor import CapabilityExecutor
        from canopus.capabilities.registry import registry
        from canopus.core.profiles import builtin_profiles

        executor = CapabilityExecutor(registry)
        ctx = CapabilityContext(profile=builtin_profiles()["local-private"])
        result = executor.invoke("mock.now", {}, ctx)
        assert result.success
        assert "utc_iso" in result.data

    def test_invoke_mcp_capability_via_cli(self, patched_config, mcp_manager_with_mock) -> None:
        from canopus.cli.app import app
        result = runner.invoke(
            app,
            ["capability", "invoke", "mock.echo", "--input-json", '{"text": "via cli"}'],
        )
        assert result.exit_code == 0, result.output
        assert "via cli" in result.output

    def test_spec_transport_is_mcp(self, mcp_manager_with_mock) -> None:
        from canopus.capabilities.registry import registry
        spec = registry.get("mock.echo")
        assert spec.transport == "mcp"

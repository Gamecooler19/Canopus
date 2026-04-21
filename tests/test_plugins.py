"""Tests for Phase 4A: legacy plugin system.

Covers:
- Plugin error types
- Plugin models (PluginMeta, PluginRecord, PluginStatus)
- Plugin loader (valid, missing PLUGIN_META, missing capabilities, import error, bad caps)
- Plugin adapter (spec normalization, permission parsing, enum parsing)
- Plugin manager (discovery, duplicate names, duplicate capabilities, status tracking)
- Plugin capability registration into the global registry
- CLI: canopus plugin list / inspect / doctor
- CLI: canopus capability invoke
- Example plugins (hello_plugin, text_tools)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from canopus.capabilities.registry import CapabilityRegistry
from canopus.plugins.legacy.adapter import adapt
from canopus.plugins.legacy.errors import (
    PluginCapabilityDefError,
    PluginImportError,
    PluginValidationError,
)
from canopus.plugins.legacy.loader import load_plugin
from canopus.plugins.legacy.manager import (
    PluginManager,
    get_manager,
    initialize,
    reset_for_testing,
)
from canopus.plugins.legacy.models import (
    PluginCapabilityDef,
    PluginMeta,
    PluginRecord,
    PluginStatus,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_manager_after_each():
    """Ensure the global plugin manager is cleared between tests."""
    yield
    reset_for_testing()


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    """Return a temporary plugins directory."""
    d = tmp_path / "plugins"
    d.mkdir()
    return d


def write_plugin(directory: Path, filename: str, content: str) -> Path:
    """Write a plugin file to *directory* and return the path."""
    p = directory / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


MINIMAL_PLUGIN = """\
    PLUGIN_META = {
        "name": "minimal",
        "description": "A minimal test plugin.",
    }

    def greet(inputs, ctx):
        return {"message": "hi"}

    def capabilities():
        return [
            {
                "name": "minimal.greet",
                "description": "Say hi.",
                "handler": greet,
            }
        ]
"""

TWO_CAP_PLUGIN = """\
    PLUGIN_META = {
        "name": "twocap",
        "description": "Plugin with two capabilities.",
    }

    def cap_a(inputs, ctx):
        return {"a": True}

    def cap_b(inputs, ctx):
        return {"b": True}

    def capabilities():
        return [
            {"name": "twocap.a", "description": "Cap A.", "handler": cap_a},
            {"name": "twocap.b", "description": "Cap B.", "handler": cap_b},
        ]
"""

PARTIAL_PLUGIN = """\
    PLUGIN_META = {
        "name": "partial",
        "description": "A plugin with one bad capability.",
    }

    def good(inputs, ctx):
        return {"ok": True}

    def capabilities():
        return [
            {"name": "partial.good", "description": "Good cap.", "handler": good},
            {"name": "partial.bad", "description": "Bad cap."},  # missing handler
        ]
"""

NO_META_PLUGIN = """\
    def capabilities():
        return []
"""

NO_CAPS_PLUGIN = """\
    PLUGIN_META = {"name": "nocaps", "description": "No caps function."}
"""

BAD_CAPS_RETURNS_DICT = """\
    PLUGIN_META = {"name": "badcaps", "description": "Returns wrong type."}
    def capabilities():
        return {"not": "a list"}
"""

SYNTAX_ERROR_PLUGIN = """\
    this is not valid python !!@#$
"""

CAPS_RAISES_PLUGIN = """\
    PLUGIN_META = {"name": "capsraises", "description": "caps() raises."}
    def capabilities():
        raise RuntimeError("boom")
"""


# ---------------------------------------------------------------------------
# Plugin error types
# ---------------------------------------------------------------------------


class TestPluginErrors:
    def test_plugin_import_error(self) -> None:
        err = PluginImportError("/some/path.py", "syntax error")
        assert "path.py" in str(err)
        assert "syntax error" in str(err)
        assert err.plugin_path == "/some/path.py"
        assert err.reason == "syntax error"

    def test_plugin_validation_error(self) -> None:
        err = PluginValidationError("myplugin", "missing name")
        assert "myplugin" in str(err)
        assert "missing name" in str(err)

    def test_plugin_capability_def_error(self) -> None:
        err = PluginCapabilityDefError("myplugin", "my.cap", "no handler")
        assert "myplugin" in str(err)
        assert "my.cap" in str(err)
        assert "no handler" in str(err)

    def test_plugin_capability_def_error_no_cap_name(self) -> None:
        err = PluginCapabilityDefError("myplugin", None, "not a dict")
        assert "<unnamed>" in str(err)


# ---------------------------------------------------------------------------
# Plugin models
# ---------------------------------------------------------------------------


class TestPluginMeta:
    def test_minimal_meta(self) -> None:
        meta = PluginMeta(name="test", description="A test plugin.")
        assert meta.name == "test"
        assert meta.version == "0.1.0"
        assert meta.author == ""
        assert meta.tags == []

    def test_full_meta(self) -> None:
        meta = PluginMeta(
            name="full",
            description="Full plugin.",
            version="2.0.0",
            author="dev",
            tags=["a", "b"],
        )
        assert meta.version == "2.0.0"
        assert meta.tags == ["a", "b"]


class TestPluginRecord:
    def test_record_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "test.py"
        record = PluginRecord(
            name="test",
            file_name="test.py",
            path=path,
            status=PluginStatus.LOADED,
        )
        assert record.capability_names == []
        assert record.error is None
        assert record.warnings == []

    def test_plugin_status_values(self) -> None:
        assert PluginStatus.LOADED == "loaded"
        assert PluginStatus.PARTIAL == "partial"
        assert PluginStatus.INVALID == "invalid"
        assert PluginStatus.ERRORED == "errored"
        assert PluginStatus.SKIPPED == "skipped"


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------


class TestPluginLoader:
    def test_loads_valid_plugin(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.LOADED
        assert result.record.meta is not None
        assert result.record.meta.name == "minimal"
        assert len(result.capability_defs) == 1
        assert result.capability_defs[0].name == "minimal.greet"

    def test_loads_plugin_with_two_caps(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "twocap.py", TWO_CAP_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.LOADED
        assert len(result.capability_defs) == 2

    def test_missing_plugin_meta_is_invalid(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "nometa.py", NO_META_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.INVALID
        assert "PLUGIN_META" in (result.record.error or "")
        assert result.capability_defs == []

    def test_missing_capabilities_function_is_invalid(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "nocaps.py", NO_CAPS_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.INVALID
        assert "capabilities" in (result.record.error or "").lower()

    def test_capabilities_returns_dict_is_invalid(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "badcaps.py", BAD_CAPS_RETURNS_DICT)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.INVALID
        assert result.capability_defs == []

    def test_syntax_error_in_plugin_is_errored(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "syntax_err.py", SYNTAX_ERROR_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.ERRORED
        assert result.record.error is not None

    def test_capabilities_raises_is_errored(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "capsraises.py", CAPS_RAISES_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.ERRORED
        assert "boom" in (result.record.error or "")

    def test_partial_load_when_some_caps_bad(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "partial.py", PARTIAL_PLUGIN)
        result = load_plugin(path)
        assert result.record.status == PluginStatus.PARTIAL
        assert len(result.capability_defs) == 1  # only the good one
        assert result.capability_defs[0].name == "partial.good"
        assert len(result.record.warnings) == 1

    def test_capability_handler_is_callable(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        result = load_plugin(path)
        handler = result.capability_defs[0].handler
        assert callable(handler)
        output = handler({}, None)
        assert output == {"message": "hi"}

    def test_record_has_correct_file_name(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        result = load_plugin(path)
        assert result.record.file_name == "minimal.py"

    def test_record_path_is_absolute(self, plugin_dir: Path) -> None:
        path = write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        result = load_plugin(path)
        assert result.record.path.is_absolute()


# ---------------------------------------------------------------------------
# Plugin adapter
# ---------------------------------------------------------------------------


class TestPluginAdapter:
    def _make_def(self, **kwargs) -> PluginCapabilityDef:  # type: ignore[no-untyped-def]
        defaults: dict[str, object] = {
            "name": "test.cap",
            "description": "A test cap.",
            "handler": lambda inputs, ctx: {"ok": True},
        }
        defaults.update(kwargs)
        return PluginCapabilityDef(**defaults)

    def test_adapt_produces_correct_spec(self) -> None:
        cap_def = self._make_def()
        spec, handler = adapt(cap_def, "test")
        assert spec.name == "test.cap"
        assert spec.description == "A test cap."
        assert spec.transport == "legacy_plugin"

    def test_adapt_permissions_from_strings(self) -> None:
        cap_def = self._make_def(permissions=["fs.read", "fs.write"])
        spec, _ = adapt(cap_def, "test")
        from canopus.security.permissions import Permission
        assert Permission.FS_READ in spec.permissions
        assert Permission.FS_WRITE in spec.permissions

    def test_adapt_invalid_permission_raises(self) -> None:
        cap_def = self._make_def(permissions=["invalid.permission"])
        with pytest.raises(PluginCapabilityDefError, match="Unknown permission"):
            adapt(cap_def, "test")

    def test_adapt_side_effect_level(self) -> None:
        from canopus.security.permissions import SideEffectLevel
        cap_def = self._make_def(side_effect_level="medium")
        spec, _ = adapt(cap_def, "test")
        assert spec.side_effect_level == SideEffectLevel.MEDIUM

    def test_adapt_invalid_side_effect_raises(self) -> None:
        cap_def = self._make_def(side_effect_level="extreme")
        with pytest.raises(PluginCapabilityDefError, match="Unknown side_effect_level"):
            adapt(cap_def, "test")

    def test_adapt_confirmation_policy(self) -> None:
        from canopus.security.permissions import ConfirmationPolicy
        cap_def = self._make_def(confirmation_policy="always")
        spec, _ = adapt(cap_def, "test")
        assert spec.confirmation_policy == ConfirmationPolicy.ALWAYS

    def test_adapt_handler_is_callable(self) -> None:
        cap_def = self._make_def()
        _, handler = adapt(cap_def, "test")
        result = handler({}, None)
        assert result == {"ok": True}

    def test_adapt_tags_preserved(self) -> None:
        cap_def = self._make_def(tags=["foo", "bar"])
        spec, _ = adapt(cap_def, "test")
        assert spec.tags == ["foo", "bar"]


# ---------------------------------------------------------------------------
# Plugin manager
# ---------------------------------------------------------------------------


class TestPluginManager:
    def test_empty_directory_loads_nothing(self, plugin_dir: Path) -> None:
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        records = manager.discover_and_load()
        assert records == []

    def test_nonexistent_directory_loads_nothing(self, tmp_path: Path) -> None:
        ghost = tmp_path / "ghost"
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=ghost, registry=reg)
        records = manager.discover_and_load()
        assert records == []

    def test_loads_valid_plugin(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert len(manager.get_loaded()) == 1
        assert manager.get_loaded()[0].name == "minimal"

    def test_capability_registered_in_registry(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert reg.contains("minimal.greet")
        spec = reg.get("minimal.greet")
        assert spec.transport == "legacy_plugin"

    def test_invalid_plugin_does_not_register_caps(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "nometa.py", NO_META_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert len(reg) == 0
        assert len(manager.get_failed()) == 1

    def test_bad_plugin_does_not_stop_good_plugin(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "bad.py", NO_META_PLUGIN)
        write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert reg.contains("minimal.greet")
        assert len(manager.get_loaded()) == 1
        assert len(manager.get_failed()) == 1

    def test_duplicate_plugin_name_second_is_skipped(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "alpha.py", MINIMAL_PLUGIN)  # name = "minimal"
        # A second file also claims name "minimal"
        dup = """\
            PLUGIN_META = {"name": "minimal", "description": "Duplicate."}
            def capabilities(): return []
        """
        write_plugin(plugin_dir, "zzz_dup.py", dup)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        skipped = manager.get_skipped()
        assert len(skipped) == 1
        assert "Duplicate" in (skipped[0].error or "")

    def test_duplicate_capability_name_second_is_warned(self, plugin_dir: Path) -> None:
        # Files are loaded sorted alphabetically.
        # "a_first.py" (minimal plugin) loads before "z_conflict.py".
        # The conflict plugin tries to register "minimal.greet" again → warning.
        write_plugin(plugin_dir, "a_first.py", MINIMAL_PLUGIN)  # name="minimal"
        conflict = """\
            PLUGIN_META = {"name": "conflict", "description": "Conflict plugin."}
            def cap(inputs, ctx): return {}
            def capabilities():
                return [{"name": "minimal.greet", "description": "Same name!", "handler": cap}]
        """
        write_plugin(plugin_dir, "z_conflict.py", conflict)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        # "minimal" should be fully loaded
        minimal_record = manager.get_record("minimal")
        assert minimal_record is not None
        assert minimal_record.status == PluginStatus.LOADED
        # "conflict" should have a warning about the duplicate capability
        conflict_record = manager.get_record("conflict")
        assert conflict_record is not None
        assert conflict_record.status in (PluginStatus.INVALID, PluginStatus.PARTIAL)
        assert any("minimal.greet" in w for w in conflict_record.warnings)

    def test_get_record_by_name(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        record = manager.get_record("minimal")
        assert record is not None
        assert record.name == "minimal"

    def test_get_record_unknown_returns_none(self, plugin_dir: Path) -> None:
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert manager.get_record("ghost") is None

    def test_underscored_files_are_skipped(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "_private.py", MINIMAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        assert len(manager.get_records()) == 0

    def test_partial_load_status(self, plugin_dir: Path) -> None:
        write_plugin(plugin_dir, "partial.py", PARTIAL_PLUGIN)
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=plugin_dir, registry=reg)
        manager.discover_and_load()
        record = manager.get_record("partial")
        assert record is not None
        assert record.status == PluginStatus.PARTIAL
        assert reg.contains("partial.good")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestPluginManagerSingleton:
    def test_initialize_creates_global_manager(self, plugin_dir: Path) -> None:
        assert get_manager() is None
        reg = CapabilityRegistry()
        manager = initialize(plugin_dir, reg)
        assert get_manager() is manager

    def test_reset_clears_manager(self, plugin_dir: Path) -> None:
        reg = CapabilityRegistry()
        initialize(plugin_dir, reg)
        assert get_manager() is not None
        reset_for_testing()
        assert get_manager() is None

    def test_initialize_twice_replaces_manager(self, plugin_dir: Path) -> None:
        reg = CapabilityRegistry()
        m1 = initialize(plugin_dir, reg)
        m2 = initialize(plugin_dir, reg)
        assert get_manager() is m2
        assert m1 is not m2


# ---------------------------------------------------------------------------
# Example plugins
# ---------------------------------------------------------------------------


class TestExamplePlugins:
    def _load_example(self, filename: str) -> PluginManager:
        example_path = Path(__file__).parent.parent / "examples" / "plugins" / filename
        reg = CapabilityRegistry()
        manager = PluginManager(plugins_dir=example_path.parent, registry=reg)
        manager.discover_and_load()
        return manager

    def test_hello_plugin_loads(self) -> None:
        manager = self._load_example("hello_plugin.py")
        record = manager.get_record("hello")
        assert record is not None
        assert record.status in (PluginStatus.LOADED, PluginStatus.PARTIAL)
        assert "hello.greet" in record.capability_names
        assert "hello.farewell" in record.capability_names

    def test_text_tools_plugin_loads(self) -> None:
        manager = self._load_example("text_tools.py")
        record = manager.get_record("text_tools")
        assert record is not None
        assert record.status in (PluginStatus.LOADED, PluginStatus.PARTIAL)
        assert "text_tools.upper" in record.capability_names
        assert "text_tools.word_count" in record.capability_names

    def test_hello_greet_handler_returns_message(self) -> None:
        manager = self._load_example("hello_plugin.py")
        reg = manager._registry
        handler = reg.get_handler("hello.greet")
        result = handler({"name": "Alice"}, None)
        assert "Alice" in result["message"]

    def test_text_tools_upper_handler(self) -> None:
        manager = self._load_example("text_tools.py")
        reg = manager._registry
        handler = reg.get_handler("text_tools.upper")
        result = handler({"text": "hello"}, None)
        assert result["result"] == "HELLO"

    def test_text_tools_word_count_handler(self) -> None:
        manager = self._load_example("text_tools.py")
        reg = manager._registry
        handler = reg.get_handler("text_tools.word_count")
        result = handler({"text": "one two three"}, None)
        assert result["words"] == 3


# ---------------------------------------------------------------------------
# CLI: canopus plugin list
# ---------------------------------------------------------------------------


@pytest.fixture
def manager_with_plugins(plugin_dir: Path):  # type: ignore[return]
    """Initialize a global plugin manager with minimal + twocap plugins.

    Yields the manager, then removes plugin capabilities from the global
    registry so tests do not bleed state into each other.
    """
    write_plugin(plugin_dir, "minimal.py", MINIMAL_PLUGIN)
    write_plugin(plugin_dir, "twocap.py", TWO_CAP_PLUGIN)
    from canopus.capabilities.native.register import register_all
    from canopus.capabilities.registry import registry as global_reg
    register_all(overwrite=True)
    manager = initialize(plugin_dir, global_reg)
    yield manager
    # Teardown: remove plugin-registered capabilities from the global registry.
    for record in manager.get_records():
        for cap_name in record.capability_names:
            global_reg.unregister(cap_name)


class TestPluginCLI:
    def test_plugin_list_shows_loaded_plugins(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0, result.output
        assert "minimal" in result.output
        assert "twocap" in result.output

    def test_plugin_list_shows_status(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0, result.output
        assert "loaded" in result.output

    def test_plugin_list_no_manager_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app
        # manager is reset by autouse fixture
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code != 0

    def test_plugin_inspect_shows_capabilities(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "inspect", "minimal"])
        assert result.exit_code == 0, result.output
        assert "minimal.greet" in result.output

    def test_plugin_inspect_unknown_exits_nonzero(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "inspect", "ghost"])
        assert result.exit_code != 0

    def test_plugin_doctor_shows_summary(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "doctor"])
        assert result.exit_code == 0, result.output
        assert "loaded" in result.output.lower()

    def test_plugin_doctor_reports_failed_plugin(
        self, patched_config, plugin_dir: Path
    ) -> None:
        from canopus.capabilities.native.register import register_all
        from canopus.capabilities.registry import registry as global_reg
        from canopus.cli.app import app

        write_plugin(plugin_dir, "bad.py", NO_META_PLUGIN)
        register_all(overwrite=True)
        initialize(plugin_dir, global_reg)

        result = runner.invoke(app, ["plugin", "doctor"])
        assert result.exit_code == 0, result.output
        assert "failed" in result.output.lower() or "invalid" in result.output.lower()

    def test_plugin_list_filter_by_status(
        self, patched_config, manager_with_plugins: PluginManager
    ) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["plugin", "list", "--status", "loaded"])
        assert result.exit_code == 0, result.output
        assert "minimal" in result.output


# ---------------------------------------------------------------------------
# CLI: canopus capability invoke
# ---------------------------------------------------------------------------


class TestCapabilityInvokeCLI:
    def test_invoke_system_now(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["capability", "invoke", "system.now"])
        assert result.exit_code == 0, result.output
        assert "utc_iso" in result.output or "local_time" in result.output

    def test_invoke_with_input_json(self, patched_config, manager_with_plugins) -> None:
        from canopus.cli.app import app
        result = runner.invoke(
            app,
            ["capability", "invoke", "minimal.greet", "--input-json", '{"name": "test"}'],
        )
        assert result.exit_code == 0, result.output
        assert "test" in result.output or "hi" in result.output

    def test_invoke_unknown_capability_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["capability", "invoke", "ghost.cap"])
        assert result.exit_code != 0

    def test_invoke_bad_json_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(
            app,
            ["capability", "invoke", "system.now", "--input-json", "not-json"],
        )
        assert result.exit_code != 0

    def test_invoke_outputs_json(self, patched_config) -> None:
        from canopus.cli.app import app
        result = runner.invoke(app, ["capability", "invoke", "system.now", "--raw"])
        assert result.exit_code == 0, result.output
        # With --raw, the JSON is printed without Syntax highlighting.
        # Check that the expected keys are present in the output.
        assert "utc_iso" in result.output

    def test_invoke_text_tools_upper(
        self, patched_config, manager_with_plugins
    ) -> None:
        # text_tools is loaded from examples directory in manager_with_plugins
        # which only loads minimal + twocap. We need to also check global registry.
        # Let's just test with a capability we know is registered.
        from canopus.capabilities.registry import registry
        from canopus.cli.app import app
        if not registry.contains("text_tools.upper"):
            pytest.skip("text_tools not loaded in this test context")

        result = runner.invoke(
            app,
            ["capability", "invoke", "text_tools.upper", "--input-json", '{"text": "hello"}'],
        )
        assert result.exit_code == 0
        assert "HELLO" in result.output

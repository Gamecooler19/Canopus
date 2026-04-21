"""Tests for Phase 3: capability system.

Covers:
- canopus.security (Permission, SideEffectLevel, ConfirmationPolicy)
- canopus.capabilities.specs (CapabilitySpec, CapabilityResult)
- canopus.capabilities.registry (CapabilityRegistry — register, get, list, duplicate)
- canopus.capabilities.executor (CapabilityExecutor — success, failure, unknown)
- canopus.capabilities.native.system_now (output shape)
- canopus.capabilities.native.filesystem_read (reads file, validates path)
- canopus.capabilities.native.filesystem_list (lists dir, validates path)
- canopus.reasoning.planner (capability pattern matching)
- canopus.reasoning.executor (capability path vs model path)
- run_pipeline integration (capability step traced)
- CLI: canopus capability list
- CLI: canopus trace show / trace list
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.executor import CapabilityExecutor
from canopus.capabilities.native import filesystem_list, filesystem_read, system_now
from canopus.capabilities.native.register import register_all
from canopus.capabilities.registry import CapabilityRegistry
from canopus.capabilities.specs import CapabilityResult, CapabilitySpec
from canopus.core.errors import CapabilityError
from canopus.reasoning.executor import Executor
from canopus.reasoning.planner import Planner
from canopus.reasoning.types import IntentCategory
from canopus.security.permissions import ConfirmationPolicy, Permission, SideEffectLevel

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

runner = CliRunner()


def _make_spec(name: str = "test.cap") -> CapabilitySpec:
    return CapabilitySpec(
        name=name,
        description="A test capability.",
        tags=["test"],
        permissions=[Permission.SYSTEM_INFO],
        side_effect_level=SideEffectLevel.NONE,
        confirmation_policy=ConfirmationPolicy.NEVER,
        transport="native",
    )


def _ok_handler(inputs: dict, ctx: CapabilityContext) -> dict:
    return {"value": "ok"}


def _boom_handler(inputs: dict, ctx: CapabilityContext) -> dict:
    raise RuntimeError("boom")


def _make_registry(*specs_and_handlers) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for spec, handler in specs_and_handlers:
        reg.register(spec, handler)
    return reg


def _make_context() -> CapabilityContext:
    from canopus.core.profiles import builtin_profiles

    return CapabilityContext(profile=builtin_profiles()["local-private"])


# ─────────────────────────────────────────────────────────────
# Security enums
# ─────────────────────────────────────────────────────────────


class TestSecurityEnums:
    def test_permission_values(self) -> None:
        assert Permission.FS_READ == "fs.read"
        assert Permission.FS_WRITE == "fs.write"
        assert Permission.NETWORK_HTTP == "network.http"
        assert Permission.SHELL_EXEC == "shell.exec"

    def test_side_effect_level_ordering_by_name(self) -> None:
        levels = [
            SideEffectLevel.NONE, SideEffectLevel.LOW,
            SideEffectLevel.MEDIUM, SideEffectLevel.HIGH,
        ]
        assert all(isinstance(level, str) for level in levels)

    def test_confirmation_policy_values(self) -> None:
        assert ConfirmationPolicy.NEVER == "never"
        assert ConfirmationPolicy.SMART == "smart"
        assert ConfirmationPolicy.ALWAYS == "always"


# ─────────────────────────────────────────────────────────────
# CapabilitySpec
# ─────────────────────────────────────────────────────────────


class TestCapabilitySpec:
    def test_minimal_spec(self) -> None:
        spec = CapabilitySpec(name="x.y", description="desc")
        assert spec.name == "x.y"
        assert spec.transport == "native"
        assert spec.side_effect_level == SideEffectLevel.NONE
        assert spec.confirmation_policy == ConfirmationPolicy.NEVER
        assert spec.tags == []
        assert spec.permissions == []

    def test_full_spec(self) -> None:
        spec = _make_spec("full.cap")
        assert spec.permissions == [Permission.SYSTEM_INFO]

    def test_capability_result_success(self) -> None:
        r = CapabilityResult(capability_name="x", success=True, data={"k": "v"})
        assert r.success
        assert r.error is None

    def test_capability_result_failure(self) -> None:
        r = CapabilityResult(capability_name="x", success=False, error="oops")
        assert not r.success
        assert r.error == "oops"


# ─────────────────────────────────────────────────────────────
# CapabilityRegistry
# ─────────────────────────────────────────────────────────────


class TestCapabilityRegistry:
    def test_register_and_get(self) -> None:
        reg = _make_registry((_make_spec(), _ok_handler))
        spec = reg.get("test.cap")
        assert spec.name == "test.cap"

    def test_get_unknown_raises(self) -> None:
        reg = CapabilityRegistry()
        with pytest.raises(CapabilityError, match="not registered"):
            reg.get("nonexistent")

    def test_duplicate_raises_by_default(self) -> None:
        reg = _make_registry((_make_spec(), _ok_handler))
        with pytest.raises(CapabilityError, match="already registered"):
            reg.register(_make_spec(), _ok_handler)

    def test_overwrite_allowed(self) -> None:
        reg = _make_registry((_make_spec(), _ok_handler))
        reg.register(_make_spec(), _ok_handler, overwrite=True)
        assert reg.contains("test.cap")

    def test_list_all_sorted(self) -> None:
        reg = CapabilityRegistry()
        reg.register(_make_spec("z.cap"), _ok_handler)
        reg.register(_make_spec("a.cap"), _ok_handler)
        names = [s.name for s in reg.list_all()]
        assert names == sorted(names)

    def test_contains(self) -> None:
        reg = _make_registry((_make_spec(), _ok_handler))
        assert reg.contains("test.cap")
        assert not reg.contains("other.cap")

    def test_len(self) -> None:
        reg = _make_registry((_make_spec("a"), _ok_handler), (_make_spec("b"), _ok_handler))
        assert len(reg) == 2

    def test_get_handler_unknown_raises(self) -> None:
        reg = CapabilityRegistry()
        with pytest.raises(CapabilityError):
            reg.get_handler("ghost")


# ─────────────────────────────────────────────────────────────
# CapabilityExecutor
# ─────────────────────────────────────────────────────────────


class TestCapabilityExecutor:
    def test_successful_invocation(self) -> None:
        reg = _make_registry((_make_spec(), _ok_handler))
        executor = CapabilityExecutor(reg)
        result = executor.invoke("test.cap", {}, _make_context())
        assert result.success
        assert result.data == {"value": "ok"}
        assert result.latency_ms is not None

    def test_handler_exception_returns_failure(self) -> None:
        reg = _make_registry((_make_spec(), _boom_handler))
        executor = CapabilityExecutor(reg)
        result = executor.invoke("test.cap", {}, _make_context())
        assert not result.success
        assert "boom" in (result.error or "")

    def test_unknown_capability_raises(self) -> None:
        reg = CapabilityRegistry()
        executor = CapabilityExecutor(reg)
        with pytest.raises(CapabilityError):
            executor.invoke("missing", {}, _make_context())

    def test_trace_events_emitted(self) -> None:
        from datetime import UTC, datetime

        from canopus.core.tracing import ExecutionTrace, TraceWriter

        trace = ExecutionTrace(
            run_id="r1",
            session_id="s1",
            mode="run",
            profile_name="local-private",
            request="test",
            started_at=datetime.now(UTC),
        )
        mock_path = MagicMock(spec=Path)
        writer = TraceWriter(trace=trace, trace_path=mock_path)

        ctx = CapabilityContext(profile=_make_context().profile, writer=writer)
        reg = _make_registry((_make_spec(), _ok_handler))
        executor = CapabilityExecutor(reg)
        executor.invoke("test.cap", {}, ctx)

        event_types = [e.event_type for e in trace.events]
        assert "capability.invoked" in event_types
        assert "capability.succeeded" in event_types


# ─────────────────────────────────────────────────────────────
# Native: system.now
# ─────────────────────────────────────────────────────────────


class TestSystemNow:
    def test_spec_name(self) -> None:
        assert system_now.SPEC.name == "system.now"

    def test_spec_transport(self) -> None:
        assert system_now.SPEC.transport == "native"

    def test_spec_no_side_effects(self) -> None:
        assert system_now.SPEC.side_effect_level == SideEffectLevel.NONE

    def test_handler_returns_expected_keys(self) -> None:
        result = system_now.handler({}, _make_context())
        expected_keys = (
            "utc_iso", "local_iso", "local_date", "local_time", "timezone", "unix_timestamp"
        )
        for key in expected_keys:
            assert key in result

    def test_unix_timestamp_is_int(self) -> None:
        result = system_now.handler({}, _make_context())
        assert isinstance(result["unix_timestamp"], int)

    def test_utc_iso_parseable(self) -> None:
        from datetime import datetime
        result = system_now.handler({}, _make_context())
        # Should not raise
        datetime.fromisoformat(result["utc_iso"])


# ─────────────────────────────────────────────────────────────
# Native: filesystem.read_text
# ─────────────────────────────────────────────────────────────


class TestFilesystemReadText:
    def test_spec_name(self) -> None:
        assert filesystem_read.SPEC.name == "filesystem.read_text"

    def test_spec_requires_fs_read(self) -> None:
        assert Permission.FS_READ in filesystem_read.SPEC.permissions

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        result = filesystem_read.handler({"path": str(f)}, _make_context())
        assert result["content"] == "hello world"
        assert result["size_bytes"] == len("hello world")
        assert result["encoding"] == "utf-8"

    def test_missing_path_raises(self) -> None:
        with pytest.raises(CapabilityError, match="requires a 'path'"):
            filesystem_read.handler({}, _make_context())

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CapabilityError, match="not found"):
            filesystem_read.handler({"path": str(tmp_path / "ghost.txt")}, _make_context())

    def test_directory_instead_of_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CapabilityError, match="not a file"):
            filesystem_read.handler({"path": str(tmp_path)}, _make_context())

    def test_null_byte_in_path_raises(self) -> None:
        with pytest.raises(CapabilityError, match="null bytes"):
            filesystem_read.handler({"path": "some\x00path"}, _make_context())

    def test_path_field_in_result_is_absolute(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        result = filesystem_read.handler({"path": str(f)}, _make_context())
        assert Path(result["path"]).is_absolute()


# ─────────────────────────────────────────────────────────────
# Native: filesystem.list_dir
# ─────────────────────────────────────────────────────────────


class TestFilesystemListDir:
    def test_spec_name(self) -> None:
        assert filesystem_list.SPEC.name == "filesystem.list_dir"

    def test_spec_requires_fs_read(self) -> None:
        assert Permission.FS_READ in filesystem_list.SPEC.permissions

    def test_lists_directory(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("a", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        result = filesystem_list.handler({"path": str(tmp_path)}, _make_context())
        names = [e["name"] for e in result["entries"]]
        assert "file.txt" in names
        assert "subdir" in names

    def test_entry_types(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("x", encoding="utf-8")
        (tmp_path / "d").mkdir()
        result = filesystem_list.handler({"path": str(tmp_path)}, _make_context())
        types = {e["name"]: e["type"] for e in result["entries"]}
        assert types["f.txt"] == "file"
        assert types["d"] == "directory"

    def test_files_have_size(self, tmp_path: Path) -> None:
        content = "hello"
        (tmp_path / "sz.txt").write_text(content, encoding="utf-8")
        result = filesystem_list.handler({"path": str(tmp_path)}, _make_context())
        entry = next(e for e in result["entries"] if e["name"] == "sz.txt")
        assert entry["size_bytes"] == len(content)

    def test_missing_path_raises(self) -> None:
        with pytest.raises(CapabilityError, match="requires a 'path'"):
            filesystem_list.handler({}, _make_context())

    def test_not_a_directory_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(CapabilityError, match="not a directory"):
            filesystem_list.handler({"path": str(f)}, _make_context())

    def test_nonexistent_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CapabilityError, match="not found"):
            filesystem_list.handler({"path": str(tmp_path / "ghost")}, _make_context())

    def test_hidden_files_excluded_by_default(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("x", encoding="utf-8")
        (tmp_path / "visible.txt").write_text("y", encoding="utf-8")
        result = filesystem_list.handler({"path": str(tmp_path)}, _make_context())
        names = [e["name"] for e in result["entries"]]
        assert ".hidden" not in names
        assert "visible.txt" in names

    def test_hidden_files_included_when_requested(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("x", encoding="utf-8")
        inputs = {"path": str(tmp_path), "show_hidden": True}
        result = filesystem_list.handler(inputs, _make_context())
        names = [e["name"] for e in result["entries"]]
        assert ".hidden" in names

    def test_null_byte_in_path_raises(self) -> None:
        with pytest.raises(CapabilityError, match="null bytes"):
            filesystem_list.handler({"path": "bad\x00path"}, _make_context())

    def test_total_entries_field(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        result = filesystem_list.handler({"path": str(tmp_path)}, _make_context())
        assert result["total_entries"] == 3
        assert result["truncated"] is False


# ─────────────────────────────────────────────────────────────
# Native capability registration
# ─────────────────────────────────────────────────────────────


class TestRegisterAll:
    def test_registers_three_native_caps(self) -> None:
        reg = CapabilityRegistry()
        from canopus.capabilities.native import filesystem_list as fl
        from canopus.capabilities.native import filesystem_read as fr
        from canopus.capabilities.native import system_now as sn

        reg.register(sn.SPEC, sn.handler)
        reg.register(fr.SPEC, fr.handler)
        reg.register(fl.SPEC, fl.handler)

        assert len(reg) == 3
        assert reg.contains("system.now")
        assert reg.contains("filesystem.read_text")
        assert reg.contains("filesystem.list_dir")

    def test_register_all_idempotent_with_overwrite(self) -> None:
        from canopus.capabilities.registry import registry

        # Global registry was populated at app import; re-registering should not crash
        register_all(overwrite=True)
        assert registry.contains("system.now")


# ─────────────────────────────────────────────────────────────
# Planner — capability routing
# ─────────────────────────────────────────────────────────────


class TestPlannerCapabilityRouting:
    def setup_method(self) -> None:
        self.planner = Planner()

    def test_what_time_is_it_routes_to_system_now(self) -> None:
        plan = self.planner.plan("what time is it")
        assert plan.requires_capabilities
        assert plan.steps[0].capability_name == "system.now"

    def test_current_time_routes_to_system_now(self) -> None:
        plan = self.planner.plan("current time")
        assert plan.steps[0].capability_name == "system.now"

    def test_what_is_todays_date_routes_to_system_now(self) -> None:
        plan = self.planner.plan("what is today's date")
        assert plan.steps[0].capability_name == "system.now"

    def test_read_file_routes_to_filesystem_read(self) -> None:
        plan = self.planner.plan("read file /tmp/notes.txt")
        assert plan.steps[0].capability_name == "filesystem.read_text"
        assert plan.steps[0].capability_inputs.get("path") == "/tmp/notes.txt"

    def test_show_contents_routes_to_filesystem_read(self) -> None:
        plan = self.planner.plan("show the contents of /etc/hosts")
        assert plan.steps[0].capability_name == "filesystem.read_text"

    def test_list_files_routes_to_filesystem_list(self) -> None:
        plan = self.planner.plan("list files in /tmp")
        assert plan.steps[0].capability_name == "filesystem.list_dir"
        assert "/tmp" in (plan.steps[0].capability_inputs.get("path") or "")

    def test_list_directory_routes_to_filesystem_list(self) -> None:
        plan = self.planner.plan("list directory /home/user")
        assert plan.steps[0].capability_name == "filesystem.list_dir"

    def test_generic_question_does_not_route_capability(self) -> None:
        plan = self.planner.plan("what is the capital of France?")
        assert all(step.capability_name is None for step in plan.steps)

    def test_capability_plan_has_high_confidence(self) -> None:
        plan = self.planner.plan("what time is it")
        assert plan.intent_confidence >= 0.9

    def test_capability_plan_intent_is_action_oriented(self) -> None:
        plan = self.planner.plan("what time is it")
        assert plan.intent == IntentCategory.ACTION_ORIENTED


# ─────────────────────────────────────────────────────────────
# Reasoning Executor — capability vs model path
# ─────────────────────────────────────────────────────────────


class TestExecutorCapabilityPath:
    def test_system_now_goes_through_capability(self) -> None:
        from canopus.capabilities.registry import registry
        from canopus.models.local.echo import EchoProvider

        planner = Planner()
        plan = planner.plan("what time is it")

        executor = Executor(EchoProvider(), capability_registry=registry)
        result = executor.execute(plan, "what time is it")

        assert result.capability_name == "system.now"
        assert result.provider_name == "capability"
        assert "Current time:" in result.raw_response

    def test_generic_question_goes_through_model(self) -> None:
        from canopus.capabilities.registry import registry
        from canopus.models.local.echo import EchoProvider

        planner = Planner()
        plan = planner.plan("explain quantum entanglement")

        executor = Executor(EchoProvider(), capability_registry=registry)
        result = executor.execute(plan, "explain quantum entanglement")

        assert result.capability_name is None
        assert result.provider_name == "echo"

    def test_filesystem_read_via_executor(self, tmp_path: Path) -> None:
        from canopus.capabilities.registry import registry
        from canopus.models.local.echo import EchoProvider

        test_file = tmp_path / "data.txt"
        test_file.write_text("file content here", encoding="utf-8")

        planner = Planner()
        plan = planner.plan(f"read file {test_file}")

        executor = Executor(EchoProvider(), capability_registry=registry)
        result = executor.execute(plan, f"read file {test_file}")

        assert result.capability_name == "filesystem.read_text"
        assert "file content here" in result.raw_response


# ─────────────────────────────────────────────────────────────
# Pipeline integration — capability trace events
# ─────────────────────────────────────────────────────────────


class TestPipelineCapabilityTracing:
    def test_capability_event_in_trace(self) -> None:
        from datetime import UTC, datetime

        from canopus.core.profiles import builtin_profiles
        from canopus.core.tracing import ExecutionTrace, TraceWriter
        from canopus.reasoning.pipeline import run_pipeline

        profile = builtin_profiles()["local-private"]
        trace = ExecutionTrace(
            run_id="r1",
            session_id="s1",
            mode="run",
            profile_name="local-private",
            request="what time is it",
            started_at=datetime.now(UTC),
        )
        mock_path = MagicMock(spec=Path)
        writer = TraceWriter(trace=trace, trace_path=mock_path)

        run_pipeline("what time is it", profile, writer=writer)

        event_types = [e.event_type for e in trace.events]
        assert "capability.invoked" in event_types
        assert "capability.succeeded" in event_types

    def test_execution_completed_event_has_capability_field(self) -> None:
        from datetime import UTC, datetime

        from canopus.core.profiles import builtin_profiles
        from canopus.core.tracing import ExecutionTrace, TraceWriter
        from canopus.reasoning.pipeline import run_pipeline

        profile = builtin_profiles()["local-private"]
        trace = ExecutionTrace(
            run_id="r2",
            session_id="s2",
            mode="run",
            profile_name="local-private",
            request="what time is it",
            started_at=datetime.now(UTC),
        )
        mock_path = MagicMock(spec=Path)
        writer = TraceWriter(trace=trace, trace_path=mock_path)

        run_pipeline("what time is it", profile, writer=writer)

        exec_events = [e for e in trace.events if e.event_type == "execution.completed"]
        assert exec_events
        assert exec_events[0].data.get("capability") == "system.now"


# ─────────────────────────────────────────────────────────────
# CLI: canopus capability list
# ─────────────────────────────────────────────────────────────


class TestCapabilityCLI:
    def test_capability_list_shows_registered_caps(self, patched_config) -> None:
        from canopus.cli.app import app

        result = runner.invoke(app, ["capability", "list"])
        assert result.exit_code == 0, result.output
        assert "system.now" in result.output
        assert "filesystem.read_text" in result.output
        assert "filesystem.list_dir" in result.output

    def test_capability_list_filter_by_tag(self, patched_config) -> None:
        from canopus.cli.app import app

        result = runner.invoke(app, ["capability", "list", "--tag", "time"])
        assert result.exit_code == 0, result.output
        assert "system.now" in result.output
        # filesystem caps should not appear for tag "time"
        assert "filesystem.read_text" not in result.output

    def test_capability_list_filter_by_transport(self, patched_config) -> None:
        from canopus.cli.app import app

        result = runner.invoke(app, ["capability", "list", "--transport", "native"])
        assert result.exit_code == 0, result.output
        assert "system.now" in result.output

    def test_capability_list_shows_transport_column(self, patched_config) -> None:
        from canopus.cli.app import app

        result = runner.invoke(app, ["capability", "list"])
        assert result.exit_code == 0, result.output
        assert "native" in result.output


# ─────────────────────────────────────────────────────────────
# CLI: canopus trace show / trace list
# ─────────────────────────────────────────────────────────────


class TestTraceCLI:
    def _write_trace(
        self,
        traces_dir: Path,
        run_id: str = "abcdef12-0000-0000-0000-000000000000",
    ) -> Path:
        """Write a minimal valid trace file and return its path."""
        from datetime import UTC, datetime

        traces_dir.mkdir(parents=True, exist_ok=True)
        trace = {
            "run_id": run_id,
            "session_id": "sess-001",
            "mode": "run",
            "profile_name": "local-private",
            "request": "what time is it",
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": 42.0,
            "model_provider": "capability",
            "model_name": "system.now",
            "events": [
                {
                    "event_type": "session.started",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {},
                },
                {
                    "event_type": "capability.invoked",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {"capability": "system.now"},
                },
            ],
            "error": None,
            "result_summary": "Capability dispatch: 'system.now'",
        }
        path = traces_dir / f"{run_id}.json"
        path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
        return path

    def test_trace_show_displays_summary(self, patched_config, tmp_canopus_paths) -> None:
        from canopus.cli.app import app

        run_id = "abcdef12-0000-0000-0000-000000000000"
        self._write_trace(tmp_canopus_paths.traces_dir, run_id)

        with patch("canopus.cli.commands.trace.load_config", return_value=patched_config):
            result = runner.invoke(app, ["trace", "show", run_id])

        assert result.exit_code == 0, result.output
        assert "abcdef12" in result.output
        assert "local-private" in result.output

    def test_trace_show_missing_run_id_exits_nonzero(self, patched_config) -> None:
        from canopus.cli.app import app

        with patch("canopus.cli.commands.trace.load_config", return_value=patched_config):
            result = runner.invoke(app, ["trace", "show", "nonexistent-run-id"])

        assert result.exit_code != 0

    def test_trace_list_shows_recent_traces(self, patched_config, tmp_canopus_paths) -> None:
        from canopus.cli.app import app

        run_id = "bbbbbbbb-0000-0000-0000-000000000000"
        self._write_trace(tmp_canopus_paths.traces_dir, run_id)

        with patch("canopus.cli.commands.trace.load_config", return_value=patched_config):
            result = runner.invoke(app, ["trace", "list"])

        assert result.exit_code == 0, result.output
        # Prefix of run_id should appear
        assert "bbbbbbbb" in result.output

    def test_trace_list_empty_is_graceful(self, patched_config, tmp_canopus_paths) -> None:
        from canopus.cli.app import app

        # Ensure traces dir exists but is empty
        tmp_canopus_paths.traces_dir.mkdir(parents=True, exist_ok=True)

        with patch("canopus.cli.commands.trace.load_config", return_value=patched_config):
            result = runner.invoke(app, ["trace", "list"])

        assert result.exit_code == 0
        assert "No traces" in result.output

    def test_trace_show_events_displayed(self, patched_config, tmp_canopus_paths) -> None:
        from canopus.cli.app import app

        run_id = "cccccccc-0000-0000-0000-000000000000"
        self._write_trace(tmp_canopus_paths.traces_dir, run_id)

        with patch("canopus.cli.commands.trace.load_config", return_value=patched_config):
            result = runner.invoke(app, ["trace", "show", run_id, "--events"])

        assert result.exit_code == 0, result.output
        assert "session.started" in result.output
        assert "capability.invoked" in result.output

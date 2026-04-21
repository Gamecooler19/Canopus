"""Tests for Phase 5B: the Canopus workflow engine.

Coverage:
- WorkflowStepDef and WorkflowDef model validation
- WorkflowStepKind enumeration
- Templating: resolve, resolve_dict, error cases
- WorkflowContext: record_step_output, resolve, resolve_dict
- WorkflowLoader: load, load_all, validate, not-found, malformed YAML
- StepExecutor: each step kind, failure capture
- WorkflowEngine: multi-step run, on_failure=continue, on_failure=abort, final_output
- CLI commands: workflow list, inspect, validate, run
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.registry import CapabilityRegistry
from canopus.capabilities.specs import CapabilitySpec
from canopus.cli.commands.workflow import workflow_app
from canopus.core.profiles import builtin_profiles
from canopus.models.local.echo import EchoProvider
from canopus.workflows.context import WorkflowContext
from canopus.workflows.engine import WorkflowEngine
from canopus.workflows.errors import (
    WorkflowLoadError,
    WorkflowNotFoundError,
    WorkflowTemplatingError,
    WorkflowValidationError,
)
from canopus.workflows.executor import StepExecutor
from canopus.workflows.loader import WorkflowLoader
from canopus.workflows.models import (
    StepStatus,
    WorkflowDef,
    WorkflowInputDef,
    WorkflowStatus,
    WorkflowStepDef,
    WorkflowStepKind,
)
from canopus.workflows.templating import resolve, resolve_dict

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _profile():
    return builtin_profiles()["local-private"]


def _make_registry(*specs_and_handlers) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for spec, handler in specs_and_handlers:
        reg.register(spec, handler)
    return reg


def _make_spec(name: str) -> CapabilitySpec:
    return CapabilitySpec(name=name, description=f"Test capability {name}")


def _make_handler(output: dict[str, Any]) -> Any:
    def handler(inputs: dict, ctx: CapabilityContext) -> dict:
        return output

    return handler


def _make_workflow_yaml(tmp_path: Path, name: str, content: dict) -> Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.dump(content), encoding="utf-8")
    return p


def _make_context(
    inputs: dict[str, Any] | None = None,
    step_outputs: dict[str, dict] | None = None,
) -> WorkflowContext:
    reg = _make_registry()
    provider = EchoProvider()
    wf = WorkflowDef(name="test-wf", steps=[])
    ctx = WorkflowContext(
        workflow=wf,
        inputs=inputs or {},
        profile=_profile(),
        registry=reg,
        provider=provider,
    )
    for step_id, output in (step_outputs or {}).items():
        ctx.record_step_output(step_id, output)
    return ctx


# ---------------------------------------------------------------------------
# WorkflowStepKind
# ---------------------------------------------------------------------------


class TestWorkflowStepKind:
    def test_values(self) -> None:
        assert WorkflowStepKind.CAPABILITY == "capability"
        assert WorkflowStepKind.MODEL == "model"
        assert WorkflowStepKind.MEMORY_SEARCH == "memory_search"
        assert WorkflowStepKind.OUTPUT == "output"
        assert WorkflowStepKind.SET_VAR == "set_var"


# ---------------------------------------------------------------------------
# WorkflowStepDef validation
# ---------------------------------------------------------------------------


class TestWorkflowStepDef:
    def test_valid_capability_step(self) -> None:
        step = WorkflowStepDef(
            id="s1", kind=WorkflowStepKind.CAPABILITY, capability="filesystem.list_dir"
        )
        assert step.capability == "filesystem.list_dir"
        assert step.effective_output_key == "s1"

    def test_capability_step_requires_capability_field(self) -> None:
        with pytest.raises(ValueError):
            WorkflowStepDef(id="s1", kind=WorkflowStepKind.CAPABILITY)

    def test_valid_model_step(self) -> None:
        step = WorkflowStepDef(id="m1", kind=WorkflowStepKind.MODEL, prompt="hello")
        assert step.prompt == "hello"

    def test_model_step_requires_prompt(self) -> None:
        with pytest.raises(ValueError):
            WorkflowStepDef(id="m1", kind=WorkflowStepKind.MODEL)

    def test_memory_search_step_no_required_fields(self) -> None:
        step = WorkflowStepDef(id="ms", kind=WorkflowStepKind.MEMORY_SEARCH)
        assert step.kind == WorkflowStepKind.MEMORY_SEARCH

    def test_output_step(self) -> None:
        step = WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="{{ inputs.x }}")
        assert step.value == "{{ inputs.x }}"

    def test_set_var_step(self) -> None:
        step = WorkflowStepDef(id="var1", kind=WorkflowStepKind.SET_VAR, value="hello")
        assert step.kind == WorkflowStepKind.SET_VAR

    def test_effective_output_key_uses_output_key_when_set(self) -> None:
        step = WorkflowStepDef(
            id="s1",
            kind=WorkflowStepKind.SET_VAR,
            value="x",
            output_key="myalias",
        )
        assert step.effective_output_key == "myalias"

    def test_on_failure_default(self) -> None:
        step = WorkflowStepDef(id="s", kind=WorkflowStepKind.OUTPUT)
        assert step.on_failure == "abort"

    def test_on_failure_continue(self) -> None:
        step = WorkflowStepDef(id="s", kind=WorkflowStepKind.OUTPUT, on_failure="continue")
        assert step.on_failure == "continue"


# ---------------------------------------------------------------------------
# WorkflowDef validation
# ---------------------------------------------------------------------------


class TestWorkflowDef:
    def test_empty_workflow(self) -> None:
        wf = WorkflowDef(name="empty")
        assert wf.steps == []
        assert wf.inputs == []
        assert wf.tags == []

    def test_duplicate_step_ids_rejected(self) -> None:
        with pytest.raises(ValueError):
            WorkflowDef(
                name="dup",
                steps=[
                    WorkflowStepDef(id="s1", kind=WorkflowStepKind.OUTPUT),
                    WorkflowStepDef(id="s1", kind=WorkflowStepKind.SET_VAR, value="x"),
                ],
            )

    def test_input_declarations(self) -> None:
        wf = WorkflowDef(
            name="wf",
            inputs=[WorkflowInputDef(name="path", required=True)],
            steps=[],
        )
        assert wf.inputs[0].name == "path"
        assert wf.inputs[0].required is True


# ---------------------------------------------------------------------------
# Templating
# ---------------------------------------------------------------------------


class TestTemplating:
    def _data(self, **kw) -> dict:
        return {
            "inputs": kw.get("inputs", {}),
            "steps": kw.get("steps", {}),
        }

    def test_resolve_input(self) -> None:
        data = self._data(inputs={"path": "/tmp/notes"})
        assert resolve("Path: {{ inputs.path }}", data) == "Path: /tmp/notes"

    def test_resolve_step_output_field(self) -> None:
        data = self._data(steps={"list_dir": {"output": {"text": "3 files"}}})
        assert resolve("{{ steps.list_dir.text }}", data) == "3 files"

    def test_resolve_step_output_key(self) -> None:
        data = self._data(steps={"s1": {"output": {"value": "hello"}}})
        assert resolve("{{ steps.s1.output }}", data) != ""  # returns the dict repr

    def test_no_templates_passthrough(self) -> None:
        data = self._data()
        assert resolve("no templates here", data) == "no templates here"

    def test_multiple_templates_in_one_string(self) -> None:
        data = self._data(
            inputs={"name": "Alice"},
            steps={"greet": {"output": {"text": "Hello Alice"}}},
        )
        result = resolve("{{ inputs.name }}: {{ steps.greet.text }}", data)
        assert "Alice" in result
        assert "Hello Alice" in result

    def test_unknown_input_raises(self) -> None:
        data = self._data()
        with pytest.raises(WorkflowTemplatingError):
            resolve("{{ inputs.missing }}", data)

    def test_unknown_step_raises(self) -> None:
        data = self._data()
        with pytest.raises(WorkflowTemplatingError):
            resolve("{{ steps.nope.text }}", data)

    def test_unknown_step_field_raises(self) -> None:
        data = self._data(steps={"s1": {"output": {"text": "hi"}}})
        with pytest.raises(WorkflowTemplatingError):
            resolve("{{ steps.s1.nonexistent }}", data)

    def test_unknown_root_raises(self) -> None:
        data = self._data()
        with pytest.raises(WorkflowTemplatingError):
            resolve("{{ env.HOME }}", data)

    def test_resolve_dict(self) -> None:
        data = self._data(inputs={"x": "42"})
        result = resolve_dict({"a": "{{ inputs.x }}", "b": 99}, data)
        assert result["a"] == "42"
        assert result["b"] == 99


# ---------------------------------------------------------------------------
# WorkflowContext
# ---------------------------------------------------------------------------


class TestWorkflowContext:
    def test_record_and_get_step_output(self) -> None:
        ctx = _make_context()
        ctx.record_step_output("s1", {"text": "hello"})
        assert ctx.get_step_output("s1") == {"text": "hello"}

    def test_get_output_missing_step_returns_empty(self) -> None:
        ctx = _make_context()
        assert ctx.get_step_output("nope") == {}

    def test_completed_step_ids(self) -> None:
        ctx = _make_context()
        ctx.record_step_output("a", {})
        ctx.record_step_output("b", {})
        assert ctx.completed_step_ids() == ["a", "b"]

    def test_resolve_template_from_inputs(self) -> None:
        ctx = _make_context(inputs={"path": "/tmp"})
        assert ctx.resolve("{{ inputs.path }}") == "/tmp"

    def test_resolve_template_from_step_output(self) -> None:
        ctx = _make_context(step_outputs={"s1": {"text": "hello"}})
        assert ctx.resolve("{{ steps.s1.text }}") == "hello"

    def test_resolve_dict_values(self) -> None:
        ctx = _make_context(inputs={"x": "world"})
        result = ctx.resolve_dict({"key": "hello {{ inputs.x }}", "num": 42})
        assert result["key"] == "hello world"
        assert result["num"] == 42


# ---------------------------------------------------------------------------
# WorkflowLoader
# ---------------------------------------------------------------------------


class TestWorkflowLoader:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        _make_workflow_yaml(
            tmp_path,
            "simple",
            {
                "name": "simple",
                "description": "A simple test workflow",
                "steps": [
                    {"id": "s1", "kind": "output", "value": "done"},
                ],
            },
        )
        loader = WorkflowLoader(tmp_path)
        wf = loader.load("simple")
        assert wf.name == "simple"
        assert len(wf.steps) == 1
        assert str(tmp_path) in wf.source_path

    def test_load_uses_file_stem_as_name_if_missing(self, tmp_path: Path) -> None:
        _make_workflow_yaml(
            tmp_path,
            "unnamed",
            {"steps": [{"id": "s1", "kind": "output"}]},
        )
        loader = WorkflowLoader(tmp_path)
        wf = loader.load("unnamed")
        assert wf.name == "unnamed"

    def test_load_not_found_raises(self, tmp_path: Path) -> None:
        loader = WorkflowLoader(tmp_path)
        with pytest.raises(WorkflowNotFoundError):
            loader.load("nonexistent")

    def test_load_malformed_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": invalid: [yaml\n: garbage", encoding="utf-8")
        loader = WorkflowLoader(tmp_path)
        with pytest.raises(WorkflowLoadError):
            loader.load("bad")

    def test_load_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        loader = WorkflowLoader(tmp_path)
        with pytest.raises(WorkflowLoadError):
            loader.load("list")

    def test_load_schema_error_raises_validation_error(self, tmp_path: Path) -> None:
        # capability step without 'capability' field
        _make_workflow_yaml(
            tmp_path,
            "broken",
            {
                "name": "broken",
                "steps": [{"id": "s1", "kind": "capability"}],  # missing capability field
            },
        )
        loader = WorkflowLoader(tmp_path)
        with pytest.raises(WorkflowValidationError):
            loader.load("broken")

    def test_list_workflow_names(self, tmp_path: Path) -> None:
        for name in ["alpha", "beta", "gamma"]:
            _make_workflow_yaml(tmp_path, name, {"steps": []})
        loader = WorkflowLoader(tmp_path)
        names = loader.list_workflow_names()
        assert names == ["alpha", "beta", "gamma"]

    def test_load_all_skips_invalid(self, tmp_path: Path) -> None:
        _make_workflow_yaml(tmp_path, "valid", {"steps": []})
        (tmp_path / "bad.yaml").write_text("not: [valid yaml", encoding="utf-8")
        loader = WorkflowLoader(tmp_path)
        workflows = loader.load_all()
        assert len(workflows) == 1
        assert workflows[0].name == "valid"

    def test_validate_returns_empty_for_valid(self, tmp_path: Path) -> None:
        _make_workflow_yaml(tmp_path, "good", {"steps": []})
        loader = WorkflowLoader(tmp_path)
        assert loader.validate("good") == []

    def test_validate_returns_errors_for_invalid(self, tmp_path: Path) -> None:
        loader = WorkflowLoader(tmp_path)
        errors = loader.validate("missing")
        assert len(errors) > 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        loader = WorkflowLoader(tmp_path)
        assert loader.list_workflow_names() == []
        assert loader.load_all() == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        loader = WorkflowLoader(tmp_path / "no_such_dir")
        assert loader.list_workflow_names() == []
        assert loader.load_all() == []


# ---------------------------------------------------------------------------
# StepExecutor
# ---------------------------------------------------------------------------


class TestStepExecutor:
    def _make_ctx(self, registry=None, inputs=None) -> WorkflowContext:
        reg = registry or _make_registry()
        provider = EchoProvider()
        wf = WorkflowDef(name="t", steps=[])
        return WorkflowContext(
            workflow=wf,
            inputs=inputs or {},
            profile=_profile(),
            registry=reg,
            provider=provider,
        )

    # output step
    def test_output_step_resolves_template(self) -> None:
        ctx = self._make_ctx(inputs={"greeting": "hello"})
        step = WorkflowStepDef(
            id="out", kind=WorkflowStepKind.OUTPUT, value="{{ inputs.greeting }}"
        )
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert result.output["text"] == "hello"

    def test_output_step_empty_value(self) -> None:
        ctx = self._make_ctx()
        step = WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT)
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert result.output["text"] == ""

    # set_var step
    def test_set_var_step(self) -> None:
        ctx = self._make_ctx(inputs={"x": "42"})
        step = WorkflowStepDef(id="v1", kind=WorkflowStepKind.SET_VAR, value="{{ inputs.x }}")
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert result.output["value"] == "42"

    # capability step
    def test_capability_step_success(self) -> None:
        spec = _make_spec("test.cap")
        handler = _make_handler({"items": ["a", "b"]})
        reg = _make_registry((spec, handler))
        ctx = self._make_ctx(registry=reg)
        step = WorkflowStepDef(
            id="cap1",
            kind=WorkflowStepKind.CAPABILITY,
            capability="test.cap",
            inputs={"key": "value"},
        )
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert result.output["items"] == ["a", "b"]

    def test_capability_step_unknown_capability_fails(self) -> None:
        ctx = self._make_ctx()
        step = WorkflowStepDef(
            id="c1", kind=WorkflowStepKind.CAPABILITY, capability="no.such.cap"
        )
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.FAILED
        assert result.error is not None

    # model step
    def test_model_step_uses_echo_provider(self) -> None:
        ctx = self._make_ctx()
        step = WorkflowStepDef(id="m1", kind=WorkflowStepKind.MODEL, prompt="Say hello")
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert "text" in result.output
        assert result.output["provider"] == "echo"

    def test_model_step_resolves_template_in_prompt(self) -> None:
        ctx = self._make_ctx(inputs={"topic": "Python"})
        step = WorkflowStepDef(
            id="m1",
            kind=WorkflowStepKind.MODEL,
            prompt="Tell me about {{ inputs.topic }}",
        )
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED

    # memory_search step
    def test_memory_search_no_service_fails(self) -> None:
        ctx = self._make_ctx()  # no memory_service
        step = WorkflowStepDef(id="ms", kind=WorkflowStepKind.MEMORY_SEARCH, query="notes")
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.FAILED
        assert "memory service" in result.error.lower()

    def test_memory_search_with_mock_service(self) -> None:
        mock_svc = MagicMock()
        mock_svc.search.return_value = []

        wf = WorkflowDef(name="t", steps=[])
        ctx = WorkflowContext(
            workflow=wf,
            inputs={"q": "recent notes"},
            profile=_profile(),
            registry=_make_registry(),
            provider=EchoProvider(),
            memory_service=mock_svc,
        )
        step = WorkflowStepDef(
            id="ms", kind=WorkflowStepKind.MEMORY_SEARCH, query="{{ inputs.q }}"
        )
        result = StepExecutor(ctx).execute(step)
        assert result.status == StepStatus.COMPLETED
        assert result.output["count"] == 0
        mock_svc.search.assert_called_once()

    def test_latency_recorded(self) -> None:
        ctx = self._make_ctx()
        step = WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="x")
        result = StepExecutor(ctx).execute(step)
        assert result.latency_ms is not None
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------


def _make_engine(
    registry=None, provider=None, memory_service=None
) -> WorkflowEngine:
    return WorkflowEngine(
        registry=registry or _make_registry(),
        provider=provider or EchoProvider(),
        memory_service=memory_service,
    )


class TestWorkflowEngine:
    def test_simple_single_step_output(self) -> None:
        wf = WorkflowDef(
            name="simple",
            steps=[
                WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="hello world"),
            ],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.COMPLETED
        assert result.final_output == "hello world"

    def test_multi_step_with_set_var_and_output(self) -> None:
        wf = WorkflowDef(
            name="chain",
            steps=[
                WorkflowStepDef(id="v1", kind=WorkflowStepKind.SET_VAR, value="42"),
                WorkflowStepDef(
                    id="out",
                    kind=WorkflowStepKind.OUTPUT,
                    value="value={{ steps.v1.value }}",
                ),
            ],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.COMPLETED
        assert result.final_output == "value=42"
        assert len(result.step_results) == 2

    def test_input_resolution(self) -> None:
        wf = WorkflowDef(
            name="input_test",
            inputs=[WorkflowInputDef(name="greeting", required=True)],
            steps=[
                WorkflowStepDef(
                    id="out", kind=WorkflowStepKind.OUTPUT, value="{{ inputs.greeting }}"
                )
            ],
        )
        result = _make_engine().run(wf, inputs={"greeting": "hi"}, profile=_profile())
        assert result.final_output == "hi"

    def test_required_input_missing_raises(self) -> None:
        wf = WorkflowDef(
            name="required_test",
            inputs=[WorkflowInputDef(name="x", required=True)],
            steps=[],
        )
        with pytest.raises(WorkflowValidationError):
            _make_engine().run(wf, inputs={}, profile=_profile())

    def test_input_default_applied(self) -> None:
        wf = WorkflowDef(
            name="default_test",
            inputs=[WorkflowInputDef(name="limit", default="10")],
            steps=[
                WorkflowStepDef(
                    id="out", kind=WorkflowStepKind.OUTPUT, value="{{ inputs.limit }}"
                )
            ],
        )
        result = _make_engine().run(wf, inputs={}, profile=_profile())
        assert result.final_output == "10"

    def test_on_failure_abort_stops_execution(self) -> None:
        # capability step that fails, followed by another step
        wf = WorkflowDef(
            name="abort_test",
            steps=[
                WorkflowStepDef(
                    id="bad",
                    kind=WorkflowStepKind.CAPABILITY,
                    capability="no.such.thing",
                    on_failure="abort",
                ),
                WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="reached"),
            ],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.FAILED
        assert len(result.step_results) == 1  # second step never ran
        assert result.error is not None

    def test_on_failure_continue_allows_completion(self) -> None:
        wf = WorkflowDef(
            name="continue_test",
            steps=[
                WorkflowStepDef(
                    id="bad",
                    kind=WorkflowStepKind.CAPABILITY,
                    capability="no.such.thing",
                    on_failure="continue",
                ),
                WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="reached"),
            ],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.PARTIAL
        assert len(result.step_results) == 2
        assert result.final_output == "reached"

    def test_result_metadata(self) -> None:
        wf = WorkflowDef(
            name="meta_test",
            steps=[WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="x")],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.workflow_name == "meta_test"
        assert result.run_id is not None
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.latency_ms is not None and result.latency_ms >= 0

    def test_trace_events_emitted(self) -> None:
        mock_writer = MagicMock()
        mock_trace = MagicMock()
        mock_writer.trace = mock_trace

        wf = WorkflowDef(
            name="trace_test",
            steps=[WorkflowStepDef(id="out", kind=WorkflowStepKind.OUTPUT, value="done")],
        )
        _make_engine().run(wf, profile=_profile(), writer=mock_writer)

        calls = [c.args[0] for c in mock_trace.add_event.call_args_list]
        assert "workflow.started" in calls
        assert "workflow.step.started" in calls
        assert "workflow.step.completed" in calls
        assert "workflow.completed" in calls

    def test_empty_workflow_completes(self) -> None:
        wf = WorkflowDef(name="empty", steps=[])
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.COMPLETED
        assert result.final_output is None

    def test_model_step_in_engine(self) -> None:
        wf = WorkflowDef(
            name="model_wf",
            steps=[
                WorkflowStepDef(id="gen", kind=WorkflowStepKind.MODEL, prompt="Say hi"),
                WorkflowStepDef(
                    id="out", kind=WorkflowStepKind.OUTPUT, value="{{ steps.gen.text }}"
                ),
            ],
        )
        result = _make_engine().run(wf, profile=_profile())
        assert result.status == WorkflowStatus.COMPLETED
        assert result.final_output is not None
        assert len(result.final_output) > 0


# ---------------------------------------------------------------------------
# WorkflowEngine — capability integration
# ---------------------------------------------------------------------------


class TestWorkflowEngineCapability:
    def test_capability_step_output_used_in_template(self) -> None:
        spec = _make_spec("echo.greet")
        handler = _make_handler({"text": "Hi from echo.greet"})
        reg = _make_registry((spec, handler))
        engine = _make_engine(registry=reg)

        wf = WorkflowDef(
            name="cap_chain",
            steps=[
                WorkflowStepDef(
                    id="greet",
                    kind=WorkflowStepKind.CAPABILITY,
                    capability="echo.greet",
                ),
                WorkflowStepDef(
                    id="out",
                    kind=WorkflowStepKind.OUTPUT,
                    value="{{ steps.greet.text }}",
                ),
            ],
        )
        result = engine.run(wf, profile=_profile())
        assert result.status == WorkflowStatus.COMPLETED
        assert result.final_output == "Hi from echo.greet"


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestWorkflowCLI:
    def _write_workflow(self, tmp_path: Path, name: str, content: dict) -> None:
        p = tmp_path / f"{name}.yaml"
        p.write_text(yaml.dump(content), encoding="utf-8")

    def _run(self, args: list[str]) -> Any:
        return runner.invoke(workflow_app, args)

    # workflow list
    def test_list_empty_directory(self, tmp_path: Path) -> None:
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["list"])
        assert result.exit_code == 0
        assert "No workflows found" in result.output

    def test_list_shows_workflows(self, tmp_path: Path) -> None:
        self._write_workflow(
            tmp_path,
            "my_wf",
            {"name": "my_wf", "description": "A test workflow", "steps": []},
        )
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["list"])
        assert result.exit_code == 0
        assert "my_wf" in result.output

    # workflow inspect
    def test_inspect_valid_workflow(self, tmp_path: Path) -> None:
        self._write_workflow(
            tmp_path,
            "inspected",
            {
                "name": "inspected",
                "description": "Inspect test",
                "inputs": [{"name": "x", "required": True}],
                "steps": [{"id": "s1", "kind": "output", "value": "done"}],
            },
        )
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["inspect", "inspected"])
        assert result.exit_code == 0
        assert "inspected" in result.output
        assert "s1" in result.output

    def test_inspect_not_found(self, tmp_path: Path) -> None:
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["inspect", "missing"])
        assert result.exit_code != 0

    # workflow validate
    def test_validate_valid_workflow(self, tmp_path: Path) -> None:
        self._write_workflow(tmp_path, "good", {"steps": []})
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["validate", "good"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_workflow(self, tmp_path: Path) -> None:
        self._write_workflow(
            tmp_path,
            "bad",
            {"steps": [{"id": "s1", "kind": "capability"}]},  # missing capability field
        )
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["validate", "bad"])
        assert result.exit_code == 1

    def test_validate_missing_workflow(self, tmp_path: Path) -> None:
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["validate", "absent"])
        assert result.exit_code == 1

    # workflow run
    def test_run_simple_workflow(self, tmp_path: Path) -> None:
        self._write_workflow(
            tmp_path,
            "simple_run",
            {
                "name": "simple_run",
                "steps": [{"id": "out", "kind": "output", "value": "workflow output"}],
            },
        )
        with (
            patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path),
            patch(
                "canopus.models.router.ModelRouter.get_provider",
                return_value=EchoProvider(),
            ),
        ):
            result = self._run(["run", "simple_run"])
        assert result.exit_code == 0
        assert "workflow output" in result.output

    def test_run_not_found_workflow(self, tmp_path: Path) -> None:
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["run", "no_such"])
        assert result.exit_code != 0

    def test_run_with_input_flag(self, tmp_path: Path) -> None:
        self._write_workflow(
            tmp_path,
            "input_wf",
            {
                "name": "input_wf",
                "inputs": [{"name": "greeting"}],
                "steps": [{"id": "out", "kind": "output", "value": "{{ inputs.greeting }}"}],
            },
        )
        with (
            patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path),
            patch(
                "canopus.models.router.ModelRouter.get_provider",
                return_value=EchoProvider(),
            ),
        ):
            result = self._run(["run", "input_wf", "--input", "greeting=hello"])
        assert result.exit_code == 0
        assert "hello" in result.output

    def test_run_bad_input_format(self, tmp_path: Path) -> None:
        self._write_workflow(tmp_path, "wf", {"steps": []})
        with patch("canopus.cli.commands.workflow._get_workflows_dir", return_value=tmp_path):
            result = self._run(["run", "wf", "--input", "noequals"])
        assert result.exit_code != 0

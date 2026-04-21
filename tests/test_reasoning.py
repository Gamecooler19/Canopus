"""Tests for the reasoning pipeline: planner, executor, reflector, and pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

from canopus.core.config import AppConfig
from canopus.core.profiles import builtin_profiles
from canopus.models.base import ModelRequest, ModelResponse
from canopus.models.local.echo import EchoProvider
from canopus.reasoning.executor import Executor
from canopus.reasoning.pipeline import run_pipeline
from canopus.reasoning.planner import Planner
from canopus.reasoning.reflector import Reflector
from canopus.reasoning.types import (
    ExecutionResult,
    IntentCategory,
    Plan,
    PlanStep,
    ReflectionOutcome,
)

# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestPlanner:
    def test_returns_plan(self) -> None:
        plan = Planner().plan("hello")
        assert isinstance(plan, Plan)

    def test_short_greeting_is_conversational(self) -> None:
        plan = Planner().plan("hello")
        assert plan.intent == IntentCategory.CONVERSATIONAL

    def test_informational_what_question(self) -> None:
        plan = Planner().plan("what is the capital of France?")
        assert plan.intent == IntentCategory.INFORMATIONAL

    def test_informational_how_question(self) -> None:
        plan = Planner().plan("how does Python memory management work?")
        assert plan.intent == IntentCategory.INFORMATIONAL

    def test_informational_explain(self) -> None:
        plan = Planner().plan("explain the difference between TCP and UDP")
        assert plan.intent == IntentCategory.INFORMATIONAL

    def test_action_oriented_run(self) -> None:
        plan = Planner().plan("run the test suite")
        assert plan.intent == IntentCategory.ACTION_ORIENTED

    def test_action_oriented_create(self) -> None:
        plan = Planner().plan("create a new file called notes.txt")
        assert plan.intent == IntentCategory.ACTION_ORIENTED

    def test_action_oriented_send(self) -> None:
        plan = Planner().plan("send the report to alice")
        assert plan.intent == IntentCategory.ACTION_ORIENTED

    def test_confidence_within_bounds(self) -> None:
        for request in ["hello", "what is AI?", "run the build"]:
            plan = Planner().plan(request)
            assert 0.0 <= plan.intent_confidence <= 1.0

    def test_plan_has_steps(self) -> None:
        plan = Planner().plan("what is Python?")
        assert len(plan.steps) > 0

    def test_all_steps_are_plan_steps(self) -> None:
        plan = Planner().plan("what is Python?")
        for step in plan.steps:
            assert isinstance(step, PlanStep)

    def test_conversational_has_one_step(self) -> None:
        plan = Planner().plan("hey there")
        assert len(plan.steps) == 1

    def test_informational_has_two_steps(self) -> None:
        plan = Planner().plan("what is the speed of light?")
        assert len(plan.steps) == 2

    def test_action_has_four_steps(self) -> None:
        plan = Planner().plan("create a backup of the database")
        assert len(plan.steps) == 4

    def test_action_requires_capabilities(self) -> None:
        plan = Planner().plan("delete the old log files")
        assert plan.requires_capabilities is True

    def test_conversational_does_not_require_capabilities(self) -> None:
        plan = Planner().plan("hi")
        assert plan.requires_capabilities is False

    def test_summary_is_non_empty(self) -> None:
        plan = Planner().plan("test request")
        assert len(plan.summary) > 0

    def test_system_prompt_key_matches_intent(self) -> None:
        plan = Planner().plan("what is AI?")
        assert plan.system_prompt_key == plan.intent.value

    def test_empty_string_is_conversational(self) -> None:
        # Degenerate input should not crash
        plan = Planner().plan("")
        assert isinstance(plan, Plan)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class TestExecutor:
    def test_returns_execution_result(self) -> None:
        provider = EchoProvider()
        plan = Planner().plan("hello")
        result = Executor(provider).execute(plan, "hello")
        assert isinstance(result, ExecutionResult)

    def test_result_contains_plan(self) -> None:
        provider = EchoProvider()
        plan = Planner().plan("hello")
        result = Executor(provider).execute(plan, "hello")
        assert result.plan is plan

    def test_result_has_non_empty_response(self) -> None:
        provider = EchoProvider()
        plan = Planner().plan("what is Python?")
        result = Executor(provider).execute(plan, "what is Python?")
        assert len(result.raw_response.strip()) > 0

    def test_result_provider_name_matches(self) -> None:
        provider = EchoProvider()
        plan = Planner().plan("hello")
        result = Executor(provider).execute(plan, "hello")
        assert result.provider_name == provider.provider_name

    def test_result_model_name_matches(self) -> None:
        provider = EchoProvider()
        plan = Planner().plan("hello")
        result = Executor(provider).execute(plan, "hello")
        assert result.model_name == provider.model_name

    def test_executor_calls_provider_complete(self) -> None:
        mock_provider = MagicMock()
        mock_provider.provider_name = "mock"
        mock_provider.model_name = "mock-1"
        mock_provider.complete.return_value = ModelResponse(
            text="mock response",
            provider_name="mock",
            model_name="mock-1",
            finish_reason="stop",
        )
        plan = Planner().plan("test")
        Executor(mock_provider).execute(plan, "test")
        mock_provider.complete.assert_called_once()

    def test_executor_passes_model_request(self) -> None:
        mock_provider = MagicMock()
        mock_provider.provider_name = "mock"
        mock_provider.model_name = "mock-1"
        mock_provider.complete.return_value = ModelResponse(
            text="ok", provider_name="mock", model_name="mock-1"
        )
        plan = Planner().plan("test")
        Executor(mock_provider).execute(plan, "test")
        call_args = mock_provider.complete.call_args[0][0]
        assert isinstance(call_args, ModelRequest)
        assert "test" in call_args.prompt


# ---------------------------------------------------------------------------
# Reflector
# ---------------------------------------------------------------------------


class TestReflector:
    def _make_result(self, raw_response: str) -> ExecutionResult:
        plan = Planner().plan("test request")
        return ExecutionResult(
            plan=plan,
            raw_response=raw_response,
            provider_name="echo",
            model_name="echo-1.0",
        )

    def test_valid_response_outcome(self) -> None:
        result = self._make_result("This is a good response from the model.")
        reflection = Reflector().reflect(result)
        assert reflection.outcome == ReflectionOutcome.VALID

    def test_valid_response_no_issues(self) -> None:
        result = self._make_result("This is a good response.")
        reflection = Reflector().reflect(result)
        assert reflection.issues == []

    def test_valid_response_final_matches_raw(self) -> None:
        result = self._make_result("  Good response.  ")
        reflection = Reflector().reflect(result)
        assert reflection.final_response == "Good response."

    def test_empty_response_fails(self) -> None:
        result = self._make_result("")
        reflection = Reflector().reflect(result)
        assert reflection.outcome == ReflectionOutcome.FAILED

    def test_empty_response_has_issue(self) -> None:
        result = self._make_result("")
        reflection = Reflector().reflect(result)
        assert len(reflection.issues) > 0

    def test_empty_response_fallback_message(self) -> None:
        result = self._make_result("")
        reflection = Reflector().reflect(result)
        assert len(reflection.final_response) > 0

    def test_whitespace_only_response_fails(self) -> None:
        result = self._make_result("   ")
        reflection = Reflector().reflect(result)
        assert reflection.outcome == ReflectionOutcome.FAILED

    def test_too_short_response_fails(self) -> None:
        result = self._make_result("Hi")  # 2 chars < min 10
        reflection = Reflector().reflect(result)
        assert reflection.outcome == ReflectionOutcome.FAILED

    def test_needs_retry_when_retries_available(self) -> None:
        result = self._make_result("")
        reflection = Reflector().reflect(result, retry_count=0, max_retries=1)
        assert reflection.outcome == ReflectionOutcome.NEEDS_RETRY

    def test_retry_count_carried_through(self) -> None:
        result = self._make_result("Good response.")
        reflection = Reflector().reflect(result, retry_count=2)
        assert reflection.retry_count == 2


# ---------------------------------------------------------------------------
# Full pipeline (integration-style)
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def test_returns_reflection_result(self, tmp_config: AppConfig) -> None:
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("hello", profile, provider=EchoProvider())
        from canopus.reasoning.types import ReflectionResult

        assert isinstance(reflection, ReflectionResult)

    def test_pipeline_outcome_is_valid_for_echo(self, tmp_config: AppConfig) -> None:
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("what is Python?", profile, provider=EchoProvider())
        assert reflection.outcome == ReflectionOutcome.VALID

    def test_pipeline_final_response_non_empty(self, tmp_config: AppConfig) -> None:
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("explain recursion", profile, provider=EchoProvider())
        assert len(reflection.final_response.strip()) > 0

    def test_pipeline_intent_classified(self, tmp_config: AppConfig) -> None:
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("what is AI?", profile, provider=EchoProvider())
        assert reflection.execution.plan.intent == IntentCategory.INFORMATIONAL

    def test_pipeline_provider_recorded(self, tmp_config: AppConfig) -> None:
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("hello", profile, provider=EchoProvider())
        assert reflection.execution.provider_name == "echo"

    def test_pipeline_writes_trace_events(self, tmp_config: AppConfig) -> None:
        from canopus.core.runtime import RequestMode, create_session
        from canopus.core.tracing import TraceWriter

        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)

        profile = builtin_profiles()["local-private"]
        run_pipeline("test", profile, writer=writer, provider=EchoProvider())

        event_types = {e.event_type for e in writer.trace.events}
        assert "provider.selected" in event_types
        assert "plan.created" in event_types
        assert "execution.completed" in event_types
        assert "reflection.completed" in event_types

    def test_pipeline_populates_trace_provider_fields(
        self, tmp_config: AppConfig
    ) -> None:
        from canopus.core.runtime import RequestMode, create_session
        from canopus.core.tracing import TraceWriter

        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)

        profile = builtin_profiles()["local-private"]
        run_pipeline("test", profile, writer=writer, provider=EchoProvider())

        assert writer.trace.model_provider == "echo"
        assert writer.trace.model_name == "echo-1.0"

    def test_pipeline_uses_router_when_no_provider_given(
        self, tmp_config: AppConfig
    ) -> None:
        """Without an explicit provider, the router should return EchoProvider."""
        profile = builtin_profiles()["local-private"]
        reflection = run_pipeline("hello", profile)
        # EchoProvider is the current fallback, so provider_name should be "echo"
        assert reflection.execution.provider_name == "echo"


# ---------------------------------------------------------------------------
# CLI run command integration
# ---------------------------------------------------------------------------


class TestRunCommandWithPipeline:
    def test_run_command_shows_intent(self, patched_config: AppConfig) -> None:
        from typer.testing import CliRunner

        from canopus.cli.app import app

        result = CliRunner().invoke(app, ["run", "what is Python?"])
        assert result.exit_code == 0
        assert "informational" in result.output

    def test_run_command_shows_provider(self, patched_config: AppConfig) -> None:
        from typer.testing import CliRunner

        from canopus.cli.app import app

        result = CliRunner().invoke(app, ["run", "hello"])
        assert result.exit_code == 0
        assert "echo" in result.output

    def test_run_command_creates_trace_with_model_fields(
        self, patched_config: AppConfig
    ) -> None:
        import json

        from typer.testing import CliRunner

        from canopus.cli.app import app

        runner = CliRunner()
        runner.invoke(app, ["run", "test"])

        traces_dir = patched_config.paths.traces_dir
        (trace_file,) = list(traces_dir.glob("*.json"))
        data = json.loads(trace_file.read_text(encoding="utf-8"))

        assert data["model_provider"] == "echo"
        assert data["model_name"] == "echo-1.0"

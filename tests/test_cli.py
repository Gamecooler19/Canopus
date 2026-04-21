"""Tests for CLI commands using Typer's test runner."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from canopus import __version__
from canopus.cli.app import app
from canopus.core.config import AppConfig

runner = CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_exits_zero(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_shows_version_string(self) -> None:
        result = runner.invoke(app, ["version"])
        assert __version__ in result.output

    def test_shows_canopus_label(self) -> None:
        result = runner.invoke(app, ["version"])
        assert "Canopus" in result.output

    def test_shows_python_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert "Python" in result.output


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    def test_exits_zero(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_shows_doctor_header(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "Doctor" in result.output

    def test_reports_active_profile(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "local-private" in result.output


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_exits_zero(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["run", "test prompt"])
        assert result.exit_code == 0

    def test_echoes_prompt_in_output(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["run", "test prompt"])
        assert "test prompt" in result.output

    def test_shows_echo_provider_info(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["run", "hello"])
        # Pipeline now runs through EchoProvider; output includes provider name
        assert "echo" in result.output

    def test_creates_trace_file(self, patched_config: AppConfig) -> None:
        traces_dir = patched_config.paths.traces_dir
        runner.invoke(app, ["run", "test prompt"])
        trace_files = list(traces_dir.glob("*.json"))
        assert len(trace_files) == 1

    def test_trace_file_is_valid_json(self, patched_config: AppConfig) -> None:
        traces_dir = patched_config.paths.traces_dir
        runner.invoke(app, ["run", "my request"])
        (trace_file,) = list(traces_dir.glob("*.json"))
        data = json.loads(trace_file.read_text(encoding="utf-8"))
        assert data["mode"] == "run"
        assert data["request"] == "my request"

    def test_missing_prompt_exits_nonzero(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# profile list
# ---------------------------------------------------------------------------


class TestProfileListCommand:
    def test_exits_zero(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0

    def test_shows_all_builtin_profiles(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "list"])
        assert "local-private" in result.output
        assert "hybrid-power" in result.output
        assert "remote-fast" in result.output

    def test_shows_active_profile_label(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "list"])
        # The active profile name appears in both the table and the footer
        assert "local-private" in result.output


# ---------------------------------------------------------------------------
# profile show
# ---------------------------------------------------------------------------


class TestProfileShowCommand:
    def test_exits_zero_explicit_name(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show", "local-private"])
        assert result.exit_code == 0

    def test_exits_zero_default_active(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show"])
        assert result.exit_code == 0

    def test_shows_profile_name(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show", "hybrid-power"])
        assert "hybrid-power" in result.output

    def test_shows_model_routing_info(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show", "hybrid-power"])
        assert "ollama" in result.output

    def test_missing_profile_exits_nonzero(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show", "nonexistent-profile"])
        assert result.exit_code != 0

    def test_missing_profile_shows_error(self, patched_config: AppConfig) -> None:
        result = runner.invoke(app, ["profile", "show", "nonexistent-profile"])
        assert "nonexistent-profile" in result.output

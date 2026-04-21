"""Tests for the execution tracing subsystem."""

from __future__ import annotations

import json
from datetime import UTC

from canopus.core.config import AppConfig
from canopus.core.runtime import RequestMode, create_session
from canopus.core.tracing import ExecutionTrace, TraceWriter


class TestTraceWriter:
    def test_close_creates_file(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        assert trace_path.exists()

    def test_trace_file_is_valid_json(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_trace_contains_run_id(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["run_id"] == session.run_id

    def test_trace_contains_session_id(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["session_id"] == session.session_id

    def test_trace_contains_request(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="my prompt", config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["request"] == "my prompt"

    def test_trace_contains_profile_name(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["profile_name"] == session.profile.name

    def test_trace_contains_mode(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["mode"] == "run"

    def test_trace_has_completed_at(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["completed_at"] is not None

    def test_trace_has_non_negative_duration(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["duration_ms"] >= 0

    def test_trace_records_added_events(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="test", config=tmp_config)
        writer = TraceWriter.from_session(session)
        writer.trace.add_event("request.received", {"text": "test"})
        writer.trace.add_event("response.generated", {"stub": True})
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        event_types = [e["event_type"] for e in data["events"]]
        assert "request.received" in event_types
        assert "response.generated" in event_types

    def test_close_appends_trace_closed_event(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        event_types = [e["event_type"] for e in data["events"]]
        assert "trace.closed" in event_types

    def test_close_stores_result_summary(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close(result_summary="completed successfully")
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["result_summary"] == "completed successfully"

    def test_close_stores_error(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        trace_path = writer.close(error="something went wrong")
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["error"] == "something went wrong"

    def test_close_is_idempotent(self, tmp_config: AppConfig) -> None:
        """Calling close() twice must return the same path and not corrupt the file."""
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        path1 = writer.close()
        path2 = writer.close()
        assert path1 == path2
        # File should still be valid JSON after the second call
        data = json.loads(path1.read_text(encoding="utf-8"))
        assert data["run_id"] == session.run_id

    def test_event_payload_serialised(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        writer = TraceWriter.from_session(session)
        writer.trace.add_event("custom.event", {"key": "value", "number": 42})
        trace_path = writer.close()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        custom = next(e for e in data["events"] if e["event_type"] == "custom.event")
        assert custom["data"]["key"] == "value"
        assert custom["data"]["number"] == 42


class TestExecutionTrace:
    def test_add_event_appends(self) -> None:
        from datetime import datetime

        trace = ExecutionTrace(
            run_id="test-id",
            session_id="test-id",
            mode="run",
            profile_name="local-private",
            request=None,
            started_at=datetime.now(UTC),
        )
        trace.add_event("test.event", {"a": 1})
        assert len(trace.events) == 1
        assert trace.events[0].event_type == "test.event"
        assert trace.events[0].data == {"a": 1}

    def test_add_event_no_data_defaults_to_empty_dict(self) -> None:
        from datetime import datetime

        trace = ExecutionTrace(
            run_id="x",
            session_id="x",
            mode="run",
            profile_name="local-private",
            request=None,
            started_at=datetime.now(UTC),
        )
        trace.add_event("no.data.event")
        assert trace.events[0].data == {}

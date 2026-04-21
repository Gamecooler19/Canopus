"""Tests for session runtime creation and lifecycle."""

from __future__ import annotations

import uuid

from canopus.core.config import AppConfig
from canopus.core.runtime import RequestMode, SessionRuntime, create_session


class TestCreateSession:
    def test_returns_session_runtime(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert isinstance(session, SessionRuntime)

    def test_run_id_is_valid_uuid(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        parsed = uuid.UUID(session.run_id)
        assert str(parsed) == session.run_id

    def test_session_id_is_valid_uuid(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        parsed = uuid.UUID(session.session_id)
        assert str(parsed) == session.session_id

    def test_unique_run_ids_per_session(self, tmp_config: AppConfig) -> None:
        s1 = create_session(RequestMode.RUN, config=tmp_config)
        s2 = create_session(RequestMode.RUN, config=tmp_config)
        assert s1.run_id != s2.run_id

    def test_mode_stored_correctly(self, tmp_config: AppConfig) -> None:
        for mode in [RequestMode.RUN, RequestMode.CHAT, RequestMode.DOCTOR]:
            session = create_session(mode, config=tmp_config)
            assert session.mode == mode

    def test_request_stored(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, request="hello world", config=tmp_config)
        assert session.request == "hello world"

    def test_no_request_defaults_to_none(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.DOCTOR, config=tmp_config)
        assert session.request is None

    def test_default_profile_loads(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.profile.name == tmp_config.active_profile

    def test_trace_path_inside_traces_dir(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.trace_path.parent == tmp_config.paths.traces_dir

    def test_trace_path_is_json_extension(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.trace_path.suffix == ".json"

    def test_trace_path_matches_run_id(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.run_id in session.trace_path.name

    def test_started_at_is_set(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.started_at is not None

    def test_completed_at_none_before_finalize(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.completed_at is None

    def test_duration_ms_none_before_finalize(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        assert session.duration_ms is None


class TestSessionFinalize:
    def test_finalize_sets_completed_at(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        session.finalize()
        assert session.completed_at is not None

    def test_finalize_duration_non_negative(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        session.finalize()
        assert session.duration_ms is not None
        assert session.duration_ms >= 0

    def test_finalize_twice_overwrites_completed_at(self, tmp_config: AppConfig) -> None:
        session = create_session(RequestMode.RUN, config=tmp_config)
        session.finalize()
        first = session.completed_at
        session.finalize()
        second = session.completed_at
        # Both are set; the second call may be equal or later but never earlier
        assert second >= first  # type: ignore[operator]


class TestDirectoriesCreated:
    def test_ensure_all_creates_traces_dir(self, tmp_config: AppConfig) -> None:
        assert tmp_config.paths.traces_dir.exists()

    def test_ensure_all_creates_plugins_dir(self, tmp_config: AppConfig) -> None:
        assert tmp_config.paths.plugins_dir.exists()

    def test_ensure_all_creates_logs_dir(self, tmp_config: AppConfig) -> None:
        assert tmp_config.paths.logs_dir.exists()

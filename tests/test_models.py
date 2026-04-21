"""Tests for the model abstraction layer: base types, EchoProvider, and ModelRouter."""

from __future__ import annotations

import pytest

from canopus.core.profiles import ProfileLoader, builtin_profiles
from canopus.models.base import ModelProvider, ModelRequest, ModelResponse
from canopus.models.local.echo import EchoProvider
from canopus.models.router import ModelRouter

# ---------------------------------------------------------------------------
# ModelRequest / ModelResponse
# ---------------------------------------------------------------------------


class TestModelRequest:
    def test_creates_with_prompt_only(self) -> None:
        req = ModelRequest(prompt="hello")
        assert req.prompt == "hello"
        assert req.system_prompt is None
        assert req.max_tokens == 1024

    def test_accepts_system_prompt(self) -> None:
        req = ModelRequest(prompt="hello", system_prompt="You are helpful.")
        assert req.system_prompt == "You are helpful."

    def test_temperature_within_range(self) -> None:
        req = ModelRequest(prompt="x", temperature=0.0)
        assert req.temperature == 0.0
        req2 = ModelRequest(prompt="x", temperature=2.0)
        assert req2.temperature == 2.0

    def test_temperature_out_of_range_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ModelRequest(prompt="x", temperature=3.0)


class TestModelResponse:
    def test_creates_with_required_fields(self) -> None:
        resp = ModelResponse(text="hi", provider_name="test", model_name="m1")
        assert resp.text == "hi"
        assert resp.provider_name == "test"
        assert resp.model_name == "m1"

    def test_optional_fields_default_none(self) -> None:
        resp = ModelResponse(text="hi", provider_name="p", model_name="m")
        assert resp.prompt_tokens is None
        assert resp.completion_tokens is None
        assert resp.latency_ms is None
        assert resp.finish_reason is None


# ---------------------------------------------------------------------------
# EchoProvider
# ---------------------------------------------------------------------------


class TestEchoProvider:
    def test_is_available(self) -> None:
        provider = EchoProvider()
        assert provider.is_available() is True

    def test_provider_name(self) -> None:
        assert EchoProvider().provider_name == "echo"

    def test_model_name(self) -> None:
        assert EchoProvider().model_name == "echo-1.0"

    def test_satisfies_protocol(self) -> None:
        assert isinstance(EchoProvider(), ModelProvider)

    def test_complete_returns_response(self) -> None:
        provider = EchoProvider()
        request = ModelRequest(prompt="hello world")
        response = provider.complete(request)
        assert isinstance(response, ModelResponse)

    def test_complete_provider_name_in_response(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="test"))
        assert response.provider_name == "echo"

    def test_complete_model_name_in_response(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="test"))
        assert response.model_name == "echo-1.0"

    def test_complete_returns_non_empty_text(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="test"))
        assert len(response.text.strip()) > 0

    def test_complete_finish_reason_is_stop(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="test"))
        assert response.finish_reason == "stop"

    def test_complete_records_prompt_tokens(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="one two three"))
        assert response.prompt_tokens == 3

    def test_complete_records_latency(self) -> None:
        response = EchoProvider().complete(ModelRequest(prompt="test"))
        assert response.latency_ms is not None
        assert response.latency_ms >= 0.0

    def test_complete_with_system_prompt_mentions_it(self) -> None:
        response = EchoProvider().complete(
            ModelRequest(prompt="test", system_prompt="You are Canopus.")
        )
        assert "System context" in response.text

    def test_complete_long_prompt_truncated_in_response(self) -> None:
        long_prompt = "word " * 50
        response = EchoProvider().complete(ModelRequest(prompt=long_prompt))
        # The ellipsis indicates truncation
        assert "…" in response.text


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


class TestModelRouter:
    def test_returns_echo_for_local_private_no_adapter(self) -> None:
        profile = builtin_profiles()["local-private"]
        provider = ModelRouter().get_provider(profile)
        assert isinstance(provider, EchoProvider)

    def test_returns_echo_for_hybrid_power_no_adapter(self) -> None:
        profile = builtin_profiles()["hybrid-power"]
        provider = ModelRouter().get_provider(profile)
        assert isinstance(provider, EchoProvider)

    def test_returns_echo_for_remote_fast_no_adapter(self) -> None:
        profile = builtin_profiles()["remote-fast"]
        provider = ModelRouter().get_provider(profile)
        assert isinstance(provider, EchoProvider)

    def test_returned_provider_is_available(self) -> None:
        profile = builtin_profiles()["local-private"]
        provider = ModelRouter().get_provider(profile)
        assert provider.is_available()

    def test_returned_provider_satisfies_protocol(self) -> None:
        profile = builtin_profiles()["local-private"]
        provider = ModelRouter().get_provider(profile)
        assert isinstance(provider, ModelProvider)

    def test_profile_with_no_providers_set_returns_echo(self, tmp_path: Path) -> None:  # noqa: F821

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        toml = """\
name = "bare"
display_name = "Bare"
description = "no providers"
"""
        (profiles_dir / "bare.toml").write_text(toml, encoding="utf-8")
        loader = ProfileLoader(profiles_dir=profiles_dir)
        profile = loader.load("bare")
        provider = ModelRouter().get_provider(profile)
        assert isinstance(provider, EchoProvider)

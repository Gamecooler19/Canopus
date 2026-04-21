"""Tests for profile loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from canopus.core.errors import ProfileNotFoundError
from canopus.core.profiles import ProfileLoader, builtin_profiles

# ---------------------------------------------------------------------------
# Built-in profile registry
# ---------------------------------------------------------------------------


class TestBuiltinProfiles:
    def test_three_builtin_profiles_ship(self) -> None:
        profiles = builtin_profiles()
        assert len(profiles) == 3

    def test_expected_names_present(self) -> None:
        profiles = builtin_profiles()
        assert "local-private" in profiles
        assert "hybrid-power" in profiles
        assert "remote-fast" in profiles

    def test_local_private_blocks_network(self) -> None:
        lp = builtin_profiles()["local-private"]
        assert not lp.network.allow_network

    def test_local_private_no_remote_fallback(self) -> None:
        lp = builtin_profiles()["local-private"]
        assert not lp.model_routing.fallback_to_remote

    def test_local_private_no_mcp(self) -> None:
        lp = builtin_profiles()["local-private"]
        assert not lp.mcp_enabled

    def test_hybrid_power_allows_fallback(self) -> None:
        hp = builtin_profiles()["hybrid-power"]
        assert hp.model_routing.fallback_to_remote

    def test_hybrid_power_allows_network(self) -> None:
        hp = builtin_profiles()["hybrid-power"]
        assert hp.network.allow_network

    def test_hybrid_power_has_mcp(self) -> None:
        hp = builtin_profiles()["hybrid-power"]
        assert hp.mcp_enabled

    def test_remote_fast_prefers_remote(self) -> None:
        rf = builtin_profiles()["remote-fast"]
        assert not rf.model_routing.prefer_local

    def test_all_builtins_have_tracing_enabled(self) -> None:
        for profile in builtin_profiles().values():
            assert profile.tracing_enabled, f"{profile.name} should have tracing enabled"

    def test_all_builtins_source_is_builtin(self) -> None:
        for profile in builtin_profiles().values():
            assert profile.source == "builtin"


# ---------------------------------------------------------------------------
# ProfileLoader — built-in resolution
# ---------------------------------------------------------------------------


class TestProfileLoaderBuiltins:
    def test_load_local_private(self) -> None:
        loader = ProfileLoader(profiles_dir=None)
        profile = loader.load("local-private")
        assert profile.name == "local-private"
        assert profile.source == "builtin"

    def test_load_hybrid_power(self) -> None:
        loader = ProfileLoader(profiles_dir=None)
        profile = loader.load("hybrid-power")
        assert profile.name == "hybrid-power"

    def test_load_remote_fast(self) -> None:
        loader = ProfileLoader(profiles_dir=None)
        profile = loader.load("remote-fast")
        assert profile.name == "remote-fast"

    def test_load_missing_raises(self) -> None:
        loader = ProfileLoader(profiles_dir=None)
        with pytest.raises(ProfileNotFoundError) as exc_info:
            loader.load("does-not-exist")
        assert exc_info.value.profile_name == "does-not-exist"

    def test_list_all_no_dir_returns_builtins(self) -> None:
        loader = ProfileLoader(profiles_dir=Path("/nonexistent"))
        names = [p.name for p in loader.list_all()]
        assert "local-private" in names
        assert "hybrid-power" in names
        assert "remote-fast" in names

    def test_list_all_none_dir_returns_builtins(self) -> None:
        loader = ProfileLoader(profiles_dir=None)
        assert len(loader.list_all()) == 3


# ---------------------------------------------------------------------------
# ProfileLoader — user TOML loading
# ---------------------------------------------------------------------------

_VALID_TOML = """\
name = "custom-profile"
display_name = "Custom Profile"
description = "A user-defined test profile"
tracing_enabled = true
mcp_enabled = false
source = "user"

[model_routing]
prefer_local = true

[voice]
stt_provider = "local"
tts_provider = "local"
push_to_talk = true
enabled = false

[network]
allow_network = false

[memory]
enabled = true
max_context_tokens = 2048
semantic_retrieval = false
"""


class TestProfileLoaderUserToml:
    def test_load_user_profile_from_toml(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "custom-profile.toml").write_text(_VALID_TOML, encoding="utf-8")

        loader = ProfileLoader(profiles_dir=profiles_dir)
        profile = loader.load("custom-profile")

        assert profile.name == "custom-profile"
        assert profile.display_name == "Custom Profile"
        assert profile.source == "user"

    def test_user_profile_overrides_builtin(self, tmp_path: Path) -> None:
        """A user TOML sharing a name with a built-in should win."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        override_toml = _VALID_TOML.replace(
            'name = "custom-profile"', 'name = "local-private"'
        ).replace(
            'display_name = "Custom Profile"', 'display_name = "Overridden Local Private"'
        )
        (profiles_dir / "local-private.toml").write_text(override_toml, encoding="utf-8")

        loader = ProfileLoader(profiles_dir=profiles_dir)
        profile = loader.load("local-private")

        assert profile.display_name == "Overridden Local Private"
        assert profile.source == "user"

    def test_list_all_includes_user_and_builtins(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "custom-profile.toml").write_text(_VALID_TOML, encoding="utf-8")

        loader = ProfileLoader(profiles_dir=profiles_dir)
        all_profiles = loader.list_all()
        names = [p.name for p in all_profiles]

        assert "custom-profile" in names
        assert "local-private" in names

    def test_malformed_toml_skipped_in_list(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "broken.toml").write_text("[[[[invalid", encoding="utf-8")

        loader = ProfileLoader(profiles_dir=profiles_dir)
        # Should not raise; broken profile is silently skipped
        all_profiles = loader.list_all()
        names = [p.name for p in all_profiles]
        assert "broken" not in names

    def test_source_defaults_to_user_if_omitted(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        toml_no_source = _VALID_TOML.replace('source = "user"\n', "")
        (profiles_dir / "custom-profile.toml").write_text(toml_no_source, encoding="utf-8")

        loader = ProfileLoader(profiles_dir=profiles_dir)
        profile = loader.load("custom-profile")
        assert profile.source == "user"

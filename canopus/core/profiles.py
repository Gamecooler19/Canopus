"""Runtime profile definitions and loading.

Profiles are named sets of configuration preferences that control:
- Model routing (local vs. remote provider, fallback rules)
- Voice engine selection
- Network access policy
- Memory subsystem behaviour
- Feature flags (MCP, tracing, …)

Three built-in profiles ship with Canopus. Users may override any built-in
or define new profiles by placing a ``.toml`` file in
``~/.canopus/config/profiles/``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from canopus.core.errors import ProfileError, ProfileNotFoundError

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ModelRoutingPreference(BaseModel):
    """Preferences for model selection and provider routing."""

    prefer_local: bool = True
    """Prefer a locally-hosted model over a remote API when both are available."""

    local_provider: str | None = None
    """Local provider identifier, e.g. ``"ollama"`` or ``"llama_cpp"``."""

    local_model: str | None = None
    """Specific local model name, e.g. ``"llama3.2:3b"``."""

    remote_provider: str | None = None
    """Remote provider identifier, e.g. ``"openai"``, ``"anthropic"``, ``"groq"``."""

    remote_model: str | None = None
    """Specific remote model name, e.g. ``"gpt-4o-mini"``."""

    fallback_to_remote: bool = False
    """If the local provider is unavailable, fall back to the remote provider."""


class VoiceSettings(BaseModel):
    """Voice pipeline configuration."""

    enabled: bool = False
    """Whether voice I/O is active for this profile."""

    stt_provider: str = "local"
    """Speech-to-text provider: ``"local"`` (Whisper) or ``"remote"``."""

    tts_provider: str = "local"
    """Text-to-speech provider: ``"local"`` (Piper) or ``"remote"``."""

    push_to_talk: bool = True
    """Use push-to-talk activation (vs. continuous / wake-word)."""


class NetworkPolicy(BaseModel):
    """Network access policy for the profile."""

    allow_network: bool = False
    """Whether outbound network calls are permitted."""

    allowed_domains: list[str] = Field(default_factory=list)
    """Explicit domain allowlist when ``allow_network`` is ``True``."""


class MemorySettings(BaseModel):
    """Configuration for the memory subsystem."""

    enabled: bool = True
    max_context_tokens: int = 4096
    """Maximum tokens to inject from retrieved memory into the context window."""

    semantic_retrieval: bool = False
    """Enable semantic (vector) retrieval. Requires a configured embedding backend."""


# ---------------------------------------------------------------------------
# Root profile model
# ---------------------------------------------------------------------------


class ProfileSettings(BaseModel):
    """Complete settings for a named Canopus runtime profile."""

    name: str
    display_name: str
    description: str

    model_routing: ModelRoutingPreference = Field(
        default_factory=ModelRoutingPreference
    )
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    memory: MemorySettings = Field(default_factory=MemorySettings)

    tracing_enabled: bool = True
    mcp_enabled: bool = False

    source: Literal["builtin", "user"] = "builtin"
    """Where this profile was loaded from."""


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

_BUILTIN_PROFILES: dict[str, ProfileSettings] = {
    "local-private": ProfileSettings(
        name="local-private",
        display_name="Local Private",
        description=(
            "Fully local operation. No network access. "
            "Uses a local LLM and local voice engines. "
            "Prioritises privacy — nothing leaves the machine."
        ),
        model_routing=ModelRoutingPreference(
            prefer_local=True,
            local_provider="ollama",
            fallback_to_remote=False,
        ),
        voice=VoiceSettings(
            enabled=False,
            stt_provider="local",
            tts_provider="local",
        ),
        network=NetworkPolicy(allow_network=False),
        mcp_enabled=False,
        source="builtin",
    ),
    "hybrid-power": ProfileSettings(
        name="hybrid-power",
        display_name="Hybrid Power",
        description=(
            "Local classification with remote reasoning for complex tasks. "
            "MCP tools enabled. Best balance of privacy and capability."
        ),
        model_routing=ModelRoutingPreference(
            prefer_local=True,
            local_provider="ollama",
            remote_provider="openai",
            fallback_to_remote=True,
        ),
        voice=VoiceSettings(
            enabled=False,
            stt_provider="local",
            tts_provider="local",
        ),
        network=NetworkPolicy(allow_network=True),
        mcp_enabled=True,
        source="builtin",
    ),
    "remote-fast": ProfileSettings(
        name="remote-fast",
        display_name="Remote Fast",
        description=(
            "Remote model and speech stack. "
            "Lightweight local runtime. "
            "Best performance for cloud-friendly workflows."
        ),
        model_routing=ModelRoutingPreference(
            prefer_local=False,
            remote_provider="openai",
            remote_model="gpt-4o-mini",
            fallback_to_remote=False,
        ),
        voice=VoiceSettings(
            enabled=False,
            stt_provider="remote",
            tts_provider="remote",
        ),
        network=NetworkPolicy(allow_network=True),
        mcp_enabled=True,
        source="builtin",
    ),
}


def builtin_profiles() -> dict[str, ProfileSettings]:
    """Return an immutable view of the built-in profile registry."""
    return dict(_BUILTIN_PROFILES)


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------


class ProfileLoader:
    """Loads profiles from user TOML files and falls back to built-ins.

    User profiles live in ``~/.canopus/config/profiles/<name>.toml``.
    A user TOML file that shares a name with a built-in profile **overrides**
    the built-in.

    Args:
        profiles_dir: Path to the user profiles directory. If ``None`` or the
            directory does not exist, only built-in profiles are available.
    """

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._profiles_dir = profiles_dir

    def load(self, name: str) -> ProfileSettings:
        """Load a profile by name.

        Checks the user profiles directory first, then falls back to built-ins.

        Args:
            name: Profile identifier, e.g. ``"local-private"``.

        Returns:
            The resolved :class:`ProfileSettings`.

        Raises:
            :class:`~canopus.core.errors.ProfileNotFoundError`: If the profile
                is not found in any source.
            :class:`~canopus.core.errors.ProfileError`: If a user TOML file
                exists but fails to parse.
        """
        if self._profiles_dir and self._profiles_dir.exists():
            toml_path = self._profiles_dir / f"{name}.toml"
            if toml_path.exists():
                return self._load_from_toml(toml_path)

        if name in _BUILTIN_PROFILES:
            return _BUILTIN_PROFILES[name]

        raise ProfileNotFoundError(name)

    def list_all(self) -> list[ProfileSettings]:
        """Return all available profiles: user-defined first, then built-ins.

        If a user-defined profile shares a name with a built-in, the
        user-defined version is returned and the built-in is omitted.
        Malformed user TOML files are silently skipped in listing.
        """
        profiles: dict[str, ProfileSettings] = {}

        if self._profiles_dir and self._profiles_dir.exists():
            for toml_path in sorted(self._profiles_dir.glob("*.toml")):
                try:
                    profile = self._load_from_toml(toml_path)
                    profiles[profile.name] = profile
                except (ProfileError, Exception):
                    pass  # Skip silently; surfaced individually via load()

        for name, profile in _BUILTIN_PROFILES.items():
            if name not in profiles:
                profiles[name] = profile

        return list(profiles.values())

    @staticmethod
    def _load_from_toml(path: Path) -> ProfileSettings:
        """Parse a :class:`ProfileSettings` from a TOML file.

        Raises:
            :class:`~canopus.core.errors.ProfileError`: On any parse or
                validation failure.
        """
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
            # Ensure source reflects real origin even if file omits it.
            data.setdefault("source", "user")
            return ProfileSettings(**data)
        except Exception as exc:
            raise ProfileError(
                f"Failed to load profile from {path}: {exc}"
            ) from exc

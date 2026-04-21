"""Model router — selects the appropriate provider for a session.

The router reads the active :class:`~canopus.core.profiles.ProfileSettings`
and returns the best available :class:`~canopus.models.base.ModelProvider`.

Routing priority (derived from profile ``model_routing`` settings):

1. Local provider — when ``prefer_local=True`` and ``local_provider`` is set.
2. Remote provider — when ``prefer_local=False`` and ``remote_provider`` is set.
3. Remote fallback — when ``fallback_to_remote=True`` after a local failure.
4. Echo provider — automatic fallback when no real provider is reachable.

Phase 2 installs only the EchoProvider fallback. Real local and remote
adapters plug in here in Phase 3, replacing the ``None``-returning stubs
in :meth:`ModelRouter._try_local` and :meth:`ModelRouter._try_remote`.
"""

from __future__ import annotations

from canopus.core.profiles import ModelRoutingPreference, ProfileSettings
from canopus.models.base import ModelProvider
from canopus.models.local.echo import EchoProvider


class ModelRouter:
    """Selects and returns a ready :class:`~canopus.models.base.ModelProvider`.

    The router is stateless — call :meth:`get_provider` for each session or
    request. Providers are not cached; callers may wrap the result in a
    session-scoped cache if needed.
    """

    def get_provider(self, profile: ProfileSettings) -> ModelProvider:
        """Return the best available provider for *profile*.

        The method follows the routing preference order described in the module
        docstring and always returns a valid provider — falling back to
        :class:`~canopus.models.local.echo.EchoProvider` if nothing else is
        reachable.

        Args:
            profile: The active runtime profile whose ``model_routing``
                settings drive the selection.

        Returns:
            A :class:`~canopus.models.base.ModelProvider` that is ready to
            accept :meth:`~canopus.models.base.ModelProvider.complete` calls.
        """
        routing = profile.model_routing

        # 1. Prefer local
        if routing.prefer_local and routing.local_provider:
            provider = self._try_local(routing)
            if provider is not None:
                return provider

        # 2. Prefer remote
        if not routing.prefer_local and routing.remote_provider:
            provider = self._try_remote(routing)
            if provider is not None:
                return provider

        # 3. Remote fallback
        if routing.fallback_to_remote and routing.remote_provider:
            provider = self._try_remote(routing)
            if provider is not None:
                return provider

        # 4. Echo fallback — always available
        return EchoProvider()

    # ------------------------------------------------------------------
    # Private stubs — replaced by real adapters in Phase 3+
    # ------------------------------------------------------------------

    @staticmethod
    def _try_local(routing: ModelRoutingPreference) -> ModelProvider | None:  # noqa: ARG004
        """Attempt to build a local provider from *routing*.

        Returns ``None`` until a real local adapter is registered. Phase 3
        will check ``routing.local_provider`` (e.g. ``"ollama"``) and return
        the matching adapter if the backend is reachable.
        """
        return None

    @staticmethod
    def _try_remote(routing: ModelRoutingPreference) -> ModelProvider | None:  # noqa: ARG004
        """Attempt to build a remote provider from *routing*.

        Returns ``None`` until a real remote adapter is registered. Phase 3
        will check ``routing.remote_provider`` (e.g. ``"openai"``) and return
        the matching adapter if credentials are available.
        """
        return None

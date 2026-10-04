"""Google Antigravity provider profile.

Natively wired: the credential is the user's signed-in Antigravity / Google session (discovered
from the OS keyring and owned by Shiina as ``credential_pool.antigravity`` — see
``shiina_cli/auth_antigravity.py``), and inference targets Google Cloud Code Assist directly
through :class:`agent.antigravity_client.AntigravityClient`. Nothing shells out to ``agy``.
"""

from __future__ import annotations

import logging
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

# Curated fallback shown in the /model picker when the live catalog can't be fetched.
ANTIGRAVITY_MODELS = (
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6",
    "gemini-pro-agent",
    "gemini-3.8-flash-tiered",
    "gpt-oss-120b-medium",
    "gemini-3.5-flash-lite",
)

ANTIGRAVITY_BASE_URL = "https://daily-cloudcode-pa.googleapis.com"


class AntigravityProfile(ProviderProfile):
    """Google Antigravity provider profile (Cloud Code Assist, session-authenticated)."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.antigravity_client import AntigravityClient

        return AntigravityClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        """Live model catalog from Cloud Code Assist, falling back to the curated list."""
        try:
            from agent.antigravity_client import AntigravityClient

            client = AntigravityClient(api_key=api_key, base_url=base_url)
            try:
                models = client.list_models(timeout=timeout)
            finally:
                client.close()
            if models:
                return models
        except Exception:
            logger.debug("Antigravity model listing failed; using the curated catalog.", exc_info=True)
        return list(ANTIGRAVITY_MODELS)


antigravity = AntigravityProfile(
    name="antigravity",
    display_name="Google Antigravity",
    description="Google Antigravity (Cloud Code Assist, signed-in session)",
    aliases=("agy", "google-antigravity", "jetski"),
    api_mode="chat_completions",
    env_vars=(),
    base_url=ANTIGRAVITY_BASE_URL,
    auth_type="oauth_external",
    fallback_models=ANTIGRAVITY_MODELS,
    default_aux_model="gemini-3.8-flash-tiered",
    supports_vision=True,
)

register_provider(antigravity)

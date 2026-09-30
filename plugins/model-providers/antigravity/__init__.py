"""Google Antigravity provider profile.

Drives the local `agy` CLI over stdio in stream-json mode, so the profile
supplies its own client via :meth:`ProviderProfile.create_client`.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

ANTIGRAVITY_MODELS = (
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6",
    "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-high",
    "gemini-pro-agent",
    "gemini-3.1-pro-high",
    "gemini-3.1-pro-low",
    "gpt-oss-120b-medium",
    "gemini-3.5-flash-lite",
)


class AntigravityProfile(ProviderProfile):
    """Google Antigravity provider profile."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.antigravity_client import AntigravityClient

        return AntigravityClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        del api_key, base_url
        try:
            from agent.antigravity_client import fetch_antigravity_models

            models = fetch_antigravity_models(timeout=timeout)
            if models:
                return models
        except Exception as exc:
            logger.debug("Failed dynamic Antigravity model fetch: %s", exc)
        return list(ANTIGRAVITY_MODELS)


antigravity = AntigravityProfile(
    name="antigravity",
    aliases=("agy", "google-antigravity", "jetski"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="agy://local",
    auth_type="external_process",
    process_command="agy",
    process_args=(
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
        "--disable-slash-commands",
    ),
    process_command_env_vars=("SHIINA_AGY_COMMAND", "AGY_BIN", "ANTIGRAVITY_BIN"),
    process_args_env_var="SHIINA_AGY_ARGS",
    fallback_models=ANTIGRAVITY_MODELS,
    default_aux_model="gemini-3.8-flash-tiered",
    supports_vision=True,
)

register_provider(antigravity)

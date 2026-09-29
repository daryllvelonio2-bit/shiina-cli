"""Freebuff CLI provider profile.

Drives the local `freebuff` CLI in headless mode, supplying its own
client facade via :meth:`ProviderProfile.create_client`.
"""

from __future__ import annotations

import logging
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

FREEBUFF_MODELS = (
    "glm-5.3-flash",
    "deepseek-v4-flash",
    "gpt-5.6-luna",
    "gpt-6-luna",
    "mimo-v2.5",
    "mimo-v2.6-pro",
    "solar-pro4",
    "solar-mini4",
    "kimi-k3-eco",
    "gemini-3.8-flash",
    "muse-spark-1.2",
)


class FreebuffProfile(ProviderProfile):
    """Freebuff CLI provider profile."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.freebuff_client import FreebuffClient

        return FreebuffClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        del api_key, base_url, timeout
        return list(FREEBUFF_MODELS)


freebuff = FreebuffProfile(
    name="freebuff",
    aliases=("codebuff", "freebuff-cli"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="freebuff://local",
    auth_type="external_process",
    process_command="freebuff",
    process_args=(),
    process_command_env_vars=("SHIINA_FREEBUFF_COMMAND", "FREEBUFF_BIN"),
    process_args_env_var="SHIINA_FREEBUFF_ARGS",
    fallback_models=FREEBUFF_MODELS,
    default_aux_model="glm-5.3-flash",
    supports_vision=False,
)

register_provider(freebuff)

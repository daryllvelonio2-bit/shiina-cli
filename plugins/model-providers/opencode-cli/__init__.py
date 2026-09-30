"""OpenCode CLI provider profile.

Drives the local `opencode` CLI in headless mode, supplying its own
client facade via :meth:`ProviderProfile.create_client`.
"""

from __future__ import annotations

import logging
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

OPENCODE_MODELS = (
    "opencode/big-pickle",
    "opencode/ling-3.0-flash-fin-free",
    "opencode/longcat-2.5-preview-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/muse-spark-1.3-contributor-free",
    "opencode/nemotron-3-ultra-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/space-bunny-free",
)


class OpenCodeCliProfile(ProviderProfile):
    """OpenCode CLI provider profile."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.opencode_client import OpenCodeClient

        return OpenCodeClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        del api_key, base_url
        try:
            from agent.opencode_client import fetch_opencode_models

            models = fetch_opencode_models(timeout=timeout)
            if models:
                return models
        except Exception as exc:
            logger.debug("Failed dynamic OpenCode model fetch: %s", exc)
        return list(OPENCODE_MODELS)


opencode_cli = OpenCodeCliProfile(
    name="opencode-cli",
    aliases=("opencode-local", "opencode-agent", "opencode-bin", "opencode-dev"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="opencode://local",
    auth_type="external_process",
    process_command="opencode",
    process_args=(),
    process_command_env_vars=("SHIINA_OPENCODE_COMMAND", "OPENCODE_BIN"),
    process_args_env_var="SHIINA_OPENCODE_ARGS",
    fallback_models=OPENCODE_MODELS,
    default_aux_model="opencode/big-pickle",
    supports_vision=False,
)

register_provider(opencode_cli)

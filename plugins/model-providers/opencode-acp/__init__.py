"""OpenCode ACP provider profile.

Drives the local `opencode` CLI in ACP mode over stdio, supplying its own
client facade via :meth:`ProviderProfile.create_client`.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

OPENCODE_MODELS = (
    "opencode/nemotron-3-ultra-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/big-pickle",
    "opencode/ling-3.0-flash-fin-free",
    "opencode/longcat-2.5-preview-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/muse-spark-1.3-contributor-free",
    "opencode/space-bunny-free",
)


def _resolve_opencode_binary() -> str:
    from_env = next(
        (os.getenv(v, "").strip() for v in ("SHIINA_OPENCODE_ACP_COMMAND", "OPENCODE_BIN", "OPENCODE_CLI_PATH") if os.getenv(v, "").strip()),
        ""
    )
    if from_env:
        return from_env
    resolved = shutil.which("opencode")
    if resolved:
        return resolved
    fallback = os.path.expanduser("~/.opencode/bin/opencode")
    if os.path.exists(fallback):
        return fallback
    return "opencode"


class OpenCodeACPProfile(ProviderProfile):
    """OpenCode ACP provider profile."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.copilot_acp_client import CopilotACPClient

        cmd = _resolve_opencode_binary()
        client_kwargs.setdefault("command", cmd)
        client_kwargs.setdefault("args", list(self.process_args))
        return CopilotACPClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        try:
            client = self.create_client()
            return client.list_models(timeout_seconds=timeout) or list(OPENCODE_MODELS)
        except Exception:
            return list(OPENCODE_MODELS)


opencode_acp = OpenCodeACPProfile(
    name="opencode-acp",
    aliases=("opencode", "opencode-cli", "opencode_acp"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="acp://opencode",
    auth_type="external_process",
    process_command="/home/jay/.opencode/bin/opencode",
    process_args=("acp",),
    process_command_env_vars=("SHIINA_OPENCODE_ACP_COMMAND", "OPENCODE_BIN", "OPENCODE_CLI_PATH"),
    process_args_env_var="SHIINA_OPENCODE_ACP_ARGS",
    fallback_models=OPENCODE_MODELS,
    default_aux_model="opencode/nemotron-3-ultra-free",
    supports_vision=True,
)

register_provider(opencode_acp)

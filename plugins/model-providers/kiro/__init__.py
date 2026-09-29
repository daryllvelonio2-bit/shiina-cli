"""Kiro provider profile.

Drives the local `kiro-cli` tool in-process via KiroClient,
authenticating with the user's logged-in Kiro account stored in ~/.local/share/kiro-cli/data.sqlite3.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

KIRO_MODELS = (
    "claude-sonnet-4.5",
    "claude-sonnet-4",
    "claude-haiku-4.5",
    "deepseek-3.2",
    "minimax-m2.5",
    "minimax-m2.1",
    "glm-5",
    "qwen3-coder-next",
    "auto",
)


class KiroProfile(ProviderProfile):
    """Kiro provider profile."""

    def create_client(self, **client_kwargs: Any) -> Any:
        from agent.kiro_client import KiroClient

        return KiroClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        from shiina_cli.auth import resolve_external_process_provider_credentials

        try:
            creds = resolve_external_process_provider_credentials(self.name)
            cmd = creds.get("command") or "kiro-cli"
            proc = subprocess.run(
                [cmd, "chat", "--list-models", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout:
                import json
                data = json.loads(proc.stdout)
                models = [m["model_id"] for m in data.get("models", []) if isinstance(m, dict) and "model_id" in m]
                if models:
                    return models
        except Exception:
            pass
        return list(KIRO_MODELS)


kiro = KiroProfile(
    name="kiro",
    aliases=("kiro-cli", "kiro-ai", "kiro-dev", "xkiro"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="kiro://local",
    auth_type="external_process",
    process_command="kiro-cli",
    process_args=("--no-interactive", "--trust-tools="),
    process_command_env_vars=("SHIINA_KIRO_COMMAND", "KIRO_BIN", "KIRO_CLI_PATH"),
    process_args_env_var="SHIINA_KIRO_ARGS",
    fallback_models=KIRO_MODELS,
    default_aux_model="claude-haiku-4.5",
    supports_vision=True,
)

register_provider(kiro)

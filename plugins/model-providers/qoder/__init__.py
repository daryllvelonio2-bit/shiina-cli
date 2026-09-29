"""Qoder AI provider profile.

Drives Qoder AI models (Qwen3.8-Max, Qwen3.8-Flash, Sonus, Cantus, DeepSeek-V4-Pro,
Kimi-K3, GLM-5.3, MiniMax-M3) natively in-process via QoderClient with sub-second
streaming, live thinking/reasoning display, and native structured tool calling.
"""

from __future__ import annotations

import logging
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

QODER_MODELS = (
    "Auto",
    "Qwen3.8-Max",
    "Qwen3.8-Flash",
    "Qwen3.7-Max",
    "Qwen3.7-Plus",
    "Sonus",
    "Cantus",
    "DeepSeek-V4-Pro",
    "DeepSeek-Flash",
    "Kimi-K3",
    "Kimi-K2.8-Preview",
    "GLM-5.3",
    "GLM-5.3-Flash",
    "MiniMax-M3",
    "Ultimate",
    "Performance",
    "Efficient",
)


class QoderProfile(ProviderProfile):
    """Qoder provider profile."""

    def create_client(self, agent: Any = None, **client_kwargs: Any) -> Any:
        from agent.qoder_client import QoderClient

        if agent is not None and "agent" not in client_kwargs:
            client_kwargs["agent"] = agent
        return QoderClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        from agent.qoder_client import fetch_qoder_models

        try:
            models = fetch_qoder_models(timeout=timeout)
            if models:
                return models
        except Exception:
            pass
        return list(QODER_MODELS)


qoder = QoderProfile(
    name="qoder",
    aliases=("qoder-ai", "qoder.com", "qoder-sh"),
    display_name="Qoder",
    description="Qoder AI (Qwen3.8, Sonus, Cantus, DeepSeek, Kimi, GLM, MiniMax via PAT)",
    signup_url="https://qoder.com/account/integrations",
    api_mode="chat_completions",
    env_vars=("QODER_PAT", "QODER_API_KEY", "QODER_PERSONAL_ACCESS_TOKEN"),
    base_url="https://api2.qoder.sh",
    auth_type="api_key",
    fallback_models=QODER_MODELS,
    default_aux_model="Qwen3.8-Flash",
    supports_vision=True,
)

register_provider(qoder)

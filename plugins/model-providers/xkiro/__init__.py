"""xKiro provider profile.

Direct OpenAI-compatible API at https://api.xkiro.com/v1 (Bearer token).
Distinct from the local ``kiro`` CLI provider: this one is key-authenticated and
serves the hosted xKiro model catalog (GPT, Claude, Gemini, Grok, Kimi, DeepSeek, GLM, ...).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.xkiro.com/v1"

XKIRO_MODELS = (
    "openai/gpt-6-sol",
    "openai/gpt-5.6-luna",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "google/gemini-3.8-flash",
    "x-ai/grok-4.7",
    "deepseek/deepseek-v4.1-flash:free",
    "z-ai/glm-5",
    "moonshotai/kimi-k3",
)


class XKiroProfile(ProviderProfile):
    """xKiro provider profile (hosted OpenAI-compatible API)."""

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        token = (api_key or os.environ.get("XKIRO_API_KEY") or "").strip()
        if not token:
            return None
        root = str(base_url or self.base_url or DEFAULT_BASE_URL).rstrip("/")
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(
                    f"{root}/models",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json() or {}
        except Exception:
            logger.debug("xKiro model listing failed; using the curated catalog.", exc_info=True)
            return list(XKIRO_MODELS)
        models = [
            entry["id"]
            for entry in (data.get("data") or [])
            if isinstance(entry, dict) and entry.get("id")
        ]
        return models or list(XKIRO_MODELS)


xkiro = XKiroProfile(
    name="xkiro",
    display_name="xKiro",
    description="xKiro (hosted multi-vendor API: GPT, Claude, Gemini, Grok, Kimi, DeepSeek, GLM)",
    aliases=("x-kiro", "xkiro-api"),
    api_mode="chat_completions",
    auth_type="api_key",
    env_vars=("XKIRO_API_KEY",),
    base_url=DEFAULT_BASE_URL,
    fallback_models=XKIRO_MODELS,
    default_aux_model="openai/gpt-5.6-luna",
    supports_vision=True,
)

register_provider(xkiro)

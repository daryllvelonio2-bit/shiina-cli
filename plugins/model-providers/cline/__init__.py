"""Cline provider profile — native access to Cline models & free tier."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, List, Optional

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

CLINE_FALLBACK_MODELS = (
    "stealth/pixel-canary",
    "stealth/space-bunny-alpha",
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
    "qwen/qwen3.8-27b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "cohere/north-mini-code:free",
)


class ClineProfile(ProviderProfile):
    """Cline provider profile."""

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 15.0
    ) -> list[str] | None:
        token = api_key
        if not token:
            try:
                from shiina_cli.auth import resolve_api_key_provider_credentials
                token = resolve_api_key_provider_credentials("cline").get("api_key")
            except Exception:
                pass
        if not token:
            return list(CLINE_FALLBACK_MODELS)
        endpoint = (base_url or "https://api.cline.bot/api/v1").rstrip("/") + "/models"
        req = urllib.request.Request(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "User-Agent": "cline/3.50.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
                if models:
                    # Prepend featured/stealth models that aren't listed in public catalog
                    for priority in ("stealth/pixel-canary", "stealth/space-bunny-alpha"):
                        if priority not in models:
                            models.insert(0, priority)
                    return models
        except Exception as exc:
            logger.debug("Failed fetching cline models: %s", exc)
        return list(CLINE_FALLBACK_MODELS)


cline = ClineProfile(
    name="cline",
    aliases=("cline-ai", "cline-bot", "cline-cli"),
    env_vars=("CLINE_API_KEY", "CLINE_TOKEN"),
    display_name="Cline",
    description="Cline AI native inference & free models (Pixel Canary, Space Bunny, etc.)",
    signup_url="https://cline.bot",
    base_url="https://api.cline.bot/api/v1",
    default_headers={"User-Agent": "cline/3.50.0"},
    fallback_models=CLINE_FALLBACK_MODELS,
)

register_provider(cline)

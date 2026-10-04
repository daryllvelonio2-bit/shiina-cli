"""Mistral AI provider profile.

Direct API provider for Mistral models (mistral-large, mistral-small, codestral, etc.).
"""

from __future__ import annotations

from providers import register_provider
from providers.base import ProviderProfile

MISTRAL_MODELS = (
    "mistral-large-latest",
    "mistral-small-latest",
    "codestral-latest",
    "pixtral-large-latest",
    "mistral-saba-latest",
)

mistral = ProviderProfile(
    name="mistral",
    aliases=("mistralai", "mistral-ai"),
    api_mode="chat_completions",
    env_vars=("MISTRAL_API_KEY",),
    base_url="https://api.mistral.ai/v1",
    auth_type="api_key",
    fallback_models=MISTRAL_MODELS,
    default_aux_model="mistral-small-latest",
    supports_vision=True,
)

register_provider(mistral)

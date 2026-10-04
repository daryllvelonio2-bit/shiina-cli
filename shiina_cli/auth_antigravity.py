"""Google Antigravity OAuth credentials — native provider wiring.

The credential is the user's signed-in Google / Antigravity session: a short-lived Google OAuth
access token plus a refresh token. Shiina stores it natively under
``credential_pool.antigravity`` in ``auth.json`` — the same store ``openai-codex``, ``nous`` and
``qwen-oauth`` use — and inference runs straight against the Google Cloud Code Assist endpoint
through :mod:`agent.antigravity_client`. No ``agy`` subprocess is ever spawned.

Discovery order (first hit wins), mirroring how the Antigravity CLI itself finds a session:

1. ``ANTIGRAVITY_ACCESS_TOKEN`` / ``AGY_ACCESS_TOKEN`` (+ ``*_REFRESH_TOKEN``) from the environment.
2. The OS keyring entry the Antigravity CLI writes (service ``gemini``, account ``antigravity``;
   Linux SecretService / macOS Keychain / Windows Credential Manager).
3. ``~/.shiina/auth.json`` ``credential_pool.antigravity`` (the native store this module owns).

A refreshed access token is written back to the native pool, so the pool entry stays the
authoritative record even when the keyring supplied the original session.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from shiina_cli.auth_constants import (
    DEFAULT_ANTIGRAVITY_BASE_URL, _antigravity_err,
)

logger = logging.getLogger("shiina_cli.auth")

_RERUN = "Sign in with the Antigravity CLI (`agy`), then re-run `shiina model`."


def _token_manager() -> Any:
    """The process-wide Antigravity token manager (lazy: keeps `agent` off this module's import)."""
    from agent.antigravity_client import get_default_token_manager

    return get_default_token_manager()


def resolve_antigravity_runtime_credentials(
    *, force_refresh: bool = False, refresh_if_expiring: bool = True,
) -> Dict[str, Any]:
    """Runtime credentials for the ``antigravity`` provider.

    Returns the shape ``_OAuthRuntimeSpec`` consumes: ``provider`` / ``base_url`` / ``api_key``
    (the bearer access token) / ``source`` / ``expires_at``. Raises :class:`AuthError` with
    ``relogin_required`` when no Antigravity session is discoverable, so the CLI shows the
    sign-in hint instead of a bare 401.
    """
    manager = _token_manager()
    try:
        token = manager.get_access_token(force_refresh=force_refresh)
    except Exception as exc:
        # A missing session, a rejected refresh token, and a transport failure all mean the same
        # thing to the caller: not usable this turn, re-authenticate.
        raise _antigravity_err(
            f"Google Antigravity credentials unavailable: {exc}. {_RERUN}",
            "antigravity_auth_failed", relogin=True) from exc
    if not str(token or "").strip():
        raise _antigravity_err(
            f"No Google Antigravity access token found. {_RERUN}",
            "antigravity_auth_missing", relogin=True)
    return {
        "provider": "antigravity",
        "base_url": DEFAULT_ANTIGRAVITY_BASE_URL,
        "api_key": token,
        "source": manager.source_label(),
        "expires_at": manager.expiry_iso(),
    }


def get_antigravity_auth_status() -> Dict[str, Any]:
    """Structural auth status for ``shiina auth status antigravity`` and the model picker.

    Refresh-validated like the other OAuth status builders: a revoked refresh token must read as
    logged out, not as a stale "signed in" that breaks the first real request.
    """
    from shiina_cli.auth import read_credential_pool

    pool_entries = len(read_credential_pool("antigravity"))
    try:
        creds = resolve_antigravity_runtime_credentials(refresh_if_expiring=True)
    except Exception as exc:
        return {"logged_in": False, "provider": "antigravity", "pool_entries": pool_entries,
                "error": str(exc)}
    return {
        "logged_in": True,
        "provider": "antigravity",
        "source": creds.get("source"),
        "api_key": creds.get("api_key"),
        "expires_at": creds.get("expires_at"),
        "base_url": creds.get("base_url"),
        "pool_entries": pool_entries,
    }


def refresh_antigravity_credentials() -> Dict[str, Any]:
    """Forced refresh, for ``shiina auth refresh antigravity``."""
    return resolve_antigravity_runtime_credentials(force_refresh=True, refresh_if_expiring=False)

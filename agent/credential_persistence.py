"""Credential-pool disk-boundary sanitization: strip raw secrets from *borrowed*
pool entries before they reach ``auth.json``. Deliberately free of
``shiina_cli.auth`` imports so the pool model and the auth-store write boundary
share one policy without import cycles."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Mapping


# Sources Shiina owns and may persist with secrets. Any other non-empty,
# non-manual source is borrowed/reference-only so new external providers fail
# closed at the disk boundary.
_PERSISTABLE_PROVIDER_SOURCES = frozenset({
    ("anthropic", "shiina_pkce"),
    ("anthropic", "oauth"),
    ("anthropic", "credentials"),
    ("minimax-oauth", "oauth"),
    ("minimax-oauth", "minimax_oauth"),
    ("minimax-oauth", "credentials"),
    ("nous", "device_code"),
    ("nous", "oauth"),
    ("nous", "dashboard_device_code"),
    ("nous", "anonymous"),
    ("nous", "credentials"),
    ("openai-codex", "device_code"),
    ("openai-codex", "oauth"),
    ("openai-codex", "chatgpt"),
    ("openai-codex", "credentials"),
    ("xai-oauth", "device_code"),
    ("xai-oauth", "oauth"),
    ("xai-oauth", "credentials"),
    ("qwen-oauth", "oauth"),
    ("qwen-oauth", "qwen_cli"),
    ("qwen-oauth", "credentials"),
    ("antigravity", "oauth"),
    ("antigravity", "google_oauth"),
    ("antigravity", "agy"),
    ("antigravity", "antigravity"),
    ("antigravity", "credentials"),
    ("agy", "oauth"),
    ("agy", "google_oauth"),
    ("agy", "agy"),
    ("agy", "credentials"),
    ("freebuff", "credentials"),
    ("freebuff", "freebuff"),
    ("freebuff", "token"),
    ("codebuff", "credentials"),
    ("codebuff", "codebuff"),
    ("freebuff-cli", "credentials"),
    ("kiro", "sqlite"),
    ("kiro", "credentials"),
    ("kiro", "kiro"),
    ("kiro", "xkiro"),
    ("kiro-cli", "credentials"),
    ("kiro-cli", "sqlite"),
    ("kiro-ai", "credentials"),
    ("xkiro", "credentials"),
    ("opencode", "opencode"),
    ("opencode", "credentials"),
    ("opencode", "oauth"),
    ("opencode-cli", "opencode"),
    ("opencode-cli", "opencode-cli"),
    ("opencode-cli", "credentials"),
    ("opencode-cli", "oauth"),
    ("opencode-local", "credentials"),
    ("opencode-local", "opencode"),
    ("opencode-agent", "credentials"),
    ("opencode-bin", "credentials"),
    ("cline", "cline"),
    ("cline", "credentials"),
    ("cline", "local_session"),
    ("cline-ai", "credentials"),
    ("cline-bot", "credentials"),
    ("cline-cli", "credentials"),
    ("copilot", "copilot_token"),
    ("copilot", "github_token"),
    ("copilot", "oauth"),
    ("copilot", "credentials"),
    ("copilot-acp", "copilot_token"),
    ("copilot-acp", "cli_config"),
    ("copilot-acp", "credentials"),
    ("gemini", "oauth"),
    ("gemini", "credentials"),
    ("openrouter", "openrouter_pkce"),
    ("openrouter", "pkce"),
    ("openrouter", "credentials"),
})

# Metadata keys that look secret-ish by suffix but are safe to persist.
_SAFE_SECRETISH_METADATA_KEYS = frozenset({
    "secret_fingerprint", "secret_source", "token_type", "scope", "client_id",
    "agent_key_id", "agent_key_expires_at", "agent_key_expires_in",
    "agent_key_reused", "agent_key_obtained_at", "expires_at", "expires_at_ms",
    "expires_in", "last_refresh", "last_status", "last_status_at",
    "last_error_code", "last_error_reason", "last_error_message",
    "last_error_reset_at",
})

_SECRET_VALUE_KEYS = frozenset({
    "access_token", "refresh_token", "agent_key", "api_key", "apikey",
    "api_token", "auth_token", "authorization", "bearer_token", "client_secret",
    "credential", "credentials", "id_token", "oauth_token", "private_key",
    "secret_key", "session_token", "password", "secret", "token", "tokens",
})

_SECRET_VALUE_SUFFIXES = (
    "_api_key", "_api_token", "_access_token", "_auth_token", "_refresh_token",
    "_bearer_token", "_client_secret", "_id_token", "_oauth_token",
    "_private_key", "_session_token", "_secret_key", "_password", "_secret",
    "_token", "_key",
)

_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _normalize_key(key: Any) -> str:
    raw = _CAMEL_CASE_BOUNDARY.sub("_", str(key or "").strip())
    return raw.lower().replace("-", "_").replace(".", "_")


_OWNED_AUTH_PROVIDERS = frozenset({
    "anthropic", "minimax-oauth", "nous", "openai-codex", "xai-oauth", "qwen-oauth",
    "antigravity", "agy", "freebuff", "codebuff", "freebuff-cli",
    "kiro", "kiro-cli", "kiro-ai", "xkiro",
    "opencode", "opencode-cli", "opencode-local", "opencode-agent", "opencode-bin",
    "cline", "cline-ai", "cline-bot", "cline-cli",
    "copilot", "copilot-acp", "gemini",
})

_OWNED_AUTH_SOURCES = frozenset({
    "oauth", "device_code", "credentials", "token", "tokens", "sqlite",
    "shiina_pkce", "minimax_oauth", "dashboard_device_code", "anonymous",
    "chatgpt", "qwen_cli", "google_oauth", "agy", "antigravity", "freebuff",
    "kiro", "xkiro", "opencode", "opencode-cli", "cline", "local_session",
    "copilot_token", "github_token", "cli_config", "pkce",
})


def is_borrowed_credential_source(source: Any, provider_id: Any = None) -> bool:
    """Return True when ``source`` points at a borrowed/reference-only secret."""
    normalized_source = str(source or "").strip().lower()
    if not normalized_source or normalized_source == "manual" or normalized_source.startswith("manual:"):
        return False
    if normalized_source.startswith("systemd:") or normalized_source.startswith("env:") or normalized_source == "claude_code":
        return True
    normalized_provider = str(provider_id or "").strip().lower()
    if (normalized_provider, normalized_source) in _PERSISTABLE_PROVIDER_SOURCES:
        return False
    if normalized_provider in _OWNED_AUTH_PROVIDERS and normalized_source in _OWNED_AUTH_SOURCES:
        return False
    return True


def _is_secret_payload_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    if not normalized or normalized in _SAFE_SECRETISH_METADATA_KEYS:
        return False
    return normalized in _SECRET_VALUE_KEYS or normalized.endswith(_SECRET_VALUE_SUFFIXES)


def fingerprint_secret_value(value: Any) -> str | None:
    """Non-reversible ``sha256:<16 hex>`` fingerprint of one secret value.

    Callers comparing a live secret against the ``secret_fingerprint`` left on
    a sanitized (borrowed) pool row need exactly the digest this module writes.
    """
    text = "" if value is None else str(value)
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"sha256:{digest[:16]}"


def _credential_secret_fingerprint(payload: Mapping[str, Any]) -> str | None:
    preferred = ("agent_key", "access_token", "refresh_token", "api_key", "token", "secret")
    candidates = [payload.get(k) for k in preferred]
    candidates += [v for k, v in payload.items() if _is_secret_payload_key(k)]
    for value in candidates:
        fingerprint = fingerprint_secret_value(value)
        if fingerprint:
            return fingerprint
    existing = payload.get("secret_fingerprint")
    if isinstance(existing, str) and existing.startswith("sha256:"):
        return existing
    return None


def sanitize_borrowed_credential_payload(
    payload: Mapping[str, Any],
    provider_id: Any = None,
) -> Dict[str, Any]:
    """Return a disk-safe credential-pool payload.

    Owned sources pass through unchanged.  Borrowed sources keep labels,
    source refs, status/cooldown metadata, counters and a fingerprint, but
    every raw secret value field is removed.
    """
    result = dict(payload)
    if not is_borrowed_credential_source(result.get("source"), provider_id):
        return result
    fingerprint = _credential_secret_fingerprint(result)
    sanitized = {k: v for k, v in result.items() if not _is_secret_payload_key(k)}
    if fingerprint:
        sanitized["secret_fingerprint"] = fingerprint
    return sanitized

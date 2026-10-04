"""Direct Google Cloud Code Assist API client for Shiina CLI.

Authenticates directly against Google Cloud Code Assist endpoints using the user's
Google One / Antigravity OAuth subscription tokens, bypassing the local `agy` CLI
subprocess completely for instant sub-second streaming and native tool calling.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

from agent.gemini_native_adapter import (
    _build_gemini_contents,
    _translate_tools_to_gemini,
    _translate_tool_choice_to_gemini,
    _effective_gemini_max_output_tokens,
    _normalize_thinking_config,
    gemini_requires_tool_call_ids,
)

logger = logging.getLogger(__name__)

DEFAULT_PROJECT = "aicode-consumers"
CODE_ASSIST_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Cloud Code Assist is one host serving method-suffixed paths (``/v1internal:<method>``). The
# provider's base_url is the HOST, so the client composes the method path onto it — a profile or
# pool entry carrying the bare host must not silently POST to ``/``.
STREAM_PATH = "/v1internal:streamGenerateContent?alt=sse"
MODELS_PATH = "/v1internal:fetchAvailableModels"

AGY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
AGY_CLIENT_SECRET = "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"
DEFAULT_USER_AGENT = "antigravity/1.2.7"
DEFAULT_TIMEOUT_SECONDS = 300.0
# Provider-level base URL (the Cloud Code Assist host), stored on the native pool entry so the
# runtime resolves the same endpoint from the credential rather than a hardcoded literal.
DEFAULT_BASE_URL = CODE_ASSIST_ENDPOINT.split("/v1internal")[0]
# Keyring location the Antigravity CLI writes its own session to.
KEYRING_SERVICE = "gemini"
KEYRING_ACCOUNT = "antigravity"

AGY_MODEL_ALIASES = {
    "agy-opus": "claude-opus-4-6-thinking",
    "claude-opus": "claude-opus-4-6-thinking",
    "opus": "claude-opus-4-6-thinking",
    "agy-sonnet": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "sonnet": "claude-sonnet-4-6",
    "agy-pro": "gemini-pro-agent",
    "gemini-pro": "gemini-pro-agent",
    "pro": "gemini-pro-agent",
    "gemini-3.1-pro-high": "gemini-pro-agent",
    "agy-flash": "gemini-3.8-flash-tiered",
    "gemini-flash": "gemini-3.8-flash-tiered",
    "flash": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-high": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-low": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-tiered": "gemini-3.8-flash-tiered",
    "gemini-3.7-flash": "gemini-3.7-flash-tiered",
    "gemini-3.7-flash-high": "gemini-3.7-flash-tiered",
    "gemini-3.7-flash-medium": "gemini-3.7-flash-tiered",
    "gemini-3.7-flash-low": "gemini-3.7-flash-tiered",
    "gemini-3.7-flash-tiered": "gemini-3.7-flash-tiered",
    "gemini-3.6-flash-high": "gemini-3.8-flash-tiered",
    "gemini-3.6-flash-medium": "gemini-3.8-flash-tiered",
    "gemini-3.6-flash-low": "gemini-3.8-flash-tiered",
    "gemini-3.6-flash-tiered": "gemini-3.8-flash-tiered",
    "gemini-3-flash": "gemini-3.8-flash-tiered",
    "gemini-flash-lite": "gemini-3.5-flash-lite",
    "flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gpt-oss": "gpt-oss-120b-medium",
    "agy-gpt-oss": "gpt-oss-120b-medium",
}


def _code_assist_host(base_url: Any) -> str:
    """Normalize an accepted base_url to the Cloud Code Assist host root.

    Accepts the bare host, the host with a trailing slash, or a full ``/v1internal:...`` endpoint —
    the client then composes the method path itself, so every credential/configuration spelling
    reaches the same place.
    """
    raw = str(base_url or "").strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        return DEFAULT_BASE_URL
    marker = raw.find("/v1internal")
    if marker != -1:
        raw = raw[:marker]
    return raw.rstrip("/") or DEFAULT_BASE_URL


def _extract_model_ids(data: Any) -> list[str]:
    """Model ids out of a ``fetchAvailableModels`` payload (dict-of-models or list-of-objects)."""
    if not isinstance(data, dict):
        return []
    raw = data.get("models")
    ids: list[str] = []
    if isinstance(raw, dict):
        ids = [str(k) for k in raw]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                model_id = item.get("modelId") or item.get("id") or item.get("name")
                if model_id:
                    ids.append(str(model_id))
    return [model_id for model_id in ids if model_id]


def resolve_agy_model(raw_model: str) -> str:
    """Resolve user/Shiina model names and aliases to Code Assist model names."""
    cleaned = (raw_model or "").strip()
    if cleaned.startswith("antigravity/"):
        cleaned = cleaned[len("antigravity/"):]
    elif cleaned.startswith("agy/"):
        cleaned = cleaned[len("agy/"):]

    cleaned_lower = cleaned.lower()
    if cleaned_lower in AGY_MODEL_ALIASES:
        return AGY_MODEL_ALIASES[cleaned_lower]

    return cleaned if cleaned else "gemini-3.8-flash-tiered"


class GoogleOAuthTokenManager:
    """Manages Google OAuth tokens for Antigravity / Google One AI subscriptions."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        *,
        persist: bool = True,
    ) -> None:
        """``persist=False`` binds the manager to a CALLER-SUPPLIED credential.

        Needed for multi-account pools: persisting writes the single active
        ``credential_pool.antigravity`` entry, so a refresh of a non-active account must not
        be persisted over it. ``expiry=inf`` means "trust the supplied token until a 401 forces
        a refresh" — the caller has no expiry to hand over.
        """
        self._access_token = access_token or None
        self._refresh_token = refresh_token or None
        self._expiry: float = float("inf") if access_token else 0.0
        self._email: Optional[str] = None
        self._source: str = "unknown"
        self._lock = threading.Lock()
        self._persist = persist
        if not (access_token or refresh_token):
            self._load_initial_tokens()

    def _extract_account_metadata(self, raw: Any) -> None:
        """Extract authenticated user email from raw secret payload or id_token."""
        if not isinstance(raw, dict):
            return
        # 1. Direct email field
        if raw.get("email"):
            self._email = str(raw["email"]).strip()
            return
        # 2. Check inside token dict
        tok_dict = raw.get("token")
        if isinstance(tok_dict, dict) and tok_dict.get("email"):
            self._email = str(tok_dict["email"]).strip()
            return
        # 3. Decode JWT id_token (no network call needed)
        id_tok = raw.get("id_token") or (tok_dict.get("id_token") if isinstance(tok_dict, dict) else None)
        if id_tok and isinstance(id_tok, str) and "." in id_tok:
            try:
                import base64
                parts = id_tok.split(".")
                if len(parts) >= 2:
                    padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                    if claims.get("email"):
                        self._email = str(claims["email"]).strip()
                        return
            except Exception as e:
                logger.debug("Failed decoding id_token: %s", e)

    def get_authenticated_email(self) -> Optional[str]:
        """Return the authenticated user email if known, or query Google tokeninfo."""
        if self._email:
            return self._email
        # Fast query to Google tokeninfo if access token is available
        token = self._access_token
        if token:
            try:
                req = urllib.request.Request(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("email"):
                        self._email = str(data["email"]).strip()
                        return self._email
            except Exception as e:
                logger.debug("Failed querying tokeninfo for email: %s", e)
        return None

    # ── Discovery ────────────────────────────────────────────────────────────────────────────
    # Order mirrors the Antigravity CLI itself: an explicit env override, then the signed-in
    # session it wrote to the OS keyring, then Shiina's own native credential store.

    def _load_initial_tokens(self) -> None:
        # 1. Environment variables
        env_token = (
            os.getenv("ANTIGRAVITY_ACCESS_TOKEN")
            or os.getenv("AGY_ACCESS_TOKEN")
            or os.getenv("GEMINI_ACCESS_TOKEN")
            or os.getenv("GOOGLE_ACCESS_TOKEN")
        )
        if env_token:
            self._access_token = env_token
            self._refresh_token = (
                os.getenv("ANTIGRAVITY_REFRESH_TOKEN")
                or os.getenv("AGY_REFRESH_TOKEN")
                or os.getenv("GEMINI_REFRESH_TOKEN")
                or os.getenv("GOOGLE_REFRESH_TOKEN")
            )
            self._expiry = time.time() + 3600
            self._source = "env"
            return

        # 2. OS keyring (service: gemini, account: antigravity)
        token_info = self._read_keyring_token()
        if token_info and self._apply_token_info(token_info, "keyring"):
            return

        # 3. Native credential store: auth.json ``credential_pool.antigravity``
        token_info = self._read_native_pool_token()
        if token_info and self._apply_token_info(token_info, "credential_pool"):
            return

        # 4. Legacy ``providers.antigravity`` block (pre-native-store installs)
        token_info = self._read_legacy_auth_json_token()
        if token_info:
            self._apply_token_info(token_info, "auth.json")

    def _apply_token_info(self, token_info: Dict[str, Any], source: str) -> bool:
        """Adopt one decoded token blob. Returns True when an access or refresh token was found."""
        access = token_info.get("access_token")
        refresh = token_info.get("refresh_token")
        if not access and not refresh:
            return False
        if access:
            self._access_token = str(access)
        if refresh:
            self._refresh_token = str(refresh)
        expiry = token_info.get("expiry")
        if isinstance(expiry, (int, float)):
            self._expiry = float(expiry)
        elif isinstance(expiry, str) and expiry.strip():
            try:
                self._expiry = datetime.fromisoformat(expiry).timestamp()
            except Exception:
                self._expiry = time.time() + 1800
        else:
            self._expiry = time.time() + 1800
        self._source = source
        logger.debug("Loaded Antigravity OAuth tokens from %s.", source)
        return True

    def _read_keyring_token(self) -> Optional[Dict[str, Any]]:
        """The Antigravity session from the OS keyring, via the first backend that answers.

        Layered deliberately: ``secretstorage`` (Linux) and ``keyring`` are optional extras, and
        neither is guaranteed on a given install — the platform CLIs (``secret-tool`` on Linux,
        ``security`` on macOS) read the same item with no Python dependency at all. Every backend
        is best-effort; a missing binding must not cost us the signed-in session.
        """
        for backend in (
            self._keyring_via_secretstorage,
            self._keyring_via_keyring_module,
            self._keyring_via_security_cli,
            self._keyring_via_secret_tool,
        ):
            try:
                info = backend()
            except Exception as exc:
                logger.debug("Keyring backend %s unavailable: %s", backend.__name__, exc)
                continue
            if isinstance(info, dict) and info.get("access_token"):
                return info
        return None

    @staticmethod
    def _decode_keyring_secret(raw: Any) -> Optional[Dict[str, Any]]:
        """Unwrap the ``{"token": {...}}`` envelope the Antigravity CLI stores."""
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            blob = json.loads(raw)
        except Exception:
            return None
        info = blob.get("token") if isinstance(blob, dict) else None
        return info if isinstance(info, dict) else None

    def _keyring_via_secretstorage(self) -> Optional[Dict[str, Any]]:
        import secretstorage

        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        items = list(collection.search_items({"service": KEYRING_SERVICE}))
        if not items:
            items = [
                item for item in collection.get_all_items()
                if item.get_attributes().get("service") == KEYRING_SERVICE
            ]
        for item in items:
            account = item.get_attributes().get("username") or item.get_attributes().get("account")
            if account and account != KEYRING_ACCOUNT:
                continue
            info = self._decode_keyring_secret(item.get_secret())
            if info and info.get("access_token"):
                return info
        return None

    def _keyring_via_keyring_module(self) -> Optional[Dict[str, Any]]:
        import keyring

        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        if raw is None:
            get_credential = getattr(keyring, "get_credential", None)
            credential = get_credential(KEYRING_SERVICE, None) if callable(get_credential) else None
            raw = getattr(credential, "password", None)
        return self._decode_keyring_secret(raw)

    def _keyring_via_security_cli(self) -> Optional[Dict[str, Any]]:
        if sys.platform != "darwin":
            return None
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", KEYRING_SERVICE, "-a", KEYRING_ACCOUNT, "-w"],
            capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return None
        return self._decode_keyring_secret(proc.stdout.strip())

    def _keyring_via_secret_tool(self) -> Optional[Dict[str, Any]]:
        """``secret-tool search`` still prints a secret stored with a non-textual content type,
        which ``secret-tool lookup`` refuses — hence search + parse rather than lookup."""
        if not shutil.which("secret-tool"):
            return None
        proc = subprocess.run(
            ["secret-tool", "search", "--all", "service", KEYRING_SERVICE, "username", KEYRING_ACCOUNT],
            capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if line.startswith("secret = "):
                info = self._decode_keyring_secret(line[len("secret = "):].strip())
                if info and info.get("access_token"):
                    return info
        return None

    def _read_native_pool_token(self) -> Optional[Dict[str, Any]]:
        """The ``credential_pool.antigravity`` slice of Shiina's auth store."""
        try:
            from shiina_cli.auth import read_credential_pool

            for entry in read_credential_pool("antigravity"):
                if isinstance(entry, dict) and (entry.get("access_token") or entry.get("refresh_token")):
                    return entry
        except Exception as exc:
            logger.debug("Failed to read credential_pool.antigravity: %s", exc)
        return None

    def _read_legacy_auth_json_token(self) -> Optional[Dict[str, Any]]:
        try:
            auth_file = Path.home() / ".shiina" / "auth.json"
            if not auth_file.exists():
                return None
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = ((data.get("providers") or {}).get("antigravity")) or {}
            if isinstance(state, dict) and (state.get("access_token") or state.get("refresh_token")):
                return {"access_token": state.get("access_token"),
                        "refresh_token": state.get("refresh_token"),
                        "expiry": state.get("expires_at")}
        except Exception as exc:
            logger.debug("Failed to read legacy providers.antigravity from auth.json: %s", exc)
        return None

    def source_label(self) -> str:
        """Where the active session came from (``keyring`` / ``credential_pool`` / ``env``)."""
        return self._source

    def expiry_iso(self) -> Optional[str]:
        return datetime.fromtimestamp(self._expiry).isoformat() if self._expiry else None

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Get a valid bearer access token, refreshing automatically if expired."""
        with self._lock:
            now = time.time()
            if not force_refresh and self._access_token and (self._expiry - now > 300):
                return self._access_token

            if not self._refresh_token:
                if self._access_token and not force_refresh:
                    return self._access_token
                self._load_initial_tokens()
                if not self._refresh_token and not self._access_token:
                    raise RuntimeError(
                        "No Google Antigravity credentials found. "
                        "Please ensure you are logged into Antigravity on your machine, "
                        "or provide credentials in ~/.shiina/auth.json."
                    )

            if force_refresh or (self._expiry - now <= 300):
                self._refresh()

            if not self._access_token:
                raise RuntimeError("Failed to acquire valid Google Antigravity access token.")
            return self._access_token

    def _refresh(self) -> None:
        if not self._refresh_token:
            raise RuntimeError("Cannot refresh Google Antigravity token: no refresh_token available.")

        data = urllib.parse.urlencode({
            "client_id": AGY_CLIENT_ID,
            "client_secret": AGY_CLIENT_SECRET,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(GOOGLE_OAUTH_TOKEN_URL, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self._access_token = result["access_token"]
                expires_in = int(result.get("expires_in", 3600))
                self._expiry = time.time() + expires_in
                logger.info("Successfully refreshed Google Antigravity OAuth access token.")
                if self._persist:
                    self._persist_refreshed_token()
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Failed to refresh Google Antigravity token: HTTP {e.code} - {err_msg}") from e

    def _persist_refreshed_token(self) -> None:
        """Write the refreshed token back to Shiina's native ``credential_pool.antigravity``.

        The pool entry is the authoritative record: `shiina auth list` reads it, the runtime
        ladder prefers it over re-reading the keyring, and it survives an `agy` sign-out.
        """
        if not self._access_token:
            return
        try:
            from shiina_cli.auth import read_credential_pool, write_credential_pool

            entry = next((e for e in read_credential_pool("antigravity") if isinstance(e, dict)), None)
            entry = dict(entry) if entry else {
                "id": uuid.uuid4().hex[:6], "label": "antigravity", "priority": 0,
            }
            entry.update({
                "auth_type": "oauth",
                "source": "manual",
                "access_token": self._access_token,
                "base_url": entry.get("base_url") or DEFAULT_BASE_URL,
                "last_refresh": datetime.now().isoformat(),
            })
            if self._refresh_token:
                entry["refresh_token"] = self._refresh_token
            if self._expiry:
                entry["expires_at"] = datetime.fromtimestamp(self._expiry).isoformat()
            write_credential_pool("antigravity", [entry])
            logger.debug("Persisted refreshed Antigravity token to credential_pool.antigravity.")
        except Exception as e:
            logger.debug("Could not persist refreshed Antigravity token: %s", e)


_DEFAULT_TOKEN_MANAGER: Optional[GoogleOAuthTokenManager] = None


def get_default_token_manager() -> GoogleOAuthTokenManager:
    global _DEFAULT_TOKEN_MANAGER
    if _DEFAULT_TOKEN_MANAGER is None:
        _DEFAULT_TOKEN_MANAGER = GoogleOAuthTokenManager()
    return _DEFAULT_TOKEN_MANAGER


def fetch_antigravity_models(timeout: float = 15.0, token_manager: Optional[GoogleOAuthTokenManager] = None) -> list[str]:
    """Fetch live available models for Google Antigravity / Code Assist.

    Prioritizes querying the Code Assist MODELS_ENDPOINT directly via bearer token;
    falls back to executing `agy models` via subprocess; and finally falls back
    to curated default models.
    """
    # 1. Direct API query with token
    try:
        mgr = token_manager or get_default_token_manager()
        token = mgr.get_access_token()
        if token:
            req = urllib.request.Request(
                MODELS_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Content-Type": "application/json",
                },
                data=json.dumps({}).encode("utf-8"),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models_dict = data.get("models", {})
            if models_dict and isinstance(models_dict, dict):
                ordered: list[str] = []
                # First prioritize recommended models from agentModelSorts
                for sort_group in data.get("agentModelSorts", []):
                    for grp in sort_group.get("groups", []):
                        for mid in grp.get("modelIds", []):
                            if mid in models_dict and mid not in ordered:
                                ordered.append(mid)
                # Then append the rest of the available models, filtering out internal test endpoints
                for mid in models_dict:
                    if mid not in ordered and not mid.startswith(("chat_", "models/proactive", "MODEL_")):
                        ordered.append(mid)
                if ordered:
                    return ordered
    except Exception as exc:
        logger.debug("Failed fetching Antigravity models via Code Assist API: %s", exc)

    # 2. CLI subprocess fallback: `agy models` or `antigravity models`
    for bin_name in (
        os.getenv("AGY_BIN"),
        os.getenv("ANTIGRAVITY_BIN"),
        shutil.which("agy"),
        shutil.which("antigravity"),
        str(Path.home() / ".local/bin/agy"),
    ):
        if not bin_name or not os.path.exists(bin_name):
            continue
        try:
            proc = subprocess.run(
                [bin_name, "models"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout:
                clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", proc.stdout)
                lines = [line.strip() for line in clean.splitlines()]
                cli_models = []
                for line in lines:
                    if not line or "Fetching available models" in line or line.startswith(("-", "*", "=")):
                        continue
                    parts = line.split()
                    if parts:
                        model_id = parts[0]
                        if model_id and not model_id.startswith(("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")):
                            cli_models.append(model_id)
                if cli_models:
                    return cli_models
        except Exception as exc:
            logger.debug("Failed fetching models via %s CLI: %s", bin_name, exc)

    # 3. Static fallback
    return [
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
        "gemini-3.8-flash-tiered",
        "gemini-3.8-flash-high",
        "gemini-pro-agent",
        "gemini-3.1-pro-high",
        "gpt-oss-120b-medium",
        "gemini-3.5-flash-lite",
    ]


class AntigravityClient:
    """OpenAI-compatible client facade directly calling Google Cloud Code Assist API."""

    SHIINA_SKIP_TRANSPORT_WRAP = True
    SHIINA_SKIP_ASYNC_WRAP = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        token_manager: GoogleOAuthTokenManager | None = None,
        project: str | None = None,
        **_: Any,
    ) -> None:
        self.token_manager = token_manager or get_default_token_manager()
        self.api_key = api_key or "antigravity"
        self.api_base = _code_assist_host(base_url)
        self.base_url = self.api_base + STREAM_PATH
        self.project = project or DEFAULT_PROJECT
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat_completion))
        self._http_client = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True
        self._http_client.close()

    def list_models(self, *, timeout: float = 15.0) -> list[str]:
        """Model ids this account can use, via Cloud Code Assist ``fetchAvailableModels``.

        Returns an empty list on any failure so the caller falls back to the curated catalog —
        model listing must never be the thing that blocks a session.
        """
        try:
            token = self.token_manager.get_access_token()
        except Exception as exc:
            logger.debug("No Antigravity token for model listing: %s", exc)
            return []
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        try:
            resp = self._http_client.post(
                self.api_base + MODELS_PATH, headers=headers, json={"project": self.project}, timeout=timeout)
            resp.raise_for_status()
            data = resp.json() or {}
        except Exception as exc:
            logger.debug("fetchAvailableModels failed: %s", exc)
            return []
        return _extract_model_ids(data)

    def _build_request_payload(
        self,
        *,
        resolved_model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: Any = None,
        thinking_config: Any = None,
    ) -> dict[str, Any]:
        is_gemini3 = True
        contents, system_instruction = _build_gemini_contents(
            messages, include_tool_call_ids=is_gemini3, is_gemini3=is_gemini3
        )

        gemini_tools = _translate_tools_to_gemini(tools) if tools else None
        if gemini_tools and "claude" in resolved_model.lower():
            gemini_tools = json.loads(json.dumps(gemini_tools).replace('"anyOf":', '"oneOf":'))

        optional: list[Tuple[str, Any]] = [
            ("systemInstruction", system_instruction),
            ("tools", gemini_tools),
            ("toolConfig", _translate_tool_choice_to_gemini(tool_choice) if tool_choice else None),
        ]
        request_obj: dict[str, Any] = {
            "contents": contents,
            **{k: v for k, v in optional if v},
        }

        eff_max_tokens = _effective_gemini_max_output_tokens(max_tokens, thinking_config)
        if "claude" in resolved_model.lower():
            eff_max_tokens = min(eff_max_tokens, 8192)
        elif "gpt-oss" in resolved_model.lower():
            eff_max_tokens = min(eff_max_tokens, 32768)
        elif "tab_" in resolved_model.lower():
            eff_max_tokens = min(eff_max_tokens, 4096)

        generation: list[Tuple[str, Any]] = [
            ("temperature", temperature),
            ("maxOutputTokens", eff_max_tokens),
            ("topP", top_p),
            ("stopSequences", (stop if isinstance(stop, list) else [str(stop)]) if stop else None),
            ("thinkingConfig", _normalize_thinking_config(thinking_config)),
        ]
        gen_config = {k: v for k, v in generation if v is not None}
        if gen_config:
            request_obj["generationConfig"] = gen_config

        return {
            "project": self.project,
            "model": resolved_model,
            "request": request_obj,
        }

    def _create_chat_completion(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: Any = None,
        thinking_config: Any = None,
        **_: Any,
    ) -> Any:
        resolved_model = resolve_agy_model(model or "")
        payload = self._build_request_payload(
            resolved_model=resolved_model,
            messages=messages or [],
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            thinking_config=thinking_config,
        )

        timeout_seconds = (
            float(timeout)
            if isinstance(timeout, (int, float)) and timeout > 0
            else DEFAULT_TIMEOUT_SECONDS
        )

        if stream:
            return self._stream_realtime_chunks(payload, resolved_model, model or resolved_model, timeout_seconds)

        return self._execute_request(payload, resolved_model, model or resolved_model, timeout_seconds)

    def _stream_realtime_chunks(
        self, payload: dict[str, Any], resolved_model: str, requested_model: str, timeout_seconds: float
    ) -> Iterator[Any]:
        from agent.gemini_native_adapter import translate_stream_event

        tool_call_indices: dict[str, dict[str, Any]] = {}
        last_req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        for event in self._iter_events(payload, timeout_seconds):
            resp_data = event.get("response", {})
            chunks = translate_stream_event(resp_data, requested_model, tool_call_indices)
            for chunk in chunks:
                if hasattr(chunk, "id") and chunk.id:
                    last_req_id = chunk.id
                yield chunk

            if "usageMetadata" in resp_data:
                usage_meta = resp_data["usageMetadata"]
                count = lambda key: int(usage_meta.get(key) or 0)
                usage = SimpleNamespace(
                    prompt_tokens=count("promptTokenCount"),
                    completion_tokens=count("candidatesTokenCount"),
                    total_tokens=count("totalTokenCount"),
                    prompt_tokens_details=SimpleNamespace(cached_tokens=count("cachedContentTokenCount")),
                )
                yield SimpleNamespace(
                    id=last_req_id,
                    object="chat.completion.chunk",
                    created=int(time.time()),
                    model=requested_model,
                    choices=[],
                    usage=usage,
                )

    def _execute_request(
        self, payload: dict[str, Any], resolved_model: str, requested_model: str, timeout_seconds: float
    ) -> Any:
        text_parts: list[str] = []
        tool_calls: list[SimpleNamespace] = []
        finish_reason: Optional[str] = None
        usage_meta: dict[str, Any] = {}
        req_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        for event in self._iter_events(payload, timeout_seconds):
            resp_data = event.get("response", {})
            if "usageMetadata" in resp_data:
                usage_meta.update(resp_data["usageMetadata"])
            for cand in resp_data.get("candidates", []):
                if not finish_reason and cand.get("finishReason"):
                    fr = str(cand["finishReason"]).lower()
                    finish_reason = "stop" if fr == "stop" else fr
                for part in cand.get("content", {}).get("parts", []):
                    if "text" in part and part["text"]:
                        text_parts.append(part["text"])
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        call_id = fc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                        thought_sig = part.get("thoughtSignature")
                        tc = SimpleNamespace(
                            id=call_id,
                            type="function",
                            function=SimpleNamespace(
                                name=fc.get("name", ""),
                                arguments=json.dumps(fc.get("args") or {}),
                            ),
                            extra_content={"google": {"thought_signature": thought_sig}} if thought_sig else None,
                        )
                        tool_calls.append(tc)
                        finish_reason = "tool_calls"

        full_text = "".join(text_parts)
        message = SimpleNamespace(
            role="assistant",
            content=full_text if full_text else (None if tool_calls else ""),
            tool_calls=tool_calls if tool_calls else None,
            reasoning=None,
            reasoning_content=None,
        )
        usage = SimpleNamespace(
            prompt_tokens=int(usage_meta.get("promptTokenCount", len(full_text) // 4)),
            completion_tokens=int(usage_meta.get("candidatesTokenCount", len(full_text) // 4)),
            total_tokens=int(usage_meta.get("totalTokenCount", len(full_text) // 2)),
        )

        return SimpleNamespace(
            id=req_id,
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason or "stop")],
            usage=usage,
            model=requested_model,
        )

    def _iter_events(self, payload: dict[str, Any], timeout_seconds: float) -> Iterator[dict[str, Any]]:
        retried = False

        while True:
            token = self.token_manager.get_access_token(force_refresh=retried)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            }

            try:
                with self._http_client.stream(
                    "POST", self.base_url, json=payload, headers=headers, timeout=timeout_seconds
                ) as resp:
                    if resp.status_code == 401 and not retried:
                        logger.warning("Antigravity access token returned 401 Unauthorized; refreshing token and retrying...")
                        retried = True
                        continue

                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")
                        try:
                            err_json = json.loads(err_text)
                            err_message = err_json.get("error", {}).get("message", err_text)
                        except Exception:
                            err_message = err_text
                        raise RuntimeError(f"Google Cloud Code Assist API error (HTTP {resp.status_code}): {err_message}")

                    for line in resp.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        json_str = line[5:].strip()
                        if not json_str:
                            continue
                        try:
                            yield json.loads(json_str)
                        except json.JSONDecodeError:
                            continue
                    return

            except httpx.RequestError as exc:
                if not retried:
                    logger.warning("Antigravity request error: %s; retrying once...", exc)
                    retried = True
                    continue
                raise RuntimeError(f"Google Cloud Code Assist request failed: {exc}") from exc

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

AGY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
AGY_CLIENT_SECRET = "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"
DEFAULT_USER_AGENT = "antigravity/1.2.7"
DEFAULT_TIMEOUT_SECONDS = 300.0

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

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expiry: float = 0.0
        self._lock = threading.Lock()
        self._load_initial_tokens()

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
            return

        # 2. Linux SecretService (service: gemini, username: antigravity)
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            items = list(collection.search_items({"service": "gemini"}))
            if not items:
                items = [item for item in collection.get_all_items() if item.get_attributes().get("service") == "gemini"]
            for item in items:
                raw = json.loads(item.get_secret().decode("utf-8"))
                token_info = raw.get("token", {})
                self._access_token = token_info.get("access_token")
                self._refresh_token = token_info.get("refresh_token")
                expiry_str = token_info.get("expiry")
                if expiry_str:
                    try:
                        dt = datetime.fromisoformat(expiry_str)
                        self._expiry = dt.timestamp()
                    except Exception:
                        self._expiry = time.time() + 1800
                logger.debug("Loaded Antigravity OAuth tokens from SecretService.")
                return
        except Exception as exc:
            logger.debug("Failed to read from SecretService: %s", exc)

        # 3. macOS Keychain (service: gemini)
        if sys.platform == "darwin":
            try:
                proc = subprocess.run(
                    ["security", "find-generic-password", "-s", "gemini", "-w"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    raw = json.loads(proc.stdout.strip())
                    token_info = raw.get("token", raw) if isinstance(raw, dict) else {}
                    if token_info.get("access_token"):
                        self._access_token = token_info["access_token"]
                        self._refresh_token = token_info.get("refresh_token")
                        logger.debug("Loaded Antigravity OAuth tokens from macOS Keychain.")
                        return
            except Exception as exc:
                logger.debug("Failed to read from macOS Keychain: %s", exc)

        # 4. Generic keyring library fallback (cross-platform)
        try:
            import keyring
            for username in ("antigravity", "gemini", ""):
                sec = keyring.get_password("gemini", username)
                if sec:
                    raw = json.loads(sec)
                    token_info = raw.get("token", raw) if isinstance(raw, dict) else {}
                    if token_info.get("access_token"):
                        self._access_token = token_info["access_token"]
                        self._refresh_token = token_info.get("refresh_token")
                        logger.debug("Loaded Antigravity OAuth tokens from keyring.")
                        return
        except Exception as exc:
            logger.debug("Failed to read from keyring: %s", exc)

        # 5. ~/.shiina/auth.json
        try:
            auth_file = Path.home() / ".shiina" / "auth.json"
            if auth_file.exists():
                with open(auth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                providers = data.get("providers", {})
                agy_state = providers.get("antigravity", {})
                if agy_state.get("access_token"):
                    self._access_token = agy_state["access_token"]
                    self._refresh_token = agy_state.get("refresh_token")
                    self._expiry = float(agy_state.get("expires_at", 0))
                    logger.debug("Loaded Antigravity OAuth tokens from auth.json.")
                    return
        except Exception as exc:
            logger.debug("Failed to read from auth.json: %s", exc)

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
                self._save_to_auth_json()
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Failed to refresh Google Antigravity token: HTTP {e.code} - {err_msg}") from e

    def _save_to_auth_json(self) -> None:
        try:
            auth_file = Path.home() / ".shiina" / "auth.json"
            if auth_file.exists():
                with open(auth_file, "r", encoding="utf-8") as f:
                    store = json.load(f)
            else:
                store = {"version": 1, "providers": {}}

            store.setdefault("providers", {})["antigravity"] = {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._expiry,
                "token_type": "Bearer",
                "auth_type": "oauth_external",
            }
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=2)
        except Exception as e:
            logger.debug("Could not persist refreshed token to auth.json: %s", e)


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
        if not base_url or not str(base_url).startswith(("http://", "https://")):
            self.base_url = CODE_ASSIST_ENDPOINT
        else:
            self.base_url = base_url
        self.project = project or DEFAULT_PROJECT
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat_completion))
        self._http_client = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True
        self._http_client.close()

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

"""Direct native Qoder API client for Shiina CLI.

Authenticates directly against Qoder OpenAPI and Gateway endpoints using the user's
Personal Access Token (PAT). Performs token exchange, AES-CBC info encryption,
RSA PKCS1v15 key wrapping, MD5 COSY signature generation, and base64 body encoding
in-process for sub-second streaming, native thinking/reasoning, and structured tool calls.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0

QODER_OPENAPI_BASE = "https://openapi.qoder.sh"
QODER_GATEWAY_BASE = "https://api2.qoder.sh"
QODER_EXCHANGE_URL = f"{QODER_OPENAPI_BASE}/api/v1/jobToken/exchange"
QODER_USERINFO_URL = f"{QODER_OPENAPI_BASE}/api/v1/userinfo"
QODER_CHAT_URL = f"{QODER_GATEWAY_BASE}/algo/api/v2/service/pro/sse/agent_chat_generation?FetchKeys=llm_model_result&AgentId=agent_common&Encode=1"
QODER_MODELS_URL = f"{QODER_GATEWAY_BASE}/algo/api/v2/model/list?Encode=1"
QODER_QUEUE_STATUS_URL = f"{QODER_GATEWAY_BASE}/algo/api/v2/service/ask/queue/status"

QODER_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDA8iMH5c02LilrsERw9t6Pv5Nc
4k6Pz1EaDicBMpdpxKduSZu5OANqUq8er4GM95omAGIOPOh+Nx0spthYA2BqGz+l
6HRkPJ7S236FZz73In/KVuLnwI8JJ2CbuJap8kvheCCZpmAWpb/cPx/3Vr/J6I17
XcW+ML9FoCI6AOvOzwIDAQAB
-----END PUBLIC KEY-----"""

QODER_GATEWAY_COSY_VERSION = "1.1.38"
QODER_CLIENT_TYPE = "5"
QODER_DATA_POLICY = "disagree"
QODER_LOGIN_VERSION = "v2"
QODER_MACHINE_TYPE_MAGIC = "5"
QODER_MACHINE_OS = "x86_64_linux"

# Encoding table mapping standard base64 to Qoder custom charset
STD_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
CUSTOM_B64 = "_doRTgHZBKcGVjlvpC,@aFSx#DPuNJme&i*MzLOEn)sUrthbf%Y^w.(kIQyXqWA!"
ENC_TRANS = str.maketrans(STD_B64 + "=", CUSTOM_B64 + "$")
DEC_TRANS = str.maketrans(CUSTOM_B64 + "$", STD_B64 + "=")


def qoder_encode_body(body_bytes: bytes) -> bytes:
    """Encode request body using Qoder custom alphabet and 3-way partition swap."""
    std = base64.b64encode(body_bytes).decode("ascii")
    custom = std.translate(ENC_TRANS)
    n = len(custom)
    a = n // 3
    swapped = custom[n - a : n] + custom[a : n - a] + custom[0 : a]
    return swapped.encode("utf-8")


def qoder_decode_body(encoded_str: str) -> bytes:
    """Decode Qoder custom alphabet string back to original bytes."""
    n = len(encoded_str)
    a = n // 3
    unswapped = encoded_str[n - a : n] + encoded_str[a : n - a] + encoded_str[0 : a]
    std = unswapped.translate(DEC_TRANS)
    return base64.b64decode(std)


QODER_FALLBACK_MODELS = (
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

# Friendly aliases mapped to canonical Qoder upstream model IDs
QODER_MODEL_ALIASES = {
    "auto": "auto",
    "qwen": "qmodel_38max",
    "qwen-max": "qmodel_38max",
    "qwen3.8-max": "qmodel_38max",
    "qmodel_38max": "qmodel_38max",
    "flash": "qfmodel",
    "qwen-flash": "qfmodel",
    "qwen3.8-flash": "qfmodel",
    "qfmodel": "qfmodel",
    "qwen3.7": "qmodel_latest",
    "qwen3.7-max": "qmodel_latest",
    "qmodel_latest": "qmodel_latest",
    "plus": "qmodel",
    "qwen-plus": "qmodel",
    "qwen3.7-plus": "qmodel",
    "qmodel": "qmodel",
    "sonus": "smodel",
    "claude-sonnet": "smodel",
    "sonnet": "smodel",
    "smodel": "smodel",
    "cantus": "cmodel",
    "claude-opus": "cmodel",
    "opus": "cmodel",
    "cmodel": "cmodel",
    "deepseek": "dmodel",
    "deepseek-v4-pro": "dmodel",
    "dmodel": "dmodel",
    "deepseek-flash": "dfmodel",
    "dfmodel": "dfmodel",
    "kimi": "kmodel_latest",
    "kimi-k3": "kmodel_latest",
    "kmodel_latest": "kmodel_latest",
    "kimi-k2.8": "kmodel",
    "kmodel": "kmodel",
    "glm": "gmodel",
    "glm-5.3": "gmodel",
    "gmodel": "gmodel",
    "glm-flash": "gfmodel",
    "glm-5.3-flash": "gfmodel",
    "gfmodel": "gfmodel",
    "minimax": "mmodel",
    "minimax-m3": "mmodel",
    "mmodel": "mmodel",
    "ultimate": "ultimate",
    "performance": "performance",
    "efficient": "efficient",
}


def resolve_qoder_model(raw_model: str) -> str:
    """Normalize model string to standard Qoder upstream key."""
    m = (raw_model or "").strip()
    # Check exact alias first
    if m.lower() in QODER_MODEL_ALIASES:
        return QODER_MODEL_ALIASES[m.lower()]
    # Strip provider prefix if present (qoder/, qoder-, qoder:)
    for prefix in ("qoder/", "qoder-", "qoder:"):
        if m.lower().startswith(prefix):
            m = m[len(prefix) :]
            break
    key = m.lower()
    return QODER_MODEL_ALIASES.get(key, m)


def _get_machine_id() -> str:
    """Resolve or generate a persistent Qoder machine ID."""
    cache_path = Path.home() / ".shiina" / "cache" / "qoder_machine_id"
    if cache_path.exists():
        with contextlib.suppress(Exception):
            mid = cache_path.read_text(encoding="utf-8").strip()
            if mid:
                return mid
    new_id = str(uuid.uuid4())
    with contextlib.suppress(Exception):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(new_id, encoding="utf-8")
    return new_id


class QoderTokenManager:
    """Manages Personal Access Token (PAT) exchange, credential caching, and automatic token refresh."""

    def __init__(self, pat: str | None = None) -> None:
        self._pat = (pat or "").strip()
        self._job_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._user_name: Optional[str] = None
        self._user_email: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        self._cache_file = Path.home() / ".shiina" / "cache" / "qoder_credentials.json"
        self._load_cached_credentials()

    def _load_cached_credentials(self) -> None:
        """Load valid cached job token from disk if available."""
        if not self._cache_file.exists():
            return
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_pat = data.get("pat", "")
            if self._pat and cached_pat and self._pat != cached_pat:
                return  # PAT changed, need re-exchange
            self._job_token = data.get("job_token")
            self._refresh_token = data.get("refresh_token")
            self._user_id = data.get("user_id")
            self._user_name = data.get("user_name")
            self._user_email = data.get("user_email")
            self._expires_at = float(data.get("expires_at", 0.0))
        except Exception as exc:
            logger.debug("Failed to read Qoder credentials cache: %s", exc)

    def _save_cached_credentials(self) -> None:
        """Save active credentials to disk cache."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "pat": self._pat,
                "job_token": self._job_token,
                "refresh_token": self._refresh_token,
                "user_id": self._user_id,
                "user_name": self._user_name,
                "user_email": self._user_email,
                "expires_at": self._expires_at,
            }
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.debug("Failed to write Qoder credentials cache: %s", exc)

    def get_pat(self) -> str:
        if self._pat:
            return self._pat
        env_pat = (
            os.environ.get("QODER_PAT")
            or os.environ.get("QODER_API_KEY")
            or os.environ.get("QODER_PERSONAL_ACCESS_TOKEN")
            or ""
        ).strip()
        if env_pat:
            self._pat = env_pat
            return self._pat
        # Check ~/.shiina/.env or config
        from shiina_cli.config import get_env_value

        saved = get_env_value("QODER_PAT") or get_env_value("QODER_API_KEY")
        if saved:
            self._pat = saved.strip()
            return self._pat
        raise RuntimeError(
            "No Qoder Personal Access Token found. Please set QODER_PAT in ~/.shiina/.env or export QODER_PAT."
        )

    def get_credentials(self, force_refresh: bool = False) -> Tuple[str, str, str, str]:
        """Return (job_token, user_id, user_name, user_email), refreshing if necessary."""
        with self._lock:
            now = time.time()
            if (
                not force_refresh
                and self._job_token
                and self._user_id
                and (self._expires_at - now > 300)
            ):
                return self._job_token, self._user_id, self._user_name or "", self._user_email or ""

            pat = self.get_pat()
            headers = {"Content-Type": "application/json", "User-Agent": "qoder"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    QODER_EXCHANGE_URL,
                    json={"personal_token": pat},
                    headers=headers,
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Qoder PAT exchange failed with status {resp.status_code}: {resp.text}"
                    )
                token_data = resp.json()
                self._job_token = token_data.get("token")
                self._refresh_token = token_data.get("refresh_token")
                expires_in = token_data.get("expires_in", 86400000) / 1000.0
                self._expires_at = time.time() + expires_in

                # Fetch user info
                user_resp = client.get(
                    QODER_USERINFO_URL,
                    headers={"Authorization": f"Bearer {self._job_token}", "User-Agent": "qoder"},
                )
                if user_resp.status_code != 200:
                    raise RuntimeError(
                        f"Qoder userinfo fetch failed with status {user_resp.status_code}: {user_resp.text}"
                    )
                user_info = user_resp.json()
                data = user_info.get("data") if isinstance(user_info.get("data"), dict) else user_info
                self._user_id = data.get("id") or data.get("uid") or ""
                self._user_name = data.get("name") or data.get("nick_name") or data.get("username") or ""
                self._user_email = data.get("email") or ""

                self._save_cached_credentials()
                logger.info("Successfully refreshed Qoder jobToken for user %s (%s)", self._user_name, self._user_id)
                return self._job_token, self._user_id, self._user_name or "", self._user_email or ""


_DEFAULT_QODER_TOKEN_MANAGER: Optional[QoderTokenManager] = None


def get_default_qoder_token_manager() -> QoderTokenManager:
    global _DEFAULT_QODER_TOKEN_MANAGER
    if _DEFAULT_QODER_TOKEN_MANAGER is None:
        _DEFAULT_QODER_TOKEN_MANAGER = QoderTokenManager()
    return _DEFAULT_QODER_TOKEN_MANAGER


def build_cosy_headers(
    encoded_body: bytes,
    request_url: str,
    job_token: str,
    user_id: str,
    user_name: str,
    user_email: str,
    machine_id: str,
    model_key: str,
) -> dict[str, str]:
    """Construct cryptographic COSY protocol headers required by Qoder Gateway."""
    aes_key = str(uuid.uuid4()).replace("-", "")[:16].encode("utf-8")
    user_info = {
        "uid": user_id,
        "security_oauth_token": job_token,
        "name": user_name,
        "aid": "",
        "email": user_email,
    }
    raw_info = json.dumps(user_info).encode("utf-8")
    pad_len = 16 - (len(raw_info) % 16)
    padded = raw_info + bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key))
    encryptor = cipher.encryptor()
    enc_info = encryptor.update(padded) + encryptor.finalize()
    info_b64 = base64.b64encode(enc_info).decode("ascii")

    rsa_key = load_pem_public_key(QODER_RSA_PUBLIC_KEY.encode("utf-8"))
    cosy_key = base64.b64encode(rsa_key.encrypt(aes_key, padding.PKCS1v15())).decode("ascii")

    req_id = str(uuid.uuid4())
    cosy_payload = {
        "version": "v1",
        "requestId": req_id,
        "info": info_b64,
        "cosyVersion": QODER_GATEWAY_COSY_VERSION,
        "ideVersion": "",
    }
    payload_b64 = base64.b64encode(json.dumps(cosy_payload).encode("utf-8")).decode("ascii")
    ts = str(int(time.time()))

    from urllib.parse import urlparse

    parsed = urlparse(request_url)
    sig_path = parsed.path
    if sig_path.startswith("/algo"):
        sig_path = sig_path[len("/algo") :]

    data_to_sign = (
        f"{payload_b64}\n{cosy_key}\n{ts}\n".encode("utf-8")
        + encoded_body
        + f"\n{sig_path}".encode("utf-8")
    )
    sig = hashlib.md5(data_to_sign).hexdigest()
    body_hash = hashlib.md5(encoded_body).hexdigest()

    return {
        "Authorization": f"Bearer COSY.{payload_b64}.{sig}",
        "Cosy-Key": cosy_key,
        "Cosy-User": user_id,
        "Cosy-Date": ts,
        "Cosy-Version": QODER_GATEWAY_COSY_VERSION,
        "Cosy-Machineid": machine_id,
        "Cosy-Machinetoken": machine_id,
        "Cosy-Machinetype": QODER_MACHINE_TYPE_MAGIC,
        "Cosy-Machineos": QODER_MACHINE_OS,
        "Cosy-Clienttype": QODER_CLIENT_TYPE,
        "Cosy-Clientip": "127.0.0.1",
        "Cosy-Bodyhash": body_hash,
        "Cosy-Bodylength": str(len(encoded_body)),
        "Cosy-Sigpath": sig_path,
        "Cosy-Data-Policy": QODER_DATA_POLICY,
        "Cosy-Organization-Id": "",
        "Cosy-Organization-Tags": "",
        "Login-Version": QODER_LOGIN_VERSION,
        "X-Request-Id": str(uuid.uuid4()),
        "X-Model-Key": model_key,
        "X-Model-Source": "system",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "User-Agent": "qoder",
    }


def fetch_qoder_models(timeout: float = 15.0) -> list[str] | None:
    """Fetch live catalog from Qoder API gateway using COSY authentication."""
    try:
        mgr = get_default_qoder_token_manager()
        job_token, user_id, user_name, user_email = mgr.get_credentials()
        machine_id = _get_machine_id()
        headers = build_cosy_headers(
            encoded_body=b"",
            request_url=QODER_MODELS_URL,
            job_token=job_token,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            machine_id=machine_id,
            model_key="auto",
        )
        headers["Accept"] = "application/json"
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(QODER_MODELS_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    items = data.get("data", [])
                    if isinstance(items, list):
                        model_ids = [m["name"] for m in items if isinstance(m, dict) and "name" in m]
                        if model_ids:
                            return model_ids
    except Exception as exc:
        logger.debug("Failed to fetch live Qoder models: %s", exc)
    return list(QODER_FALLBACK_MODELS)


def parse_qoder_queue_info(inner: dict[str, Any]) -> tuple[bool, int, str]:
    """Check if response envelope indicates model is queued or rate limited.
    Returns (is_queued, wait_seconds, queue_type).
    """
    code_val = str(inner.get("code", "")).strip()
    msg = inner.get("message") or inner.get("msg") or ""

    is_queued = code_val in ("10605", "429")
    wait_sec = 30
    queue_type = "p3"

    nested: Any = None
    if isinstance(msg, str) and (msg.strip().startswith("{") or "10605" in msg or "isQueued" in msg):
        with contextlib.suppress(Exception):
            nested = json.loads(msg)
    elif isinstance(msg, dict):
        nested = msg

    if nested and isinstance(nested, dict):
        if str(nested.get("code", "")).strip() in ("10605", "429") or nested.get("isQueued") is True:
            is_queued = True
        sub_msg = nested.get("message")
        if isinstance(sub_msg, str) and ("isQueued" in sub_msg or "10605" in sub_msg):
            with contextlib.suppress(Exception):
                sub_nested = json.loads(sub_msg)
                if isinstance(sub_nested, dict):
                    nested = sub_nested
                    is_queued = True

        if nested.get("retryAfterSeconds") is not None:
            with contextlib.suppress(Exception):
                wait_sec = int(nested["retryAfterSeconds"])
        elif nested.get("waitTime") is not None:
            with contextlib.suppress(Exception):
                wait_sec = int(nested["waitTime"])
        if nested.get("queueType"):
            queue_type = str(nested["queueType"])

    if is_queued and wait_sec <= 0:
        wait_sec = 15

    return is_queued, wait_sec, queue_type


class QoderClient:
    """OpenAI-compatible client facade directly communicating with Qoder AI Gateway."""

    SHIINA_SKIP_TRANSPORT_WRAP = True
    SHIINA_SKIP_ASYNC_WRAP = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        token_manager: QoderTokenManager | None = None,
        status_callback: Optional[Callable[[str], None]] = None,
        agent: Optional[Any] = None,
        **_: Any,
    ) -> None:
        self.token_manager = token_manager or (
            QoderTokenManager(api_key) if api_key and api_key.startswith("pt-") else get_default_qoder_token_manager()
        )
        self.base_url = base_url or QODER_GATEWAY_BASE
        self.machine_id = _get_machine_id()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat_completion))
        self.is_closed = False
        self.status_callback = status_callback
        self.agent = agent

    def close(self) -> None:
        self.is_closed = True

    def _report_queue_status(self, text: str) -> None:
        """Report queue wait progress cleanly in-place via TUI spinner/thinking callback or single-line tty update."""
        # 1. Custom status_callback if supplied
        cb = getattr(self, "status_callback", None)
        if cb is not None and callable(cb):
            try:
                cb(text)
                return
            except Exception:
                pass

        # 2. Agent _emit_wait_notice if agent is explicitly bound
        bound_agent = getattr(self, "agent", None)
        if bound_agent and hasattr(bound_agent, "_emit_wait_notice") and callable(bound_agent._emit_wait_notice):
            try:
                bound_agent._emit_wait_notice(text)
                return
            except Exception:
                pass

        # 3. Discover active agent from cli module if running inside Shiina / Shiina CLI
        try:
            import cli
            active_agent = getattr(cli, "_active_agent_ref", None)
            if active_agent and hasattr(active_agent, "_emit_wait_notice") and callable(active_agent._emit_wait_notice):
                active_agent._emit_wait_notice(text)
                return
        except Exception:
            pass

        # 4. Fallback for non-agent runs:
        # Check if stdout or stderr is wrapped by prompt_toolkit's StdoutProxy
        is_stdout_proxy = False
        try:
            from prompt_toolkit.patch_stdout import StdoutProxy
            is_stdout_proxy = isinstance(sys.stdout, StdoutProxy) or isinstance(sys.stderr, StdoutProxy)
        except ImportError:
            is_stdout_proxy = (
                type(sys.stdout).__name__ == "StdoutProxy" or type(sys.stderr).__name__ == "StdoutProxy"
            )

        if is_stdout_proxy:
            # Under StdoutProxy, \r does not work and \033[K garbles into ?[K.
            # Do NOT write to stdout/stderr.
            return

        # 5. Direct terminal write only if stdout or stderr is an actual interactive TTY
        try:
            out = sys.stderr if sys.stderr.isatty() else (sys.stdout if sys.stdout.isatty() else None)
            if out is not None:
                if text:
                    out.write(f"\r{text:<80}")
                    out.flush()
                else:
                    out.write(f"\r{' ' * 80}\r")
                    out.flush()
        except Exception:
            pass

    def _format_messages_for_qoder(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format OpenAI-compatible messages for Qoder's chat service."""
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "user")).lower()
            content = msg.get("content")
            if isinstance(content, list):
                # Flatten text parts
                text_parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        text_parts.append(p.get("text", ""))
                    elif isinstance(p, str):
                        text_parts.append(p)
                content_str = "".join(text_parts)
            else:
                content_str = str(content) if content is not None else ""

            m_dict: dict[str, Any] = {
                "role": role,
                "content": content_str,
            }
            if msg.get("tool_calls"):
                m_dict["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                m_dict["tool_call_id"] = msg["tool_call_id"]
            if msg.get("name"):
                m_dict["name"] = msg["name"]
            formatted.append(m_dict)
        return formatted

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
        **_: Any,
    ) -> Any:
        raw_model = model or "qfmodel"
        resolved_model = resolve_qoder_model(raw_model)
        formatted_messages = self._format_messages_for_qoder(messages or [])
        timeout_seconds = (
            float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else DEFAULT_TIMEOUT_SECONDS
        )

        job_token, user_id, user_name, user_email = self.token_manager.get_credentials()

        record_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        last_user_text = ""
        for m in reversed(formatted_messages):
            if m.get("role") == "user":
                last_user_text = m.get("content", "")
                break

        parameters: dict[str, Any] = {}
        if temperature is not None:
            parameters["temperature"] = temperature
        if max_tokens is not None:
            parameters["max_tokens"] = max_tokens

        req_body: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "request_set_id": record_id,
            "chat_record_id": record_id,
            "session_id": session_id,
            "stream": True,
            "chat_task": "FREE_INPUT",
            "is_reply": True,
            "is_retry": False,
            "source": 1,
            "version": "3",
            "session_type": "qodercli",
            "agent_id": "agent_common",
            "task_id": "common",
            "code_language": "",
            "chat_prompt": "",
            "image_urls": None,
            "aliyun_user_type": "",
            "system": "",
            "messages": formatted_messages,
            "tools": tools or [],
            "parameters": parameters,
            "chat_context": {
                "chatPrompt": "",
                "imageUrls": None,
                "extra": {
                    "context": [],
                    "modelConfig": {"key": resolved_model, "is_reasoning": True},
                    "originalContent": last_user_text,
                },
                "features": [],
                "text": last_user_text,
            },
            "model_config": {"key": resolved_model, "source": "system"},
            "business": {
                "product": "cli",
                "version": "1.0.0",
                "type": "agent",
                "stage": "start",
                "id": str(uuid.uuid4()),
                "name": last_user_text[:30] if last_user_text else "Shiina Agent Chat",
                "begin_at": int(time.time() * 1000),
            },
        }

        body_bytes = json.dumps(req_body).encode("utf-8")
        encoded_body = qoder_encode_body(body_bytes)

        headers = build_cosy_headers(
            encoded_body=encoded_body,
            request_url=QODER_CHAT_URL,
            job_token=job_token,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            machine_id=self.machine_id,
            model_key=resolved_model,
        )

        if stream:
            return self._stream_response(
                req_body=req_body,
                raw_model=raw_model,
                resolved_model=resolved_model,
                timeout_seconds=timeout_seconds,
                job_token=job_token,
                user_id=user_id,
                user_name=user_name,
                user_email=user_email,
            )

        return self._execute_sync(
            req_body=req_body,
            raw_model=raw_model,
            resolved_model=resolved_model,
            timeout_seconds=timeout_seconds,
            job_token=job_token,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
        )

    def poll_queue_status(
        self,
        record_id: str,
        model_key: str,
        queue_type: str = "p3",
        job_token: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        user_email: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Poll Qoder queue status endpoint at /algo/api/v2/service/ask/queue/status."""
        try:
            if not job_token:
                job_token, user_id, user_name, user_email = self.token_manager.get_credentials()
            url = f"{self.base_url}/algo/api/v2/service/ask/queue/status?requestSetId={record_id}&modelKey={model_key}&queueType={queue_type}"
            headers = build_cosy_headers(
                encoded_body=b"",
                request_url=url,
                job_token=job_token,
                user_id=user_id or "",
                user_name=user_name or "",
                user_email=user_email or "",
                machine_id=self.machine_id,
                model_key=model_key,
            )
            headers["Accept"] = "application/json"
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        return data
        except Exception as exc:
            logger.debug("Qoder queue status poll failed: %s", exc)
        return {}

    def _stream_response(
        self,
        req_body: dict[str, Any] | bytes,
        headers_or_raw_model: Any = None,
        raw_model: str = "",
        resolved_model: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        job_token: str = "",
        user_id: str = "",
        user_name: str = "",
        user_email: str = "",
    ) -> Iterator[Any]:
        # Handle raw byte payload for backward-compatibility
        if isinstance(req_body, bytes):
            encoded_body = req_body
            headers = headers_or_raw_model if isinstance(headers_or_raw_model, dict) else {}
            chat_url = f"{self.base_url}/algo/api/v2/service/pro/sse/agent_chat_generation?FetchKeys=llm_model_result&AgentId=agent_common&Encode=1"
            client = httpx.Client(timeout=timeout_seconds)
            try:
                with client.stream("POST", chat_url, headers=headers, content=encoded_body) as resp:
                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")
                        raise RuntimeError(f"Qoder Gateway request failed (HTTP {resp.status_code}): {err_text}")
                    buffer = ""
                    last_chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                    for raw in resp.iter_bytes():
                        buffer += raw.decode("utf-8", errors="replace")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                return
                            try:
                                env = json.loads(data_str)
                            except Exception:
                                continue
                            body_field = env.get("body")
                            if body_field == "[DONE]":
                                return
                            inner = None
                            if isinstance(body_field, str):
                                with contextlib.suppress(Exception):
                                    inner = json.loads(body_field)
                            elif isinstance(body_field, dict):
                                inner = body_field
                            if not inner or not isinstance(inner, dict):
                                continue
                            if "code" in inner and str(inner.get("code")) not in ("200", "0"):
                                err_msg = inner.get("message") or inner.get("msg") or f"Error code {inner.get('code')}"
                                raise RuntimeError(f"Qoder API error: {err_msg}")
                            chunk_id = inner.get("id") or last_chunk_id
                            last_chunk_id = chunk_id
                            choices_raw = inner.get("choices") or []
                            if not choices_raw and "usage" in inner:
                                u = inner["usage"]
                                yield SimpleNamespace(
                                    id=chunk_id,
                                    object="chat.completion.chunk",
                                    created=int(time.time()),
                                    model=raw_model,
                                    choices=[],
                                    usage=SimpleNamespace(
                                        prompt_tokens=int(u.get("prompt_tokens") or 0),
                                        completion_tokens=int(u.get("completion_tokens") or 0),
                                        total_tokens=int(u.get("total_tokens") or 0),
                                    ),
                                )
                                return
                            converted = []
                            for c in choices_raw:
                                d = c.get("delta") or {}
                                converted.append(SimpleNamespace(index=c.get("index", 0), delta=SimpleNamespace(
                                    role=d.get("role"), content=d.get("content"), reasoning_content=d.get("reasoning_content")
                                ), finish_reason=c.get("finish_reason")))
                            yield SimpleNamespace(id=chunk_id, object="chat.completion.chunk", created=int(time.time()), model=raw_model, choices=converted)
            finally:
                client.close()
            return

        # Normal dictionary request body with full queue wait & transparent retry loop
        effective_raw_model = raw_model or (headers_or_raw_model if isinstance(headers_or_raw_model, str) else "qfmodel")
        effective_resolved_model = resolved_model or resolve_qoder_model(effective_raw_model)
        chat_url = f"{self.base_url}/algo/api/v2/service/pro/sse/agent_chat_generation?FetchKeys=llm_model_result&AgentId=agent_common&Encode=1"
        record_id = req_body.get("request_set_id") or str(uuid.uuid4())
        max_queue_wait_seconds = 300.0
        queue_start_time = time.time()
        attempt = 0
        last_chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        if not job_token:
            job_token, user_id, user_name, user_email = self.token_manager.get_credentials()

        while True:
            attempt += 1
            current_body = dict(req_body)
            current_body["request_id"] = str(uuid.uuid4())
            current_body["is_retry"] = (attempt > 1)

            body_bytes = json.dumps(current_body).encode("utf-8")
            encoded_body = qoder_encode_body(body_bytes)

            headers = build_cosy_headers(
                encoded_body=encoded_body,
                request_url=chat_url,
                job_token=job_token,
                user_id=user_id or "",
                user_name=user_name or "",
                user_email=user_email or "",
                machine_id=self.machine_id,
                model_key=effective_resolved_model,
            )

            client = httpx.Client(timeout=timeout_seconds)
            is_queued = False
            wait_seconds = 30
            queue_type = "p3"
            received_tokens = False

            try:
                with client.stream("POST", chat_url, headers=headers, content=encoded_body) as resp:
                    if resp.status_code == 429:
                        is_queued = True
                        wait_seconds = 20
                    elif resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")
                        raise RuntimeError(f"Qoder Gateway request failed (HTTP {resp.status_code}): {err_text}")

                    if not is_queued:
                        for line in resp.iter_lines():
                            line = (line or "").strip()
                            if not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                return
                            try:
                                env = json.loads(data_str)
                            except Exception:
                                continue

                            body_field = env.get("body")
                            if body_field == "[DONE]":
                                return

                            inner = None
                            if isinstance(body_field, str):
                                with contextlib.suppress(Exception):
                                    inner = json.loads(body_field)
                            elif isinstance(body_field, dict):
                                inner = body_field

                            if not inner or not isinstance(inner, dict):
                                continue

                            # Check for queue / rate-limit envelope before failing
                            q_flag, q_wait, q_t = parse_qoder_queue_info(inner)
                            if q_flag and not received_tokens:
                                is_queued = True
                                wait_seconds = q_wait
                                queue_type = q_t
                                break

                            # Check for other API error envelopes
                            if "code" in inner and str(inner.get("code")) not in ("200", "0"):
                                err_msg = inner.get("message") or inner.get("msg") or f"Error code {inner.get('code')}"
                                raise RuntimeError(f"Qoder API error: {err_msg}")

                            # Extract chunk data
                            chunk_id = inner.get("id") or last_chunk_id
                            last_chunk_id = chunk_id
                            choices_raw = inner.get("choices") or []

                            if not choices_raw and "usage" in inner:
                                u = inner["usage"]
                                usage = SimpleNamespace(
                                    prompt_tokens=int(u.get("prompt_tokens") or 0),
                                    completion_tokens=int(u.get("completion_tokens") or 0),
                                    total_tokens=int(u.get("total_tokens") or 0),
                                    prompt_tokens_details=SimpleNamespace(
                                        cached_tokens=int(u.get("prompt_tokens_details", {}).get("cached_tokens") or 0)
                                    ),
                                )
                                yield SimpleNamespace(
                                    id=chunk_id,
                                    object="chat.completion.chunk",
                                    created=int(time.time()),
                                    model=effective_raw_model,
                                    choices=[],
                                    usage=usage,
                                )
                                return

                            converted_choices = []
                            for c in choices_raw:
                                delta_raw = c.get("delta") or {}
                                tool_calls_converted = None
                                if "tool_calls" in delta_raw:
                                    tool_calls_converted = []
                                    for tc in delta_raw["tool_calls"]:
                                        func_data = tc.get("function") or {}
                                        tool_calls_converted.append(
                                            SimpleNamespace(
                                                index=tc.get("index", 0),
                                                id=tc.get("id") or None,
                                                type=tc.get("type", "function"),
                                                function=SimpleNamespace(
                                                    name=func_data.get("name") or None,
                                                    arguments=func_data.get("arguments") or None,
                                                ),
                                            )
                                        )

                                content_str = delta_raw.get("content") or None
                                reasoning_str = delta_raw.get("reasoning_content") or None
                                if content_str or reasoning_str or tool_calls_converted:
                                    if not received_tokens:
                                        self._report_queue_status("")
                                    received_tokens = True

                                delta = SimpleNamespace(
                                    role=delta_raw.get("role"),
                                    content=content_str,
                                    reasoning_content=reasoning_str,
                                    reasoning=reasoning_str,
                                    tool_calls=tool_calls_converted,
                                )
                                converted_choices.append(
                                    SimpleNamespace(
                                        index=c.get("index", 0),
                                        delta=delta,
                                        finish_reason=c.get("finish_reason"),
                                    )
                                )

                            yield SimpleNamespace(
                                id=chunk_id,
                                object="chat.completion.chunk",
                                created=int(time.time()),
                                model=effective_raw_model,
                                choices=converted_choices,
                            )

                            # If finish_reason was emitted and usage was already in the same inner packet, finish immediately
                            if any(c.get("finish_reason") in ("stop", "tool_calls", "length") for c in choices_raw):
                                if "usage" in inner:
                                    u = inner["usage"]
                                    usage = SimpleNamespace(
                                        prompt_tokens=int(u.get("prompt_tokens") or 0),
                                        completion_tokens=int(u.get("completion_tokens") or 0),
                                        total_tokens=int(u.get("total_tokens") or 0),
                                        prompt_tokens_details=SimpleNamespace(
                                            cached_tokens=int(u.get("prompt_tokens_details", {}).get("cached_tokens") or 0)
                                        ),
                                    )
                                    yield SimpleNamespace(
                                        id=chunk_id,
                                        object="chat.completion.chunk",
                                        created=int(time.time()),
                                        model=effective_raw_model,
                                        choices=[],
                                        usage=usage,
                                    )
                                    return
            finally:
                client.close()

            if not is_queued:
                self._report_queue_status("")
                return

            elapsed = time.time() - queue_start_time
            if elapsed >= max_queue_wait_seconds:
                self._report_queue_status("")
                raise RuntimeError(
                    f"Qoder API error: model queue wait exceeded limit ({int(elapsed)}s). Please try again later."
                )

            # Interactive UI progress matching Qoder CLI
            display_elapsed = int(elapsed)
            msg_status = f"[Qoder] Model queued ({display_elapsed}s) — waiting for capacity (~{wait_seconds}s)..."
            self._report_queue_status(msg_status)
            logger.info(msg_status)

            start_poll = time.time()
            poll_interval = 3.0
            while (time.time() - start_poll) < wait_seconds:
                time.sleep(poll_interval)
                cur_elapsed = int(time.time() - queue_start_time)
                self._report_queue_status(f"[Qoder] Model queued ({cur_elapsed}s) — estimated wait less than 1min...")
                st = self.poll_queue_status(
                    record_id=record_id,
                    model_key=effective_resolved_model,
                    queue_type=queue_type,
                    job_token=job_token,
                    user_id=user_id,
                    user_name=user_name,
                    user_email=user_email,
                )
                if st.get("serviceAvailable") is True and not st.get("isQueued"):
                    break

            self._report_queue_status("")

    def _execute_sync(
        self,
        req_body: dict[str, Any] | bytes,
        headers_or_raw_model: Any = None,
        raw_model: str = "",
        resolved_model: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        job_token: str = "",
        user_id: str = "",
        user_name: str = "",
        user_email: str = "",
    ) -> Any:
        """Accumulate streaming chunks into a single ChatCompletion object."""
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        usage: Optional[SimpleNamespace] = None
        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        effective_raw_model = raw_model or (headers_or_raw_model if isinstance(headers_or_raw_model, str) else "qfmodel")

        for chunk in self._stream_response(
            req_body=req_body,
            headers_or_raw_model=headers_or_raw_model,
            raw_model=effective_raw_model,
            resolved_model=resolved_model,
            timeout_seconds=timeout_seconds,
            job_token=job_token,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
        ):
            if hasattr(chunk, "id") and chunk.id:
                req_id = chunk.id
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage
            for choice in getattr(chunk, "choices", []):
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
                if delta.content:
                    content_parts.append(delta.content)
                if delta.reasoning_content:
                    reasoning_parts.append(delta.reasoning_content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": getattr(tc, "id", None) or f"call_{uuid.uuid4().hex[:12]}",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if getattr(tc, "id", None):
                            tool_calls_acc[idx]["id"] = tc.id
                        func = getattr(tc, "function", None)
                        if func:
                            if getattr(func, "name", None):
                                tool_calls_acc[idx]["function"]["name"] += func.name
                            if getattr(func, "arguments", None):
                                tool_calls_acc[idx]["function"]["arguments"] += func.arguments

        full_content = "".join(content_parts)
        full_reasoning = "".join(reasoning_parts)

        tool_calls_list = []
        if tool_calls_acc:
            for idx in sorted(tool_calls_acc.keys()):
                entry = tool_calls_acc[idx]
                tool_calls_list.append(
                    SimpleNamespace(
                        id=entry["id"],
                        type="function",
                        function=SimpleNamespace(
                            name=entry["function"]["name"],
                            arguments=entry["function"]["arguments"],
                        ),
                    )
                )

        if not usage:
            usage = SimpleNamespace(
                prompt_tokens=len(full_content) // 4,
                completion_tokens=len(full_content) // 4,
                total_tokens=len(full_content) // 2,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            )

        message = SimpleNamespace(
            role="assistant",
            content=full_content if full_content else (None if tool_calls_list else ""),
            reasoning=full_reasoning or None,
            reasoning_content=full_reasoning or None,
            tool_calls=tool_calls_list if tool_calls_list else None,
        )

        return SimpleNamespace(
            id=req_id,
            object="chat.completion",
            created=int(time.time()),
            model=effective_raw_model,
            choices=[
                SimpleNamespace(
                    index=0,
                    message=message,
                    finish_reason=finish_reason or ("tool_calls" if tool_calls_list else "stop"),
                )
            ],
            usage=usage,
        )

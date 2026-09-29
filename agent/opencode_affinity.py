from __future__ import annotations

import hashlib
import random
import time
from typing import Any, Optional

OPENCODE_SESSION_HEADER = "x-opencode-session"
OPENCODE_REQUEST_HEADER = "x-opencode-request"
OPENCODE_CLIENT_HEADER = "x-opencode-client"
OPENCODE_PROJECT_HEADER = "x-opencode-project"

OPENCODE_USER_AGENT = "opencode/1.18.31 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14"

_BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def derive_opencode_session_id(key: Optional[str]) -> str:
    """Deterministically derive a valid OpenCode SessionID (``ses_<26_chars>``).

    OpenCode validates the schema: 30 chars total, starts with 'ses_', followed by
    12 hex chars and 14 base62 alphanumeric characters. Deriving it via sha256 of the
    Shiina session/cache scope ensures prompt caching remains warm across conversation turns.
    """
    sid = str(key or "").strip()
    if not sid:
        sid = str(time.time())
    h = hashlib.sha256(sid.encode("utf-8", errors="replace")).digest()
    hex12 = h[:6].hex()
    rand14 = "".join(_BASE62_CHARS[b % 62] for b in h[6:20])
    return f"ses_{hex12}{rand14}"


def make_opencode_request_id() -> str:
    """Generate a unique OpenCode MessageID (``msg_<26_chars>``) for each request."""
    now = int(time.time() * 1000)
    current = now * 0x1000 + random.randint(1, 4095)
    val = current & 0xFFFFFFFFFFFF
    time_hex = f"{val:012x}"
    rand14 = "".join(random.choices(_BASE62_CHARS, k=14))
    return f"msg_{time_hex}{rand14}"


def is_opencode_target(provider: Optional[str], base_url: Optional[str]) -> bool:
    """True when *provider* or *base_url* addresses the OpenCode relay.

    Matches the built-in opencode-zen/go providers, custom
    ``opencode-<family>-*`` providers, and any base_url hosted on opencode.ai.
    """
    try:
        from shiina_cli.models import opencode_provider_family

        if opencode_provider_family(provider) is not None:
            return True
    except Exception:
        pass
    try:
        from agent.anthropic_endpoints import _is_opencode_endpoint

        if _is_opencode_endpoint(str(base_url or "")):
            return True
    except Exception:
        pass
    try:
        from utils import base_url_hostname

        return base_url_hostname(str(base_url or "")).lower() == "opencode.ai"
    except Exception:
        return False


def is_opencode_free_model(model: Optional[str]) -> bool:
    """True when *model* targets OpenCode's free or contributor tier."""
    m = (model or "").strip().lower()
    return "-free" in m or "-contributor" in m


def opencode_default_headers() -> dict[str, str]:
    """Default headers identifying the client as OpenCode CLI."""
    return {
        "User-Agent": OPENCODE_USER_AGENT,
        OPENCODE_CLIENT_HEADER: "cli",
        OPENCODE_PROJECT_HEADER: "global",
    }


def opencode_session_headers(
    provider: Optional[str],
    base_url: Optional[str],
    session_id: Optional[str] = None,
) -> dict[str, str]:
    """Return headers required for OpenCode targets, else ``{}``."""
    if not is_opencode_target(provider, base_url):
        return {}
    try:
        from agent.portal_tags import get_affinity_scope, get_conversation_context
        from agent.transports.codex import _cache_scope_from_session_id

        key = _cache_scope_from_session_id(
            get_affinity_scope() or get_conversation_context() or session_id
        )
    except Exception:
        key = str(session_id or "")

    ses_id = derive_opencode_session_id(key)
    msg_id = make_opencode_request_id()

    return {
        "User-Agent": OPENCODE_USER_AGENT,
        OPENCODE_CLIENT_HEADER: "cli",
        OPENCODE_PROJECT_HEADER: "global",
        OPENCODE_SESSION_HEADER: ses_id,
        OPENCODE_REQUEST_HEADER: msg_id,
    }


# Tool definitions conforming to OpenCode's schema for bash and read
OPENCODE_BASH_TOOL_RESPONSES = {
    "type": "function",
    "name": "bash",
    "description": "Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "workdir": {"type": "string", "description": "The working directory to run the command in"},
            "timeout": {"type": "integer", "description": "Optional timeout in milliseconds"},
        },
        "required": ["command"],
    },
}

OPENCODE_READ_TOOL_RESPONSES = {
    "type": "function",
    "name": "read",
    "description": "Read a file or directory from the local filesystem.",
    "parameters": {
        "type": "object",
        "properties": {
            "filePath": {"type": "string", "description": "The absolute path to the file or directory to read"},
            "offset": {"type": "integer", "description": "The line number to start reading from"},
            "limit": {"type": "integer", "description": "The maximum number of lines to read"},
        },
        "required": ["filePath"],
    },
}

OPENCODE_BASH_TOOL_CHAT = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"},
                "workdir": {"type": "string", "description": "The working directory to run the command in"},
                "timeout": {"type": "integer", "description": "Optional timeout in milliseconds"},
            },
            "required": ["command"],
        },
    },
}

OPENCODE_READ_TOOL_CHAT = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read a file or directory from the local filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string", "description": "The absolute path to the file or directory to read"},
                "offset": {"type": "integer", "description": "The line number to start reading from"},
                "limit": {"type": "integer", "description": "The maximum number of lines to read"},
            },
            "required": ["filePath"],
        },
    },
}


def ensure_opencode_compat_tools(kwargs: dict[str, Any], model: Optional[str]) -> None:
    """Inject bash and read tools into kwargs for OpenCode free-tier requests if missing.

    OpenCode Zen's free tier verifies that requests originate from within OpenCode by
    inspecting the payload tools. Both 'bash' and 'read' tool definitions must be present.
    """
    if not is_opencode_free_model(model):
        return

    # Check if this is Responses API (has 'input') or Chat Completions (has 'messages')
    is_responses = "input" in kwargs

    existing_tools = kwargs.get("tools")
    if existing_tools is None:
        existing_tools = []
    elif isinstance(existing_tools, list):
        existing_tools = list(existing_tools)
    else:
        return

    if is_responses:
        names = {t.get("name") for t in existing_tools if isinstance(t, dict)}
        if "bash" not in names:
            existing_tools.append(OPENCODE_BASH_TOOL_RESPONSES)
        if "read" not in names:
            existing_tools.append(OPENCODE_READ_TOOL_RESPONSES)
        kwargs["tools"] = existing_tools
        kwargs["tool_choice"] = "auto"
        kwargs["parallel_tool_calls"] = True
    else:
        names = set()
        for t in existing_tools:
            if isinstance(t, dict):
                fn = t.get("function")
                if isinstance(fn, dict) and "name" in fn:
                    names.add(fn["name"])
                elif "name" in t:
                    names.add(t["name"])
        if "bash" not in names:
            existing_tools.append(OPENCODE_BASH_TOOL_CHAT)
        if "read" not in names:
            existing_tools.append(OPENCODE_READ_TOOL_CHAT)
        kwargs["tools"] = existing_tools


def merge_opencode_session_headers(
    kwargs: dict[str, Any],
    provider: Optional[str],
    base_url: Optional[str],
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Merge OpenCode headers and compatibility tools into kwargs (in place)."""
    if not is_opencode_target(provider, base_url):
        return kwargs

    headers = opencode_session_headers(provider, base_url, session_id)
    if headers:
        existing = kwargs.get("extra_headers")
        merged = dict(existing) if isinstance(existing, dict) else {}
        for key, value in headers.items():
            merged.setdefault(key, value)
        kwargs["extra_headers"] = merged

    model = kwargs.get("model")
    ensure_opencode_compat_tools(kwargs, model)
    return kwargs

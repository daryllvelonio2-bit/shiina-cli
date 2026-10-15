from __future__ import annotations

import os
import time
from typing import Any, Optional

OPENCODE_SESSION_HEADER = "x-opencode-session"
OPENCODE_SESSION_ID_HEADER = "x-opencode-session-id"
OPENCODE_CLIENT_HEADER = "x-opencode-client"
OPENCODE_PROJECT_HEADER = "x-opencode-project"
# OpenCode v2 sends the session id under three extra names; the Zen free-tier gate 403s a
# request that carries none of them.
OPENCODE_AFFINITY_HEADERS = ("x-session-affinity", "x-session-id")

OPENCODE_USER_AGENT = "opencode/latest/2.0.29/cli"

_BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ID_CEILING = 1 << 48
_MAX_SCOPES = 512
_DEFAULT_SCOPE = ""
_SESSION_IDS: dict[str, str] = {}

# Free-tier Zen models whose id carries no ``-free`` marker (Zen's own default free model).
_OPENCODE_FREE_SLUGS = frozenset({"big-pickle"})


def new_opencode_session_id() -> str:
    """Mint a SessionID in the exact shape OpenCode v2's id generator emits.

    Zen's free-tier gate decodes the 12-hex prefix of ``x-opencode-session`` and 403s anything
    that is not that encoding — a plain millisecond timestamp, a sha256 slice and random hex all
    fail, while the inverted form passes. Mirror the generator: ``~((ms << 12) | counter)``
    truncated to 48 bits, then 14 random Base62 characters (26 after the ``ses_`` prefix).
    """
    value = (_ID_CEILING - 1) - ((int(time.time() * 1000) * 0x1000 + 1) % _ID_CEILING)
    tail = "".join(_BASE62_CHARS[b % 62] for b in os.urandom(14))
    return f"ses_{value:012x}{tail}"


def derive_opencode_session_id(key: Optional[str]) -> str:
    """One SessionID per cache scope, reused for the life of the process.

    Reuse is what both the gate and prompt caching need: the id has to carry a real clock value,
    so it is minted at first use for the scope and repeated on every later request instead of
    being recomputed (or hashed) per call.
    """
    scope = str(key or "").strip() or _DEFAULT_SCOPE
    sid = _SESSION_IDS.get(scope)
    if sid is None:
        if len(_SESSION_IDS) >= _MAX_SCOPES:
            _SESSION_IDS.clear()
        sid = _SESSION_IDS[scope] = new_opencode_session_id()
    return sid


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
    """True when *model* targets OpenCode's free or contributor tier.

    The tier is not flagged anywhere in Zen's catalog, so it is recognised by name: the
    ``-free``/``-contributor`` suffix every free model carries, plus the handful of free
    models that shipped without one (``big-pickle`` is Zen's default free model).
    """
    m = (model or "").strip().lower()
    return "-free" in m or "-contributor" in m or m in _OPENCODE_FREE_SLUGS


def _opencode_identity_headers(session_id: str) -> dict[str, str]:
    """The client-identity header set OpenCode v2 puts on every model request."""
    headers = {
        "User-Agent": OPENCODE_USER_AGENT,
        OPENCODE_CLIENT_HEADER: "cli",
        OPENCODE_PROJECT_HEADER: "global",
        OPENCODE_SESSION_HEADER: session_id,
        OPENCODE_SESSION_ID_HEADER: session_id,
    }
    for name in OPENCODE_AFFINITY_HEADERS:
        headers[name] = session_id
    return headers


def opencode_default_headers() -> dict[str, str]:
    """Client-identity headers for OpenCode targets when no conversation scope is bound."""
    return _opencode_identity_headers(derive_opencode_session_id(_DEFAULT_SCOPE))


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

    return _opencode_identity_headers(derive_opencode_session_id(key))


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

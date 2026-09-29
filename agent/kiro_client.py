"""Direct native Kiro client for Shiina CLI.

Drives the local [2J[H[?1000h[?1003h[?1006h[?1006l[?1003l[?1000l[?2004h[?u[>4;1m[?25l[6n[?2004h[?2026h[J● [97mI[0m[37mn[0m[37mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m
────────────────────────────────────────────────────────────[0m
                                                 [95m~/.shiina/shiina-agent[39m · (main)[0m
[0m
[7m [0mInitializing · type to queue a message[0m
                                                             /copy to clipboard[0m
[0m
[0m[?2026l[3A[1G[?25l[?2026h[4A
[2K                                      [95mKIRO[39m[0m
[2K[0m
[2K   An early release of [95mKiro CLI V3[39m is now available! Try it out: [95mkiro-cli --v3[39m[0m
[2K                                         [0m
[2K         [1mWhat's new:[22m Specs, expanded hooks, and an improved trust model.[0m
[2K                          [95mhttps://kiro.dev/docs/cli/v3/[39m[0m
[2K                                         [0m
[2K    [1mTip: [22mStart your message with ! to run a shell command without leaving the[0m
[2K    chat; [95mCtrl+C[39m cancels it.[0m
[2K[0m
[2K● [97mI[0m[37mn[0m[37mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m
[2K────────────────────────────────────────────────────────────[0m
[2K                                                 [95m~/.shiina/shiina-agent[39m · (main)[0m
[2K[0m
[2K[7m [0mInitializing · type to queue a message[0m
[2K                                                             /copy to clipboard[0m
[2K[0m
[2K[0m[?2026l[3A[1G[?25l[?2026h[4A
[2K● [37mI[0m[97mn[0m[37mi[0m[37mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [37mI[0m[37mn[0m[97mi[0m[37mt[0m[37mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[37mn[0m[37mi[0m[97mt[0m[37mi[0m[37ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[37mi[0m[37mt[0m[97mi[0m[37ma[0m[37ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[37mt[0m[37mi[0m[97ma[0m[37ml[0m[37mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[37mi[0m[37ma[0m[97ml[0m[37mi[0m[37mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[37ma[0m[37ml[0m[97mi[0m[37mz[0m[37mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[37ml[0m[37mi[0m[97mz[0m[37mi[0m[37mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[37mi[0m[37mz[0m[97mi[0m[37mn[0m[37mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[37mz[0m[37mi[0m[97mn[0m[37mg[0m[37m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[37mi[0m[37mn[0m[97mg[0m[37m.[0m[37m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[37mn[0m[37mg[0m[97m.[0m[37m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[37mg[0m[37m.[0m[97m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[37m.[0m[37m.[0m[97m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[37m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[1G[?25l[1G[?25l[?2026h[4A
[2K● [97mI[0m[37mn[0m[37mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [37mI[0m[97mn[0m[37mi[0m[37mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [37mI[0m[37mn[0m[97mi[0m[37mt[0m[37mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[37mn[0m[37mi[0m[97mt[0m[37mi[0m[37ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[37mi[0m[37mt[0m[97mi[0m[37ma[0m[37ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[37mt[0m[37mi[0m[97ma[0m[37ml[0m[37mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[37mi[0m[37ma[0m[97ml[0m[37mi[0m[37mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[37ma[0m[37ml[0m[97mi[0m[37mz[0m[37mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[37ml[0m[37mi[0m[97mz[0m[37mi[0m[37mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[37mi[0m[37mz[0m[97mi[0m[37mn[0m[37mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[37mz[0m[37mi[0m[97mn[0m[37mg[0m[37m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[37mi[0m[37mn[0m[97mg[0m[37m.[0m[37m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[37mn[0m[37mg[0m[97m.[0m[37m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[37mg[0m[37m.[0m[97m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[37m.[0m[37m.[0m[97m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[37m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[37m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[1G[?25l[1G[?25l[?2026h[4A
[2K● [97mI[0m[37mn[0m[37mi[0m[mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [37mI[0m[97mn[0m[37mi[0m[37mt[0m[mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [37mI[0m[37mn[0m[97mi[0m[37mt[0m[37mi[0m[ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[37mn[0m[37mi[0m[97mt[0m[37mi[0m[37ma[0m[ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K● [mI[0m[mn[0m[37mi[0m[37mt[0m[97mi[0m[37ma[0m[37ml[0m[mi[0m[mz[0m[mi[0m[mn[0m[mg[0m[m.[0m[m.[0m[m.[0m[0m[?2026l[4B[1G[?25l[?2026h[4A
[2K[0m
[2K────────────────────────────────────────────────────────────[0m
[2K[95mkiro_default[39m · auto                              [95m~/.shiina/shiina-agent[39m · (main)[0m[?2026l[2B[1G[?25l[?2026h
[2K[7m [0mask a question or describe a task ↵[0m[?2026l[1G[?25l[?2026h[2A
[2K[95mkiro_default[39m · auto · [32m◔[39m [32m10%[39m                      [95m~/.shiina/shiina-agent[39m · (main)[0m[?2026l[2B[1G[?25l[?2004l[>4;0m[4B
[?25h[?2004l tool directly in-process without requiring
a separate bridge daemon or proxy server. Reads user's active session & credentials
directly from .
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0
KIRO_DB_PATH = Path.home() / ".local/share/kiro-cli/data.sqlite3"

KIRO_MODELS = (
    "claude-sonnet-4.5",
    "claude-sonnet-4",
    "claude-haiku-4.5",
    "deepseek-3.2",
    "minimax-m2.5",
    "minimax-m2.1",
    "glm-5",
    "qwen3-coder-next",
    "auto",
)

KIRO_MODEL_ALIASES = {
    "kiro-sonnet": "claude-sonnet-4.5",
    "claude-sonnet": "claude-sonnet-4.5",
    "sonnet-4.5": "claude-sonnet-4.5",
    "kiro-deepseek": "deepseek-3.2",
    "deepseek": "deepseek-3.2",
    "kiro-haiku": "claude-haiku-4.5",
    "haiku": "claude-haiku-4.5",
    "kiro-qwen": "qwen3-coder-next",
    "qwen": "qwen3-coder-next",
    "kiro-minimax": "minimax-m2.5",
    "minimax": "minimax-m2.5",
    "kiro-auto": "auto",
}


def resolve_kiro_model(raw_model: str) -> str:
    """Normalize model string to standard Kiro model ID."""
    m = (raw_model or "").strip()
    for prefix in ("kiro/", "kiro-"):
        if m.startswith(prefix):
            m = m[len(prefix):]
            break
    return KIRO_MODEL_ALIASES.get(m, m) if m else "claude-sonnet-4.5"


def check_kiro_credentials() -> tuple[bool, Optional[str]]:
    """Check if the user is authenticated with Kiro CLI in data.sqlite3."""
    if not KIRO_DB_PATH.exists():
        return False, None
    try:
        conn = sqlite3.connect(f"file:{KIRO_DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM auth_kv WHERE key='kirocli:social:token'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            data = json.loads(row[0])
            token = data.get("access_token")
            if token:
                return True, data.get("provider", "social")
    except Exception as exc:
        logger.debug("Failed to inspect Kiro credentials: %s", exc)
    return False, None


def clean_kiro_output(raw_text: str) -> str:
    """Strip ANSI styling and decorative metadata lines emitted by kiro-cli chat."""
    clean = re.sub(r"\[[0-9;?]*[a-zA-Z]", "", raw_text)
    lines = clean.splitlines()
    content_lines = []
    found_content = False

    for line in lines:
        stripped = line.strip()
        if not found_content:
            if stripped.startswith("> "):
                found_content = True
                content_lines.append(stripped[2:])
                continue
            elif stripped.startswith(">"):
                found_content = True
                content_lines.append(stripped[1:].lstrip())
                continue
            elif stripped.startswith("WARNING:") or "needs to be prepended" in stripped or "All tools are now trusted" in stripped:
                continue
            elif not stripped:
                continue
            else:
                found_content = True
                content_lines.append(line)
                continue

        # Look for trailer/footer markers like '▸ Credits: 0.05 • Time: 3s'
        if ("Credits:" in stripped and ("Time:" in stripped or "▸" in stripped)) or stripped.startswith("▸ Credits:"):
            break

        if stripped.startswith("> "):
            content_lines.append(stripped[2:])
        elif stripped == ">":
            content_lines.append("")
        else:
            content_lines.append(line)

    return "\n".join(content_lines).strip()


def format_messages_for_kiro(messages: list[dict[str, Any]]) -> str:
    """Format an OpenAI-style messages list into a plain text prompt for kiro-cli."""
    if not messages:
        return ""

    if len(messages) == 1 and messages[0].get("role") == "user":
        content = messages[0].get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )

    sections = []
    for msg in messages:
        role = (msg.get("role") or "user").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        elif not isinstance(content, str):
            content = str(content or "")

        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            tc_strs = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                tc_strs.append(f"Tool Call: {fn.get('name')}({fn.get('arguments')})")
            content = (content + "\n" if content else "") + "\n".join(tc_strs)

        if role in ("SYSTEM", "DEVELOPER"):
            sections.append(f"[System Instructions]\n{content}")
        elif role == "USER":
            sections.append(f"[User]\n{content}")
        elif role == "ASSISTANT":
            sections.append(f"[Assistant]\n{content}")
        elif role == "TOOL":
            name = msg.get("name") or "tool"
            sections.append(f"[Tool Result ({name})]\n{content}")
        else:
            sections.append(f"[{role}]\n{content}")

    return "\n\n".join(sections)


class KiroClient:
    """Native OpenAI-compatible client facade directly invoking kiro-cli."""

    SHIINA_SKIP_TRANSPORT_WRAP = True
    SHIINA_SKIP_ASYNC_WRAP = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        command: str | None = None,
        **_: Any,
    ) -> None:
        self.api_key = api_key or "kiro-local"
        self.base_url = base_url or "kiro://local"
        self.command = command or os.environ.get("KIRO_BIN") or shutil.which("kiro-cli") or "/home/janelle/.local/bin/kiro-cli"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat_completion))
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True

    def _create_chat_completion(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        stream: bool = False,
        **_: Any,
    ) -> Any:
        resolved_model = resolve_kiro_model(model or "")
        prompt = format_messages_for_kiro(messages or [])
        if not prompt.strip():
            prompt = "Hello"

        timeout_seconds = float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else DEFAULT_TIMEOUT_SECONDS

        cmd = [
            self.command,
            "chat",
            "--no-interactive",
            "--trust-tools=",
            "--model",
            resolved_model,
        ]

        env = {
            **os.environ,
            "NO_COLOR": "1",
        }

        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Kiro CLI timed out after {timeout_seconds} seconds") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Could not find kiro-cli at '{self.command}'. Please install it or set KIRO_BIN.") from exc

        raw_output = proc.stdout or ""
        cleaned = clean_kiro_output(raw_output)

        if not cleaned and proc.returncode != 0:
            err = proc.stderr.strip() if proc.stderr else f"Process exited with code {proc.returncode}"
            raise RuntimeError(f"Kiro execution failed: {err}")

        from agent.acp_openai_bridge import (
            completion_to_stream_chunks as _completion_to_stream_chunks,
            extract_tool_calls_from_text as _extract_tool_calls_from_text,
        )

        tool_calls, cleaned_text = _extract_tool_calls_from_text(cleaned)

        message = SimpleNamespace(
            content=cleaned_text,
            tool_calls=tool_calls,
            reasoning=None,
            reasoning_content=None,
            reasoning_details=None,
        )

        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if tool_calls else "stop")],
            usage=SimpleNamespace(
                prompt_tokens=len(prompt) // 4,
                completion_tokens=len(cleaned_text) // 4,
                total_tokens=(len(prompt) + len(cleaned_text)) // 4,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
            model=model or resolved_model,
        )

        if stream:
            return _completion_to_stream_chunks(completion)
        return completion

"""Direct native Kiro client for Shiina CLI.

Drives the local kiro-cli tool directly in-process without requiring
a separate bridge daemon or proxy server. Reads user's active session & credentials
directly from local storage.
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


def ensure_shiina_agent_config() -> None:
    pass

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
    "sonnet": "claude-sonnet-4.5",
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
    if not m:
        return "claude-sonnet-4.5"
    if m in KIRO_MODEL_ALIASES:
        return KIRO_MODEL_ALIASES[m]
    for prefix in ("kiro/", "kiro-"):
        if m.startswith(prefix):
            m = m[len(prefix):]
            break
    return KIRO_MODEL_ALIASES.get(m, m)


def _get_kiro_db_path() -> Optional[Path]:
    """Find Kiro SQLite database across Linux, macOS, and Windows."""
    candidates = [
        Path.home() / ".local/share/kiro-cli/data.sqlite3",
        Path.home() / "Library/Application Support/kiro-cli/data.sqlite3",
    ]
    if "LOCALAPPDATA" in os.environ:
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "kiro-cli/data.sqlite3")
    for p in candidates:
        if p.is_file():
            return p
    return None


def check_kiro_credentials() -> tuple[bool, Optional[str]]:
    """Check if the user is authenticated with Kiro CLI in data.sqlite3."""
    db_path = _get_kiro_db_path()
    if not db_path:
        return False, None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
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


def extract_thinking_from_text(raw: str) -> tuple[Optional[str], str]:
    """Extract reasoning from <thinking> or <thought> tags."""
    if not raw:
        return None, ""
    pattern = re.compile(r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>", re.DOTALL | re.IGNORECASE)
    match = pattern.search(raw)
    if match:
        thinking = match.group(1).strip()
        text = pattern.sub("", raw).strip()
        return thinking, text
    return None, raw.strip()


def kiro_completion_to_stream_chunks(completion: Any) -> list[Any]:
    """Convert a Kiro completion object into stream chunks for streaming responses."""
    msg = completion.choices[0].message if completion.choices else None
    reasoning = getattr(msg, "reasoning_content", None) if msg else None
    content = getattr(msg, "content", "") if msg else ""
    finish_reason = completion.choices[0].finish_reason if completion.choices else "stop"

    chunks = []
    if reasoning:
        chunks.append(SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(reasoning_content=reasoning), finish_reason=None)]
        ))
    if content:
        chunks.append(SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=None)]
        ))
    chunks.append(SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(), finish_reason=finish_reason)]
    ))
    return chunks


def format_messages_for_kiro(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
) -> str:
    """Format an OpenAI-style messages list into a plain text prompt for kiro-cli."""
    if not messages and not tools:
        return ""

    sections = []
    if tools:
        tool_desc = ["Available tools:"]
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            tool_desc.append(f"- {name}: {desc} (parameters: {json.dumps(params)})")
        sections.append("\n".join(tool_desc))

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

        reasoning = msg.get("reasoning_content") or msg.get("reasoning")
        body_parts = []
        if reasoning:
            body_parts.append(f"<thinking>\n{reasoning}\n</thinking>")
        if content:
            body_parts.append(content)

        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                body_parts.append(f"<tool_call>{json.dumps(tc)}</tool_call>")

        body = "\n".join(body_parts)
        if role == "TOOL":
            name = msg.get("name") or "tool"
            cid = msg.get("tool_call_id")
            header = f"[Tool Result ({name} id={cid})]" if cid else f"[Tool Result ({name})]"
            sections.append(f"{header}\n{body}")
        elif role in ("SYSTEM", "DEVELOPER"):
            sections.append(f"[System Instructions]\n{body}")
        elif role == "USER":
            sections.append(f"[User]\n{body}")
        elif role == "ASSISTANT":
            sections.append(f"[Assistant]\n{body}")
        else:
            sections.append(f"[{role}]\n{body}")

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
        self.command = (
            command
            or os.environ.get("KIRO_BIN")
            or shutil.which("kiro-cli")
            or shutil.which("kiro")
            or str(Path.home() / ".local/bin/kiro-cli")
        )
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
        prompt = format_messages_for_kiro(messages or [], tools=tools)
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

        thinking, text_without_thinking = extract_thinking_from_text(cleaned)

        from agent.acp_openai_bridge import (
            extract_tool_calls_from_text as _extract_tool_calls_from_text,
        )

        tool_calls, cleaned_text = _extract_tool_calls_from_text(text_without_thinking)

        message = SimpleNamespace(
            content=cleaned_text,
            tool_calls=tool_calls,
            reasoning=thinking,
            reasoning_content=thinking,
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
            return kiro_completion_to_stream_chunks(completion)
        return completion

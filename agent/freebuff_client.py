"""Native Freebuff client for Shiina CLI.

Provides dynamic token and binary discovery, live model catalog fetching via the
Freebuff session API, and an OpenAI-compatible client facade driving the Freebuff CLI.
"""

from __future__ import annotations

import contextlib
import glob
import json
import logging
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0
ANSI_REGEX = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][AB012]")
READY_MARKERS = ("Enter a coding task", "for commands", "Freebucks remaining", "left \u00b7")
TAKEOVER_MARKERS = ("take over", "Take over")
MANICODE_DIR = Path.home() / ".config" / "manicode"

FREEBUFF_FALLBACK_MODELS = (
    "glm-5.3-flash",
    "deepseek-v4-flash",
    "gpt-5.6-luna",
    "gpt-6-luna",
    "mimo-v2.5",
    "mimo-v2.6-pro",
    "solar-pro4",
    "solar-mini4",
    "kimi-k3-eco",
    "gemini-3.8-flash",
    "muse-spark-1.2",
    "space-bunny-alpha",
)


def strip_ansi(s: str) -> str:
    """Strip ANSI escape sequences from terminal output."""
    return ANSI_REGEX.sub("", s)


def get_freebuff_token() -> Optional[str]:
    """Dynamically discover Freebuff / Codebuff auth token.

    Searches environment variables, ~/.config/manicode/credentials.json,
    and ~/.shiina/auth.json.
    """
    # 1. Environment variables
    for var in (
        "FREEBUFF_AUTH_TOKEN",
        "FREEBUFF_TOKEN",
        "CODEBUFF_AUTH_TOKEN",
        "CODEBUFF_TOKEN",
        "MANICODE_AUTH_TOKEN",
    ):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()

    # 2. ~/.config/manicode/credentials.json
    cred_file = MANICODE_DIR / "credentials.json"
    if cred_file.is_file():
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            if isinstance(cdata, dict):
                token = cdata.get("default", {}).get("authToken")
                if token:
                    return str(token).strip()
                for v in cdata.values():
                    if isinstance(v, dict) and v.get("authToken"):
                        return str(v["authToken"]).strip()
        except Exception as exc:
            logger.debug("Failed reading Freebuff token from %s: %s", cred_file, exc)

    # 3. ~/.shiina/auth.json
    try:
        shiina_auth = Path.home() / ".shiina" / "auth.json"
        if shiina_auth.is_file():
            with open(shiina_auth, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            providers = sdata.get("providers", {})
            fb_entry = providers.get("freebuff") or providers.get("codebuff") or {}
            token = fb_entry.get("authToken") or fb_entry.get("api_key") or fb_entry.get("access_token")
            if token:
                return str(token).strip()
    except Exception as exc:
        logger.debug("Failed reading Freebuff token from ~/.shiina/auth.json: %s", exc)

    return None


def find_freebuff_binary() -> Optional[str]:
    """Dynamically find the Freebuff executable across platforms."""
    # 1. Environment variables
    for env_var in ("FREEBUFF_BIN", "SHIINA_FREEBUFF_COMMAND", "CODEBUFF_BIN"):
        val = os.getenv(env_var)
        if val and os.path.isfile(val):
            return val

    # 2. PATH resolution
    for name in ("freebuff", "codebuff"):
        found = shutil.which(name)
        if found:
            return found

    # 3. Standard user installation directories
    home = Path.home()
    candidates = [
        home / ".npm-global" / "bin" / "freebuff",
        home / ".local" / "bin" / "freebuff",
        home / ".local" / "bin" / "codebuff",
        Path("/usr/local/bin/freebuff"),
        Path("/usr/bin/freebuff"),
        MANICODE_DIR / "freebuff",
    ]
    # NVM node bin directories
    nvm_matches = glob.glob(str(home / ".nvm" / "versions" / "node" / "*" / "bin" / "freebuff"))
    for match in nvm_matches:
        candidates.append(Path(match))

    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    return None


def fetch_freebuff_models(timeout: float = 15.0) -> list[str]:
    """Dynamically fetch live available models and prices from Freebuff API.

    Queries https://www.codebuff.com/api/v1/freebuff/session using the user's
    active auth token. Falls back to FREEBUFF_FALLBACK_MODELS if unavailable.
    """
    token = get_freebuff_token()
    if token:
        try:
            req = urllib.request.Request(
                "https://www.codebuff.com/api/v1/freebuff/session",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "freebuff-client/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                sdata = json.loads(resp.read().decode("utf-8"))
            prices = sdata.get("freebucks", {}).get("prices", {})
            if prices and isinstance(prices, dict):
                raw_models = sorted(prices.keys(), key=lambda m: (prices[m], m))
                cleaned_models: list[str] = []
                for m in raw_models:
                    clean = m.split("/")[-1] if "/" in m else m
                    if clean not in cleaned_models:
                        cleaned_models.append(clean)
                if cleaned_models:
                    return cleaned_models
        except Exception as exc:
            logger.debug("Failed fetching live Freebuff models: %s", exc)

    return list(FREEBUFF_FALLBACK_MODELS)


def _get_chat_state(chat_dir: str) -> tuple[Optional[str], bool, bool]:
    """Parse Freebuff transcript at chat_dir/chat-messages.json."""
    messages_file = os.path.join(chat_dir, "chat-messages.json")
    if not os.path.isfile(messages_file):
        return None, False, False
    try:
        with open(messages_file, "r", encoding="utf-8") as f:
            msgs = json.load(f)
    except Exception:
        return None, False, False
    if not isinstance(msgs, list):
        return None, False, False

    out_chunks: list[str] = []
    is_complete = False
    has_user = False
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("variant") == "user":
            has_user = True
        if m.get("variant") != "ai":
            continue
        for block in m.get("blocks") or []:
            if block.get("type") == "text" and block.get("textType") == "text" and block.get("content"):
                out_chunks.append(block["content"])
        if m.get("isComplete"):
            is_complete = True
    return ("\n".join(out_chunks) if out_chunks else None), is_complete, has_user


def format_messages_for_freebuff(messages: list[dict[str, Any]]) -> str:
    """Format an OpenAI-style messages list into a plain text task prompt for Freebuff."""
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
            sections.append(f"[Instructions]\n{content}")
        elif role == "USER":
            sections.append(f"[Task]\n{content}")
        elif role == "ASSISTANT":
            sections.append(f"[Assistant]\n{content}")
        elif role == "TOOL":
            name = msg.get("name") or "tool"
            sections.append(f"[Tool Result ({name})]\n{content}")
        else:
            sections.append(f"[{role}]\n{content}")

    return "\n\n".join(sections)


class FreebuffClient:
    """Native OpenAI-compatible client facade driving the local Freebuff CLI."""

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
        self.api_key = api_key or get_freebuff_token() or "freebuff-local"
        self.base_url = base_url or "freebuff://local"
        self.command = command or find_freebuff_binary()
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
        stream: bool = False,
        **_: Any,
    ) -> Any:
        bin_path = self.command or find_freebuff_binary()
        if not bin_path or not os.path.exists(bin_path):
            raise RuntimeError(
                "Freebuff CLI executable not found on this system.\n"
                "Please install Freebuff globally (`npm install -g freebuff`), "
                "or set the FREEBUFF_BIN environment variable."
            )

        token = get_freebuff_token()
        if not token:
            raise RuntimeError(
                "No Freebuff credentials found.\n"
                "Please run `freebuff` in your terminal to sign in, "
                "or set the FREEBUFF_AUTH_TOKEN environment variable."
            )

        prompt = format_messages_for_freebuff(messages or [])
        if not prompt.strip():
            prompt = "Hello"

        timeout_seconds = (
            float(timeout)
            if isinstance(timeout, (int, float)) and timeout > 0
            else DEFAULT_TIMEOUT_SECONDS
        )

        cwd = os.getcwd()
        chats_dir = MANICODE_DIR / "projects" / os.path.basename(os.path.abspath(cwd)) / "chats"
        before = set(os.listdir(chats_dir)) if chats_dir.is_dir() else set()

        master, slave = pty.openpty()
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"

        proc = subprocess.Popen(
            [bin_path],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=env,
            close_fds=True,
            preexec_fn=os.setsid,
        )
        os.close(slave)

        buf = ""
        deadline = time.time() + timeout_seconds
        typed = False
        last_nudge = 0.0
        nudges = 0

        def pump() -> None:
            nonlocal buf
            r, _, _ = select.select([master], [], [], 0.25)
            if master in r:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    return
                if chunk:
                    text = strip_ansi(chunk.decode("utf-8", "replace"))
                    buf = (buf + text)[-8000:]

        def get_newest_ready() -> Optional[str]:
            if not chats_dir.is_dir():
                return None
            current = set(os.listdir(chats_dir))
            for d in sorted(current - before, reverse=True):
                text, done, has_user = _get_chat_state(str(chats_dir / d))
                if done and text:
                    return text
            return None

        result_text: Optional[str] = None
        try:
            while time.time() < deadline:
                pump()

                # Handle session takeover if prompted
                if typed and any(m in buf for m in TAKEOVER_MARKERS):
                    os.write(master, b"\r")
                    buf = ""
                    time.sleep(2.0)
                    continue

                if not typed:
                    if any(m in buf for m in READY_MARKERS):
                        time.sleep(1.0)
                        os.write(master, prompt.encode("utf-8"))
                        time.sleep(0.5)
                        os.write(master, b"\r")
                        typed = True
                        buf = ""
                        last_nudge = time.time()
                    continue

                found = get_newest_ready()
                if found:
                    result_text = found
                    break

                # Re-submit prompt return if waiting on session connect
                if nudges < 8 and time.time() - last_nudge > 15.0:
                    os.write(master, b"\r")
                    nudges += 1
                    last_nudge = time.time()
        finally:
            with contextlib.suppress(Exception):
                os.killpg(os.getpgid(proc.pid), 15)
            time.sleep(0.3)
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                os.close(master)

        if not result_text:
            reason = (
                "Timed out waiting for Freebuff response"
                if typed
                else "Freebuff CLI never reached its input prompt"
            )
            raise RuntimeError(reason)

        if stream:
            return self._stream_generator(result_text, model or "glm-5.3-flash")
        else:
            return SimpleNamespace(
                id=f"chatcmpl-freebuff-{int(time.time())}",
                object="chat.completion",
                created=int(time.time()),
                model=model or "glm-5.3-flash",
                choices=[
                    SimpleNamespace(
                        index=0,
                        message=SimpleNamespace(role="assistant", content=result_text),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

    def _stream_generator(self, text: str, model_name: str) -> Iterator[Any]:
        chunk_size = 32
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            yield SimpleNamespace(
                id=f"chatcmpl-freebuff-{int(time.time())}",
                object="chat.completion.chunk",
                created=int(time.time()),
                model=model_name,
                choices=[
                    SimpleNamespace(
                        index=0,
                        delta=SimpleNamespace(role="assistant", content=chunk),
                        finish_reason=None,
                    )
                ],
            )
        yield SimpleNamespace(
            id=f"chatcmpl-freebuff-{int(time.time())}",
            object="chat.completion.chunk",
            created=int(time.time()),
            model=model_name,
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content=""),
                    finish_reason="stop",
                )
            ],
        )

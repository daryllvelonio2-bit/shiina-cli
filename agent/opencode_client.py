"""Direct native OpenCode client for Shiina CLI.

Drives the local `opencode` CLI tool in headless/json mode, authenticating with
the user's logged-in OpenCode account and local credentials (~/.local/share/opencode/auth.json).
Supports dynamic model listing, free built-in models, and streaming JSON events.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0

OPENCODE_FALLBACK_MODELS = (
    "opencode/big-pickle",
    "opencode/ling-3.0-flash-fin-free",
    "opencode/longcat-2.5-preview-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/muse-spark-1.3-contributor-free",
    "opencode/nemotron-3-ultra-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/space-bunny-free",
)


def find_opencode_binary() -> Optional[str]:
    """Find the opencode executable across standard platform locations."""
    env_bin = os.environ.get("OPENCODE_BIN") or os.environ.get("SHIINA_OPENCODE_COMMAND")
    if env_bin and shutil.which(env_bin):
        return env_bin
    if env_bin and os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin

    which_bin = shutil.which("opencode")
    if which_bin:
        return which_bin

    candidates = [
        Path.home() / ".opencode/bin/opencode",
        Path.home() / ".local/bin/opencode",
        Path.home() / ".npm-global/bin/opencode",
    ]
    if "LOCALAPPDATA" in os.environ:
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "opencode/bin/opencode.exe")
    if "APPDATA" in os.environ:
        candidates.append(Path(os.environ["APPDATA"]) / "npm/opencode.cmd")

    for p in candidates:
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)

    return None


def _opencode_version() -> str:
    binary = find_opencode_binary()
    if not binary:
        return "unknown"
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5.0)
        return ((out.stdout or out.stderr or "").strip().splitlines() or ["unknown"])[0]
    except Exception:
        return "unknown"


def _format_tool_use(part: Dict[str, Any]) -> Optional[str]:
    state = part.get("state") or {}
    if state.get("status") != "completed":
        return None
    raw_input = json.dumps(state.get("input") or {}, ensure_ascii=False)[:500]
    output = state.get("output")
    return f"[tool: {part.get('tool') or 'tool'}] {raw_input}\n{output if isinstance(output, str) else ''}"


def _opencode_mcp_enabled() -> bool:
    """D4: the shiina-tools bridge is on for the opencode-cli path; SHIINA_OPENCODE_MCP=0 kills it."""
    return os.environ.get("SHIINA_OPENCODE_MCP", "1").strip() != "0"


def _opencode_mcp_profile_env() -> Dict[str, str]:
    """D3: profile scope handed to the generated MCP entry (mirrors codex app-server)."""
    env: Dict[str, str] = {}
    if os.environ.get("SHIINA_HOME"):
        env["SHIINA_HOME"] = os.environ["SHIINA_HOME"]
    if os.environ.get("SHIINA_KANBAN_TASK"):
        from agent.delegation_context import KANBAN_ENV_KEYS, is_dispatcher_owned_worker_context

        if is_dispatcher_owned_worker_context():
            for key in (*KANBAN_ENV_KEYS, "SHIINA_KANBAN_DB", "SHIINA_KANBAN_BOARD"):
                if key in os.environ:
                    env[key] = os.environ[key]
    return env


def _discard_spawn_config(env: Optional[Dict[str, str]]) -> None:
    """Remove the per-invocation OPENCODE_CONFIG file once the child has exited."""
    path = (env or {}).get("OPENCODE_CONFIG")
    if path:
        Path(path).unlink(missing_ok=True)


def get_opencode_credentials() -> Dict[str, Any]:
    """Dynamically discover OpenCode credentials from local auth storage or environment."""
    candidates = [
        Path.home() / ".local/share/opencode/auth.json",
        Path.home() / "Library/Application Support/opencode/auth.json",
        Path.home() / ".config/opencode/auth.json",
        Path.home() / ".shiina/auth.json",
    ]
    if "LOCALAPPDATA" in os.environ:
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "opencode/auth.json")

    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    return data
            except Exception as exc:
                logger.debug("Failed reading OpenCode credentials from %s: %s", path, exc)

    return {}


def check_opencode_credentials() -> Tuple[bool, Optional[str]]:
    """Check if the user has OpenCode installed or local credentials configured."""
    creds = get_opencode_credentials()
    if creds:
        providers = list(creds.keys())
        first = providers[0] if providers else "credentials"
        return True, f"OpenCode store ({first})"

    for env_var in ("OPENCODE_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY"):
        if os.getenv(env_var):
            return True, f"env: {env_var}"

    binary = find_opencode_binary()
    if binary:
        return True, f"OpenCode CLI ({os.path.basename(binary)})"

    return False, None


def fetch_opencode_models(timeout: float = 15.0) -> List[str]:
    """Dynamically query available models from local opencode CLI."""
    binary = find_opencode_binary()
    if not binary:
        return list(OPENCODE_FALLBACK_MODELS)

    try:
        proc = subprocess.run(
            [binary, "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0 and proc.stdout:
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            models: List[str] = []
            for line in lines:
                if line.startswith("opencode/"):
                    models.append(line)
            for line in lines:
                if not line.startswith("opencode/") and line not in models:
                    models.append(line)

            if models:
                return models
    except Exception as exc:
        logger.debug("Dynamic opencode model discovery error: %s", exc)

    return list(OPENCODE_FALLBACK_MODELS)


def _format_messages_for_prompt(messages: List[Dict[str, Any]]) -> str:
    """Combine chat history messages into a clean prompt string for opencode run."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_blocks = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    text_blocks.append(b.get("text", ""))
                elif isinstance(b, str):
                    text_blocks.append(b)
            content = "\n".join(text_blocks)
        content_str = str(content or "").strip()
        if not content_str:
            continue
        if role == "system":
            parts.append(f"[System Instruction]\n{content_str}")
        elif role == "assistant":
            parts.append(f"[Assistant]\n{content_str}")
        elif role == "user":
            parts.append(f"[User]\n{content_str}")
        else:
            parts.append(f"[{role.capitalize()}]\n{content_str}")

    return "\n\n".join(parts) if parts else ""


class OpenCodeClient:
    """OpenAI-compatible client facade driving opencode CLI subprocess in headless mode."""

    def __init__(self, **kwargs: Any) -> None:
        self.timeout = float(kwargs.get("timeout") or DEFAULT_TIMEOUT_SECONDS)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_completion))

    def _create_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        binary = find_opencode_binary()
        if not binary:
            raise RuntimeError(
                "OpenCode binary not found. Please install opencode or set OPENCODE_BIN."
            )

        target_model = (model or "opencode/big-pickle").strip()
        for prefix in ("opencode-cli/", "opencode/"):
            if target_model.startswith(prefix) and prefix == "opencode-cli/":
                target_model = target_model[len(prefix):]

        prompt = _format_messages_for_prompt(messages)
        if not prompt:
            prompt = "Hello"

        cmd = [
            binary,
            "run",
            "--format",
            "json",
            "--pure",
            "--thinking",
            "-m",
            target_model,
            prompt,
        ]

        logger.debug("Executing opencode command: %s", cmd[:7])

        spawn_env: Optional[Dict[str, str]] = None
        if _opencode_mcp_enabled():
            from agent.opencode_mcp_bridge import write_opencode_config
            from tools.environments.local import shiina_subprocess_env

            spawn_env = shiina_subprocess_env(inherit_credentials=True)
            spawn_env["OPENCODE_CONFIG"] = str(write_opencode_config(_opencode_mcp_profile_env()))

        if stream:
            return self._stream_generator(cmd, target_model, spawn_env)
        return self._execute_sync(cmd, target_model, spawn_env)

    def _execute_sync(self, cmd: List[str], model: str, env: Optional[Dict[str, str]] = None) -> Any:
        session_id = f"ses_{int(time.time() * 1000)}"
        full_text: List[str] = []
        full_reasoning: List[str] = []
        finish_reason = "stop"
        saw_tool_use = False
        usage_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            stdout, stderr = proc.communicate(timeout=self.timeout)
            if proc.returncode != 0 and not stdout:
                err_msg = (stderr or "").strip()
                raise RuntimeError(f"opencode exited with code {proc.returncode}: {err_msg}")

            for line in (stdout or "").splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                    ev_type = data.get("type")
                    part = data.get("part", {})
                    if data.get("sessionID"):
                        session_id = data["sessionID"]

                    if ev_type == "text":
                        full_text.append(part.get("text", ""))
                    elif ev_type == "reasoning":
                        full_reasoning.append(part.get("text", ""))
                    elif ev_type == "tool_use":
                        tool_text = _format_tool_use(part)
                        if tool_text is not None:
                            saw_tool_use = True
                            full_text.append(tool_text)
                    elif ev_type == "step_finish":
                        finish_reason = part.get("reason", "stop")
                        tokens = part.get("tokens", {})
                        if tokens:
                            usage_tokens["prompt_tokens"] = tokens.get("input", 0)
                            usage_tokens["completion_tokens"] = tokens.get("output", 0)
                            usage_tokens["total_tokens"] = tokens.get("total", 0)
                except Exception:
                    continue

        except subprocess.TimeoutExpired:
            proc.kill()
            raise TimeoutError(f"opencode run timed out after {self.timeout} seconds.")
        finally:
            _discard_spawn_config(env)

        content_str = "".join(full_text).strip()
        reasoning_str = "".join(full_reasoning).strip() or None

        if finish_reason == "tool-calls" and not saw_tool_use:
            raise RuntimeError(
                f"opencode {_opencode_version()} returned tool-calls for {model} with no "
                f"tool_use \u2014 refusing a hollow assistant turn."
            )

        msg = SimpleNamespace(
            content=content_str,
            reasoning_content=reasoning_str,
            role="assistant",
        )
        choice = SimpleNamespace(
            message=msg,
            finish_reason=finish_reason,
            index=0,
        )
        usage = SimpleNamespace(**usage_tokens)

        return SimpleNamespace(
            id=session_id,
            choices=[choice],
            model=model,
            usage=usage,
        )

    def _stream_generator(self, cmd: List[str], model: str, env: Optional[Dict[str, str]] = None) -> Iterator[Any]:
        session_id = f"ses_{int(time.time() * 1000)}"
        last_finish = "stop"
        saw_output = False
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                    ev_type = data.get("type")
                    part = data.get("part", {})
                    if data.get("sessionID"):
                        session_id = data["sessionID"]

                    delta_text = None
                    delta_reasoning = None
                    finish_reason = None

                    if ev_type == "text":
                        delta_text = part.get("text", "")
                    elif ev_type == "reasoning":
                        delta_reasoning = part.get("text", "")
                    elif ev_type == "tool_use":
                        delta_text = _format_tool_use(part)
                    elif ev_type == "step_finish":
                        finish_reason = part.get("reason", "stop")
                        last_finish = finish_reason

                    if delta_text is not None or delta_reasoning is not None:
                        saw_output = True

                    if delta_text is not None or delta_reasoning is not None or finish_reason is not None:
                        delta = SimpleNamespace(
                            content=delta_text,
                            reasoning_content=delta_reasoning,
                            role="assistant",
                        )
                        choice = SimpleNamespace(
                            delta=delta,
                            finish_reason=finish_reason,
                            index=0,
                        )
                        yield SimpleNamespace(
                            id=session_id,
                            choices=[choice],
                            model=model,
                        )
                except Exception:
                    continue

            proc.wait(timeout=5.0)
            if last_finish == "tool-calls" and not saw_output:
                raise RuntimeError(
                    f"opencode {_opencode_version()} ended a stream with finish_reason='tool-calls' "
                    f"for model {model} and yielded nothing \u2014 refusing a hollow assistant turn."
                )
        except Exception:
            proc.kill()
            raise
        finally:
            if proc.poll() is None:
                proc.kill()
            _discard_spawn_config(env)

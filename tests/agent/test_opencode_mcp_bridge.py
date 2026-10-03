"""Tests for the per-invocation opencode MCP config builder (PLAN-7 s2)."""

import json
import stat
import subprocess
import sys
from pathlib import Path

from agent.opencode_mcp_bridge import build_opencode_mcp_config, write_opencode_config
from agent.transports.shiina_tools_mcp_server import SHIINA_TOOLS_MCP_SERVER_NAME

_SERVER_COMMAND = [sys.executable, "-m", "agent.transports.shiina_tools_mcp_server"]


def test_config_declares_local_shiina_tools_server():
    env = {"SHIINA_HOME": "/tmp/profile-a", "PATH": "/usr/bin"}
    config = build_opencode_mcp_config(env)
    assert config["mcp"][SHIINA_TOOLS_MCP_SERVER_NAME] == {
        "type": "local",
        "command": _SERVER_COMMAND,
        "enabled": True,
        "environment": env,
    }


def test_environment_carries_shiina_home_verbatim():
    env = {"SHIINA_HOME": "/tmp/some-profile-home"}
    config = build_opencode_mcp_config(env)
    assert config["mcp"][SHIINA_TOOLS_MCP_SERVER_NAME]["environment"] == env


def test_write_opencode_config_roundtrip_mode_0600():
    env = {"SHIINA_HOME": "/tmp/profile-a"}
    path = write_opencode_config(env)
    try:
        assert path.exists()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        loaded = json.loads(path.read_text())
        assert loaded["mcp"][SHIINA_TOOLS_MCP_SERVER_NAME]["environment"] == env
        assert loaded["mcp"][SHIINA_TOOLS_MCP_SERVER_NAME]["command"] == _SERVER_COMMAND
    finally:
        path.unlink(missing_ok=True)


def test_module_import_does_not_pull_opencode_client():
    code = (
        "import sys, agent.opencode_mcp_bridge; "
        "pulled = sorted(m for m in sys.modules if m.startswith('agent.opencode_client')); "
        "assert not pulled, pulled"
    )
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=repo_root
    )
    assert result.returncode == 0, result.stderr

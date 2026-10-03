"""Per-invocation opencode MCP config builder.

opencode reads this JSON via ``OPENCODE_CONFIG`` and spawns the stdio MCP server
``agent.transports.shiina_tools_mcp_server`` itself, so a model-driving opencode
child gets Shiina's tools without a schema-injection provider. The user's
``~/.config/opencode/opencode.json`` is never touched; the ``environment`` block
carries the profile-scoped spawn env resolved by the caller.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from agent.transports.shiina_tools_mcp_server import SHIINA_TOOLS_MCP_SERVER_NAME

_OPENCODE_CONFIG_SCHEMA = "https://opencode.ai/config.json"


def build_opencode_mcp_config(profile_env: dict) -> dict:
    """Config declaring the local shiina-tools MCP server with the given spawn env."""
    return {
        "$schema": _OPENCODE_CONFIG_SCHEMA,
        "mcp": {
            SHIINA_TOOLS_MCP_SERVER_NAME: {
                "type": "local",
                "command": [sys.executable, "-m", "agent.transports.shiina_tools_mcp_server"],
                "enabled": True,
                "environment": profile_env,
            }
        },
    }


def write_opencode_config(profile_env: dict) -> Path:
    """Write the config to a fresh owner-only temp file and return its Path."""
    fd, tmp_path = tempfile.mkstemp(prefix="opencode-config-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(build_opencode_mcp_config(profile_env), f)
    os.chmod(tmp_path, 0o600)
    return Path(tmp_path)

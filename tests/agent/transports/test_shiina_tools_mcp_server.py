"""Tests for the shiina-tools-as-MCP server module surface.

We don't run a live MCP session in unit tests — that requires the codex
subprocess + client + an event loop. These tests pin the static
contract: the module imports, the EXPOSED_TOOLS list is sane, and the
build helper assembles a server when the SDK is present.
"""

from __future__ import annotations

import inspect
from typing import get_args

from agent.transports.shiina_tools_mcp_server import (
    _signature_from_schema,
)


class TestSignatureFromSchema:
    """Test the JSON Schema -> Python signature conversion."""

    def test_simple_required_string_param(self):
        """A required string param becomes str with no default."""
        schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        sig, annots = _signature_from_schema(schema)

        assert len(sig.parameters) == 1
        param = sig.parameters["query"]
        assert param.name == "query"
        assert param.kind == inspect.Parameter.KEYWORD_ONLY
        assert annots["query"] == str
        assert param.default is inspect.Parameter.empty



    def test_skip_private_params(self):
        """Params starting with '_' are excluded from the signature."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "_internal": {"type": "string"},
            },
            "required": ["query", "_internal"],
        }
        sig, annots = _signature_from_schema(schema)

        assert "_internal" not in sig.parameters
        assert "_internal" not in annots
        assert "query" in sig.parameters

    def test_all_json_types(self):
        """All JSON schema types map to correct Python types."""
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string"},
                "i": {"type": "integer"},
                "n": {"type": "number"},
                "b": {"type": "boolean"},
                "a": {"type": "array"},
                "o": {"type": "object"},
            },
            "required": ["s", "i", "n", "b", "a", "o"],
        }
        sig, annots = _signature_from_schema(schema)

        assert annots["s"] == str
        assert annots["i"] == int
        assert annots["n"] == float
        assert annots["b"] == bool
        assert annots["a"] == list
        assert annots["o"] == dict








class TestModuleSurface:
    def test_module_imports_clean(self):
        from agent.transports import shiina_tools_mcp_server as m
        assert callable(m.main)
        assert callable(m._build_server)
        assert isinstance(m.EXPOSED_TOOLS, tuple)
        assert len(m.EXPOSED_TOOLS) > 0

    def test_exposed_tools_are_safe_subset(self):
        """We MUST NOT expose tools codex already has, because codex'
        own builtins are better-integrated with its sandbox + approvals.
        Specifically: no terminal/shell, no read_file/write_file, no
        patch — those are codex's built-in tools."""
        from agent.transports.shiina_tools_mcp_server import EXPOSED_TOOLS
        forbidden = {
            "terminal", "shell", "read_file", "write_file", "patch",
            "search_files", "process",
        }
        leaked = forbidden & set(EXPOSED_TOOLS)
        assert not leaked, (
            f"these tools must NOT be exposed via the codex callback "
            f"because codex has built-in equivalents: {leaked}"
        )






class TestResolveExposedTools:
    """Per-invocation permission scoping for the exposed tool set."""

    def test_no_env_equals_curated_tuple(self, monkeypatch):
        """Unset env ⇒ today's EXPOSED_TOOLS tuple, in order (codex path unchanged)."""
        monkeypatch.delenv("SHIINA_TOOLS_MCP_EXPOSE", raising=False)
        monkeypatch.delenv("SHIINA_TOOLS_MCP_DENY", raising=False)
        from agent.transports import shiina_tools_mcp_server as m

        assert m.resolve_exposed_tools() == m.EXPOSED_TOOLS

    def test_blank_env_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("SHIINA_TOOLS_MCP_EXPOSE", "  , ")
        monkeypatch.setenv("SHIINA_TOOLS_MCP_DENY", "")
        from agent.transports import shiina_tools_mcp_server as m

        assert m.resolve_exposed_tools() == m.EXPOSED_TOOLS

    def test_deny_subtracts_only_that_member(self, monkeypatch):
        monkeypatch.delenv("SHIINA_TOOLS_MCP_EXPOSE", raising=False)
        monkeypatch.setenv("SHIINA_TOOLS_MCP_DENY", "web_search")
        from agent.transports import shiina_tools_mcp_server as m

        resolved = m.resolve_exposed_tools()
        assert "web_search" in m.EXPOSED_TOOLS
        assert "web_search" not in resolved
        assert set(resolved) == set(m.EXPOSED_TOOLS) - {"web_search"}
        assert len(resolved) == len(m.EXPOSED_TOOLS) - 1

    def test_expose_narrows_but_cannot_add_outside_curated_set(self, monkeypatch):
        """EXPOSE is an allow-list over EXPOSED_TOOLS: it names a subset, never a superset.

        'terminal' is intentionally outside the curated set (codex has a builtin); naming
        it must not leak it in.
        """
        monkeypatch.setenv("SHIINA_TOOLS_MCP_EXPOSE", "web_search, terminal")
        monkeypatch.delenv("SHIINA_TOOLS_MCP_DENY", raising=False)
        from agent.transports import shiina_tools_mcp_server as m

        assert m.resolve_exposed_tools() == ("web_search",)


class TestMain:
    def test_main_returns_2_when_mcp_unavailable(self, monkeypatch):
        """When the mcp package isn't installed, main() should exit
        cleanly with code 2 and an install hint, not crash."""
        import agent.transports.shiina_tools_mcp_server as m

        def boom_build(*a, **kw):
            raise ImportError("mcp not installed")

        monkeypatch.setattr(m, "_build_server", boom_build)
        rc = m.main(["--verbose"])
        assert rc == 2

    def test_main_handles_keyboard_interrupt(self, monkeypatch):
        import agent.transports.shiina_tools_mcp_server as m

        class FakeServer:
            def run(self):
                raise KeyboardInterrupt()

        monkeypatch.setattr(m, "_build_server", lambda: FakeServer())
        rc = m.main([])
        assert rc == 0

    def test_main_returns_1_on_runtime_error(self, monkeypatch):
        import agent.transports.shiina_tools_mcp_server as m

        class CrashingServer:
            def run(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(m, "_build_server", lambda: CrashingServer())
        rc = m.main([])
        assert rc == 1

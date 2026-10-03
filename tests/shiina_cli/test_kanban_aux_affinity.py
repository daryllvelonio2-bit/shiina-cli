"""Kanban specify/decompose run headless (no agent turn), yet their auxiliary calls must still carry a
relay-affinity key — the OpenCode Go relay rejects a request without ``x-opencode-session`` with
400 MissingSessionID (#112043). ``_call_aux`` declares a per-task affinity scope unless one is bound.

The header value is the *derived* OpenCode SessionID for that scope, never the raw scope: OpenCode's
canonical SessionID shape is ``ses_`` + 12 lowercase-hex + 14 Base62 characters (30 total), and the
Zen free tier rejects any other shape. ``derive_opencode_session_id()`` hashes the scope into that
shape, so one task keeps one stable id across its headless aux calls.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.opencode_affinity import derive_opencode_session_id
from shiina_cli import kanban_decompose as decompose
from shiina_cli import kanban_specify as specify

# Canonical OpenCode SessionID: "ses_" + 12 lowercase-hex + 14 Base62 (30 chars).
_CANONICAL_SESSION_ID_RE = re.compile(r"^ses_[0-9a-f]{12}[0-9A-Za-z]{14}$")


def _capturing_call_llm(seen: list):
    def call_llm(**kwargs):
        from agent.opencode_affinity import opencode_session_headers
        seen.append(opencode_session_headers("opencode-go", None).get("x-opencode-session"))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    return call_llm


def _assert_canonical(seen: list):
    for value in seen:
        assert _CANONICAL_SESSION_ID_RE.match(value), value  # OpenCode/Zen-valid, not the raw scope


@pytest.mark.parametrize("caller", [specify._call_aux, decompose._call_aux])
def test_headless_kanban_aux_call_declares_a_stable_per_task_affinity_key(caller):
    from agent.portal_tags import get_affinity_scope
    seen: list = []
    with patch("agent.auxiliary_client.call_llm", _capturing_call_llm(seen)):
        for task_id in ("t_123", "t_123", "t_456"):
            reply, reason = caller(
                "specify", task_id, aux_task="triage_specifier", system="s", user="u",
                max_tokens=10, timeout=5)
            assert (reply, reason) == ("ok", "")
    assert seen == [
        derive_opencode_session_id("kanban:t_123"),
        derive_opencode_session_id("kanban:t_123"),
        derive_opencode_session_id("kanban:t_456"),
    ]
    _assert_canonical(seen)
    assert get_affinity_scope() is None  # nothing leaks past the call


def test_in_turn_caller_keeps_its_declared_affinity_key():
    from agent.portal_tags import reset_affinity_scope, set_affinity_scope
    seen: list = []
    token = set_affinity_scope("conversation-root")
    try:
        with patch("agent.auxiliary_client.call_llm", _capturing_call_llm(seen)):
            specify._call_aux("specify", "t_123", aux_task="triage_specifier", system="s", user="u",
                              max_tokens=10, timeout=5)
    finally:
        reset_affinity_scope(token)
    assert seen == [derive_opencode_session_id("conversation-root")]
    _assert_canonical(seen)


def _dashboard_plugin_api():
    mod_name = "shiina_dashboard_plugin_kanban_aux_affinity_test"
    if mod_name not in sys.modules:
        plugin_file = Path(__file__).resolve().parents[2] / "plugins" / "kanban" / "dashboard" / "plugin_api.py"
        spec = importlib.util.spec_from_file_location(mod_name, plugin_file)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[mod_name]


def test_dashboard_estimate_declares_an_affinity_key_too():
    """The dashboard estimate endpoints are the same headless aux call: per task when one exists,
    one stable key for the create dialog (no task yet)."""
    from agent.portal_tags import get_affinity_scope
    api = _dashboard_plugin_api()
    seen: list = []
    with patch("agent.auxiliary_client.call_llm", _capturing_call_llm(seen)):
        api._run_estimate("title", "body", task_id="t_1")
        api._run_estimate("title", "body", task_id=None)
    assert seen == [
        derive_opencode_session_id("kanban:t_1"),
        derive_opencode_session_id("kanban:estimate"),
    ]
    _assert_canonical(seen)
    assert get_affinity_scope() is None

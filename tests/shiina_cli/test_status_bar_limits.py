"""Unit tests for status bar limits, reset time display, and non-blocking caching."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agent.account_usage import AccountUsageSnapshot, AccountUsageWindow, _snapshot
from shiina_cli.cli_status_bar_mixin import CLIStatusBarMixin
from shiina_cli.status_bar_limits import (
    clear_limits_cache,
    format_limits_compact,
    format_reset_compact,
    get_cached_account_limits,
    refresh_account_limits_async,
    resolve_provider_for_model,
    _filter_model_windows,
    _limits_cache,
)


def test_format_reset_compact_none_or_expired():
    assert format_reset_compact(None) == ""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert format_reset_compact(past) == ""


def test_format_reset_compact_intervals():
    now = datetime.now(timezone.utc)
    # seconds
    assert format_reset_compact(now + timedelta(seconds=45)) in ("44s", "45s")
    # minutes
    assert format_reset_compact(now + timedelta(minutes=15)) in ("14m", "15m")
    # hours & minutes
    val = format_reset_compact(now + timedelta(hours=3, minutes=10))
    assert val.startswith("3h") and ("10m" in val or "9m" in val)
    # days & hours
    val_days = format_reset_compact(now + timedelta(days=3, hours=20))
    assert val_days.startswith("3d") and ("20h" in val_days or "19h" in val_days)


def test_filter_model_windows():
    w_gemini = AccountUsageWindow(label="Gemini Models (weekly)", used_percent=30.0)
    w_claude = AccountUsageWindow(label="Claude and GPT models (weekly)", used_percent=80.0)
    snap = _snapshot("antigravity", "quota", [w_gemini, w_claude], [])

    # Gemini model filters
    assert _filter_model_windows(snap, "agy-flash") == [w_gemini]
    assert _filter_model_windows(snap, "gemini-2.5-pro") == [w_gemini]

    # Claude / GPT filters
    assert _filter_model_windows(snap, "claude-3-7-sonnet") == [w_claude]
    assert _filter_model_windows(snap, "gpt-4o") == [w_claude]

    # Fallback when model has no keyword match
    assert _filter_model_windows(snap, "custom-model") == [w_gemini, w_claude]


def test_format_limits_compact_wide_and_narrow():
    now = datetime.now(timezone.utc)
    w_5h = AccountUsageWindow(label="Gemini Models (5h)", used_percent=30.0, reset_at=now + timedelta(hours=3))
    w_wk = AccountUsageWindow(label="Gemini Models (weekly)", used_percent=52.0, reset_at=now + timedelta(days=3, hours=20))
    snap = _snapshot("antigravity", "quota", [w_5h, w_wk], [])

    # Wide: shows both 5h and weekly
    frags_wide, text_wide = format_limits_compact(snap, model="agy-flash", width=80, styled=True)
    assert "5h 70%" in text_wide
    assert "w 48%" in text_wide
    assert any(st == "class:status-bar-good" for st, _ in frags_wide)
    assert any(st == "class:status-bar-warn" for st, _ in frags_wide)

    # Narrow: shows only primary 5h
    frags_narrow, text_narrow = format_limits_compact(snap, model="agy-flash", width=60, styled=True)
    assert "70%" in text_narrow
    assert "w 48%" not in text_narrow


def test_format_limits_compact_exhausted_weekly_prioritization():
    now = datetime.now(timezone.utc)
    w_5h = AccountUsageWindow(label="Claude and GPT models (5h)", used_percent=0.0, reset_at=now + timedelta(hours=4))
    w_wk = AccountUsageWindow(label="Claude and GPT models (weekly)", used_percent=100.0, reset_at=now + timedelta(days=2))
    snap = _snapshot("antigravity", "quota", [w_5h, w_wk], [])

    # Even in narrow mode, exhausted weekly (0% remaining) should be prioritized
    frags, text = format_limits_compact(snap, model="claude-3-7-sonnet", width=60, styled=True)
    assert "w 0%" in text
    assert any(st == "class:status-bar-critical" and t == "0%" for st, t in frags)


def test_resolve_provider_for_model():
    assert resolve_provider_for_model("openai-codex", "codex") == "openai-codex"
    assert resolve_provider_for_model(None, "agy-flash") == "antigravity"
    assert resolve_provider_for_model(None, "gemini-2.5-pro") == "antigravity"
    assert resolve_provider_for_model(None, "claude-sonnet") == "antigravity"
    assert resolve_provider_for_model(None, "xkiro/gpt-4o") == "xkiro"
    assert resolve_provider_for_model(None, "cline/sonnet") == "cline"
    assert resolve_provider_for_model(None, "kilocode/deepseek") == "kilocode"
    assert resolve_provider_for_model(None, "nous/hermes-3") == "nous"
    assert resolve_provider_for_model(None, None) is None


def test_format_limits_compact_credits_and_balance():
    # Cline balance window without used_percent
    snap_cline = _snapshot("cline", "balance", [AccountUsageWindow("Cline Balance", None, detail="447,388 credits available")], [])
    _, text_cline = format_limits_compact(snap_cline, model="cline", width=80, styled=True)
    assert text_cline == "447,388 cred"

    # Kilo balance window
    snap_kilo = _snapshot("kilocode", "balance", [AccountUsageWindow("Kilo Account", None, detail="$2.50 balance")], [])
    _, text_kilo = format_limits_compact(snap_kilo, model="kilocode", width=80, styled=True)
    assert text_kilo == "$2.50"



def test_caching_and_non_blocking_behavior():
    clear_limits_cache()

    dummy_snap = _snapshot("antigravity", "quota", [AccountUsageWindow("5h", 10.0)], [])
    _limits_cache["antigravity:agy-flash"] = (float("inf"), dummy_snap)

    # Immediate cache hit
    hit = get_cached_account_limits("antigravity", "agy-flash")
    assert hit is dummy_snap

    # Clear and verify background fetch trigger without blocking
    clear_limits_cache()
    with patch("agent.account_usage.fetch_account_usage", return_value=dummy_snap) as mock_fetch:
        updated = []
        res = get_cached_account_limits(
            "antigravity", "agy-flash", on_update=lambda: updated.append(True)
        )
        assert res is None  # Initial return is non-blocking (None)
        # Background thread will execute
        import time
        for _ in range(50):
            if updated:
                break
            time.sleep(0.02)
        assert len(updated) == 1
        assert mock_fetch.called


class DummyCLI(CLIStatusBarMixin):
    def __init__(self):
        self._status_bar_visible = True
        self.session_start = datetime.now()
        self.model = "agy-flash"
        self.provider = "antigravity"
        self.agent = None
        self._prompt_stash = type("Stash", (), {"indicator": lambda self: ""})()

    def _is_session_yolo_active(self):
        return False

    def _get_status_bar_session_title(self):
        return ""

    def _format_prompt_elapsed(self, *a, **k):
        return ""

    def _format_idle_since(self, *a, **k):
        return ""

    def _cache_hit_rate(self, *a, **k):
        return None

    def _status_bar_context_style(self, *a, **k):
        return ""

    def _status_bar_display_width(self, t):
        return len(t)

    def _get_tui_terminal_width(self):
        return 80


def test_minimal_status_bar_renders_limits_beside_ctx(monkeypatch):
    clear_limits_cache()
    now = datetime.now(timezone.utc)
    w_5h = AccountUsageWindow(label="Gemini Models (5h)", used_percent=30.0, reset_at=now + timedelta(hours=3, minutes=10))
    w_wk = AccountUsageWindow(label="Gemini Models (weekly)", used_percent=52.0, reset_at=now + timedelta(days=3, hours=20))
    snap = _snapshot("antigravity", "quota", [w_5h, w_wk], [])
    _limits_cache["antigravity:agy-flash"] = (float("inf"), snap)

    cli = DummyCLI()

    import cli as cli_mod
    monkeypatch.setattr(cli_mod, "CLI_CONFIG", {"display": {"status_bar": {"fields": ["model", "context_detail"]}}})

    # Plain text bar
    text = cli._build_status_bar_text(width=80)
    assert text.startswith("★ agy-flash")
    assert "ctx -- · 5h 70%" in text
    assert "w 48%" in text

    # Fragments bar
    frags = cli._get_status_bar_fragments()
    full_str = "".join(t for _, t in frags)
    assert "★" in full_str
    assert "agy-flash" in full_str
    assert "ctx -- · 5h 70%" in full_str
    assert "w 48%" in full_str


def test_status_bar_limits_respects_account_id(monkeypatch):
    """Multiple accounts under the same provider and model cache separately by account_id."""
    clear_limits_cache()
    snap_acc1 = _snapshot("antigravity", "quota", [AccountUsageWindow(label="Gemini Models (weekly)", used_percent=5.0)], [])
    snap_acc2 = _snapshot("antigravity", "quota", [AccountUsageWindow(label="Gemini Models (weekly)", used_percent=95.0)], [])

    _limits_cache["antigravity:agy-flash:acc-1"] = (float("inf"), snap_acc1)
    _limits_cache["antigravity:agy-flash:acc-2"] = (float("inf"), snap_acc2)

    hit1 = get_cached_account_limits("antigravity", "agy-flash", account_id="acc-1")
    hit2 = get_cached_account_limits("antigravity", "agy-flash", account_id="acc-2")

    assert hit1 is snap_acc1
    assert hit2 is snap_acc2

    _, text1 = format_limits_compact(hit1, model="agy-flash")
    _, text2 = format_limits_compact(hit2, model="agy-flash")

    assert "95%" in text1
    assert "5%" in text2

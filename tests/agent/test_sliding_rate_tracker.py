"""Unit tests for agent.sliding_rate_tracker."""

from datetime import datetime, timezone
import time
from unittest.mock import patch

from agent.sliding_rate_tracker import (
    DEFAULT_PROVIDER_LIMITS,
    get_sliding_details,
    get_sliding_usage,
    get_sliding_windows,
    record_turn,
    resolve_provider_limits,
)


def test_resolve_provider_limits():
    # Built-in defaults
    nvidia_limits = resolve_provider_limits("nvidia")
    assert nvidia_limits["rpm"] == 40
    assert nvidia_limits["window"] == 60.0

    gemini_limits = resolve_provider_limits("gemini")
    assert gemini_limits["rpm"] == 15

    # Config override
    with patch("shiina_cli.config.load_config", return_value={"providers": {"nvidia": {"max_rpm": 60}}}):
        overridden = resolve_provider_limits("nvidia")
        assert overridden["rpm"] == 60


def test_sliding_window_turn_tracking(tmp_path):
    cache_file = tmp_path / "sliding_rate_tracker.json"
    with patch("agent.sliding_rate_tracker._get_cache_file", return_value=cache_file):
        now = 1_000_000.0

        # Initially 0 turns
        usage0 = get_sliding_usage("nvidia", now=now)
        assert usage0.used_requests == 0
        assert usage0.limit_requests == 40
        assert usage0.remaining_requests == 40
        assert usage0.avail_percent == 100.0
        assert usage0.reset_at is None

        # Record 3 turns at T=1000000, 1000010, 1000020
        record_turn("nvidia", tokens=100, timestamp=now)
        record_turn("nvidia", tokens=250, timestamp=now + 10.0)
        record_turn("nvidia", tokens=150, timestamp=now + 20.0)

        # Check usage at T=1000025 (all 3 in window)
        usage1 = get_sliding_usage("nvidia", now=now + 25.0)
        assert usage1.used_requests == 3
        assert usage1.remaining_requests == 37
        assert usage1.used_tokens == 500
        # Oldest request was at now (1_000_000.0). In a 60s window, it expires at 1_000_060.0.
        # At T=1_000_025.0, remaining seconds = 35.0s
        assert abs(usage1.reset_seconds - 35.0) < 0.1
        assert usage1.reset_at == datetime.fromtimestamp(now + 60.0, tz=timezone.utc)
        assert round(usage1.avail_percent, 1) == round(((40 - 3) / 40) * 100.0, 1)

        # Advance time to T=1000065 (first request expired, only 2 remain)
        usage2 = get_sliding_usage("nvidia", now=now + 65.0)
        assert usage2.used_requests == 2
        assert usage2.remaining_requests == 38
        assert usage2.used_tokens == 400
        # Oldest now is T=1000010. Expires at T=1000070.
        # At T=1000065, remaining seconds = 5.0s
        assert abs(usage2.reset_seconds - 5.0) < 0.1

        # Advance time to T=1000100 (all expired)
        usage3 = get_sliding_usage("nvidia", now=now + 100.0)
        assert usage3.used_requests == 0
        assert usage3.remaining_requests == 40
        assert usage3.avail_percent == 100.0


def test_get_sliding_windows_formatting(tmp_path):
    cache_file = tmp_path / "sliding_rate_tracker.json"
    with patch("agent.sliding_rate_tracker._get_cache_file", return_value=cache_file):
        now = 1_000_000.0
        record_turn("nvidia", tokens=200, timestamp=now)
        record_turn("nvidia", tokens=300, timestamp=now + 15.0)

        with patch("time.time", return_value=now + 20.0):
            windows = get_sliding_windows("nvidia")
            assert len(windows) >= 1
            rpm_win = windows[0]
            assert rpm_win.label == "RPM (Turns)"
            assert rpm_win.used_percent == (2 / 40) * 100.0
            assert "2/40 turns in 60s (38 left)" in rpm_win.detail
            assert rpm_win.reset_at is not None

            details = get_sliding_details("nvidia")
            assert any("40 RPM rolling window" in d for d in details)
            assert any("2/40 turns used" in d for d in details)


def test_reusable_with_other_providers(tmp_path):
    cache_file = tmp_path / "sliding_rate_tracker.json"
    with patch("agent.sliding_rate_tracker._get_cache_file", return_value=cache_file):
        now = 1_000_000.0
        record_turn("gemini", tokens=500, timestamp=now)
        record_turn("gemini", tokens=500, timestamp=now + 5.0)

        usage = get_sliding_usage("gemini", now=now + 10.0)
        assert usage.provider == "gemini"
        assert usage.used_requests == 2
        assert usage.limit_requests == 15  # 15 RPM for free gemini
        assert usage.remaining_requests == 13

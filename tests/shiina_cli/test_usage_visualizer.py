from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from agent.account_usage import AccountUsageSnapshot, AccountUsageWindow
from shiina_cli.usage_visualizer import (
    ProviderAccountUsage,
    build_usage_dashboard,
    discover_quota_providers,
    format_countdown,
    render_line_gauge,
    shorten_label,
)


def test_render_line_gauge_percentages():
    # 100% available -> all characters bold green
    gauge_100 = render_line_gauge(100.0, width=10)
    assert "[bold green]" in gauge_100
    assert "\u2501" * 10 in gauge_100
    assert "\u2500" not in gauge_100

    # 50% available -> 5 bold green, 5 dim light line
    gauge_50 = render_line_gauge(50.0, width=10)
    assert "[bold green]" in gauge_50
    assert "\u2501" * 5 in gauge_50
    assert "\u2500" * 5 in gauge_50

    # 10% available -> bold yellow
    gauge_10 = render_line_gauge(10.0, width=10)
    assert "[bold yellow]" in gauge_10
    assert "\u2501" * 1 in gauge_10

    # 0% available -> bold red exhausted line
    gauge_0 = render_line_gauge(0.0, width=10)
    assert "[bold red]" in gauge_0
    assert "\u2500" * 10 in gauge_0


def test_format_countdown():
    assert format_countdown(None) == ""

    now = datetime.now(timezone.utc)
    # Expired / in the past
    past = now - timedelta(minutes=5)
    assert format_countdown(past) == "now"

    # Minutes only
    in_30m = now + timedelta(minutes=30, seconds=10)
    assert format_countdown(in_30m) == "30m"

    # Hours and minutes
    in_2h_15m = now + timedelta(hours=2, minutes=15, seconds=30)
    assert format_countdown(in_2h_15m) == "2h 15m"

    # Days and hours
    in_3d_5h = now + timedelta(days=3, hours=5, minutes=10)
    assert format_countdown(in_3d_5h) == "3d 5h"


def test_shorten_label():
    assert shorten_label("Gemini Models (weekly)") == "Gemini (weekly)"
    assert shorten_label("Gemini Models (5h)") == "Gemini (5h)"
    assert shorten_label("Claude and GPT models (weekly)") == "Claude/GPT (weekly)"
    assert shorten_label("Claude and GPT models (5h)") == "Claude/GPT (5h)"
    assert shorten_label("Custom Window") == "Custom Window"


def test_discover_quota_providers(monkeypatch):
    monkeypatch.setattr(
        "shiina_cli.auth._load_auth_store",
        lambda: {"credential_pool": {"xkiro": {}, "cline": {}, "gemini": {}}},
    )
    monkeypatch.setattr(
        "shiina_cli.usage_visualizer.load_pool",
        lambda p: MagicMock(entries=lambda: [MagicMock()]),
    )

    quota_cands, other_cands = discover_quota_providers(active_provider="antigravity")
    # Antigravity prioritized
    assert "antigravity" in quota_cands
    assert quota_cands[0] == "antigravity"
    # xkiro and cline are supported quota providers
    assert "xkiro" in quota_cands
    assert "cline" in quota_cands
    # gemini is API-key only
    other_names = [p for p, _ in other_cands]
    assert "gemini" in other_names


def test_build_usage_dashboard_rendering():
    now = datetime.now(timezone.utc)
    reset_5h = now + timedelta(hours=2, minutes=10)
    reset_weekly = now + timedelta(days=3, hours=19)

    snapshots = {
        "antigravity": AccountUsageSnapshot(
            provider="antigravity",
            source="quota_api",
            fetched_at=now,
            title="Google Antigravity",
            plan=None,
            windows=(
                AccountUsageWindow(label="Gemini Models (5h)", used_percent=45.0, reset_at=reset_5h),
                AccountUsageWindow(label="Gemini Models (weekly)", used_percent=55.0, reset_at=reset_weekly),
                AccountUsageWindow(label="Claude and GPT models (weekly)", used_percent=100.0, reset_at=reset_weekly),
            ),
            details=("Some details",),
            unavailable_reason=None,
        ),
        "xkiro": AccountUsageSnapshot(
            provider="xkiro",
            source="usage_api",
            fetched_at=now,
            title="xKiro",
            plan=None,
            windows=(
                AccountUsageWindow(
                    label="Daily Free Tokens",
                    used_percent=0.0,
                    reset_at=now + timedelta(hours=11),
                    detail="500,000 of 500,000 free tokens remaining",
                ),
            ),
            details=("Wallet balance: $0.00", "User: test@example.com"),
            unavailable_reason=None,
        ),
        "cline": AccountUsageSnapshot(
            provider="cline",
            source="balance_api",
            fetched_at=now,
            title="Cline",
            plan=None,
            windows=(
                AccountUsageWindow(label="Cline Balance", used_percent=None, reset_at=None, detail="447,388 credits available"),
            ),
            details=("Credits balance: 447,388 credits", "User: cline@example.com"),
            unavailable_reason=None,
        ),
    }

    other_providers = [("gemini", 9), ("mistral", 2)]

    panel = build_usage_dashboard(
        snapshots,
        active_provider="antigravity",
        other_providers=other_providers,
        console_width=80,
    )

    rendered_text = str(panel.renderable)

    # Check active provider badge
    assert "★ Google Antigravity" in rendered_text
    assert "(active model)" in rendered_text

    # Check gauges and percentages
    assert "55%" in rendered_text
    assert "45%" in rendered_text
    assert "0%" in rendered_text
    assert "resets 2h" in rendered_text
    assert "resets 3d" in rendered_text

    # Check xKiro free tier
    assert "✦ xKiro" in rendered_text
    assert "(Daily Free Tier)" in rendered_text
    assert "Daily Free Tokens" in rendered_text
    assert "100%" in rendered_text

    # Check Cline credits
    assert "✦ Cline" in rendered_text
    assert "447,388 credits available" in rendered_text

    # Check other providers footer
    assert "Other connected providers:" in rendered_text
    assert "gemini (9 keys)" in rendered_text
    assert "mistral (2 keys)" in rendered_text


def test_cli_show_usage_calls_visual_dashboard(capsys):
    from shiina_cli.cli_info_mixin import CLIInfoMixin
    from rich.console import Console

    class TestCLI(CLIInfoMixin):
        def __init__(self):
            self.provider = "antigravity"
            self.model = "agy-flash"
            self.agent = None
            self.base_url = None
            self.api_key = None
            self.verbose = False
            self.console = Console(force_terminal=True, color_system="truecolor", width=80)

        def _agent_or_self(self, attr):
            return getattr(self, attr, None)

        def _print_nous_credits_block(self):
            return False

        def _print_usage_cta(self):
            pass

        def _console_print(self, *args, **kwargs):
            self.console.print(*args, **kwargs)

    cli = TestCLI()

    now = datetime.now(timezone.utc)
    mock_snap = AccountUsageSnapshot(
        provider="antigravity",
        source="quota_api",
        fetched_at=now,
        title="Google Antigravity",
        plan=None,
        windows=(
            AccountUsageWindow(label="Gemini Models (5h)", used_percent=50.0, reset_at=now + timedelta(hours=2)),
        ),
        details=(),
        unavailable_reason=None,
    )

    with patch("shiina_cli.usage_visualizer.fetch_all_provider_usage", return_value={"antigravity": mock_snap}):
        cli._show_usage()

    captured = capsys.readouterr().out
    assert "Provider Quotas & Usage Limits" in captured
    assert "Google Antigravity" in captured
    assert "50%" in captured


def test_build_usage_dashboard_multi_account_cline():
    from shiina_cli.usage_visualizer import ProviderAccountUsage

    now = datetime.now(timezone.utc)
    acc1 = ProviderAccountUsage(
        snapshot=AccountUsageSnapshot(
            provider="cline",
            source="balance_api",
            fetched_at=now,
            title="Cline",
            plan=None,
            windows=(AccountUsageWindow(label="Cline Balance", used_percent=None, reset_at=None, detail="447,388 credits available"),),
            details=("Credits balance: 447,388 credits", "User: da velonio (daryllvelonio2@gmail.com)"),
            unavailable_reason=None,
        ),
        label="2",
        credential_id="id1",
        priority=0,
        is_current=True,
    )
    acc2 = ProviderAccountUsage(
        snapshot=AccountUsageSnapshot(
            provider="cline",
            source="balance_api",
            fetched_at=now,
            title="Cline",
            plan=None,
            windows=(AccountUsageWindow(label="Cline Balance", used_percent=None, reset_at=None, detail="500,000 credits available"),),
            details=("Credits balance: 500,000 credits", "User: Daryll Velonio (daryllvelonio9@gmail.com)"),
            unavailable_reason=None,
        ),
        label="9",
        credential_id="id2",
        priority=1,
        is_current=False,
    )
    acc3 = ProviderAccountUsage(
        snapshot=AccountUsageSnapshot(
            provider="cline",
            source="balance_api",
            fetched_at=now,
            title="Cline",
            plan=None,
            windows=(AccountUsageWindow(label="Cline Balance", used_percent=None, reset_at=None, detail="500,000 credits available"),),
            details=("Credits balance: 500,000 credits", "User: daryll velonio (mahiruushiinaaaaa@gmail.com)"),
            unavailable_reason=None,
        ),
        label="mahiru",
        credential_id="id3",
        priority=2,
        is_current=False,
    )

    panel = build_usage_dashboard(
        {"cline": [acc1, acc2, acc3]},
        console_width=86,
    )
    rendered = str(panel.renderable)

    # Multi-account header with summed total credits
    assert "✦ Cline" in rendered
    assert "3 accounts" in rendered
    assert "1,447,388 total credits" in rendered

    # Individual accounts
    assert "#2" in rendered
    assert "←" in rendered  # active marker
    assert "447,388 cred" in rendered
    assert "daryllvelonio2@gmail.com" in rendered

    assert "#9" in rendered
    assert "500,000 cred" in rendered
    assert "daryllvelonio9@gmail.com" in rendered

    assert "#mahiru" in rendered
    assert "mahiruushiinaaaaa@gmail.com" in rendered


def test_build_usage_dashboard_nvidia_rendering():
    now = datetime.now(timezone.utc)
    acc1 = ProviderAccountUsage(
        snapshot=AccountUsageSnapshot(
            provider="nvidia",
            source="models_api",
            fetched_at=now,
            title="NVIDIA NIM Account",
            plan="Free Trial Tier",
            windows=(AccountUsageWindow(label="NVIDIA NIM", used_percent=None, detail="Active • Free Trial (Dynamic Rate Limits)"),),
            details=("Access: Free Trial Tier", "Models: 82 catalog models available"),
            unavailable_reason=None,
        ),
        label="2",
        credential_id="id1",
        priority=0,
        is_current=True,
    )
    acc2 = ProviderAccountUsage(
        snapshot=AccountUsageSnapshot(
            provider="nvidia",
            source="models_api",
            fetched_at=now,
            title="NVIDIA NIM Account",
            plan="Free Trial Tier",
            windows=(AccountUsageWindow(label="NVIDIA NIM", used_percent=None, detail="Active • Free Trial (Dynamic Rate Limits)"),),
            details=("Access: Free Trial Tier", "Models: 82 catalog models available"),
            unavailable_reason=None,
        ),
        label="main",
        credential_id="id2",
        priority=1,
        is_current=False,
    )

    panel = build_usage_dashboard(
        {"nvidia": [acc1, acc2]},
        console_width=86,
    )
    rendered = str(panel.renderable)

    assert "✦ NVIDIA NIM" in rendered
    assert "Free Trial • 2 accounts" in rendered
    assert "#2" in rendered
    assert "←" in rendered
    assert "Active" in rendered
    assert "#main" in rendered



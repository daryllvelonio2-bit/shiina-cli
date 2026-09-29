from datetime import datetime, timezone

from agent.account_usage import (
    AccountUsageSnapshot,
    AccountUsageWindow,
    fetch_account_usage,
    render_account_usage_lines,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payload)


class _RoutingClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payloads[url])


def test_fetch_account_usage_codex(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_codex_runtime_credentials",
        lambda refresh_if_expiring=True: {
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "access-token",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage._read_codex_tokens",
        lambda: {"tokens": {"account_id": "acct_123"}},
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=15.0: _Client(
            {
                "plan_type": "pro",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 15,
                        "reset_at": 1_900_000_000,
                        "limit_window_seconds": 18000,
                    },
                    "secondary_window": {
                        "used_percent": 40,
                        "reset_at": 1_900_500_000,
                        "limit_window_seconds": 604800,
                    },
                },
                "credits": {"has_credits": True, "balance": 12.5},
            }
        ),
    )

    snapshot = fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.plan == "Pro"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[0].used_percent == 15.0
    assert snapshot.windows[0].reset_at == datetime.fromtimestamp(1_900_000_000, tz=timezone.utc)
    assert "Credits balance: $12.50" in snapshot.details


def test_render_account_usage_lines_includes_reset_and_provider():
    snapshot = AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime.now(timezone.utc),
        plan="Pro",
        windows=(
            AccountUsageWindow(
                label="Session",
                used_percent=25,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
        details=("Credits balance: $9.99",),
    )
    lines = render_account_usage_lines(snapshot)

    assert lines[0] == "📈 Account limits"
    assert "openai-codex (Pro)" in lines[1]
    assert "Session: 75% remaining (25% used)" in lines[2]
    assert "Credits balance: $9.99" in lines[3]


def test_fetch_account_usage_openrouter_uses_limit_remaining_and_ignores_deprecated_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 300.0, "total_usage": 10.92}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": 100.0,
                        "limit_remaining": 70.0,
                        "limit_reset": "monthly",
                        "usage": 12.5,
                        "usage_daily": 0.5,
                        "usage_weekly": 2.0,
                        "usage_monthly": 8.0,
                        "rate_limit": {"requests": -1, "interval": "10s"},
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == (
        AccountUsageWindow(
            label="API key quota",
            used_percent=30.0,
            detail="$70.00 of $100.00 remaining • resets monthly",
        ),
    )
    assert "Credits balance: $289.08" in snapshot.details
    assert "API key usage: $12.50 total • $0.50 today • $2.00 this week • $8.00 this month" in snapshot.details
    assert all("-1 requests / 10s" not in line for line in render_account_usage_lines(snapshot))


def test_fetch_account_usage_openrouter_omits_quota_window_when_key_has_no_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 100.0, "total_usage": 25.5}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": None,
                        "limit_remaining": None,
                        "usage": 25.5,
                        "usage_daily": 1.25,
                        "usage_weekly": 4.5,
                        "usage_monthly": 18.0,
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")
    assert snapshot is not None
    assert snapshot.windows == ()
    assert "Credits balance: $74.50" in snapshot.details
    assert "API key usage: $25.50 total • $1.25 today • $4.50 this week • $18.00 this month" in snapshot.details


def test_fetch_account_usage_antigravity(monkeypatch):
    class _PostClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            return _Response({
                "groups": [
                    {
                        "displayName": "Gemini Models",
                        "buckets": [
                            {
                                "window": "weekly",
                                "remainingFraction": 0.6899,
                                "resetTime": "2026-10-01T08:01:06Z",
                            },
                            {
                                "window": "5h",
                                "remainingFraction": 1.0,
                                "resetTime": None,
                            },
                        ],
                    },
                    {
                        "displayName": "Claude and GPT models",
                        "buckets": [
                            {
                                "window": "weekly",
                                "remainingFraction": 0.0,
                                "disabled": True,
                                "resetTime": "2026-09-29T16:47:24Z",
                            }
                        ],
                    },
                ],
                "description": "Quota shared within groups.",
            })

    monkeypatch.setattr(
        "agent.antigravity_client.GoogleOAuthTokenManager.get_access_token",
        lambda self: "fake-oauth-token",
    )
    monkeypatch.setattr("agent.account_usage.httpx.Client", lambda timeout=10.0: _PostClient())

    snap = fetch_account_usage("antigravity", model="gemini-3.8-flash-high")
    assert snap is not None
    assert snap.provider == "antigravity"
    assert len(snap.windows) == 3
    # First window is Gemini weekly
    w0 = snap.windows[0]
    assert w0.label == "Gemini Models (weekly)"
    assert abs(w0.used_percent - 31.01) < 0.01
    assert w0.reset_at == datetime(2026, 10, 1, 8, 1, 6, tzinfo=timezone.utc)
    # 5h window
    w1 = snap.windows[1]
    assert w1.label == "Gemini Models (5h)"
    assert w1.used_percent == 0.0
    assert w1.reset_at is None
    # Claude exhausted
    w2 = snap.windows[2]
    assert w2.label == "Claude and GPT models (weekly)"
    assert w2.used_percent == 100.0
    assert w2.detail == "quota exhausted (disabled)"
    assert "Quota shared within groups." in snap.details


def test_fetch_account_usage_xkiro(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "xkiro",
            "base_url": "https://api.xkiro.com/v1",
            "api_key": "sk-test-xkiro",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({
            "free_tokens": {
                "used_today": 100000,
                "limit_per_day": 500000,
                "remaining": 400000,
            },
            "wallet": {"balance_usd": "2.50"},
            "user": {"name": "Test User", "email": "test@example.com"},
        }),
    )

    snap = fetch_account_usage("xkiro")
    assert snap is not None
    assert snap.provider == "xkiro"
    assert len(snap.windows) == 1
    assert snap.windows[0].label == "Daily Free Tokens"
    assert snap.windows[0].used_percent == 20.0
    assert "400,000 of 500,000 free tokens remaining" in snap.windows[0].detail
    assert "Wallet balance: $2.50" in snap.details
    assert "User: Test User (test@example.com)" in snap.details


def test_fetch_account_usage_kilocode(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "kilocode",
            "base_url": "https://api.kilo.ai/api/gateway",
            "api_key": "kilo-test-key",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _Client({
            "microdollars_used": 250000,
            "total_microdollars_acquired": 1000000,
            "next_credit_expiration_at": "2026-12-31T23:59:59Z",
            "google_user_name": "Kilo User",
            "google_user_email": "kilo@example.com",
        }),
    )

    snap = fetch_account_usage("kilocode")
    assert snap is not None
    assert snap.provider == "kilocode"
    assert len(snap.windows) == 1
    assert snap.windows[0].label == "Kilo Credits"
    assert snap.windows[0].used_percent == 25.0
    assert "$0.75 of $1.00 remaining" in snap.windows[0].detail


def test_fetch_account_usage_cline(monkeypatch):
    class _ClineClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "users/me" in url:
                return _Response({"data": {"id": "usr-123", "displayName": "Cline User", "email": "cline@test.com"}})
            return _Response({"data": {"balance": 500000}})

    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "cline",
            "base_url": "https://api.cline.bot/api/v1",
            "api_key": "sk-cline-test",
        },
    )
    monkeypatch.setattr("agent.account_usage.httpx.Client", lambda timeout=10.0: _ClineClient())

    snap = fetch_account_usage("cline")
    assert snap is not None
    assert snap.provider == "cline"
    assert len(snap.windows) == 1
    assert snap.windows[0].label == "Cline Balance"
    assert "500,000 credits available" in snap.windows[0].detail
    assert "User: Cline User (cline@test.com)" in snap.details


def test_fetch_account_usage_nvidia(monkeypatch):
    class _NvidiaClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return _Response({"data": [{"id": "meta/llama-3.2-11b"}, {"id": "mistralai/mistral-nemotron"}]})

    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "nvidia",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "nvapi-test",
        },
    )
    monkeypatch.setattr("agent.account_usage.httpx.Client", lambda timeout=6.0: _NvidiaClient())

    snap = fetch_account_usage("nvidia")
    assert snap is not None
    assert snap.provider == "nvidia"
    assert len(snap.windows) >= 1
    assert snap.windows[0].label == "RPM (Turns)"
    assert "turns in 60s" in snap.windows[0].detail
    assert any("2 catalog models available" in d for d in snap.details)




"""Sliding-window local rate limit and turn tracker for inference providers.

Tracks API requests and tokens across rolling time windows (default: 60s for RPM/TPM),
calculating remaining capacity, turn usage, and exact countdown to capacity reset.
Designed to be reusable across providers (NVIDIA NIM, Gemini, Groq, Ollama, etc.)
where upstream rate-limit headers are absent or trial tiers have known RPM limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default limits (RPM, TPM, Window in seconds) for known trial / free tiers
DEFAULT_PROVIDER_LIMITS: dict[str, dict[str, Any]] = {
    "nvidia": {"rpm": 40, "tpm": 40_000, "window": 60.0, "label": "RPM (Turns)"},
    "custom:nvidia": {"rpm": 40, "tpm": 40_000, "window": 60.0, "label": "RPM (Turns)"},
    "groq": {"rpm": 30, "tpm": 30_000, "window": 60.0, "label": "RPM (Turns)"},
    "gemini": {"rpm": 15, "tpm": 1_000_000, "window": 60.0, "label": "RPM (Turns)"},
    "codestral": {"rpm": 30, "tpm": 0, "window": 60.0, "label": "RPM (Turns)"},
    "openrouter": {"rpm": 20, "tpm": 0, "window": 60.0, "label": "RPM (Turns)"},
}

_DEFAULT_FALLBACK = {"rpm": 40, "tpm": 0, "window": 60.0, "label": "RPM (Turns)"}

_TRACKER_LOCK = threading.Lock()
_MEM_CACHE: dict[str, list[dict[str, Any]]] = {}


def _get_cache_file() -> Path:
    """Resolve cache file path in ~/.shiina/cache/sliding_rate_tracker.json."""
    try:
        from shiina_cli.config import get_shiina_home
        cache_dir = get_shiina_home() / "cache"
    except Exception:
        cache_dir = Path.home() / ".shiina" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "sliding_rate_tracker.json"


def clear_tracker_cache() -> None:
    """Clear in-memory and on-disk tracker records (primarily for tests)."""
    with _TRACKER_LOCK:
        _MEM_CACHE.clear()
        try:
            cache_file = _get_cache_file()
            if cache_file.exists():
                cache_file.unlink()
        except Exception:
            pass


def _load_tracker_data() -> dict[str, list[dict[str, Any]]]:
    """Load recent records from disk or return current in-memory cache."""
    cache_file = _get_cache_file()
    if not cache_file.exists():
        return {}
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_tracker_data(data: dict[str, list[dict[str, Any]]]) -> None:
    """Atomic write to cache file."""
    cache_file = _get_cache_file()
    temp_file = cache_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        temp_file.replace(cache_file)
    except Exception as exc:
        logger.debug("Failed saving sliding rate tracker cache: %s", exc)


def _clean_expired(records: list[dict[str, Any]], now: float, max_age: float = 300.0) -> list[dict[str, Any]]:
    """Prune timestamps older than max_age."""
    return [r for r in records if isinstance(r, dict) and (now - float(r.get("ts", 0))) <= max_age]


def resolve_provider_limits(provider: str) -> dict[str, Any]:
    """Resolve RPM/TPM limits for a provider, checking config.yaml then built-in defaults."""
    norm = str(provider or "").strip().lower()
    limits = dict(DEFAULT_PROVIDER_LIMITS.get(norm) or _DEFAULT_FALLBACK)

    # Check user config overrides if available
    try:
        from shiina_cli.config import load_config
        cfg = load_config()
        providers_cfg = cfg.get("providers", {})
        if isinstance(providers_cfg, dict):
            entry = providers_cfg.get(norm) or providers_cfg.get(norm.replace("custom:", ""))
            if isinstance(entry, dict):
                for rpm_key in ("max_rpm", "rate_limit_rpm", "rpm"):
                    if entry.get(rpm_key):
                        limits["rpm"] = int(entry[rpm_key])
                        break
                for tpm_key in ("max_tpm", "rate_limit_tpm", "tpm"):
                    if entry.get(tpm_key):
                        limits["tpm"] = int(entry[tpm_key])
                        break
    except Exception:
        pass

    return limits


def record_turn(
    provider: str,
    tokens: int = 0,
    model: str = "",
    credential_id: str = "",
    timestamp: Optional[float] = None,
) -> None:
    """Record an API turn/request for sliding-window rate tracking.

    Args:
        provider: Provider identifier (e.g. 'nvidia', 'gemini').
        tokens: Tokens consumed in this turn (input + output), if known.
        model: Model name.
        credential_id: Specific credential/account ID in the provider pool.
        timestamp: Unix epoch timestamp (defaults to time.time()).
    """
    if not provider:
        return
    norm_p = provider.strip().lower()
    now = float(timestamp or time.time())
    entry = {
        "ts": now,
        "tokens": max(0, int(tokens or 0)),
        "model": str(model or ""),
        "cred": str(credential_id or ""),
    }

    with _TRACKER_LOCK:
        data = _load_tracker_data()
        records = _clean_expired(data.get(norm_p, []), now)
        records.append(entry)
        data[norm_p] = records
        _MEM_CACHE[norm_p] = records
        _save_tracker_data(data)


@dataclass(frozen=True)
class SlidingUsageWindow:
    """Sliding-window consumption and reset metrics."""
    provider: str
    used_requests: int
    limit_requests: int
    remaining_requests: int
    used_tokens: int
    limit_tokens: int
    reset_seconds: float
    reset_at: Optional[datetime]
    window_seconds: float = 60.0

    @property
    def used_percent(self) -> float:
        if self.limit_requests <= 0:
            return 0.0
        return max(0.0, min(100.0, (self.used_requests / self.limit_requests) * 100.0))

    @property
    def avail_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


def get_sliding_usage(
    provider: str,
    credential_id: Optional[str] = None,
    window_seconds: Optional[float] = None,
    now: Optional[float] = None,
) -> SlidingUsageWindow:
    """Calculate sliding-window turn usage, remaining capacity, and reset countdown."""
    norm_p = str(provider or "").strip().lower()
    limits = resolve_provider_limits(norm_p)
    win_sec = float(window_seconds or limits.get("window", 60.0))
    limit_rpm = int(limits.get("rpm", 40))
    limit_tpm = int(limits.get("tpm", 0))

    cur_time = float(now or time.time())

    with _TRACKER_LOCK:
        data = _load_tracker_data()
        records = data.get(norm_p, [])

    # Filter to records within the sliding window
    in_window: list[dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        ts = float(r.get("ts", 0))
        if (cur_time - ts) <= win_sec and (cur_time - ts) >= 0:
            if credential_id:
                cred = str(r.get("cred", ""))
                # If record has a credential ID attached, match it; if record is unlabelled, count it
                if cred and cred != credential_id:
                    continue
            in_window.append(r)

    used_req = len(in_window)
    used_tok = sum(int(r.get("tokens", 0) or 0) for r in in_window)
    rem_req = max(0, limit_rpm - used_req)

    if in_window:
        oldest_ts = min(float(r.get("ts", cur_time)) for r in in_window)
        reset_sec = max(0.0, (oldest_ts + win_sec) - cur_time)
        reset_at = datetime.fromtimestamp(oldest_ts + win_sec, tz=timezone.utc)
    else:
        reset_sec = 0.0
        reset_at = None

    return SlidingUsageWindow(
        provider=norm_p,
        used_requests=used_req,
        limit_requests=limit_rpm,
        remaining_requests=rem_req,
        used_tokens=used_tok,
        limit_tokens=limit_tpm,
        reset_seconds=reset_sec,
        reset_at=reset_at,
        window_seconds=win_sec,
    )


def get_sliding_windows(
    provider: str,
    credential_id: Optional[str] = None,
) -> list[Any]:
    """Generate AccountUsageWindow objects for integration with AccountUsageSnapshot."""
    from agent.account_usage import AccountUsageWindow

    usage = get_sliding_usage(provider, credential_id=credential_id)
    limits = resolve_provider_limits(provider)
    label = limits.get("label", "RPM (Turns)")

    windows = [
        AccountUsageWindow(
            label=label,
            used_percent=usage.used_percent,
            reset_at=usage.reset_at,
            detail=f"{usage.used_requests}/{usage.limit_requests} turns in 60s ({usage.remaining_requests} left)",
        )
    ]

    if usage.used_tokens > 0 or usage.limit_tokens > 0:
        tpm_used_pct = ((usage.used_tokens / usage.limit_tokens) * 100.0) if usage.limit_tokens > 0 else None
        windows.append(
            AccountUsageWindow(
                label="TPM (Tokens)",
                used_percent=tpm_used_pct,
                reset_at=usage.reset_at,
                detail=f"{usage.used_tokens:,} tokens in 60s",
            )
        )

    return windows


def get_sliding_details(provider: str, credential_id: Optional[str] = None) -> list[str]:
    """Helper returning human-readable details lines for rate tracker state."""
    usage = get_sliding_usage(provider, credential_id=credential_id)
    lines = [
        f"Rate limits: {usage.limit_requests} RPM rolling window (60s)",
    ]
    if usage.used_requests > 0:
        lines.append(f"Sliding window: {usage.used_requests}/{usage.limit_requests} turns used, {usage.remaining_requests} remaining")
    else:
        lines.append("Sliding window: 0 turns used in last 60s (full capacity)")
    return lines

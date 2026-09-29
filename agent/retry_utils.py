"""Retry utilities — jittered backoff for decorrelated retries.

Jittered delays (vs. fixed exponential) prevent thundering-herd retry spikes
when many sessions hit the same rate-limited provider concurrently.
"""

import random
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

# Monotonic counter for jitter-seed uniqueness within a process; locked
# because concurrent gateway sessions retry simultaneously.
_jitter_counter = 0
_jitter_lock = threading.Lock()

# Z.AI Coding Plan's GLM-5.2 endpoint often returns 429 code 1305 ("service may be
# temporarily overloaded"). Short retries hammer the same window, so after
# ``_ZAI_CODING_OVERLOAD_SHORT_ATTEMPTS`` normal retries the wait widens progressively;
# the cap stays interactive-friendly (a TUI message should fail visibly in minutes).
# The short count is shared by ``adaptive_rate_limit_backoff`` and
# ``zai_coding_overload_retry_ceiling`` so the two cannot silently desync.
_ZAI_CODING_OVERLOAD_LONG_BACKOFF = (30.0, 60.0, 90.0, 120.0)
_ZAI_CODING_OVERLOAD_SHORT_ATTEMPTS = 3


def parse_duration_string(text: str) -> Optional[float]:
    """Parse duration strings like '2.054s', '5m32s', '2 hours 5 minutes', '500ms' into seconds."""
    if not text:
        return None
    raw = str(text).strip()
    try:
        val = float(raw)
        return max(0.0, val)
    except ValueError:
        pass

    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)",
        re.IGNORECASE,
    )
    total = 0.0
    found_any = False
    for num_str, unit in pattern.findall(raw):
        u = unit.lower()
        val = float(num_str)
        if u in ("hours", "hour", "hrs", "hr", "h"):
            total += val * 3600.0
            found_any = True
        elif u in ("minutes", "minute", "mins", "min", "m"):
            total += val * 60.0
            found_any = True
        elif u in ("milliseconds", "millis", "ms"):
            total += val / 1000.0
            found_any = True
        elif u in ("seconds", "second", "secs", "sec", "s"):
            total += val
            found_any = True

    return total if found_any else None


def parse_retry_after_seconds(value_or_headers: Any) -> Optional[float]:
    """Parse a ``Retry-After`` value (numeric / HTTP-date / duration) or a headers mapping (both casings tried) into
    seconds, clamped at 0.0; None when absent / unparseable."""
    raw = value_or_headers
    if raw is not None and not isinstance(raw, (str, int, float)):
        getter = getattr(raw, "get", None)
        if not callable(getter):
            return None
        candidate_keys = (
            "Retry-After", "retry-after",
            "x-ratelimit-reset", "X-RateLimit-Reset",
            "x-ratelimit-reset-requests", "X-RateLimit-Reset-Requests",
            "x-ratelimit-reset-tokens", "X-RateLimit-Reset-Tokens",
            "ratelimit-reset", "RateLimit-Reset",
        )
        for k in candidate_keys:
            try:
                val = getter(k)
                if val is not None:
                    raw = val
                    break
            except Exception:
                pass
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        numeric = float(raw)
        if numeric >= 1_000_000_000:
            return max(0.0, numeric - time.time())
        return max(0.0, numeric)
    text = str(raw).strip()
    if not text:
        return None
    try:
        numeric = float(text)
        if numeric >= 1_000_000_000:
            return max(0.0, numeric - time.time())
        return max(0.0, numeric)
    except (TypeError, ValueError):
        pass
    dur = parse_duration_string(text)
    if dur is not None:
        return max(0.0, dur)
    # HTTP-date form (RFC 7231): seconds until that instant, clamped at 0.
    try:
        when = parsedate_to_datetime(text)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        pass
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        pass
    return None


# Free-text "reset" grammars providers put in error bodies, tried in order. One table so the
# conversation loop's error context and the credential pool's cooldown agree on the same wait.
_QUOTA_RESET_DELAY_RE = re.compile(r"quotaResetDelay[:\s\"]+(\d+(?:\.\d+)?)(ms|s)", re.IGNORECASE)
_DURATION_PATTERN_STR = r"((?:\d+(?:\.\d+)?\s*[a-zA-Z]+\s*)+)"
_RETRY_AFTER_OR_IN_RE = re.compile(
    rf"(?:please\s+)?(?:try\s+again|retry)\s+(?:after|in)\s+{_DURATION_PATTERN_STR}",
    re.IGNORECASE,
)
_WAIT_RE = re.compile(
    rf"(?:please\s+)?wait\s+{_DURATION_PATTERN_STR}",
    re.IGNORECASE,
)
_RESETS_IN_RE = re.compile(
    rf"resets?\s+(?:in|after)\s+{_DURATION_PATTERN_STR}",
    re.IGNORECASE,
)
_RESET_OR_RETRY_AT_ISO_RE = re.compile(
    r"(?:resets?|retry)\s+(?:at|after)\s+([0-9]{4}-[0-9]{2}-[0-9]{2}[T\s][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?)",
    re.IGNORECASE,
)


def _quota_reset_seconds(m: "re.Match[str]") -> float:
    value = float(m.group(1))
    return value / 1000.0 if m.group(2).lower() == "ms" else value


def _iso_reset_seconds(m: "re.Match[str]") -> Optional[float]:
    raw = m.group(1).strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


# An explicit "retry after N s" / "try again in N" wins over "resets in ..." (the credential pool's precedence):
# a body carrying both describes a short throttle inside a long quota window, and the
# shorter explicit wait is the one the provider actually asks for.
RETRY_DELAY_PATTERNS = (
    (_QUOTA_RESET_DELAY_RE, _quota_reset_seconds),
    (_RETRY_AFTER_OR_IN_RE, lambda m: parse_duration_string(m.group(1))),
    (_WAIT_RE, lambda m: parse_duration_string(m.group(1))),
    (_RESET_OR_RETRY_AT_ISO_RE, _iso_reset_seconds),
    (_RESETS_IN_RE, lambda m: parse_duration_string(m.group(1))),
)


def reset_delay_from_message(message: str) -> Optional[float]:
    """Seconds-until-reset parsed from free-text provider error messages, or None."""
    if not message:
        return None
    for pattern, to_seconds in RETRY_DELAY_PATTERNS:
        m = pattern.search(message)
        if m:
            seconds = to_seconds(m)
            if seconds is not None:
                return seconds
    return None


def jittered_backoff(attempt: int, *, base_delay: float = 5.0, max_delay: float = 120.0, jitter_ratio: float = 0.5) -> float:
    """min(base * 2^(attempt-1), max_delay) + uniform jitter in
    [0, jitter_ratio * delay]. ``attempt`` is 1-based."""
    global _jitter_counter
    with _jitter_lock:
        _jitter_counter += 1
        tick = _jitter_counter

    exponent = max(0, attempt - 1)
    delay = max_delay if (exponent >= 63 or base_delay <= 0) else min(base_delay * (2 ** exponent), max_delay)

    # Seed from time + counter so coarse clocks still decorrelate.
    seed = (time.time_ns() ^ (tick * 0x9E3779B9)) & 0xFFFFFFFF
    return delay + random.Random(seed).uniform(0, jitter_ratio * delay)


def _error_text(error: Any) -> str:
    """Best-effort flattened provider error text for retry classification."""
    parts = [error, getattr(error, "message", None), getattr(error, "body", None), getattr(error, "response", None)]
    return " ".join(str(part) for part in parts if part is not None).lower()


def is_zai_coding_overload_error(*, base_url: str | None, model: str | None, error: Any) -> bool:
    """True only for the narrow Z.AI Coding Plan overload shape (429 + code
    1305 / "temporarily overloaded"), so ordinary quota 429s still fail fast."""
    text = _error_text(error)
    return (
        getattr(error, "status_code", None) == 429
        and "api.z.ai/api/coding/paas/v4" in (base_url or "").lower()
        and "glm-5.2" in (model or "").lower()
        and ("1305" in text or "temporarily overloaded" in text)
    )


def adaptive_rate_limit_backoff(
    attempt: int, *, base_url: str | None, model: str | None, error: Any, default_wait: float,
    short_attempts: int = _ZAI_CODING_OVERLOAD_SHORT_ATTEMPTS,
) -> tuple[float, str | None]:
    """``(wait_seconds, reason_label)``: ``default_wait`` for most providers; Z.AI Coding GLM-5.2 overloads keep
    ``short_attempts`` short retries, then 30→60→90→120s with light jitter. ``attempt`` is 1-based."""
    if not is_zai_coding_overload_error(base_url=base_url, model=model, error=error):
        return default_wait, None
    if attempt <= short_attempts:
        return default_wait, "zai_coding_overload_short"
    idx = min(attempt - short_attempts - 1, len(_ZAI_CODING_OVERLOAD_LONG_BACKOFF) - 1)
    base_delay = _ZAI_CODING_OVERLOAD_LONG_BACKOFF[idx]
    return jittered_backoff(1, base_delay=base_delay, max_delay=base_delay, jitter_ratio=0.2), "zai_coding_overload_long"


def zai_coding_overload_retry_ceiling(short_attempts: int = _ZAI_CODING_OVERLOAD_SHORT_ATTEMPTS) -> int:
    """Retry-loop ceiling for the full Z.AI overload schedule: one past the last long entry,
    because the loop gives up when ``retry_count >= ceiling`` BEFORE computing the attempt's
    backoff (the default ``api_max_retries`` of 3 equals ``short_attempts``)."""
    return short_attempts + len(_ZAI_CODING_OVERLOAD_LONG_BACKOFF) + 1

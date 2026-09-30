"""Provider quota limits and reset time caching and formatting for the CLI status bar.

Maintains a non-blocking in-memory TTL cache so status-bar repaints stay sub-millisecond,
fetching upstream quota data asynchronously in daemon background threads.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple, List, Any

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60.0
_limits_cache: dict[str, Tuple[float, Any]] = {}
_active_fetches: set[str] = set()
_fetch_lock = threading.Lock()


def _cache_key(provider: Optional[str], model: Optional[str] = None) -> str:
    p = str(provider or "").strip().lower()
    m = str(model or "").strip().lower()
    return f"{p}:{m}"


def clear_limits_cache() -> None:
    """Clear cached provider limits (primarily for tests)."""
    with _fetch_lock:
        _limits_cache.clear()
        _active_fetches.clear()


def resolve_provider_for_model(provider: Optional[str] = None, model: Optional[str] = None) -> Optional[str]:
    """Resolve provider name from explicit provider or model name/alias."""
    p = str(provider or "").strip().lower()
    if p:
        return p
    m = str(model or "").strip().lower()
    if not m:
        return None
    try:
        from cli import CLI_CONFIG
        aliases = (CLI_CONFIG.get("model_aliases") or {}) if isinstance(CLI_CONFIG, dict) else {}
        entry = aliases.get(m)
        if isinstance(entry, dict) and entry.get("provider"):
            return str(entry["provider"]).strip().lower()
    except Exception:
        pass
    if m.startswith("agy-") or m.startswith("gemini-"):
        return "antigravity"
    if m.startswith("claude-") and not m.startswith("claude-3-"):
        return "antigravity"
    if m.startswith("xkiro") or "/" in m and m.split("/")[0] in ("xkiro", "custom:xkiro"):
        return "xkiro"
    if m.startswith("kilo") or "/" in m and m.split("/")[0] == "kilocode":
        return "kilocode"
    if m.startswith("cline") or "/" in m and m.split("/")[0] == "cline":
        return "cline"
    if m.startswith("openrouter") or "/" in m and m.split("/")[0] in ("openrouter", "custom:openrouter"):
        return "openrouter"
    if m.startswith("nous") or "hermes" in m:
        return "nous"
    if m.startswith("nvidia") or ("/" in m and m.split("/")[0] in ("nvidia", "custom:nvidia")) or "nemotron" in m:
        return "nvidia"
    return None


def format_reset_compact(dt: Optional[datetime]) -> str:
    """Compact string representation of remaining duration until reset (e.g. '3h 10m', '3d 20h')."""
    if not dt:
        return ""
    try:
        now = datetime.now(timezone.utc)
        target = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        delta = (target - now).total_seconds()
        if delta <= 0:
            return ""
        if delta < 60:
            return f"{int(delta)}s"
        if delta < 3600:
            return f"{int(delta // 60)}m"
        if delta < 86400:
            hours, rem = divmod(int(delta), 3600)
            mins = rem // 60
            return f"{hours}h {mins}m" if mins else f"{hours}h"
        days, rem = divmod(int(delta), 86400)
        hours = rem // 3600
        return f"{days}d {hours}h" if hours else f"{days}d"
    except Exception:
        return ""


def _filter_model_windows(snapshot: Any, model: Optional[str] = None) -> list:
    """Filter and order quota windows relevant to the active model."""
    windows = getattr(snapshot, "windows", ()) or ()
    if not windows:
        return []
    m = (model or "").lower()
    # Antigravity group filtering
    if any(k in m for k in ("gemini", "flash", "pro")):
        matched = [w for w in windows if "gemini" in getattr(w, "label", "").lower()]
        if matched:
            return matched
    elif any(k in m for k in ("claude", "gpt", "opus", "sonnet")):
        matched = [w for w in windows if any(k in getattr(w, "label", "").lower() for k in ("claude", "gpt"))]
        if matched:
            return matched
    return list(windows)


def _limit_style(pct: int) -> str:
    if pct >= 50:
        return "class:status-bar-good"
    if pct >= 20:
        return "class:status-bar-warn"
    if pct > 0:
        return "class:status-bar-bad"
    return "class:status-bar-critical"


def format_limits_compact(
    snapshot: Any,
    model: Optional[str] = None,
    width: int = 80,
    styled: bool = True,
) -> Tuple[List[Tuple[str, str]], str]:
    """Format provider limits for status bar display.

    Returns:
        (styled_fragments, plain_text)
    """
    if not snapshot or not getattr(snapshot, "available", False):
        return [], ""

    relevant = _filter_model_windows(snapshot, model)
    if not relevant:
        return [], ""

    # Look for 5h/session and weekly windows
    w_5h = next((w for w in relevant if any(k in w.label.lower() for k in ("5h", "session", "primary"))), None)
    w_wk = next((w for w in relevant if any(k in w.label.lower() for k in ("weekly", "week", "secondary"))), None)

    items: List[Tuple[str, Any]] = []
    if width >= 80 and w_5h and w_wk:
        items = [("5h ", w_5h), ("w ", w_wk)]
    elif w_5h and w_wk:
        pw = round(100 - w_wk.used_percent) if w_wk.used_percent is not None else 100
        if pw == 0:
            items = [("w ", w_wk)]
        else:
            items = [("", w_5h)]
    elif relevant:
        items = [("", relevant[0])]

    frags: List[Tuple[str, str]] = []
    plain_parts: List[str] = []

    for tag, w in items:
        if w.used_percent is None:
            if w.detail and any(k in w.detail.lower() for k in ("credit", "balance", "$")):
                first_word = w.detail.split()[0]
                label_val = f"{first_word} cred" if "credit" in w.detail.lower() and not first_word.endswith("cred") else first_word
                if frags:
                    frags.append(("class:status-bar-dim" if styled else "", " · "))
                    plain_parts.append(" · ")
                frags.append(("class:status-bar-good" if styled else "", label_val))
                plain_parts.append(label_val)
            continue
        rem_pct = max(0, min(100, round(100 - w.used_percent)))
        rst = format_reset_compact(w.reset_at)
        st = _limit_style(rem_pct) if styled else ""
        rst_str = f" ({rst})" if rst else ""

        if frags:
            frags.append(("class:status-bar-dim" if styled else "", " · "))
            plain_parts.append(" · ")
        if tag:
            frags.append(("class:status-bar-dim" if styled else "", tag))
            plain_parts.append(tag)
        frags.append((st, f"{rem_pct}%"))
        plain_parts.append(f"{rem_pct}%")
        if rst_str:
            frags.append(("class:status-bar-dim" if styled else "", rst_str))
            plain_parts.append(rst_str)

    return frags, "".join(plain_parts)


def get_cached_account_limits(
    provider: Optional[str],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    on_update: Optional[Callable[[], None]] = None,
) -> Any:
    """Non-blocking query for cached account usage limits.

    Returns the cached snapshot immediately (<0.01ms). If cache is missing or expired,
    spawns a background thread to refresh without blocking the TUI loop, invoking
    `on_update` when fresh data arrives.
    """
    if not provider:
        return None
    key = _cache_key(provider, model)
    now = time.monotonic()

    with _fetch_lock:
        hit = _limits_cache.get(key)
        is_fresh = hit is not None and (now - hit[0] < _TTL_SECONDS)
        already_fetching = key in _active_fetches

        if is_fresh:
            return hit[1]

        if not already_fetching:
            _active_fetches.add(key)
            threading.Thread(
                target=_background_fetch_limits,
                args=(provider, model, base_url, api_key, key, on_update),
                daemon=True,
                name=f"limits-fetch-{key}",
            ).start()

        return hit[1] if hit is not None else None


def _background_fetch_limits(
    provider: str,
    model: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    cache_key: str,
    on_update: Optional[Callable[[], None]],
) -> None:
    snap = None
    try:
        from agent.account_usage import fetch_account_usage
        snap = fetch_account_usage(provider, base_url=base_url, api_key=api_key, model=model)
    except Exception as exc:
        logger.debug("Background limits fetch failed for %s: %s", cache_key, exc)
    finally:
        with _fetch_lock:
            _limits_cache[cache_key] = (time.monotonic(), snap)
            _active_fetches.discard(cache_key)

    if snap is not None and on_update is not None:
        try:
            on_update()
        except Exception:
            pass


def refresh_account_limits_async(
    provider: Optional[str],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    on_update: Optional[Callable[[], None]] = None,
) -> None:
    """Trigger an asynchronous refresh of account limits (e.g. after a chat turn)."""
    if not provider:
        return
    key = _cache_key(provider, model)
    with _fetch_lock:
        _limits_cache.pop(key, None)
    get_cached_account_limits(provider, model=model, base_url=base_url, api_key=api_key, on_update=on_update)

"""Visual multi-provider usage and quota dashboard for Shiina CLI.

Renders high-fidelity terminal gauges, compact countdowns, and multi-provider /
multi-account limits (Antigravity, xKiro, Cline, Kilo Code, OpenRouter, etc.).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Optional, Union

from rich.panel import Panel
from rich.markup import escape as _escape_markup

from agent.account_usage import AccountUsageSnapshot, AccountUsageWindow, fetch_account_usage, _USAGE_FETCHERS
from agent.credential_pool import load_pool
from shiina_cli.skin_engine import get_active_skin

logger = logging.getLogger(__name__)

# Supported providers that can expose live quota, balance, or usage metrics.
SUPPORTED_QUOTA_PROVIDERS: frozenset[str] = frozenset({
    "antigravity", "agy", "google-antigravity", "jetski",
    "xkiro", "custom:xkiro",
    "cline", "kilocode",
    "openrouter", "custom:openrouter",
    "openai-codex", "anthropic", "nous",
    "nvidia", "custom:nvidia",
})

# Aliases mapped to canonical display names
_CANONICAL_NAMES: dict[str, str] = {
    "antigravity": "Google Antigravity",
    "agy": "Google Antigravity",
    "google-antigravity": "Google Antigravity",
    "jetski": "Google Antigravity",
    "xkiro": "xKiro",
    "custom:xkiro": "xKiro",
    "cline": "Cline",
    "kilocode": "Kilo Code",
    "openrouter": "OpenRouter",
    "custom:openrouter": "OpenRouter",
    "openai-codex": "OpenAI Codex",
    "anthropic": "Anthropic",
    "nous": "Shiina Portal",
    "nvidia": "NVIDIA NIM",
    "custom:nvidia": "NVIDIA NIM",
}


@dataclass
class ProviderAccountUsage:
    snapshot: AccountUsageSnapshot
    label: Optional[str] = None
    credential_id: Optional[str] = None
    priority: int = 0
    is_current: bool = False


def render_line_gauge(avail_pct: float, width: int = 15) -> str:
    """Render a visual line gauge where green indicates available quota.

    - Available portion: bold green heavy line (``━``, \\u2501).
    - Consumed portion: dim dark line (``─``, \\u2500).
    - When 0% available: red alert line.
    """
    avail_pct = max(0.0, min(100.0, avail_pct))
    if avail_pct <= 0.0:
        bar_exhausted = "\u2500" * width
        return f"[bold red]{bar_exhausted}[/]"
    filled = max(1, int(round(width * (avail_pct / 100.0))))
    empty = width - filled
    c = "bold green" if avail_pct >= 25.0 else "bold yellow"
    bar_fill = "\u2501" * filled
    bar_empty = "\u2500" * empty
    return f"[{c}]{bar_fill}[/][dim #444444]{bar_empty}[/]"


def format_countdown(dt: Optional[datetime]) -> str:
    """Format remaining duration until a reset timestamp into compact format (e.g. '2h 24m')."""
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        now = datetime.now()
    diff = (dt - now).total_seconds()
    if diff <= 0:
        return "now"
    mins = int(diff // 60)
    hours = int(mins // 60)
    days = int(hours // 24)
    if days > 0:
        rem_hours = hours % 24
        return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"
    if hours > 0:
        rem_mins = mins % 60
        return f"{hours}h {rem_mins}m" if rem_mins else f"{hours}h"
    if diff < 60:
        return f"{max(1, int(round(diff)))}s"
    return f"{max(1, mins)}m"


def shorten_label(label: str) -> str:
    """Shorten common window labels so they fit on standard terminal lines."""
    replacements = {
        "Claude and GPT models (weekly)": "Claude/GPT (weekly)",
        "Claude and GPT models (5h)": "Claude/GPT (5h)",
        "Gemini Models (weekly)": "Gemini (weekly)",
        "Gemini Models (5h)": "Gemini (5h)",
    }
    return replacements.get(label, label)


def extract_user_info(details: tuple[str, ...], max_len: int = 34) -> str:
    """Extract and compact user identity (name / email) from details."""
    raw = ""
    for d in details or ():
        if d.lower().startswith("user:"):
            raw = d[5:].strip()
            break
    if not raw:
        return ""
    if len(raw) <= max_len:
        return raw
    # If in 'Name (email@domain)' format and too long, prefer email or shortened name
    m = re.search(r"\(([^)]+@[^)]+)\)", raw)
    if m and len(m.group(1)) <= max_len:
        return m.group(1)
    return raw[:max_len - 1] + "…"


def extract_credits(text: Optional[str]) -> int:
    """Extract numeric credits value from a string (e.g. '447,388 credits available')."""
    if not text:
        return 0
    m = re.search(r"([\d,]+)\s+credits", text)
    return int(m.group(1).replace(",", "")) if m else 0


def discover_quota_providers(
    active_provider: Optional[str] = None,
) -> tuple[list[str], list[tuple[str, int]]]:
    """Discover all supported providers to query, plus other configured API-key providers.

    Returns:
        (quota_providers_to_query, other_configured_providers)
    """
    import shiina_cli.auth as auth_mod
    from shiina_cli.auth import PROVIDER_REGISTRY
    from shiina_cli.auth_commands import list_custom_pool_providers, _get_custom_provider_entries
    from shiina_cli.providers import ALIASES
    from shiina_cli.runtime_provider_backends import _is_external_process_provider
    from agent.account_usage import _USAGE_FETCHERS

    try:
        credential_pool = auth_mod._load_auth_store().get("credential_pool")
    except Exception:
        credential_pool = {}

    all_configured = sorted({
        "antigravity",
        *PROVIDER_REGISTRY.keys(), "openrouter", *list_custom_pool_providers(),
        *(e.get("provider_key") for e in _get_custom_provider_entries() if e.get("provider_key")),
        *(credential_pool.keys() if isinstance(credential_pool, dict) else ()),
    })

    quota_candidates: list[str] = []
    other_providers: list[tuple[str, int]] = []
    seen: set[str] = set()

    # Prioritize active provider if set
    norm_active = (active_provider or "").lower().strip()
    if norm_active and norm_active in SUPPORTED_QUOTA_PROVIDERS:
        quota_candidates.append(norm_active)
        seen.add(norm_active)
        if norm_active in ("antigravity", "agy", "google-antigravity", "jetski"):
            seen.update({"antigravity", "agy", "google-antigravity", "jetski"})

    # Always check Antigravity (has Google OAuth credentials)
    if "antigravity" not in seen and not any(a in seen for a in ("agy", "google-antigravity", "jetski")):
        quota_candidates.append("antigravity")
        seen.update({"antigravity", "agy", "google-antigravity", "jetski"})

    for p in all_configured:
        norm = p.lower().strip()
        if norm in seen:
            continue

        # Alias variants (kiro-cli, kiro-ai, opencode-local, qoder-ai, …) are the same credential
        # under another name; fold them onto their canonical provider so the dashboard lists the
        # provider once. A variant with its own usage fetcher (xkiro, cline) keeps its identity.
        canon = norm if norm in _USAGE_FETCHERS else str(ALIASES.get(norm) or norm)
        if canon in seen:
            continue

        # Check if provider has pooled credentials
        try:
            pool = load_pool(p)
            n_entries = len(pool.entries())
        except Exception:
            n_entries = 0

        # Check if provider matches supported quota providers
        is_supported = (
            canon in SUPPORTED_QUOTA_PROVIDERS
            or canon in _USAGE_FETCHERS
            or (canon.startswith("custom:") and any(x in canon for x in ("xkiro", "openrouter", "cline", "kilo")))
        )

        if is_supported:
            if n_entries > 0 or canon in ("openai-codex", "anthropic", "nous"):
                quota_candidates.append(canon)
                seen.add(canon)
        elif n_entries > 0 and _is_external_process_provider(canon):
            # Local/subscription CLI with no quota API (kiro, opencode-cli, qoder): render it with
            # its connection detail instead of burying it in the summary line.
            quota_candidates.append(canon)
            seen.add(canon)
        elif n_entries > 0:
            other_providers.append((canon, n_entries))

    # Fold alias variants onto their canonical provider so the summary counts read
    # "qoder (4 keys)" rather than four separate one-key rows.
    totals: dict[str, int] = {}
    for name, cnt in other_providers:
        totals[name] = totals.get(name, 0) + cnt
    return quota_candidates, list(totals.items())


def fetch_all_provider_usage(
    providers: list[str],
    active_provider: Optional[str] = None,
    active_model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 8.0,
) -> dict[str, list[ProviderAccountUsage]]:
    """Concurrently fetch usage snapshots for all credentials/accounts of the requested providers."""
    tasks = []

    for p in providers:
        norm_p = p.lower().strip()
        is_active = (active_provider and norm_p == active_provider.lower().strip())

        try:
            pool = load_pool(p)
            entries = pool.entries() if pool else []
        except Exception:
            entries = []

        if entries:
            current = pool.peek()
            for entry in entries:
                is_curr = (current is not None and entry.id == current.id)
                b = entry.base_url or (base_url if is_active else None)
                m = active_model if is_active else None
                tasks.append((p, entry.access_token, b, m, entry.label, entry.id, entry.priority, is_curr))
        else:
            # Ambient or explicitly passed credentials
            k = api_key if is_active else None
            b = base_url if is_active else None
            m = active_model if is_active else None
            tasks.append((p, k, b, m, None, None, 0, True))

    def _execute_task(task_spec):
        p, k, b, m, lbl, cid, prio, is_curr = task_spec
        try:
            snap = fetch_account_usage(p, api_key=k, base_url=b, model=m)
            if snap and (snap.windows or snap.details or not snap.unavailable_reason):
                return p, ProviderAccountUsage(
                    snapshot=snap, label=lbl, credential_id=cid, priority=prio, is_current=is_curr
                )
        except Exception as exc:
            logger.debug("Account usage fetch failed for %s (%s): %s", p, lbl, exc)
        return p, None

    snapshots_by_provider: dict[str, list[ProviderAccountUsage]] = {}
    if not tasks:
        return snapshots_by_provider

    with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as ex:
        futures = [ex.submit(_execute_task, t) for t in tasks]
        for fut in as_completed(futures):
            try:
                p, acc_usage = fut.result(timeout=timeout)
                if acc_usage is not None:
                    snapshots_by_provider.setdefault(p, []).append(acc_usage)
            except Exception:
                pass

    # Sort accounts by priority within each provider
    for p in snapshots_by_provider:
        snapshots_by_provider[p].sort(key=lambda a: a.priority)

    return snapshots_by_provider


def build_usage_dashboard(
    snapshots: dict[str, Union[AccountUsageSnapshot, list[Any]]],
    active_provider: Optional[str] = None,
    other_providers: Optional[list[tuple[str, int]]] = None,
    console_width: int = 80,
) -> Panel:
    """Build a styled Rich Panel presenting provider quotas, visual gauges, and multi-account breakdown."""
    skin = get_active_skin()
    name_color = skin.get_color("ui_accent", "#38bdf8")
    title_color = skin.get_color("banner_title", "#60a5fa")
    border_color = skin.get_color("banner_border", "#3b82f6")
    norm_active = (active_provider or "").lower().strip()
    if norm_active in ("agy", "google-antigravity", "jetski"):
        norm_active = "antigravity"

    # Normalize snapshots input to dict[str, list[ProviderAccountUsage]]
    normalized: dict[str, list[ProviderAccountUsage]] = {}
    for p, val in snapshots.items():
        if isinstance(val, list):
            accs = []
            for item in val:
                if isinstance(item, ProviderAccountUsage):
                    accs.append(item)
                elif isinstance(item, AccountUsageSnapshot):
                    accs.append(ProviderAccountUsage(snapshot=item, is_current=True))
            normalized[p] = accs
        elif isinstance(val, AccountUsageSnapshot):
            normalized[p] = [ProviderAccountUsage(snapshot=val, is_current=True)]

    def _sort_key(k: str) -> tuple[int, str]:
        norm_k = k.lower().strip()
        if norm_active and (norm_k == norm_active or (norm_active == "antigravity" and "antigravity" in norm_k)):
            return (0, k)
        if "antigravity" in norm_k or "agy" in norm_k:
            return (1, k)
        if "cline" in norm_k:
            return (2, k)
        if "xkiro" in norm_k:
            return (3, k)
        if "nvidia" in norm_k:
            return (4, k)
        return (5, k)

    ordered_keys = sorted(normalized.keys(), key=_sort_key)
    lines: list[str] = []

    gauge_width = max(10, min(14, console_width - 70))

    for idx, p in enumerate(ordered_keys):
        accs = normalized[p]
        if not accs:
            continue

        norm_p = p.lower().strip()
        is_active = (norm_active and (norm_p == norm_active or (norm_active == "antigravity" and "antigravity" in norm_p)))
        display_name = _CANONICAL_NAMES.get(norm_p) or accs[0].snapshot.title or p.capitalize()
        pool_suffix = f" [dim]({p})[/]" if (p.startswith("custom:") or p in ("xkiro", "custom:xkiro", "openrouter", "custom:openrouter")) and len([k for k in normalized if _CANONICAL_NAMES.get(k.lower(), "") == display_name]) > 1 else ""

        # Check single vs multi account
        if len(accs) == 1:
            acc = accs[0]
            snap = acc.snapshot

            if is_active:
                header = f"[bold {name_color}]★ {display_name}[/] [dim cyan](active model)[/]{pool_suffix}"
            elif "xkiro" in norm_p or (snap.plan and "free" in snap.plan.lower()):
                header = f"[bold {name_color}]✦ {display_name}[/] [dim green](Daily Free Tier)[/]{pool_suffix}"
            elif "nvidia" in norm_p:
                header = f"[bold {name_color}]✦ {display_name}[/] [dim green](Free Trial)[/]{pool_suffix}"
            else:
                header = f"[bold {name_color}]✦ {display_name}[/]{pool_suffix}"

            lines.append(header)

            # Quota Windows
            if snap.windows:
                for w in snap.windows:
                    w_name = shorten_label(w.label)
                    if w.used_percent is not None:
                        avail = max(0.0, min(100.0, 100.0 - w.used_percent))
                        gauge = render_line_gauge(avail, width=gauge_width)
                        pct_str = f"[bold green]{avail:>3.0f}%[/]" if avail >= 25.0 else (f"[bold yellow]{avail:>3.0f}%[/]" if avail > 0 else "[bold red]  0%[/]")
                        reset_str = f"[dim]• resets {format_countdown(w.reset_at)}[/]" if w.reset_at else ""
                        lines.append(f"   [white]{w_name:<19}[/] {gauge}  {pct_str}  {reset_str}".rstrip())
                    else:
                        detail_val = w.detail or "available"
                        if "free trial" in detail_val.lower() or "rate limit" in detail_val.lower():
                            lines.append(f"   [white]{w_name:<19}[/] [bold green]Active[/] [dim]• Free Trial (Rate Limits)[/]")
                        else:
                            lines.append(f"   [white]{w_name:<19}[/] [bold green]{detail_val}[/]")

            # Details
            seen_details = {str(w.detail).lower() for w in snap.windows if w.detail}
            if snap.details:
                for d in snap.details:
                    low_d = d.lower()
                    if any(low_d in s or s in low_d for s in seen_details):
                        continue
                    num_tokens = [tok for s in seen_details for tok in s.split() if tok.replace(",", "").isdigit()]
                    if num_tokens and any(num in low_d for num in num_tokens):
                        continue
                    if any(d.startswith(prefix) for prefix in ("Within each group", "Quota is consumed")):
                        continue
                    lines.append(f"   [dim]{_escape_markup(d)}[/]")

        else:
            # Multi-account presentation (e.g. Cline 3 keys, xKiro 2 keys, Kilo 4 keys, NVIDIA 2 keys)
            total_cred = sum(extract_credits(w.detail) for acc in accs for w in acc.snapshot.windows if w.detail)
            cred_hdr = f" • {total_cred:,} total credits" if total_cred > 0 else ""
            tier_hdr = "Daily Free Tier • " if "xkiro" in norm_p else ("Free Trial • " if "nvidia" in norm_p else "")

            if is_active:
                header = f"[bold {name_color}]★ {display_name}[/] [dim cyan](active model • {len(accs)} accounts{cred_hdr})[/]{pool_suffix}"
            elif "xkiro" in norm_p or "nvidia" in norm_p:
                header = f"[bold {name_color}]✦ {display_name}[/] [dim green]({tier_hdr}{len(accs)} accounts)[/]{pool_suffix}"
            else:
                header = f"[bold {name_color}]✦ {display_name}[/] [dim cyan]({len(accs)} accounts{cred_hdr})[/]{pool_suffix}"

            lines.append(header)

            for acc in accs:
                snap = acc.snapshot
                marker = "[bold cyan]← (active)[/]" if acc.is_current else ""
                raw_lbl = str(acc.label) if acc.label else str(acc.priority + 1)
                lbl = f"#{raw_lbl}"
                user = extract_user_info(snap.details, max_len=32)
                user_str = f"[dim]• {user}[/]" if user and user != raw_lbl else ""

                if len(snap.windows) > 1:
                    lines.append(f"   [bold white]{lbl}[/] {marker} {user_str}".rstrip())
                    for w in snap.windows:
                        w_name = shorten_label(w.label)
                        if w.used_percent is not None:
                            avail = max(0.0, min(100.0, 100.0 - w.used_percent))
                            gauge = render_line_gauge(avail, width=max(8, gauge_width - 4))
                            pct_str = (
                                f"[bold green]{avail:>3.0f}%[/]"
                                if avail >= 25.0
                                else (f"[bold yellow]{avail:>3.0f}%[/]" if avail > 0 else "[bold red]  0%[/]")
                            )
                            reset_str = f"[dim]• resets {format_countdown(w.reset_at)}[/]" if w.reset_at else ""
                            lines.append(f"      [white]{w_name:<19}[/] {gauge}  {pct_str}  {reset_str}".rstrip())
                        else:
                            detail_val = w.detail or "available"
                            if "free trial" in detail_val.lower() or "rate limit" in detail_val.lower():
                                lines.append(f"      [white]{w_name:<19}[/] [bold green]Active[/] [dim]• Free Trial (Rate Limits)[/]")
                            else:
                                lines.append(f"      [white]{w_name:<19}[/] [bold green]{detail_val}[/]")
                    continue

                single_marker = "[bold cyan]←[/]" if acc.is_current else " "
                w = snap.windows[0] if snap.windows else None
                if w and w.used_percent is not None:
                    avail = max(0.0, min(100.0, 100.0 - w.used_percent))
                    gauge = render_line_gauge(avail, width=max(8, gauge_width - 4))
                    pct_str = f"[bold green]{avail:>3.0f}%[/]" if avail >= 25.0 else (f"[bold yellow]{avail:>3.0f}%[/]" if avail > 0 else "[bold red]  0%[/]")
                    res_str = f"[dim]• {format_countdown(w.reset_at)}[/]" if w.reset_at else ""

                    # Compact token / turn details
                    tok_str = ""
                    if "free tokens" in (w.detail or ""):
                        parts = w.detail.split(" of ")
                        if len(parts) == 2:
                            k_rem = int(parts[0].replace(",", "")) // 1000
                            k_tot = int(parts[1].split()[0].replace(",", "")) // 1000
                            tok_str = f" [dim]({k_rem // 1000}M/{k_tot // 1000}M)[/]" if k_rem >= 1000 else f" [dim]({k_rem}k/{k_tot}k)[/]"
                    elif "turns" in (w.detail or "").lower():
                        m = re.search(r"(\d+/\d+\s+turns)", w.detail)
                        if m:
                            tok_str = f" [dim]({m.group(1)})[/]"

                    lines.append(f"   [white]{lbl:<6}[/] {single_marker} {gauge}  {pct_str} {tok_str} {res_str} {user_str}".rstrip())
                elif w and "credits" in (w.detail or "").lower():
                    c_num = extract_credits(w.detail)
                    lines.append(f"   [white]{lbl:<6}[/] {single_marker} [bold green]{c_num:>7,} cred[/]  {user_str}".rstrip())
                elif w and ("free trial" in (w.detail or "").lower() or "rate limit" in (w.detail or "").lower()):
                    lines.append(f"   [white]{lbl:<6}[/] {single_marker} [bold green]Active[/] [dim]• Free Trial (Rate Limits)[/]  {user_str}".rstrip())
                else:
                    det = w.detail if w else "Ready"
                    lines.append(f"   [white]{lbl:<6}[/] {single_marker} [dim]{det}[/]  {user_str}".rstrip())

        if idx < len(ordered_keys) - 1:
            lines.append("")

    # Summary of other connected providers without usage APIs
    if other_providers:
        grouped: dict[str, int] = {}
        for p, cnt in other_providers:
            root = p.split("-")[0].split(".")[0]
            grouped[root] = grouped.get(root, 0) + cnt
        other_labels = [f"{p} ({cnt} key{'s' if cnt != 1 else ''})" for p, cnt in sorted(grouped.items())]
        lines.append("")
        lines.append(f"[dim]Other connected providers: {', '.join(other_labels)}[/]")

    title_text = f"[bold {title_color}]✨ Provider Quotas & Usage Limits[/]"
    return Panel(
        "\n".join(lines).rstrip(),
        title=title_text,
        border_style=border_color,
        padding=(1, 2),
    )

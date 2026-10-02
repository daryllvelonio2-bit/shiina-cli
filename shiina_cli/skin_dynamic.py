"""Dynamic skin palettes — colours derived live from the desktop's own scheme.

A static skin cannot survive a changing wallpaper: a hand-picked palette goes unreadable the
moment the shell derives a background of a different luminance. This module reads the desktop's
Material-3 scheme (caelestia's ``scheme.json``), maps its roles onto Shiina's colour keys, and
enforces a minimum WCAG contrast ratio against every surface we paint on.

Two halves, deliberately separate:

* **Hue follows the wallpaper** — brand/accent/syntax keys take the scheme's own roles
  (``primary``/``tertiary``/``secondary``, which the shell derives from the image).
* **Value contrast is guaranteed** — semantic keys (ok/error/warn/diff) keep their meaning
  (green stays green) while their lightness is pushed away from the surfaces they are painted on
  until the contrast ratio clears the target. That is the value axis of colour-wheel contrast;
  hue rotation cannot rescue a palette whose background just flipped polarity.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Skin names served by this module (canonical first — only the canonical one is listed).
DYNAMIC_SKIN_NAMES: Tuple[str, ...] = ("caelestia", "dynamic")

# Minimum WCAG contrast ratio against the closest surface the colour is painted on.
_TEXT = 4.5      # body text (AA)
_ACCENT = 4.0    # labels, accents, borders used as foreground
_DIM = 3.0       # muted/secondary text and rules

# Hue-fixed anchors for semantic colours: the diff/status meaning must not follow the wallpaper
# (a wallpaper-derived "green" is often peach — see caelestia's term2 on a warm palette).
_ANCHORS = {
    "ok": "#3FA34D", "ok_bright": "#5CC46F",
    "bad": "#E5484D", "bad_bright": "#FF6B6B",
    "warn": "#D9A03C",
}

# How far a hue-fixed anchor is pulled toward the scheme's own hue (keeps its identity).
_HARMONY = 0.22

# Shiina colour key -> (scheme role or anchor key, minimum contrast). A 0.0 target means the key
# is a surface/decorative fill and is taken verbatim.
_COLOR_SPEC: Dict[str, Tuple[str, float]] = {
    "background": ("surface", 0.0),
    "banner_border": ("primary", _DIM), "banner_title": ("primary", _ACCENT),
    "banner_accent": ("tertiary", _ACCENT), "banner_dim": ("onSurfaceVariant", _DIM),
    "banner_text": ("onSurface", _TEXT),
    "ui_accent": ("tertiary", _ACCENT), "ui_label": ("primary", _ACCENT),
    "ui_text": ("onSurface", _TEXT), "ui_border": ("outlineVariant", _DIM),
    "ui_tool": ("tertiary", _ACCENT), "ui_thinking": ("secondary", _DIM),
    "ui_ok": ("ok", _TEXT), "ui_error": ("error", _TEXT), "ui_warn": ("warn", _ACCENT),
    "diff_added": ("ok", _TEXT), "diff_removed": ("bad", _TEXT),
    "diff_added_word": ("ok_bright", _TEXT), "diff_removed_word": ("bad_bright", _TEXT),
    "syntax_string": ("tertiary", _ACCENT), "syntax_number": ("secondary", _ACCENT),
    "syntax_keyword": ("primary", _ACCENT), "syntax_comment": ("onSurfaceVariant", _DIM),
    "prompt": ("onSurface", _TEXT), "input_rule": ("primary", _DIM),
    "response_border": ("primary", _ACCENT),
    "status_bar_bg": ("surfaceContainer", 0.0), "status_bar_text": ("onSurfaceVariant", _TEXT),
    "status_bar_strong": ("primary", _ACCENT), "status_bar_dim": ("outline", _DIM),
    "status_bar_good": ("ok", _TEXT), "status_bar_warn": ("warn", _TEXT),
    "status_bar_bad": ("error", _TEXT), "status_bar_critical": ("bad_bright", _TEXT),
    "session_label": ("primary", _ACCENT), "session_border": ("primary", _DIM),
    "completion_menu_bg": ("surfaceContainerLow", 0.0),
    "completion_menu_current_bg": ("surfaceContainerHighest", 0.0),
    "completion_menu_meta_bg": ("surfaceContainerHigh", 0.0),
    "completion_menu_meta_current_bg": ("surfaceContainerHigh", 0.0),
    "selection_bg": ("surfaceContainerHigh", 0.0), "voice_status_bg": ("surfaceContainer", 0.0),
    "shell_dollar": ("tertiary", _ACCENT),
}

# Surfaces every foreground colour may land on (all four are backgrounds in the style templates).
_BG_ROLES = ("surface", "surfaceContainer", "surfaceContainerLow", "surfaceContainerHigh",
             "surfaceContainerHighest")

_DESCRIPTION = "Caelestia dynamic — hue follows your wallpaper, contrast enforced"


def _candidates() -> List[Path]:
    global _candidates_cache
    key = (os.environ.get("XDG_STATE_HOME") or "", os.environ.get("HOME") or "")
    if _candidates_cache[0] != key:
        home = Path(key[1]).expanduser() if key[1] else Path.home()
        state = Path(key[0]) if key[0] else home / ".local" / "state"
        _candidates_cache = (key, [state / "caelestia" / "scheme.json",
                                   home / ".config" / "caelestia" / "scheme.json"])
    return _candidates_cache[1]


def scheme_path() -> Optional[Path]:
    """The live scheme file, memoized so the steady state is one ``stat``.

    The first candidate found is the one watched (caelestia writes the state file); when it
    disappears the candidates are rescanned, so a desktop that starts emitting a scheme later
    is still picked up.
    """
    global _probe
    if _probe is not None:
        try:
            _probe.stat()
            return _probe
        except OSError:
            _probe = None
    found = [p for p in _candidates() if p.is_file()]
    _probe = max(found, key=lambda p: p.stat().st_mtime_ns) if found else None
    return _probe


def scheme_generation() -> Tuple[str, int]:
    """Cheap change token for the active scheme (one stat); ``()`` when there is no scheme."""
    path = scheme_path()
    if path is None:
        return ()
    try:
        return str(path), path.stat().st_mtime_ns
    except OSError:
        return ()


def reset_cache() -> None:
    """Drop every memoized lookup (tests, and switches of the desktop scheme source)."""
    global _probe, _scheme_cache, _last_generation, _candidates_cache
    _probe = None
    _scheme_cache = ((), {})
    _last_generation = ()
    _candidates_cache = ((), [])


_probe: Optional[Path] = None
_candidates_cache: Tuple[Tuple[str, str], List[Path]] = ((), [])
_scheme_cache: Tuple[Tuple[str, int], Dict[str, Any]] = ((), {})
_last_generation: Tuple[str, int] = ()


def scheme_changed() -> bool:
    """True (once) when the scheme file moved since the last palette build."""
    global _last_generation
    generation = scheme_generation()
    if generation == _last_generation:
        return False
    _last_generation = generation
    return True


def _read_scheme() -> Dict[str, str]:
    """Role -> hex map from the live scheme file, cached by (path, mtime)."""
    global _scheme_cache
    generation = scheme_generation()
    if not generation:
        return {}
    if _scheme_cache[0] == generation:
        return _scheme_cache[1]
    roles: Dict[str, str] = {}
    try:
        raw = json.loads(Path(generation[0]).read_text(encoding="utf-8"))
        colours = raw.get("colours") or raw.get("colors") or {}
        if isinstance(colours, dict):
            roles = {str(k): _normalize(v) for k, v in colours.items() if _normalize(v)}
    except Exception as e:  # noqa: BLE001 - a malformed scheme must never break rendering
        logger.debug("Dynamic skin: unreadable scheme %s: %s", generation[0], e)
    _scheme_cache = (generation, roles)
    return roles


def _normalize(value: Any) -> str:
    """``#rgb``/``rgb``/``#rrggbb`` -> ``#rrggbb``; empty string when it is not a colour."""
    if not isinstance(value, str):
        return ""
    digits = value.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return f"#{digits.lower()}" if len(digits) == 6 and all(c in "0123456789abcdefABCDEF" for c in digits) else ""


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    digits = hex_color.lstrip("#")
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def _luminance(hex_color: str) -> float:
    """WCAG relative luminance (sRGB -> linear)."""
    channels = []
    for c in _rgb(hex_color):
        v = c / 255
        channels.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colours (1.0 … 21.0)."""
    a, b = _luminance(fg), _luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _mix(rgb: Sequence[float], toward: Sequence[float], amount: float) -> Tuple[float, float, float]:
    return tuple(c + (t - c) * amount for c, t in zip(rgb, toward))


def _worst_ratio(fg: str, bg_lums: Sequence[float]) -> float:
    """Lowest contrast ratio against any of the surfaces (the readability floor)."""
    lum = _luminance(fg)
    return min((max(lum, b) + 0.05) / (min(lum, b) + 0.05) for b in bg_lums)


def enforce_contrast(color: str, backgrounds: Sequence[str], minimum: float) -> str:
    """Push ``color`` toward white/black until it clears ``minimum`` on EVERY background.

    Direction is chosen from the surfaces' mean luminance, which is the value axis of
    colour-wheel contrast: on dark surfaces the text moves lighter, on light ones darker.
    """
    if minimum <= 0 or not backgrounds or not color:
        return color
    bg_lums = [_luminance(b) for b in backgrounds]
    if _worst_ratio(color, bg_lums) >= minimum:
        return color
    toward = (255, 255, 255) if sum(bg_lums) / len(bg_lums) < 0.5 else (0, 0, 0)
    rgb = _rgb(color)
    for step in range(5, 105, 5):
        candidate = _hex(_mix(rgb, toward, step / 100))
        if _worst_ratio(candidate, bg_lums) >= minimum:
            return candidate
    return _hex(toward)


def _harmonize(color: str, roles: Dict[str, str]) -> str:
    """Pull a hue-fixed anchor toward the scheme's own hue so it sits in the wallpaper's family.

    Identity is preserved (the anchor keeps ~78% of its own hue) — this is the analogous-colour
    half of colour-wheel harmony; legibility comes from the contrast pass that follows.
    """
    source = roles.get("primary") or roles.get("surfaceTint") or ""
    if not source:
        return color
    return _hex(_mix(_rgb(color), _rgb(source), _HARMONY))


def build_colors(roles: Dict[str, str]) -> Dict[str, str]:
    """Map scheme roles onto Shiina colour keys with contrast enforced."""
    if not roles:
        return {}
    backgrounds = [roles.get(role, "") for role in _BG_ROLES]
    backgrounds = [c for c in backgrounds if c] or [roles.get("surface", "#000000")]
    colors: Dict[str, str] = {}
    for key, (source, minimum) in _COLOR_SPEC.items():
        anchor = _ANCHORS.get(source)
        base = _harmonize(anchor, roles) if anchor else roles.get(source, "")
        if not base:
            continue
        colors[key] = enforce_contrast(base, backgrounds, minimum)
    return colors


def live_colors() -> Dict[str, str]:
    """The current dynamic palette, or ``{}`` when no desktop scheme is available."""
    return build_colors(_read_scheme())


def recolor_markup(markup: str, roles: Optional[Dict[str, str]] = None) -> str:
    """Recolor a Rich-markup art block into the scheme's hue, preserving its shading ramp.

    Art blocks ship with a fixed shade ladder (bright to dim); each distinct tone is mapped to an
    equally-spaced step between the palette's accent and its outline, so the artwork keeps its
    depth while following the wallpaper. Returns ``markup`` unchanged without a scheme.
    """
    roles = _read_scheme() if roles is None else roles
    if not markup or not roles:
        return markup
    shades = list(dict.fromkeys(h.lower() for h in re.findall(r"#([0-9a-fA-F]{6})", markup)))
    top = roles.get("primary") or roles.get("surfaceTint")
    bottom = roles.get("outline") or roles.get("onSurfaceVariant")
    if not top or not bottom:
        return markup
    rank = {h: i for i, h in enumerate(sorted(shades, key=lambda h: -_luminance("#" + h)))}
    step = max(1, len(shades) - 1)

    def swap(match: "re.Match") -> str:
        index = rank.get(match.group(1).lower(), 0)
        return _hex(_mix(_rgb(top), _rgb(bottom), index / step))

    return re.sub(r"#([0-9a-fA-F]{6})", swap, markup)

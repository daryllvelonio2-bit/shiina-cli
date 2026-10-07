"""Shiina skin/theme engine — the theme SDK for every surface."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shiina_cli import skin_dynamic
from shiina_constants import get_shiina_home

logger = logging.getLogger(__name__)


@dataclass
class SkinConfig:
    """Complete skin configuration."""
    name: str
    description: str = ""
    colors: Dict[str, str] = field(default_factory=dict)
    # Paired palettes for the opposite background polarity (mirrors the desktop app's
    # colors/darkColors pairing): a light terminal prefers `light_colors` (falling back to
    # `colors`), and vice versa for `dark_colors`.
    light_colors: Dict[str, str] = field(default_factory=dict)
    dark_colors: Dict[str, str] = field(default_factory=dict)
    spinner: Dict[str, Any] = field(default_factory=dict)
    branding: Dict[str, str] = field(default_factory=dict)
    # Palette derived live from the desktop scheme: consumers must not re-adapt it (its polarity
    # already follows the wallpaper) — see cli.py's light-mode remap.
    dynamic: bool = False
    tool_prefix: str = "┊"
    tool_emojis: Dict[str, str] = field(default_factory=dict)  # per-tool emoji overrides
    banner_logo: str = ""    # Rich-markup ASCII art logo (replaces SHIINA_AGENT_LOGO)
    banner_hero: str = ""    # Rich-markup hero art (replaces SHIINA_CADUCEUS)
    # Terminal chrome design tokens for the TUI (`tui:` section): spacing density,
    # glyph overrides, border style, status-rule segment order. Passed through
    # verbatim — the renderer validates per token so a half-authored block still
    # renders (see ui-tui `design.ts`).
    tui: Dict[str, Any] = field(default_factory=dict)

    def get_color(self, key: str, fallback: str = "") -> str:
        return self.colors.get(key, fallback)

    def get_branding(self, key: str, fallback: str = "") -> str:
        return self.branding.get(key, fallback)

    def get_spinner_wings(self) -> List[Tuple[str, str]]:
        """Spinner wing pairs, or empty list if none."""
        return [(str(pair[0]), str(pair[1])) for pair in self.spinner.get("wings", [])
                if isinstance(pair, (list, tuple)) and len(pair) == 2]


def _branding(who: str, symbol: str, goodbye: str, prompt: str = "", help_header: str = "") -> Dict[str, str]:
    """Branding block for a "<who> Agent" persona keyed by its glyph."""
    return {
        "agent_name": f"{who} Agent",
        "symbol": symbol,
        "icon": symbol,
        "welcome": f"Welcome to {who} Agent! Type your message or /help for commands.",
        "goodbye": goodbye, "response_label": f" {symbol} {who} ", "prompt_symbol": prompt or symbol,
        "help_header": help_header or f"({symbol}) Available Commands"}


def _wings(*glyphs) -> List[List[str]]:
    """Spinner wing pairs `⟪g` / `g⟫`; a (left, right) tuple gives asymmetric glyphs."""
    return [[f"⟪{g[0] if isinstance(g, tuple) else g}", f"{g[1] if isinstance(g, tuple) else g}⟫"]
            for g in glyphs]


# Branding shared by every Shiina-named built-in (mono/daylight override help_header).
_SHIINA_BRANDING: Dict[str, str] = {
    "agent_name": "Shiina",
    "symbol": "›",
    "icon": "›",
    "welcome": "Type your message or /help for commands.",
    "goodbye": "Goodbye!",
    "response_label": " Shiina ",
    "prompt_symbol": ">",
    "help_header": "Available Commands",
}

def _codex_skin_dict() -> Dict[str, Any]:
    try:
        from shiina_cli.design_engine import load_design
        design = load_design("codex")
        c = dict(design.colors or {})
    except Exception:
        c = {}
    return {
        "name": "codex",
        "description": "Codex — pure YAML-driven configuration",
        "colors": {
            "background": c.get("background", ""),
            "banner_border": c.get("border", "#4b4b4b"),
            "banner_title": c.get("accent", "#8fd694"),
            "banner_accent": c.get("accent", "#8fd694"),
            "banner_dim": c.get("muted", "#8b8b8b"),
            "banner_text": c.get("text", "#d4d4d4"),
            "ui_accent": c.get("accent", "#8fd694"),
            "ui_label": c.get("label", "#8fd694"),
            "ui_text": c.get("text", "#d4d4d4"),
            "ui_border": c.get("border", "#4b4b4b"),
            "ui_tool": c.get("tool", "#9ca3af"),
            "ui_thinking": c.get("thinking", "#6b7280"),
            "ui_ok": c.get("ok", "#8fd694"),
            "ui_error": c.get("error", "#f7768e"),
            "ui_warn": c.get("warn", "#e0af68"),
            "diff_added": c.get("diffAdded", "#1c2e24"),
            "diff_removed": c.get("diffRemoved", "#321d24"),
            "diff_added_word": c.get("diffAddedWord", "#86efac"),
            "diff_removed_word": c.get("diffRemovedWord", "#fca5a5"),
            "syntax_string": c.get("syntaxString", "#8fd694"),
            "syntax_number": c.get("syntaxNumber", "#e0af68"),
            "syntax_keyword": c.get("syntaxKeyword", "#7aa2f7"),
            "syntax_comment": c.get("syntaxComment", "#6b7280"),
            "prompt": c.get("prompt", "#8fd694"),
            "input_rule": c.get("border", "#4b4b4b"),
            "response_border": c.get("border", "#4b4b4b"),
            "status_bar_bg": c.get("statusBg", "#2a2a2a"),
            "status_bar_text": c.get("statusFg", "#d4d4d4"),
            "status_bar_strong": c.get("accent", "#8fd694"),
            "status_bar_dim": c.get("muted", "#8b8b8b"),
            "status_bar_good": c.get("statusGood", "#8fd694"),
            "status_bar_warn": c.get("statusWarn", "#e0af68"),
            "status_bar_bad": c.get("statusBad", "#f7768e"),
            "status_bar_critical": c.get("statusCritical", "#f7768e"),
            "session_label": c.get("sessionLabel", "#9ca3af"),
            "session_border": c.get("sessionBorder", "#4b4b4b"),
            "completion_menu_bg": c.get("completionBg", "#2a2a2a"),
            "completion_menu_current_bg": c.get("completionCurrentBg", "#3a3a3a"),
            "selection_bg": c.get("selectionBg", "#3a3a3a"),
            "shell_dollar": c.get("shellDollar", "#7aa2f7"),
            "voice_status_bg": c.get("statusBg", "#2a2a2a"),
        },
        "spinner": {},
        "branding": _SHIINA_BRANDING,
        "tool_prefix": "›",
    }

_BUILTIN_SKINS: Dict[str, Dict[str, Any]] = {
    "default": _codex_skin_dict(),
    "codex": _codex_skin_dict(),
}

_active_skin: Optional[SkinConfig] = None
_active_skin_name: str = "codex"
# Routed multiplex profiles: (name, skin) per home key. ``display.skin`` and ``<home>/skins/*.yaml``
# are per profile, and the relay display name / TUI skin payload are read under each profile's
# override — one module slot would be last-writer-wins across profiles. Unscoped keeps the module slot.
_active_skin_by_home: Dict[str, Tuple[str, SkinConfig]] = {}


def _routed_home_key() -> Optional[str]:
    from shiina_constants import get_shiina_home_override, shiina_home_key
    return None if get_shiina_home_override() is None else shiina_home_key()


def _profile_config() -> dict:
    try:
        from shiina_cli.config import load_config_readonly
        return load_config_readonly() or {}
    except Exception:
        return {}


def _skins_dir() -> Path:
    return get_shiina_home() / "skins"


def _load_skin_from_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load a skin definition from a YAML file; None on any failure."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as e:
        logger.debug("Failed to load skin from %s: %s", path, e)
    return None


def _build_skin_config(data: Dict[str, Any], *, dynamic: bool = False) -> SkinConfig:
    """Build a SkinConfig from a raw dict (built-in or loaded from YAML)."""
    default = _BUILTIN_SKINS["default"]
    skin_name = str(data.get("name", "unknown"))

    def section(key: str) -> Dict[str, Any]:
        value = data.get(key)
        if isinstance(value, dict):
            return value
        if value is not None:
            logger.warning("Skin '%s' has invalid '%s' section type (%s); ignoring section",
                           skin_name, key, type(value).__name__)
        return {}

    def merged(key: str) -> Dict[str, Any]:
        return {**default.get(key, {}), **section(key)}
    # Paired palettes are NOT merged over the default skin's blocks: an empty block means
    # "no hand-tuned variant for that polarity" and consumers (the TUI) fall back to `colors`
    # + automatic adaptation, which beats the default's gold light palette under a crimson skin.
    return SkinConfig(
        name=skin_name, description=data.get("description", ""), colors=merged("colors"),
        light_colors=section("light_colors"), dark_colors=section("dark_colors"),
        spinner=merged("spinner"), branding=merged("branding"), dynamic=dynamic,
        tool_prefix=data.get("tool_prefix", default.get("tool_prefix", "┊")),
        tool_emojis=section("tool_emojis"), banner_logo=data.get("banner_logo", ""),
        banner_hero=data.get("banner_hero", ""), tui=section("tui"))


def list_skins() -> List[Dict[str, str]]:
    """Strictly codex only — zero built-in layouts or themes."""
    return [{"name": "codex", "description": "Codex — pure YAML-driven configuration", "source": "builtin"}]


def load_skin(name: str) -> SkinConfig:
    """Load a skin by name: user skins first, then built-in, then default.

    Dynamic skins (``caelestia``) get their colours from the live desktop scheme at load time;
    a user YAML of the same name still wins, so individual keys stay overridable.
    """
    canonical = _canonical_dynamic_name(name)
    loader_name = canonical or name
    user_file = _skins_dir() / f"{loader_name}.yaml"
    data = _load_skin_from_yaml(user_file) if user_file.is_file() else None
    if not data and loader_name not in _BUILTIN_SKINS:
        logger.warning("Skin '%s' not found, using default", name)
    data = data or _BUILTIN_SKINS.get(loader_name) or _BUILTIN_SKINS["default"]
    live = skin_dynamic.live_colors() if canonical else {}
    if live:
        data = {**data, "colors": {**(data.get("colors") or {}), **live}}
    # Only a skin that actually received a live palette counts as dynamic; a fallback to the
    # default colours must keep normal consumer adaptation (cli.py's light-mode remap).
    return _build_skin_config(data, dynamic=bool(live))


def _canonical_dynamic_name(name: str) -> str:
    """``caelestia`` for any dynamic alias, else "" (only the canonical name is listed)."""
    return skin_dynamic.DYNAMIC_SKIN_NAMES[0] if name in skin_dynamic.DYNAMIC_SKIN_NAMES else ""


def get_active_skin() -> SkinConfig:
    """Currently active skin config (cached)."""
    global _active_skin
    home_key = _routed_home_key()
    if home_key is not None:
        entry = _active_skin_by_home.get(home_key)
        if entry is None:
            # Cold routed profile: its own ``display.skin`` (nobody ran init_skin_from_config for it).
            init_skin_from_config(_profile_config())
            entry = _active_skin_by_home[home_key]
        # A dynamic skin tracks the desktop scheme: one stat decides whether to rebuild.
        if _canonical_dynamic_name(entry[0]) and skin_dynamic.scheme_changed():
            entry = _active_skin_by_home[home_key] = (entry[0], load_skin(entry[0]))
        return entry[1]
    if _active_skin is None:
        _active_skin = load_skin(_active_skin_name)
    elif _canonical_dynamic_name(_active_skin_name) and skin_dynamic.scheme_changed():
        _active_skin = load_skin(_active_skin_name)
    return _active_skin


def set_active_skin(name: str) -> SkinConfig:
    """Switch the active skin. Returns the new SkinConfig."""
    global _active_skin, _active_skin_name
    skin = load_skin(name)
    home_key = _routed_home_key()
    if home_key is not None:
        _active_skin_by_home[home_key] = (name, skin)
        return skin
    _active_skin_name = name
    _active_skin = skin
    return _active_skin


def get_active_skin_name() -> str:
    home_key = _routed_home_key()
    if home_key is not None:
        entry = _active_skin_by_home.get(home_key)
        return entry[0] if entry else "default"
    return _active_skin_name


def init_skin_from_config(config: dict) -> None:
    """Initialize the active skin from CLI config at startup."""
    display = config.get("display") or {}
    skin_name = display.get("skin", "default") if isinstance(display, dict) else "default"
    set_active_skin(skin_name.strip() if isinstance(skin_name, str) and skin_name.strip() else "default")


def _active_branding(key: str, fallback: str) -> str:
    try:
        return get_active_skin().get_branding(key, fallback)
    except Exception:
        return fallback


def get_active_prompt_symbol(fallback: str = "❯") -> str:
    """Interactive prompt symbol (skins store a bare token) plus a single trailing space."""
    cleaned = (_active_branding("prompt_symbol", fallback) or fallback).strip()
    return f"{cleaned or fallback.strip()} "


def get_active_brand_symbol(fallback: str = "★") -> str:
    """Active brand symbol / icon for prompt and status-bar decoration."""
    return (_active_branding("symbol", fallback) or _active_branding("icon", fallback) or fallback).strip()


def get_active_help_header(fallback: str = "(^_^)? Available Commands") -> str:
    return _active_branding("help_header", fallback)


def get_active_goodbye(fallback: str = "Goodbye! ★") -> str:
    return _active_branding("goodbye", fallback)


# Palette resolution order for prompt_toolkit styles: (name, skin color key, fallback). A
# fallback starting with "@" names an earlier entry (so a missing key inherits its remapped value).
_STYLE_PALETTE = (
    ("prompt", "prompt", ""), ("input_rule", "input_rule", "#CD7F32"),
    ("title", "banner_title", "#FFD700"), ("text", "banner_text", "#FFF8DC"),
    ("dim", "banner_dim", "#555555"), ("label", "ui_label", "@title"), ("warn", "ui_warn", "#FF8C00"),
    ("error", "ui_error", "#FF6B6B"), ("status_bg", "status_bar_bg", "#1a1a2e"),
    ("status_text", "status_bar_text", "@text"), ("status_strong", "status_bar_strong", "@title"),
    ("status_dim", "status_bar_dim", "@dim"), ("ok", "ui_ok", "#8FBC8F"),
    ("status_good", "status_bar_good", "@ok"), ("status_warn", "status_bar_warn", "@warn"),
    ("accent", "banner_accent", "@warn"), ("status_bad", "status_bar_bad", "@accent"),
    ("status_critical", "status_bar_critical", "@error"), ("voice_bg", "voice_status_bg", "@status_bg"),
    ("menu_bg", "completion_menu_bg", "#1a1a2e"), ("menu_current_bg", "completion_menu_current_bg", "#333355"),
    ("menu_meta_bg", "completion_menu_meta_bg", "@menu_bg"),
    ("menu_meta_current_bg", "completion_menu_meta_current_bg", "@menu_current_bg"))

# prompt_toolkit style class -> format template over the resolved palette names.
_STYLE_TEMPLATES = {
    "input-area": "",  # terminal default fg/bg — `prompt` styles the symbol, NOT typed text
    "placeholder": "{dim} italic", "prompt": "{prompt}", "prompt-working": "{dim} italic",
    "hint": "{dim} italic",
    "status-bar": "bg:{status_bg} {status_text}", "status-bar-strong": "bg:{status_bg} {status_strong} bold",
    "status-bar-model": "bg:{menu_current_bg} {status_strong} bold",
    "status-bar-session-title": "bg:{status_strong} {status_bg} bold",
    "status-bar-dim": "bg:{status_bg} {status_dim}", "status-bar-good": "bg:{status_bg} {status_good} bold",
    "status-bar-warn": "bg:{status_bg} {status_warn} bold", "status-bar-bad": "bg:{status_bg} {status_bad} bold",
    "status-bar-critical": "bg:{status_bg} {status_critical} bold",
    "status-bar-yolo": "bg:{status_bg} {status_critical} bold",
    "subagent-dock": "bg:{status_bg} {status_text}",
    "subagent-dock.heading": "bg:{status_bg} {status_strong} bold",
    "subagent-dock.selected": "bg:{menu_current_bg} {text} bold",
    "input-rule": "{input_rule}", "image-badge": "{label} bold",
    "completion-menu": "bg:{menu_bg} {text}", "completion-menu.completion": "bg:{menu_bg} {text}",
    "completion-menu.completion.current": "bg:{menu_current_bg} {title}",
    "completion-menu.meta.completion": "bg:{menu_meta_bg} {dim}",
    "completion-menu.meta.completion.current": "bg:{menu_meta_current_bg} {label}",
    "clarify-border": "{input_rule}", "clarify-title": "{title} bold", "clarify-question": "{text} bold",
    "clarify-choice": "{dim}", "clarify-selected": "{title} bold", "clarify-active-other": "{title} italic",
    "clarify-answer": "{ok} bold", "clarify-countdown": "{input_rule}",
    "sudo-prompt": "{error} bold", "sudo-border": "{input_rule}", "sudo-title": "{error} bold",
    "sudo-text": "{text}",
    "approval-border": "{input_rule}", "approval-title": "{warn} bold", "approval-desc": "{text} bold",
    "approval-cmd": "{dim} italic", "approval-choice": "{dim}", "approval-selected": "{title} bold",
    "voice-status": "bg:{voice_bg} {label}", "voice-status-recording": "bg:{voice_bg} {error} bold",
    "voice-prompt": "{accent}", "voice-recording": "{error} bold", "voice-processing": "{label} italic"}


def get_prompt_toolkit_style_overrides() -> Dict[str, str]:
    """Return prompt_toolkit style overrides derived from the active skin and design."""
    try:
        skin = get_active_skin()
    except Exception:
        return {}
    # `prompt` is unset by default so typed text inherits the terminal's foreground (readable
    # on light and dark schemes); skins opt into a colored prompt symbol via `prompt` in YAML.
    # Every read goes through skin.get_color (cli.py wraps it for light-mode remapping).
    palette: Dict[str, str] = {}
    for name, key, fallback in _STYLE_PALETTE:
        palette[name] = skin.get_color(key, palette[fallback[1:]] if fallback.startswith("@") else fallback)

    # Blend active design colors onto the CLI prompt_toolkit palette
    try:
        from shiina_cli.design_engine import get_active_design
        design_colors = get_active_design().colors or {}
        if "border" in design_colors:
            palette["input_rule"] = design_colors["border"]
            palette["dim"] = design_colors.get("muted", palette.get("dim", "#8b8b8b"))
        if "warn" in design_colors:
            palette["warn"] = design_colors["warn"]
        if "accent" in design_colors:
            palette["accent"] = design_colors["accent"]
            palette["title"] = design_colors["accent"]
        if "text" in design_colors:
            palette["text"] = design_colors["text"]
    except Exception:
        pass

    # This badge paints both sides; foreground-only light remapping destroys its contrast.
    palette["badge_bg"] = skin.colors.get(
        "status_bar_strong", skin.colors.get("banner_title", "#FFD700"))
    palette["badge_fg"] = skin.colors.get("status_bar_bg", "#1a1a2e")
    return {cls: tpl.format(**palette) for cls, tpl in _STYLE_TEMPLATES.items()}

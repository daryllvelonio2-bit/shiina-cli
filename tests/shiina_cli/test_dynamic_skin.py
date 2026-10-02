"""Dynamic skin palettes (caelestia): the palette follows the desktop scheme and stays readable.

Contract, not snapshot: whatever the scheme's polarity, text clears its contrast target on every
surface we paint on, semantic colours keep their meaning, and a scheme rewrite repaints without a
process restart.
"""

import json
import time
from pathlib import Path

import pytest

from shiina_cli import skin_dynamic
from shiina_cli import skin_engine

# A dark and a light Material-3 scheme (only the roles the mapper reads).
_DARK = {
    "surface": "110d10", "base": "110d10", "onSurface": "f1e1eb", "onSurfaceVariant": "b5a7b1",
    "outline": "7e727b", "outlineVariant": "4f454d", "primary": "e4bade", "tertiary": "ffcace",
    "secondary": "d9bfd3", "error": "f97386", "surfaceContainer": "1e181d",
    "surfaceContainerLow": "171216", "surfaceContainerHigh": "251d23",
    "surfaceContainerHighest": "2c232a",
}
_LIGHT = {
    "surface": "fdf6f0", "base": "fdf6f0", "onSurface": "2b1d18", "onSurfaceVariant": "574740",
    "outline": "8a7a72", "outlineVariant": "cbbdb4", "primary": "8c4a2f", "tertiary": "7d5260",
    "secondary": "6d5a52", "error": "b3261e", "surfaceContainer": "f2e9e2",
    "surfaceContainerLow": "f8f0ea", "surfaceContainerHigh": "ece2da",
    "surfaceContainerHighest": "e6dbd2",
}

# Keys consumers render as foreground text on our surfaces, with their enforced minimum.
_FOREGROUND_MINIMUMS = {
    "banner_text": 4.5, "ui_text": 4.5, "prompt": 4.5, "status_bar_text": 4.5,
    "ui_label": 4.0, "banner_title": 4.0, "banner_accent": 4.0, "status_bar_strong": 4.0,
    "ui_ok": 4.5, "ui_error": 4.5, "diff_added": 4.5, "diff_removed": 4.5,
    "status_bar_good": 4.5, "status_bar_bad": 4.5,
}
_SURFACE_KEYS = ("background", "status_bar_bg", "completion_menu_bg",
                 "completion_menu_current_bg", "voice_status_bg")


@pytest.fixture(autouse=True)
def _isolated_scheme(tmp_path, monkeypatch):
    """Point the scheme lookup at a temp desktop state dir and reset the module caches."""
    home = tmp_path / "home"
    state = tmp_path / "state" / "caelestia"
    state.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("SHIINA_HOME", raising=False)
    skin_dynamic.reset_cache()
    skin_engine.set_active_skin("shiina")
    yield state / "scheme.json"
    skin_dynamic.reset_cache()
    skin_engine.set_active_skin("shiina")


def _write_scheme(path: Path, colours: dict, mode: str = "dark") -> None:
    path.write_text(json.dumps({"name": "dynamic", "mode": mode, "colours": colours}))
    time.sleep(0.01)  # distinct mtime_ns for the change probe


def _worst_contrast(skin, key: str) -> float:
    color = skin.get_color(key)
    return min(skin_dynamic.contrast_ratio(color, skin.get_color(s)) for s in _SURFACE_KEYS)


# Keys the TUI (fromSkin) and the classic CLI consume — mirrors the authority list in
# tests/shiina_cli/test_skin_palettes.py (this file must stay runnable in its own subprocess).
_REQUIRED_KEYS = frozenset({
    "banner_border", "banner_title", "banner_accent", "banner_dim", "banner_text",
    "ui_accent", "ui_label", "ui_ok", "ui_error", "ui_warn", "prompt", "input_rule",
    "response_border", "status_bar_bg", "status_bar_text", "status_bar_strong",
    "status_bar_dim", "status_bar_good", "status_bar_warn", "status_bar_bad",
    "status_bar_critical", "session_label", "session_border", "completion_menu_bg",
    "completion_menu_current_bg", "selection_bg", "shell_dollar", "voice_status_bg",
})

# Foreground keys rendered on the terminal pole (the scheme's own background under a
# transparent terminal) and their floors, matching the TUI's STRONG/SOFT tiers.
_STRONG_FG = ("banner_title", "banner_accent", "banner_text", "ui_accent", "ui_label", "ui_ok",
              "ui_error", "prompt", "status_bar_strong", "status_bar_good", "status_bar_bad",
              "status_bar_critical", "shell_dollar")
_SOFT_FG = ("banner_dim", "banner_border", "ui_warn", "input_rule", "response_border",
            "status_bar_dim", "status_bar_warn", "session_label", "session_border")


@pytest.mark.parametrize("colours", [_DARK, _LIGHT], ids=["dark", "light"])
def test_palette_is_complete_and_meets_the_pole_floors(_isolated_scheme, colours):
    """The dynamic palette carries the whole product contract, not just our own floors."""
    _write_scheme(_isolated_scheme, colours, mode="light" if colours is _LIGHT else "dark")
    skin = skin_engine.load_skin("caelestia")
    pole = skin.get_color("background")

    assert _REQUIRED_KEYS - skin.colors.keys() == set()
    weak = {key: round(skin_dynamic.contrast_ratio(skin.get_color(key), pole), 2)
            for key in _STRONG_FG if skin_dynamic.contrast_ratio(skin.get_color(key), pole) < 3.9}
    weak |= {key: round(skin_dynamic.contrast_ratio(skin.get_color(key), pole), 2)
             for key in _SOFT_FG if skin_dynamic.contrast_ratio(skin.get_color(key), pole) < 2.8}
    assert weak == {}


@pytest.mark.parametrize("colours", [_DARK, _LIGHT], ids=["dark", "light"])
def test_fills_match_the_scheme_polarity(_isolated_scheme, colours):
    """Fills must never be a light surface in a dark scheme (or the reverse)."""
    is_light = colours is _LIGHT
    _write_scheme(_isolated_scheme, colours, mode="light" if is_light else "dark")
    skin = skin_engine.load_skin("caelestia")

    for key in ("status_bar_bg", "completion_menu_bg", "completion_menu_current_bg",
                "selection_bg", "voice_status_bg"):
        lum = skin_dynamic._luminance(skin.get_color(key))
        assert (lum > 0.4) if is_light else (lum < 0.35), f"{key} fill polarity: lum {lum:.2f}"


def test_selection_chip_is_distinguishable(_isolated_scheme):
    _write_scheme(_isolated_scheme, _DARK)
    skin = skin_engine.load_skin("caelestia")

    assert skin_dynamic.contrast_ratio(skin.get_color("completion_menu_current_bg"),
                                      skin.get_color("completion_menu_bg")) >= 1.15


def test_semantic_colors_follow_the_scheme_hue(_isolated_scheme):
    """Harmonized anchors track the wallpaper's hue while keeping their own identity."""
    _write_scheme(_isolated_scheme, _DARK)  # a pink-family scheme
    pink = skin_engine.load_skin("caelestia")
    _write_scheme(_isolated_scheme, {**_LIGHT, "primary": "1f4d8f", "tertiary": "2f5f7f"},
                  mode="light")  # a blue-family scheme
    blue = skin_engine.load_skin("caelestia")

    assert pink.get_color("ui_ok") != blue.get_color("ui_ok")
    assert pink.get_color("ui_warn") != blue.get_color("ui_warn")
    # ...and the identity survives: success stays green in both.
    for skin in (pink, blue):
        r, g, b = skin_dynamic._rgb(skin.get_color("ui_ok"))
        assert g > r and g > b


def test_art_recolours_into_the_scheme_hue(_isolated_scheme):
    """The banner artwork follows the wallpaper instead of shipping a fixed shade ladder."""
    _write_scheme(_isolated_scheme, _DARK)
    art = "[#60a5fa]█[/][#3b82f6]█[/][#2563eb]█[/]"

    recolored = skin_dynamic.recolor_markup(art)

    shades = [m for m in recolored.split("[") if m.startswith("#")]
    assert len(shades) == 3 and "#60a5fa" not in recolored
    # Shading order survives: the brightest original tone stays the brightest.
    lums = [skin_dynamic._luminance("#" + s[1:7]) for s in shades]
    assert lums == sorted(lums, reverse=True)
    assert skin_dynamic._rgb("#" + shades[0][1:7]) == skin_dynamic._rgb(
        skin_dynamic._read_scheme()["primary"])


def test_art_is_untouched_without_a_scheme():
    art = "[#60a5fa]█[/][#2563eb]█[/]"

    assert skin_dynamic.recolor_markup(art, {}) == art


@pytest.mark.parametrize("colours", [_DARK, _LIGHT], ids=["dark", "light"])
def test_every_foreground_clears_its_contrast_target(_isolated_scheme, colours):
    """Stronger than the pole floors: every foreground clears its own floor on EVERY surface."""
    _write_scheme(_isolated_scheme, colours, mode="light" if colours is _LIGHT else "dark")

    skin = skin_engine.load_skin("caelestia")

    assert skin.dynamic
    assert skin.name == "caelestia"
    low = {key: round(_worst_contrast(skin, key), 2) for key, floor in _FOREGROUND_MINIMUMS.items()
           if _worst_contrast(skin, key) < floor}
    assert low == {}


def test_palette_polarity_follows_the_scheme(_isolated_scheme):
    _write_scheme(_isolated_scheme, _DARK)
    dark = skin_engine.load_skin("caelestia")

    _write_scheme(_isolated_scheme, _LIGHT, mode="light")
    light = skin_engine.load_skin("caelestia")

    # Light text on the dark scheme, dark text on the light one — the relationship is the contract.
    assert skin_dynamic._luminance(dark.get_color("ui_text")) > skin_dynamic._luminance(
        dark.get_color("background"))
    assert skin_dynamic._luminance(light.get_color("ui_text")) < skin_dynamic._luminance(
        light.get_color("background"))
    assert dark.get_color("ui_text") != light.get_color("ui_text")


@pytest.mark.parametrize("colours", [_DARK, _LIGHT], ids=["dark", "light"])
def test_semantic_colors_keep_their_hue(_isolated_scheme, colours):
    """A wallpaper-derived "green" is often warm; success/error must not follow it."""
    _write_scheme(_isolated_scheme, colours, mode="light" if colours is _LIGHT else "dark")
    skin = skin_engine.load_skin("caelestia")

    def hue(hex_color: str) -> float:
        r, g, b = (c / 255 for c in skin_dynamic._rgb(hex_color))
        high, low = max(r, g, b), min(r, g, b)
        if high == low:
            return 0.0
        delta = high - low
        if high == r:
            return (60 * ((g - b) / delta)) % 360
        return 60 * ((b - r) / delta) + 120 if high == g else 60 * ((r - g) / delta) + 240

    assert 70 <= hue(skin.get_color("ui_ok")) <= 180
    assert hue(skin.get_color("ui_error")) <= 30 or hue(skin.get_color("ui_error")) >= 330


def test_scheme_rewrite_repaints_without_restart(_isolated_scheme):
    _write_scheme(_isolated_scheme, _DARK)
    skin_engine.set_active_skin("caelestia")
    first = skin_engine.get_active_skin()

    _write_scheme(_isolated_scheme, _LIGHT, mode="light")
    second = skin_engine.get_active_skin()

    assert second.get_color("background") != first.get_color("background")
    assert not skin_dynamic.scheme_changed()  # the rebuild consumed the change


def test_static_skin_never_stats_the_scheme(_isolated_scheme, monkeypatch):
    calls = []
    _write_scheme(_isolated_scheme, _DARK)
    monkeypatch.setattr(skin_dynamic, "scheme_generation", lambda: calls.append(1) or ())
    skin_engine.set_active_skin("shiina")

    skin_engine.get_active_skin()

    assert calls == [] and not skin_engine.get_active_skin().dynamic


def test_missing_scheme_falls_back_to_the_default_palette(_isolated_scheme):
    skin = skin_engine.load_skin("caelestia")  # fixture dir exists, file does not

    assert not skin.dynamic
    assert skin.get_color("background") == skin_engine.load_skin("default").get_color("background")


def test_list_skins_offers_the_dynamic_skin():
    assert "caelestia" in {s["name"] for s in skin_engine.list_skins()}


def test_enforce_contrast_is_idempotent_and_moves_the_right_way():
    surfaces = ["#fdf6f0", "#ece2da"]
    lifted = skin_dynamic.enforce_contrast("#eeeeee", surfaces, 4.5)

    assert skin_dynamic._worst_ratio(lifted, [skin_dynamic._luminance(s) for s in surfaces]) >= 4.5
    assert skin_dynamic._luminance(lifted) < skin_dynamic._luminance("#eeeeee")
    assert skin_dynamic.enforce_contrast(lifted, surfaces, 4.5) == lifted

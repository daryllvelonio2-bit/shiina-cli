"""No CLI chrome class may render a hardcoded color: the skin palette must cover every one.

The classic CLI builds its prompt_toolkit style by layering the active skin over
``cli._TUI_STYLE_FALLBACK``. A class that exists only in the fallback keeps its literal color no
matter which skin is active — the hardcoded-color bug this pins shut.
"""

from cli import _TUI_STYLE_FALLBACK
from shiina_cli import skin_engine


def test_every_fallback_class_is_covered_by_the_skin_palette():
    uncovered = sorted(set(_TUI_STYLE_FALLBACK) - set(skin_engine.get_prompt_toolkit_style_overrides()))

    assert uncovered == []


def test_skin_palette_has_no_unresolved_tokens():
    """Every style must resolve to real values (a missing palette name renders as `None`)."""
    broken = {name: style for name, style in skin_engine.get_prompt_toolkit_style_overrides().items()
              if style is None or "None" in str(style)}

    assert broken == {}


def test_semantic_chrome_classes_follow_the_skin():
    """Spot-check the classes that were hardcoded: they must move with the palette."""
    for skin_name in ("default", "ares", "caelestia"):
        skin_engine.set_active_skin(skin_name)
        style = skin_engine.get_prompt_toolkit_style_overrides()
        skin = skin_engine.get_active_skin()

        assert skin.get_color("status_bar_critical") in style["status-bar-yolo"]
        assert skin.get_color("ui_ok") in style["clarify-answer"]
        assert skin.get_color("ui_error") in style["voice-recording"]
        assert skin.get_color("ui_accent") in style["voice-prompt"]
        # The model pill is a chip with its own palette fill, and its text stays readable on it.
        assert skin.get_color("completion_menu_current_bg") in style["status-bar-model"]
    skin_engine.set_active_skin("default")


def test_model_pill_text_contrasts_with_its_fill():
    """The pill's fill and text are both palette values — they must not collide."""
    for skin_name in ("default", "ares", "caelestia", "daylight"):
        skin_engine.set_active_skin(skin_name)
        skin = skin_engine.get_active_skin()
        fill, text = skin.get_color("completion_menu_current_bg"), skin.get_color("status_bar_strong")

        assert fill and text and fill != text, skin_name
    skin_engine.set_active_skin("default")

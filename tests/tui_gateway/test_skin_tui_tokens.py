"""The skin's ``tui:`` block — chrome design tokens (spacing, glyphs, segment order).

The block is producer-owned data: the skin engine carries it verbatim and the
renderer validates each token, so these tests pin the plumbing (a typo in one
token must not cost the whole block) and the payload shape the TUI consumes.
"""

from shiina_cli.skin_engine import SkinConfig, _build_skin_config
from tui_gateway import server

# The handler bodies are rebound onto the server's globals at install time, so
# the RPC surface is the real call site (and the attribute is runtime-injected,
# hence getattr rather than a static import).
resolve_skin = getattr(server, "resolve_skin")

TUI_BLOCK = {
    "density": "compact",
    "glyphs": {"chevronOpen": "v", "separator": " :: "},
    "status_bar": {"segments": ["bg", "duration"]},
}


def test_tui_block_is_carried_through_the_skin_config():
    skin = _build_skin_config({"name": "probe", "tui": TUI_BLOCK})

    assert skin.tui == TUI_BLOCK


def test_missing_tui_block_stays_empty():
    assert _build_skin_config({"name": "probe"}).tui == {}


def test_malformed_tui_block_is_ignored_like_every_other_section():
    """A ``tui: compact`` typo must not raise or leak a non-dict into the payload."""
    assert _build_skin_config({"name": "probe", "tui": "compact"}).tui == {}


def test_resolve_skin_payload_carries_the_tokens(monkeypatch):
    monkeypatch.setattr(
        "shiina_cli.skin_engine.get_active_skin",
        lambda: SkinConfig(name="probe", tui=TUI_BLOCK),
    )
    monkeypatch.setattr("shiina_cli.skin_engine.init_skin_from_config", lambda config: None)

    payload = resolve_skin()

    assert payload["tui"] == TUI_BLOCK
    # Colour/branding plumbing is untouched by the addition.
    assert payload["name"] == "probe"


class _LegacySkin:
    """A skin object from before this feature existed — no `tui` attribute."""

    name = "legacy"
    branding = {}
    banner_logo = ""
    banner_hero = ""
    tool_prefix = "┊"
    colors = {}
    light_colors = {}
    dark_colors = {}


def test_resolve_skin_defaults_to_an_empty_block(monkeypatch):
    monkeypatch.setattr("shiina_cli.skin_engine.get_active_skin", lambda: _LegacySkin())
    monkeypatch.setattr("shiina_cli.skin_engine.init_skin_from_config", lambda config: None)

    assert resolve_skin()["tui"] == {}

"""``display.design`` is the TUI's visual-design knob (the design folder).

The renderer reads the RESOLVED design from the skin payload (``gateway.ready`` /
``skin.changed``) and switches live through ``config.set``, which persists
``display.design`` and lets the change watcher repaint. Both halves of the
reader/registry invariant are asserted here through the loader the TUI actually
uses: the key is registered in DEFAULT_CONFIG *and* read back normalised, so a
missing entry cannot leave ``/design`` reporting a switch that never lands.

The accepted set is the design FOLDER rather than a static list, so the tests
assert against names that ship in ``shiina_cli/designs/`` — always present, since
built-ins load regardless of the home.
"""

import pytest
import yaml

from shiina_cli.config_defaults import DEFAULT_CONFIG
from tui_gateway import server


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_shiina_home", tmp_path)
    server._cfg_cache = server._cfg_sig = server._cfg_path = None
    yield tmp_path / "config.yaml"
    server._cfg_cache = server._cfg_sig = server._cfg_path = None


def _get():
    return server._methods["config.get"](1, {"key": "design"})["result"]


def _set(value):
    return server._methods["config.set"](1, {"key": "design", "value": value})


def test_default_config_registers_the_key():
    assert DEFAULT_CONFIG["display"]["design"] == "default"


def test_absent_key_resolves_to_the_default_rather_than_blanking(config_home):
    # Fail-safe with the renderer's resolver: an unset key (the overwhelmingly
    # common case) reads back as the built-in look, never as None or a blank.
    config_home.write_text("display:\n  tui_compact: true\n", encoding="utf-8")

    assert _get() == {"value": "default"}


def test_set_persists_and_reads_back(config_home):
    assert _set("timeline")["result"] == {"key": "design", "value": "timeline"}
    assert yaml.safe_load(config_home.read_text(encoding="utf-8"))["display"]["design"] == "timeline"
    assert _get() == {"value": "timeline"}

    # Whitespace tolerated, like the other word setters.
    assert _set(" minimal ")["result"]["value"] == "minimal"
    assert _get() == {"value": "minimal"}


def test_unknown_design_is_refused_rather_than_written(config_home):
    answer = _set("emacs")

    assert answer["error"]["code"] == 4002
    assert "unknown design" in answer["error"]["message"]
    assert not config_home.exists()


def test_a_name_that_is_not_a_design_reads_back_as_default(config_home):
    # Written by hand (or by an older build): the reader must not surface a name
    # the renderer cannot resolve, or `/design` would report a switch that the
    # engine is going to silently ignore.
    config_home.write_text("display:\n  design: emacs\n", encoding="utf-8")
    server._cfg_cache = server._cfg_sig = server._cfg_path = None

    assert _get() == {"value": "default"}


def test_the_skin_payload_carries_the_design(config_home):
    # The one wire every consumer agrees on: the resolved design plus the
    # catalog `/design` offers.
    from shiina_cli.design_engine import design_names

    payload = server.resolve_skin()

    assert "design" in payload and "designs" in payload
    assert set(payload["designs"]) >= {"default", "minimal", "studio", "timeline"}
    assert payload["designs"] == design_names()


def test_the_default_design_is_an_empty_no_op(config_home):
    # `default` declares nothing, which is what makes "no design" and "the
    # built-in look" the same thing — the renderer maps {} to null and the theme
    # keeps referential equality.
    _set("default")

    payload = server.resolve_skin()["design"]

    assert payload == {}


def test_a_real_design_resolves_to_its_palette(config_home):
    _set("timeline")

    payload = server.resolve_skin()["design"]

    assert payload["name"] == "timeline"
    assert payload["prompt"] == "▌"
    assert len(payload["colors"]) > 0
    assert payload["spinner"]["think"]

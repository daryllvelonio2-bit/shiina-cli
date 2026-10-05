"""``display.layout`` is the TUI's structural-layout knob (minimal | workbench | studio).

The renderer reads it from ``config.get full`` and switches live through
``config.set`` (the ``useConfigSync`` mtime poll → ``applyDisplay``). Both halves
of the reader/registry invariant are asserted here through the loader the TUI
actually uses (``tui_gateway`` → ``load_user_config_effective``): the key is
registered in DEFAULT_CONFIG *and* read back normalised, so a missing entry
cannot leave ``/layout`` reporting a switch that never lands.
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
    return server._methods["config.get"](1, {"key": "layout"})["result"]


def _set(value):
    return server._methods["config.set"](1, {"key": "layout", "value": value})


def test_default_config_registers_the_key():
    assert DEFAULT_CONFIG["display"]["layout"] == "workbench"


def test_absent_key_resolves_to_the_default_rather_than_blanking(config_home):
    # Fail-safe contract with the renderer's normalizeLayout: an unset key (the
    # overwhelmingly common case) reads back as today's layout, never as None.
    config_home.write_text("display:\n  tui_compact: true\n", encoding="utf-8")

    assert _get() == {"value": "workbench"}


def test_set_persists_and_reads_back_through_the_tui_loader(config_home):
    assert _set("studio")["result"] == {"key": "layout", "value": "studio"}
    assert yaml.safe_load(config_home.read_text(encoding="utf-8"))["display"]["layout"] == "studio"
    assert _get() == {"value": "studio"}

    # Normalised like the renderer's parseLayout: case/space tolerant.
    assert _set(" Minimal ")["result"]["value"] == "minimal"
    assert _get() == {"value": "minimal"}


def test_unknown_layout_is_refused_rather_than_written(config_home):
    answer = _set("emacs")

    assert answer["error"]["code"] == 4002
    assert not config_home.exists()

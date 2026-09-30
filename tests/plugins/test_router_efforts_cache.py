"""The Ramp Router plugin's disk-mirror TTL must exist.

Regression: ``_DISK_TTL_SECONDS`` was referenced in ``_load_disk`` and ``_efforts_cache_only``
but never defined, so every ``supported_reasoning_efforts()`` call on a warm disk mirror raised
``NameError`` — past the ``except Exception`` that guards only the read itself.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def router_plugin(monkeypatch):
    """Load the plugin by path: its parent dir (``model-providers``) is not importable."""
    name = "router_plugin_under_test"
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[2] / "plugins" / "model-providers" / "router" / "__init__.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)

    module = sys.modules[name]
    # Module-level cache slots (the unscoped ``_state()`` holder) are shared across tests.
    module._efforts_cache = None
    module._disk_checked = False
    module._warm_started = False
    return module


def _write_mirror(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "router_catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_stale_disk_mirror_is_served_and_triggers_a_warm(router_plugin, monkeypatch, tmp_path):
    """A mirror older than the TTL is still served (hot path must never issue HTTP) while a
    background refresh is kicked off."""
    warms: list[int] = []
    monkeypatch.setattr(router_plugin, "_warm_efforts_async", lambda: warms.append(1))
    monkeypatch.setattr(
        router_plugin, "_disk_path",
        lambda: _write_mirror(tmp_path, {
            "ts": time.time() - router_plugin._DISK_TTL_SECONDS - 60,
            "efforts": {"m": ["low"]},
        }),
    )

    assert router_plugin._efforts_cache_only() == {"m": ["low"]}
    assert warms == [1]


def test_fresh_disk_mirror_is_served_without_a_warm(router_plugin, monkeypatch, tmp_path):
    warms: list[int] = []
    monkeypatch.setattr(router_plugin, "_warm_efforts_async", lambda: warms.append(1))
    monkeypatch.setattr(
        router_plugin, "_disk_path",
        lambda: _write_mirror(tmp_path, {"ts": time.time(), "efforts": {"m": ["low"]}}),
    )

    assert router_plugin._efforts_cache_only() == {"m": ["low"]}
    assert warms == []


def test_unparseable_timestamp_reports_the_ttl_as_age(router_plugin, monkeypatch, tmp_path):
    """A mirror with a corrupt ``ts`` reads as exactly one TTL old, so callers treat it as stale."""
    monkeypatch.setattr(
        router_plugin, "_disk_path",
        lambda: _write_mirror(tmp_path, {"ts": "not-a-number", "efforts": {"m": ["low"]}}),
    )

    parsed, age = router_plugin._load_disk()

    assert parsed == {"m": ["low"]}
    assert age == router_plugin._DISK_TTL_SECONDS

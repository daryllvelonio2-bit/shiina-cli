"""Red-on-base guard: entry-point provider discovery reads the opt-in gate first.

``providers/__init__.py::_discover_entry_point_providers()`` runs during
``import shiina_cli.config`` (``_inject_profile_env_vars`` calls
``list_providers()``).  On a stock install ``plugins.enabled`` is unset, and the
fix makes the function return BEFORE importing ``importlib.metadata`` and the
plugin-manager facade (``shiina_cli.plugins``) — that import was ~345 ms spent
for nothing on every CLI start.

The load-bearing property is only observable in a FRESH interpreter, so the
guard shells out to ``python -c`` with ``cwd`` = the repo root (so the checked-out
tree wins over a venv editable install) and an empty ``SHIINA_HOME``.

Red-on-base: on ``cb326dc`` (pre-fix) an empty home still leaves both
``shiina_cli.plugins`` and ``importlib.metadata`` in ``sys.modules``, so the
first test fails there.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_PROBE = (
    "import shiina_cli.config, sys; "
    "print('shiina_cli.plugins' in sys.modules, "
    "'importlib.metadata' in sys.modules)"
)


@pytest.fixture()
def empty_home(tmp_path, monkeypatch):
    """Isolated, empty SHIINA_HOME: no config.yaml, no plugins installed.

    Mirrors the ``tests/shiina_cli/test_profiles.py`` pattern (``Path.home`` mock
    plus ``SHIINA_HOME``) so nothing reads the real user home.
    """
    home = tmp_path / ".shiina"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("SHIINA_HOME", str(home))
    return home


def _probe() -> tuple[bool, bool]:
    """Run the fresh-interpreter probe; return (plugins_loaded, metadata_loaded)."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"probe failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    plugins, metadata = result.stdout.split()
    return plugins == "True", metadata == "True"


def test_disabled_gate_imports_neither_metadata_nor_facade(empty_home):
    """Stock install (``plugins.enabled`` unset) must not pay the import."""
    plugins, metadata = _probe()
    assert not plugins, "shiina_cli.plugins imported despite plugins.enabled unset"
    assert not metadata, "importlib.metadata imported despite plugins.enabled unset"


def test_enabled_gate_still_imports_metadata_and_facade(empty_home):
    """``plugins.enabled`` set: the enabled path must stay fully intact."""
    (empty_home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - some-plugin\n", encoding="utf-8"
    )
    plugins, metadata = _probe()
    assert plugins, "shiina_cli.plugins not imported on the enabled path"
    assert metadata, "importlib.metadata not imported on the enabled path"

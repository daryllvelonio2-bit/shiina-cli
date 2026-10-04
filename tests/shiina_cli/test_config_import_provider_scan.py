"""Importing ``shiina_cli.config`` must not trigger the pip entry-point provider scan.

``config.py`` runs ``_inject_profile_env_vars()`` at module scope, which reaches
``providers._discover_entry_point_providers()``. On a stock install ``plugins.enabled`` is
unset, so that scan must bail out BEFORE importing ``importlib.metadata`` and the
plugin-manager facade (``shiina_cli.plugins``). Regression guard for PLAN-OPT8.

Subprocess assertion on purpose: pytest/conftest import ``shiina_cli.config`` during
collection, so an in-process ``sys.modules`` check cannot witness the first import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PROBE = """
import sys
import shiina_cli.config as cfg

assert "shiina_cli.plugins" not in sys.modules, "config import pulled in shiina_cli.plugins"
assert "importlib.metadata" not in sys.modules, "config import pulled in importlib.metadata"
assert cfg.OPTIONAL_ENV_VARS, "OPTIONAL_ENV_VARS empty: profile env injection did not run"
print("OK", len(cfg.OPTIONAL_ENV_VARS))
"""


def test_config_import_skips_entry_point_provider_scan(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, SHIINA_HOME=str(home), PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("OK"), proc.stdout

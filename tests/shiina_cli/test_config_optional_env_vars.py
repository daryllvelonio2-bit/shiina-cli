"""Regression net for PLAN-OPT8: importing ``shiina_cli.config`` must still inject the
env vars of bundled and ``$SHIINA_HOME`` model-provider plugins into ``OPTIONAL_ENV_VARS``.

PLAN-OPT8 makes the pip entry-point provider scan opt-in. The filesystem discovery of
bundled + ``$SHIINA_HOME/plugins/model-providers/*`` profiles must keep running and keep
contributing .env keys — this guards that path. It is green before AND after the fix
(a guard, not a proof of the fix).

Subprocess assertion on purpose: pytest/conftest import ``shiina_cli.config`` at
collection time, so in-process ``sys.modules`` / ``OPTIONAL_ENV_VARS`` are already
polluted and cannot witness the import-time injection under a fresh ``SHIINA_HOME``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PLUGIN_YAML = """\
name: acme-provider
kind: model-provider
version: 1.0.0
description: Acme test provider
"""

_PLUGIN_INIT = """\
from providers import register_provider
from providers.base import ProviderProfile

register_provider(
    ProviderProfile(
        name="acme",
        auth_type="api_key",
        env_vars=("ACME_API_KEY", "ACME_BASE_URL"),
    )
)
"""

# Fresh interpreter: import the config facade (which runs _inject_profile_env_vars at
# module scope) and report the OPTIONAL_ENV_VARS entries we care about.
_PROBE = """\
import json
from shiina_cli.config import OPTIONAL_ENV_VARS

keys = ("ACME_API_KEY", "ACME_BASE_URL", "DEEPINFRA_API_KEY")
print("__RESULT__" + json.dumps({k: OPTIONAL_ENV_VARS.get(k) for k in keys}))
"""


def _make_home(tmp_path: Path) -> Path:
    home = tmp_path / "shiina_home"
    plugin = home / "plugins" / "model-providers" / "acme"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text(_PLUGIN_YAML, encoding="utf-8")
    (plugin / "__init__.py").write_text(_PLUGIN_INIT, encoding="utf-8")
    return home


def _probe(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("SHIINA_HOME", "PYTHONPATH")}
    env["SHIINA_HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])
    raise AssertionError(f"probe produced no result:\n{proc.stdout}\n{proc.stderr}")


def test_bundled_and_user_provider_env_vars_injected(tmp_path):
    result = _probe(_make_home(tmp_path))

    # $SHIINA_HOME model-provider plugin self-registers and its env vars land.
    assert result["ACME_API_KEY"] is not None, result
    assert result["ACME_API_KEY"]["password"] is True, result
    assert result["ACME_BASE_URL"] is not None, result
    assert result["ACME_BASE_URL"]["password"] is False, result

    # A bundled provider key is still injected (not statically declared in config.py).
    assert result["DEEPINFRA_API_KEY"] is not None, result
    assert result["DEEPINFRA_API_KEY"]["password"] is True, result

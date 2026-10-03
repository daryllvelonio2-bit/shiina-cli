"""Regression for PLAN-9 s1: ``shiina_cli.main`` must not request the config facade.

Importing ``shiina_cli.main`` used to request the ``shiina_cli.config`` facade from *inside
main.py* twice: an eager ``from shiina_cli.config import get_shiina_home`` at module scope and
the ``shiina_cli.config_effective`` import (which itself pulls ``shiina_cli.config``). Both are
now gone from main.py — the home helper is served by ``shiina_constants`` (same object) and the
effective-config import is deferred into the ``config.yaml``-exists branch where the name is
actually used.

Note: ``shiina_cli.config_effective`` still ends up in ``sys.modules`` on a fresh home, because
``shiina_logging.setup_logging`` (invoked at main.py:690) reads ``logging.*`` through it. This
test therefore asserts what main.py owes — that *no* ``shiina_cli.config`` /
``shiina_cli.config_effective`` import request originates in main.py — not module absence.

Each assertion runs in a subprocess so the import graph is pristine; ``PYTHONPATH`` pins the
worktree over the shared editable install.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Records the *direct* requester frame (skipping the importlib machinery frames) of every
# request for the two config-facade modules, then reports how many came from main.py.
_HOOK = r"""
import os, sys

WT = os.environ["WT"]
MAIN = os.path.join(WT, "shiina_cli", "main.py")


class _Finder:
    def __init__(self):
        self.hits = []

    def find_spec(self, name, path=None, target=None):
        if name in ("shiina_cli.config", "shiina_cli.config_effective"):
            frame = sys._getframe(1)
            while frame is not None and "importlib" in frame.f_code.co_filename:
                frame = frame.f_back
            if frame is not None:
                self.hits.append((name, os.path.abspath(frame.f_code.co_filename)))
        return None


_f = _Finder()
sys.meta_path.insert(0, _f)
import shiina_cli.main  # noqa: F401

for _mod in ("shiina_cli.config", "shiina_cli.config_effective"):
    _n = sum(1 for name, fn in _f.hits if name == _mod and fn == MAIN)
    print("MAIN_REQUESTERS_%s=%d" % (_mod.rsplit(".", 1)[-1], _n))
"""


def _import_probe(home: Path) -> dict:
    env = dict(os.environ)
    env["SHIINA_HOME"] = str(home)
    env["WT"] = str(REPO_ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    proc = subprocess.run(
        [sys.executable, "-c", _HOOK],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    values: dict = {}
    for line in proc.stdout.splitlines():
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def test_import_main_requests_no_config_facade(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    probe = _import_probe(home)
    # (a) no `shiina_cli.config` request from main.py (was 1, main.py:649)
    assert probe["MAIN_REQUESTERS_config"] == "0", probe
    # (b) no `shiina_cli.config_effective` request from main.py (was 1, main.py:666)
    assert probe["MAIN_REQUESTERS_config_effective"] == "0", probe

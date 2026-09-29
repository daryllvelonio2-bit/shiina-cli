"""Resolve SHIINA_HOME for standalone skill scripts.

Skill scripts may run outside the Shiina process (e.g. system Python,
nix env, CI) where ``shiina_constants`` is not importable.  This module
provides the same ``get_shiina_home()`` and ``display_shiina_home()``
contracts as ``shiina_constants`` without requiring it on ``sys.path``.

When ``shiina_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``shiina_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``SHIINA_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from shiina_constants import display_shiina_home as display_shiina_home
    from shiina_constants import get_shiina_home as get_shiina_home
except (ModuleNotFoundError, ImportError):

    def get_shiina_home() -> Path:
        """Return the Shiina home directory (default: ~/.shiina).

        Mirrors ``shiina_constants.get_shiina_home()``."""
        val = os.environ.get("SHIINA_HOME", "").strip()
        return Path(val) if val else Path.home() / ".shiina"

    def display_shiina_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``shiina_constants.display_shiina_home()``."""
        home = get_shiina_home()
        try:
            return "~/" + home.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(home)

"""Resolve SHIINA_HOME for standalone skill scripts.

Skill scripts may run outside the Shiina process (system Python, nix env,
CI) where ``shiina_constants`` is not importable.  This module provides the
same ``get_shiina_home()`` contract without requiring it on ``sys.path``.

When ``shiina_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from shiina_constants import get_shiina_home as get_shiina_home
except (ModuleNotFoundError, ImportError):

    def get_shiina_home() -> Path:
        """Return the Shiina home directory (default: ``~/.shiina``)."""
        val = os.environ.get("SHIINA_HOME", "").strip()
        return Path(val) if val else Path.home() / ".shiina"

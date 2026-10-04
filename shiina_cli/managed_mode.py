"""Managed mode (NixOS declarative config) detection.

Deliberately outside ``config.py``: imports only os, pathlib and shiina_constants, so
light readers (``shiina_logging``) can ask ``is_managed()`` without pulling the config
facade. ``config.py`` re-exports the entry points.
"""

import os
from pathlib import Path
from typing import Optional

from shiina_constants import get_shiina_home

_MANAGED_TRUE_VALUES = ("true", "1", "yes")
_NIX_MANAGED_SYSTEMS = {"nixos", "home-manager"}
# Only the NixOS module ever wrote a bare "true" or an empty marker.
_LEGACY_MANAGED_SYSTEM = "nixos"
# Nix store root; identifies `nix run` / `nix profile install` installs (which don't set
# SHIINA_MANAGED). Module-level so tests can patch it without touching /nix/store.
_NIX_STORE = Path("/nix/store")
# Homebrew is no longer a supported distribution: these markers fall through to git/unknown
# detection instead of blocking config writes.
_IGNORED_MANAGED_VALUES = frozenset({"brew", "homebrew"})
# Explicit opt-out (``SHIINA_MANAGED=false``): without this a bool-shaped value became a package
# manager literally named "false" and is_managed() blocked `shiina update` (#12864).
_MANAGED_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def get_managed_system() -> Optional[str]:
    """Return the package manager owning this install, if any.
    Signals: SHIINA_MANAGED env var (systemd service) or a ``.managed`` marker file in
    SHIINA_HOME (NixOS activation script — interactive shells don't see the service env)."""
    marker = os.getenv("SHIINA_MANAGED", "").strip().lower() or None
    managed_marker = get_shiina_home() / ".managed"
    if marker is None and managed_marker.exists():
        try:
            marker = managed_marker.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            marker = ""
    if marker is None or marker in _IGNORED_MANAGED_VALUES or marker in _MANAGED_FALSE_VALUES:
        return None
    if marker == "" or marker in _MANAGED_TRUE_VALUES:
        return _LEGACY_MANAGED_SYSTEM
    return marker


def is_managed() -> bool:
    """Check if Shiina is running in package-manager-managed mode."""
    return get_managed_system() is not None

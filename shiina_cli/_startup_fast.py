"""Pre-import startup fast paths — THE canonical lightweight helpers.

Imported by ``shiina_cli/main.py`` BEFORE its heavy import wall (config, argparse tree, logging,
providers). Everything here must stay **stdlib-only and cheap** (os/sys file probes; no yaml, no
shiina_cli.config, no argparse). Exists so version-printing stops being reimplemented as
``*_fast()`` copies in main.py that duplicate project-root / container / profile detection.
"""

from __future__ import annotations

import os
import sys

__all__ = [
    "project_root_str", "ensure_project_root_on_path", "is_termux_env",
    "is_termux_fast_version_argv", "is_global_fast_version_argv",
    "is_container_startup_environment", "active_profile_may_override_home",
    "container_mode_may_be_active", "read_openai_version", "read_install_method",
    "detect_install_method", "recommended_update_command",
    "print_fast_version_info", "try_fast_version",
]


def _read_text(path: str) -> str | None:
    """Read a small text file, or None when it is missing/unreadable."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def project_root_str() -> str:
    """Repo root as a str — the single source for main.py's PROJECT_ROOT."""
    return os.path.realpath(os.path.join(os.path.dirname(__file__), os.pardir))


def ensure_project_root_on_path() -> None:
    """Put the project root at sys.path[0], deduping realpath-equivalents."""
    project_root = project_root_str()
    normalized_root = os.path.normcase(os.path.realpath(project_root))
    sys.path[:] = [entry for entry in sys.path
                   if not entry or os.path.normcase(os.path.realpath(entry)) != normalized_root]
    sys.path.insert(0, project_root)


def is_termux_env() -> bool:
    """Tiny Termux check for pre-import startup shortcuts."""
    prefix = os.environ.get("PREFIX", "")
    return bool(os.environ.get("TERMUX_VERSION") or "com.termux/files/usr" in prefix
                or prefix.startswith("/data/data/com.termux/"))


def is_termux_fast_version_argv(argv: list[str]) -> bool:
    return argv in (["--version"], ["-V"])


is_global_fast_version_argv = is_termux_fast_version_argv


def is_container_startup_environment() -> bool:
    """True when we're already INSIDE a container (fast path is then safe)."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    cgroup = _read_text("/proc/1/cgroup") or ""
    return "docker" in cgroup or "podman" in cgroup or "/lxc/" in cgroup


def active_profile_may_override_home(shiina_root: str) -> bool:
    """Cheap probe: does an active non-default profile redirect SHIINA_HOME?"""
    active = (_read_text(os.path.join(shiina_root, "active_profile")) or "").strip()
    return bool(active and active != "default")


def _default_home() -> str:
    return os.path.join(os.path.expanduser("~"), ".shiina")


def _resolved_home() -> str:
    return os.environ.get("SHIINA_HOME", "").strip() or _default_home()


def container_mode_may_be_active() -> bool:
    """Conservative probe for NixOS container-mode routing.

    False positives are fine (the slow path does the authoritative check). False negatives are NOT —
    they'd print the host's version instead of the container's — so any profile ambiguity means "may
    be active".
    """
    if os.environ.get("SHIINA_DEV") == "1" or is_container_startup_environment():
        return False
    shiina_home = os.environ.get("SHIINA_HOME", "").strip()
    if shiina_home:
        if os.path.exists(os.path.join(shiina_home, ".container-mode")):
            return True
        parent_name = os.path.basename(os.path.dirname(os.path.normpath(shiina_home)))
        return parent_name != "profiles" and active_profile_may_override_home(shiina_home)
    default_home = _default_home()
    return active_profile_may_override_home(default_home) or os.path.exists(
        os.path.join(default_home, ".container-mode"))


def read_openai_version() -> str | None:
    """Read OpenAI SDK version without importing ``importlib.metadata``."""
    for base in sys.path:
        version_file = os.path.join(base or os.getcwd(), "openai", "_version.py")
        try:
            with open(version_file, encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped.startswith("__version__"):
                        continue
                    _key, _sep, value = stripped.partition("=")
                    value = value.split("#", 1)[0].strip().strip("\"'")
                    return value or None
        except OSError:
            continue
    return None


def read_install_method() -> str | None:
    """The installer's ``.install_method`` stamp, if present.

    Only the stamp (step 1 of ``config.detect_install_method``'s resolution order) — the
    managed/git/pip fallbacks need heavier imports and stay on the slow path.
    """
    method = _read_text(os.path.join(_resolved_home(), ".install_method"))
    return (method or "").strip().lower() or None


# The two helpers below mirror ``shiina_cli/config.py``'s install-method resolver step for step,
# stdlib only, so ``shiina --version`` never pays the ~800 ms ``shiina_cli.config`` import. Keep
# them in lockstep with config.py — parity is pinned by tests/shiina_cli/test_startup_fast_version.py.
_SUPPORTED_INSTALL_METHODS = frozenset({"apt", "docker", "nix", "nixos", "home-manager", "git", "unknown"})
_NIX_MANAGED_SYSTEMS = frozenset({"nixos", "home-manager"})
_MANAGED_TRUE_VALUES = ("true", "1", "yes")
_MANAGED_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_IGNORED_MANAGED_VALUES = frozenset({"brew", "homebrew"})
_LEGACY_MANAGED_SYSTEM = "nixos"
_NIX_STORE = "/nix/store"
# Nix installs arrive by several routes (nix run, nix profile, system flake, home-manager) and the
# running process cannot tell which, so the text names the routes instead of one command.
_NIX_UPDATE_MSG = (
    "Update Shiina through the Nix source that installed it "
    "(e.g. nix profile upgrade, or update your flake input and rebuild with nixos-rebuild or home-manager switch)"
)
_UPDATE_COMMAND_BY_METHOD = {
    "docker": "docker pull nousresearch/shiina-agent:latest",
    "apt": "pkg upgrade shiina-agent",  # "apt" == Termux APT by contract; uses Termux's `pkg`.
}


def _install_method_stamp(path: str) -> str | None:
    method = (_read_text(path) or "").strip().lower()
    return method if method in _SUPPORTED_INSTALL_METHODS else None


def _managed_system() -> str | None:
    """Package manager owning this install, or None — mirrors ``config.get_managed_system``."""
    marker = os.environ.get("SHIINA_MANAGED", "").strip().lower() or None
    if marker is None:
        managed_marker = os.path.join(_resolved_home(), ".managed")
        if os.path.exists(managed_marker):
            marker = (_read_text(managed_marker) or "").strip().lower()
    if marker is None or marker in _IGNORED_MANAGED_VALUES or marker in _MANAGED_FALSE_VALUES:
        return None
    if marker == "" or marker in _MANAGED_TRUE_VALUES:
        return _LEGACY_MANAGED_SYSTEM
    return marker


def detect_install_method(project_root: str | None = None) -> str:
    """Detect the install method (apt/docker/nix/nixos/home-manager/git/unknown) — stdlib only.

    Mirrors ``shiina_cli.config.detect_install_method`` step for step: code-scoped stamp ->
    legacy ``$SHIINA_HOME`` stamp (a ``docker`` value is ignored unless we are really inside a
    container) -> managed marker -> ``/nix/store`` -> ``.git`` -> ``unknown``. See that function
    for why the code-scoped stamp wins (a home can be shared by a container and a host install).
    """
    root = project_root if project_root is not None else project_root_str()
    method = _install_method_stamp(os.path.join(root, ".install_method"))
    if method:
        return method
    method = _install_method_stamp(os.path.join(_resolved_home(), ".install_method"))
    if method and not (method == "docker" and not is_container_startup_environment()):
        return method
    managed = _managed_system()
    if managed:
        return managed.lower().replace(" ", "-")
    # Code under /nix/store/ is the hallmark of a nix-built install.
    resolved = os.path.realpath(root)
    if resolved != _NIX_STORE and resolved.startswith(_NIX_STORE + os.sep):
        return "nix"
    # A .git directory, or a ``gitdir:`` pointer file for worktrees.
    git_path = os.path.join(root, ".git")
    if os.path.isdir(git_path):
        return "git"
    pointer = _read_text(git_path)
    if pointer and pointer.strip().startswith("gitdir:"):
        return "git"
    return "unknown"


def recommended_update_command(method: str) -> str:
    """Update command/guidance for ``method`` — mirrors ``config.recommended_update_command``.

    Managed state wins over the code-scoped stamp: a managed install can carry a stale stamp
    naming an update path the managed guard refuses.
    """
    if _managed_system() in _NIX_MANAGED_SYSTEMS:
        return _NIX_UPDATE_MSG
    if method == "nix" or method in _NIX_MANAGED_SYSTEMS:
        return _NIX_UPDATE_MSG
    return _UPDATE_COMMAND_BY_METHOD.get(method, "shiina update")


def print_fast_version_info(*, check_updates: bool = True) -> None:
    """THE canonical ``shiina --version`` output (also used by /version).

    Every lazy block degrades gracefully — a broken/heavy import can never take the basic version
    output down.
    """
    # Registry-owned banner label (includes "· upstream <sha>" for git installs); banner.py keeps
    # rich/prompt_toolkit lazy, so this import is light.
    try:
        from shiina_cli.banner import format_banner_version_label

        print(format_banner_version_label())
    except Exception:
        from shiina_cli import __release_date__, __version__

        print(f"Shiina Agent v{__version__} ({__release_date__})")
    print(f"Install directory: {project_root_str()}")
    # stdlib-only resolver (config.detect_install_method's exact order) — keeps shiina_cli.config
    # off this path.
    install_method = detect_install_method(project_root_str())
    if install_method:
        print(f"Install method: {install_method}")
    print(f"Python: {sys.version.split()[0]}")
    openai_version = read_openai_version()
    print(f"OpenAI SDK: {openai_version}" if openai_version else "OpenAI SDK: Not installed")
    if not check_updates:
        return
    # Synchronous update status — bounded by check_for_updates' own subprocess/network timeouts
    # and its 6-hour cache; any failure prints nothing.
    try:
        from shiina_cli.banner import UPDATE_AVAILABLE_NO_COUNT, check_for_updates

        update_command = recommended_update_command(install_method)
        behind = check_for_updates(passive=True)
        if behind == UPDATE_AVAILABLE_NO_COUNT:
            print(f"Update available — run '{update_command}'")
        elif behind and behind > 0:
            commits_word = "commit" if behind == 1 else "commits"
            print(f"Update available: {behind} {commits_word} behind — run '{update_command}'")
        elif behind == 0:
            print("Up to date")
    except Exception:
        pass


def try_fast_version(argv: list[str] | None = None) -> bool:
    """Handle ``shiina --version`` before the heavy import wall.

    Only ``--version``/``-V`` (``--version`` carries the full output incl. update status), and never
    when container mode may need to route the command into the container. Termux keeps the
    SHIINA_TERMUX_DISABLE_FAST_CLI escape hatch.
    """
    if argv is None:
        argv = sys.argv[1:]
    is_termux = is_termux_env()
    if is_termux and os.environ.get("SHIINA_TERMUX_DISABLE_FAST_CLI") == "1":
        return False
    if is_termux:
        if not is_termux_fast_version_argv(argv):
            return False
    elif not is_global_fast_version_argv(argv) or container_mode_may_be_active():
        return False
    print_fast_version_info()
    return True

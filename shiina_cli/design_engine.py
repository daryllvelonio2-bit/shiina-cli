"""Shiina TUI design engine — the look SDK for the terminal UI.

A *design* is the complete appearance of the TUI: colours, glyph vocabulary,
borders, prompt symbol, animations, status-bar fields, and its structural
arrangement. Designs are pure data in ``~/.shiina/designs/*.yaml``; the shipped
built-ins live in ``shiina_cli/designs/`` and the schema is documented in
``shiina_cli/designs/README.md``.

Mirrors ``skin_engine`` deliberately: user file → built-in → ``default``, so a
design declares only what it changes and adding one needs no code change. The
one wire shape every consumer agrees on is :meth:`DesignConfig.to_payload`,
which ``ui-tui/src/domain/design.ts::resolveDesignSpec`` parses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shiina_cli import skin_dynamic
from shiina_constants import get_shiina_home

logger = logging.getLogger(__name__)

# The design every other design inherits from, and the one that means
# "the built-in look" — it declares nothing, so wearing it is a no-op.
DEFAULT_DESIGN = "codex"

# Guard against a design that (directly or transitively) extends itself.
_MAX_EXTENDS_DEPTH = 8


@dataclass
class DesignConfig:
    """A resolved TUI design. Every field is optional data; empty means
    "leave the built-in value alone"."""

    name: str
    description: str = ""
    # Palette overrides applied ON TOP of the skin's colours. Empty is the
    # normal case and is what keeps a dynamic-wallpaper skin intact.
    colors: Dict[str, str] = field(default_factory=dict)
    # Colours came from the live desktop scheme, not the file.
    dynamic: bool = False
    prompt: str = ""
    # density / panel / rule / glyphs / status_bar — renderer validates each
    # token, so a half-authored block still renders (see ui-tui `design.ts`).
    design: Dict[str, Any] = field(default_factory=dict)
    spinner: Dict[str, Any] = field(default_factory=dict)
    layout: Dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"
    path: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """The wire shape shared with ``ui-tui/src/domain/design.ts``.

        Emits only the sections that carry data, so an empty design serialises
        to a name and nothing else — the renderer turns that back into ``null``
        and the theme keeps referential equality (no memo churn per frame).
        """
        payload: Dict[str, Any] = {"name": self.name, "colors": self.colors}
        if self.description:
            payload["description"] = self.description
        if self.prompt:
            payload["prompt"] = self.prompt
        for key in ("design", "spinner", "layout"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload

    def is_empty(self) -> bool:
        """True when wearing this design changes nothing (the built-in look)."""
        return not any((self.colors, self.prompt, self.design, self.spinner, self.layout))


def _designs_dir() -> Path:
    return get_shiina_home() / "designs"


def _builtin_designs_dir() -> Path:
    return Path(__file__).resolve().parent / "designs"


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load a design definition from YAML; None on any failure."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as e:  # noqa: BLE001 - a bad design must not break boot
        logger.debug("Failed to load design from %s: %s", path, e)
    return None


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``over`` onto ``base``; nested dicts merge, scalars/lists replace.

    Deep rather than shallow so a design that sets one glyph keeps every other
    glyph from the design it extends.
    """
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _find_file(name: str) -> Tuple[Optional[Path], str]:
    """(path, source) for a design name: the user's file wins over the built-in."""
    user = _designs_dir() / f"{name}.yaml"
    if user.is_file():
        return user, "user"
    builtin = _builtin_designs_dir() / f"{name}.yaml"
    if builtin.is_file():
        return builtin, "builtin"
    return None, ""


def _builtin_names() -> List[str]:
    """Strictly codex only — all other designs are removed."""
    return ["codex"]


def _user_names() -> List[str]:
    try:
        return sorted(p.stem for p in _designs_dir().glob("*.yaml"))
    except OSError:
        return []


def list_designs() -> List[Dict[str, str]]:
    """Available designs (built-ins + user files); a user file shadows its
    built-in of the same name and is reported as ``user``."""
    user = set(_user_names())
    result = [
        {"name": name, "description": "", "source": "user" if name in user else "builtin", "path": ""}
        for name in sorted(user | set(_builtin_names()))
    ]
    for entry in result:
        path, source = _find_file(entry["name"])
        if path is not None:
            entry["path"] = str(path)
            entry["source"] = source
            raw = _load_yaml(path) or {}
            entry["description"] = str(raw.get("description", ""))
    return result


def _resolve_raw(name: str, _seen: Optional[Tuple[str, ...]] = None) -> Optional[Dict[str, Any]]:
    """Fully resolve a design file, following ``extends`` chains.

    ``extends`` names a design whose values are merged UNDER this one, so a
    design only declares its differences. Missing parents and cycles fall back
    to ``default`` rather than failing — a broken reference must not blank the UI.
    """
    seen = _seen or ()
    if name in seen or len(seen) >= _MAX_EXTENDS_DEPTH:
        logger.warning("Design '%s' has a circular 'extends' chain; ignoring it", name)
        return None

    path, source = _find_file(name)
    if path is None:
        return None

    data = _load_yaml(path)
    if data is None:
        return None

    data = dict(data)
    data.setdefault("name", name)

    parent_name = data.pop("extends", None)
    if isinstance(parent_name, str) and parent_name.strip() and parent_name.strip() != name:
        parent = _resolve_raw(parent_name.strip(), seen + (name,))
        if parent is not None:
            parent.pop("extends", None)
            # The parent contributes its values and source, never its identity.
            parent_source = parent.pop("_source", None)
            data = _deep_merge(parent, data)
            data.setdefault("name", name)
            source = source or parent_source

    data["_source"] = source
    return data


def _sections(data: Dict[str, Any]) -> Tuple[Dict[str, str], str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Pull the typed sections out of a raw design dict, tolerating wrong types."""
    name = str(data.get("name", DEFAULT_DESIGN))

    def section(key: str) -> Dict[str, Any]:
        value = data.get(key)
        if isinstance(value, dict):
            return value
        if value is not None:
            logger.warning("Design '%s' has invalid '%s' section (%s); ignoring it",
                           name, key, type(value).__name__)
        return {}

    colors = {str(k): str(v) for k, v in section("colors").items() if isinstance(v, str)}
    prompt = data.get("prompt")
    return colors, prompt if isinstance(prompt, str) else "", section("design"), section("spinner"), section("layout")


def load_design(name: str) -> DesignConfig:
    """Load a design by name: user file, then built-in, then ``default``.

    A design with ``dynamic: true`` takes its palette from the live desktop
    scheme at load time; keys declared in the file still win, so an individual
    colour stays overridable — the same contract ``skin_engine`` uses.
    """
    requested = (name or "").strip() or DEFAULT_DESIGN
    data = _resolve_raw(requested)

    if data is None:
        if requested != DEFAULT_DESIGN:
            logger.warning("Design '%s' not found, using default (%s)", requested, DEFAULT_DESIGN)
        data = _resolve_raw(DEFAULT_DESIGN) or {"name": DEFAULT_DESIGN}

    colors, prompt, design, spinner, layout = _sections(data)

    live: Dict[str, str] = {}
    if data.get("dynamic") is True:
        try:
            live = skin_dynamic.live_colors() or {}
        except Exception as e:  # noqa: BLE001 - a missing desktop scheme is not fatal
            logger.debug("Live colours unavailable for design '%s': %s", requested, e)
        if live:
            colors = {**live, **colors}

    return DesignConfig(
        name=str(data.get("name", requested)),
        description=str(data.get("description", "")),
        colors=colors,
        dynamic=bool(live),
        prompt=prompt,
        design=design,
        spinner=spinner,
        layout=layout,
        source=str(data.pop("_source", "") or ""),
        path=str(_find_file(requested)[0] or "") or None,
    )


# ── active design ────────────────────────────────────────────────────
# Cached per home, like the skin engine: the gateway resolves this on every
# change-watcher tick, so re-reading YAML each time would be wasteful.
_active_design: Optional[DesignConfig] = None
_active_name: str = DEFAULT_DESIGN


def get_active_design() -> DesignConfig:
    """The active design config (cached)."""
    global _active_design
    if _active_design is None:
        _active_design = load_design(_active_name)
    return _active_design


def get_active_design_name() -> str:
    return _active_name


def set_active_design(name: str) -> DesignConfig:
    """Switch the active design. Returns the new config."""
    global _active_design, _active_name
    _active_name = (name or "").strip() or DEFAULT_DESIGN
    _active_design = load_design(_active_name)
    return _active_design


def init_design_from_config(config: dict) -> None:
    """Initialize the active design from CLI config at startup."""
    display = config.get("display") or {}
    raw = display.get("design") if isinstance(display, dict) else None
    set_active_design(raw if isinstance(raw, str) and raw.strip() else DEFAULT_DESIGN)


def resolve_design_payload() -> Dict[str, Any]:
    """The active design in wire shape, or ``{}`` when it is the built-in look.

    ``{}`` rather than an empty design object on purpose: the renderer maps it
    to ``null``, so "no design" costs no allocation and keeps ``ui.theme``
    referentially stable.
    """
    try:
        design = get_active_design()
    except Exception as e:  # noqa: BLE001 - never break the skin payload
        logger.debug("Could not resolve the active design: %s", e)
        return {}
    return {} if design.is_empty() else design.to_payload()


# Records the sha256 of each file as we seeded it, so a later `init` can tell
# "the user edited this" from "this is our own stale copy" and only rewrite the
# latter. Without it, seeding is a one-shot: a built-in change never reaches a
# folder that has already been seeded (or clobbers the user's edits).
_SEED_MANIFEST = ".seeded.json"


def _sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_seed_manifest() -> Dict[str, str]:
    import json
    try:
        raw = (_designs_dir() / _SEED_MANIFEST).read_text(encoding="utf-8")
        data = json.loads(raw)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - a missing/corrupt manifest just means "unknown"
        return {}


def _write_seed_manifest(entries: Dict[str, str]) -> None:
    import json
    try:
        from utils import atomic_json_write
        atomic_json_write(_designs_dir() / _SEED_MANIFEST, entries)
    except Exception as e:  # noqa: BLE001 - the manifest is an optimisation, not state
        logger.debug("Could not write the design seed manifest: %s", e)


def ensure_designs_dir(*, overwrite: bool = False) -> Dict[str, list]:
    """Seed ``~/.shiina/designs/`` from the shipped built-ins.

    Returns ``{"written": [...], "kept": [...], "unchanged": [...]}``:

    * ``written``   — copied (new, or upgraded because it was still our copy)
    * ``kept``      — left alone because the user edited it
    * ``unchanged`` — already identical to the built-in

    "Still our copy" is decided by a hash manifest written at seed time, so an
    updated built-in reaches a seeded folder WITHOUT ever overwriting an edit.
    ``overwrite`` discards local edits deliberately (the ``--force`` flag).
    """
    target = _designs_dir()
    result: Dict[str, list] = {"kept": [], "unchanged": [], "written": []}
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create %s: %s", target, e)
        return result

    manifest = _read_seed_manifest()
    next_manifest: Dict[str, str] = dict(manifest)

    for src in sorted(_builtin_designs_dir().glob("*.yaml")):
        try:
            builtin = src.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read built-in design %s: %s", src.name, e)
            continue

        dest = target / src.name
        want = _sha256(builtin)

        if not dest.exists():
            try:
                dest.write_text(builtin, encoding="utf-8")
                next_manifest[src.stem] = want
                result["written"].append(src.stem)
            except OSError as e:
                logger.warning("Could not seed design %s: %s", src.name, e)
            continue

        try:
            current = dest.read_text(encoding="utf-8")
        except OSError:
            continue

        if current == builtin:
            next_manifest[src.stem] = want
            result["unchanged"].append(src.stem)
            continue

        # Differs. Only replace it when we know it is still the copy we wrote.
        untouched_since_seed = not overwrite and manifest.get(src.stem) == _sha256(current)

        if overwrite or untouched_since_seed:
            try:
                dest.write_text(builtin, encoding="utf-8")
                next_manifest[src.stem] = want
                result["written"].append(src.stem)
            except OSError as e:
                logger.warning("Could not upgrade design %s: %s", src.name, e)
        else:
            result["kept"].append(src.stem)

    # The contract README ships alongside the files and is ours to refresh.
    readme = _builtin_designs_dir() / "README.md"
    dest_readme = target / "README.md"
    if readme.is_file() and (overwrite or not dest_readme.exists()):
        try:
            dest_readme.write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass

    _write_seed_manifest(next_manifest)
    return result


def design_names() -> List[str]:
    """Every available design name, sorted.

    The accepted set for ``display.design`` and the menu a client offers. Sorted
    so ``shiina design list``, the gateway catalog and error messages agree.
    """
    return [str(entry["name"]) for entry in list_designs()]


def design_signature() -> Tuple[str, Optional[int]]:
    """(active name, newest mtime across its file + the user dir).

    Cheap stat-only signature for the change watcher: a name switch, a live
    edit of the active file, or a new file appearing all move it.
    """
    name = _active_name
    path, _ = _find_file(name)
    stamps = []
    if path is not None:
        try:
            stamps.append(path.stat().st_mtime_ns)
        except OSError:
            pass
    builtin_path = _builtin_designs_dir() / f"{name}.yaml"
    if builtin_path.is_file():
        try:
            stamps.append(builtin_path.stat().st_mtime_ns)
        except OSError:
            pass
    try:
        stamps.append(_designs_dir().stat().st_mtime_ns)
    except OSError:
        pass
    return name, max(stamps) if stamps else None


def reset_cache() -> None:
    """Drop the cached active design (tests + a config reload)."""
    global _active_design
    _active_design = None

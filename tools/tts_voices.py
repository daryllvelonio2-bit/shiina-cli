"""Curated TTS voice presets behind ``/voice voice`` — the CLI voice picker.

One preset table per provider plus the config key that provider reads its voice from
(``tts.<provider>.voice`` for most, ``.voice_id`` for the API vendors). Presets are pure data so
the picker works offline; :func:`fetch_provider_voices` adds the *live* catalog for providers that
expose one (edge), best-effort and cached for a day.

A preset carries the voice name plus optional ``speed`` (multiplier) and ``pitch`` (Hz). Both are
written to the provider's own section, so switching presets never leaks a knob into another
provider. ``pitch`` is honoured by edge (``tts.edge.pitch``) and minimax; providers without a
pitch knob simply ignore the extra key.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Provider -> key inside ``tts.<provider>`` naming the voice (SDK vendors use ``voice_id``).
VOICE_KEYS: Dict[str, str] = {
    "edge": "voice",
    "openai": "voice",
    "gemini": "voice",
    "deepinfra": "voice",
    "kittentts": "voice",
    "piper": "voice",
    "neutts": "voice",
    "elevenlabs": "voice_id",
    "minimax": "voice_id",
    "xai": "voice_id",
    "mistral": "voice_id",
}

# Providers whose synthesizer takes a pitch knob (others silently ignore ``pitch``).
PITCH_PROVIDERS = frozenset({"edge", "minimax"})

# Providers that run their output through the post-synthesis effect chain
# (``tools.tts_effects``; mirrors its ``applies_to``).
EFFECT_PROVIDERS = frozenset({"edge"})

# Providers the picker can list without an API key (free / local).
FREE_PROVIDERS = frozenset({"edge", "kittentts", "piper", "neutts"})

# Where each provider's own default voice lives (the CLI/TTS code is the source of truth — read
# it rather than duplicating a constant that can drift).
_DEFAULT_ATTRS: Dict[str, Tuple[str, str]] = {
    "edge": ("tools.tts_tool_providers", "DEFAULT_EDGE_VOICE"),
    "openai": ("tools.tts_tool_openai", "DEFAULT_OPENAI_VOICE"),
    "gemini": ("tools.tts_tool_providers", "DEFAULT_GEMINI_TTS_VOICE"),
    "elevenlabs": ("tools.tts_tool_providers", "DEFAULT_ELEVENLABS_VOICE_ID"),
    "minimax": ("tools.tts_tool_providers", "DEFAULT_MINIMAX_VOICE_ID"),
    "mistral": ("tools.tts_tool_providers", "DEFAULT_MISTRAL_TTS_VOICE_ID"),
    "xai": ("tools.tts_tool_providers", "DEFAULT_XAI_VOICE_ID"),
    "deepinfra": ("tools.tts_tool_openai", "DEFAULT_DEEPINFRA_TTS_VOICE"),
    "kittentts": ("tools.tts_tool_local", "DEFAULT_KITTENTTS_VOICE"),
    "piper": ("tools.tts_tool_local", "DEFAULT_PIPER_VOICE"),
}

_CACHE_TTL_SECONDS = 24 * 60 * 60


def provider_default(provider: str) -> str:
    """The provider's own default voice id (``""`` when it has none / can't be imported)."""
    module_name, attr = _DEFAULT_ATTRS.get(str(provider or "").strip().lower(), ("", ""))
    if not module_name:
        return ""
    try:
        import importlib

        return str(getattr(importlib.import_module(module_name), attr) or "")
    except Exception:
        return ""


def _p(name: str, voice: str, note: str, *, speed: Optional[float] = None,
       pitch: Optional[int] = None, effects: Optional[str] = None) -> Dict[str, Any]:
    """One preset row; omitted knobs mean "leave the provider default alone"."""
    preset: Dict[str, Any] = {"name": name, "voice": voice, "note": note}
    if speed is not None:
        preset["speed"] = speed
    if pitch is not None:
        preset["pitch"] = pitch
    if effects is not None:
        preset["effects"] = effects
    return preset


# ── Presets ───────────────────────────────────────────────────────────────────────────────
# edge: every id below is a real Microsoft short name (verified against edge_tts.list_voices).
PRESETS: Dict[str, Tuple[Dict[str, Any], ...]] = {
    "edge": (
        _p("mommy", "en-US-AvaNeural", "soft, warm, unhurried — the motherly one",
           speed=0.85, pitch=-6),
        _p("seductive", "en-US-AvaNeural", "slow, low and close — pitch-shifted down after synthesis",
           speed=0.75, pitch=-14, effects="sultry"),
        _p("mommy-asmr", "en-US-AvaNeural", "very slow, close and breathy",
           speed=0.7, pitch=-4),
        _p("aria", "en-US-AriaNeural", "provider default — positive, confident"),
        _p("ava", "en-US-AvaMultilingualNeural", "expressive, caring (multilingual)"),
        _p("emma", "en-US-EmmaMultilingualNeural", "cheerful, conversational"),
        _p("jenny", "en-US-JennyNeural", "friendly, comforting"),
        _p("michelle", "en-US-MichelleNeural", "pleasant, even-toned"),
        _p("ana", "en-US-AnaNeural", "cute (child voice)"),
        _p("sonia", "en-GB-SoniaNeural", "British, warm"),
        _p("libby", "en-GB-LibbyNeural", "British, gentle"),
        _p("natasha", "en-AU-NatashaNeural", "Australian, friendly"),
        _p("andrew", "en-US-AndrewMultilingualNeural", "warm, confident (male)"),
        _p("brian", "en-US-BrianMultilingualNeural", "casual, sincere (male)"),
        _p("christopher", "en-US-ChristopherNeural", "deep, authoritative (male)"),
        _p("guy", "en-US-GuyNeural", "lively (male)"),
        _p("eric", "en-US-EricNeural", "rational, even (male)"),
        _p("narrator", "en-US-ChristopherNeural", "slow, deep documentary read",
           speed=0.92, pitch=-12),
    ),
    "openai": (
        _p("alloy", "alloy", "provider default — neutral"),
        _p("ash", "ash", "warm, conversational"),
        _p("ballad", "ballad", "expressive, story-telling"),
        _p("coral", "coral", "bright, friendly"),
        _p("echo", "echo", "calm (male)"),
        _p("fable", "fable", "British, narrative"),
        _p("nova", "nova", "energetic (female)"),
        _p("onyx", "onyx", "deep (male)"),
        _p("sage", "sage", "measured (female)"),
        _p("shimmer", "shimmer", "soft (female)"),
        _p("verse", "verse", "expressive (male)"),
    ),
    "gemini": (
        _p("kore", "Kore", "provider default — firm (female)"),
        _p("aoede", "Aoede", "light, breezy (female)"),
        _p("leda", "Leda", "youthful (female)"),
        _p("zephyr", "Zephyr", "bright (female)"),
        _p("puck", "Puck", "upbeat (male)"),
        _p("charon", "Charon", "informative (male)"),
        _p("fenrir", "Fenrir", "excitable (male)"),
        _p("orus", "Orus", "firm (male)"),
    ),
    "xai": (
        _p("eve", "eve", "provider default (female)"),
        _p("ara", "ara", "warm (female)"),
        _p("leo", "leo", "authoritative (male)"),
        _p("rex", "rex", "confident (male)"),
        _p("sal", "sal", "smooth (male)"),
    ),
    "minimax": (
        _p("narrator", "English_expressive_narrator", "provider default — expressive narrator"),
        _p("graceful-lady", "English_Graceful_Lady", "gentle, poised (female)"),
        _p("wise-woman", "Wise_Woman", "mature, calm (female)"),
        _p("friendly-person", "Friendly_Person", "warm, casual"),
        _p("inspirational-girl", "Inspirational_girl", "bright (female)"),
        _p("calm-woman", "Calm_Woman", "slow, soothing (female)"),
        _p("sweet-girl", "Sweet_Girl", "soft, high (female)"),
        _p("deep-voice-man", "Deep_Voice_Man", "deep (male)"),
    ),
    "elevenlabs": (
        # Public-library ids. Your own library ids/names work too — pass them raw.
        _p("adam", "pNInz6obpgDQGcFmaJgB", "provider default — deep (male)"),
        _p("rachel", "21m00Tcm4TlvDq8ikWAM", "calm, narration (female)"),
    ),
    "kittentts": (
        _p("jasper", "Jasper", "provider default (male)"),
        _p("bella", "Bella", "warm (female)"),
        _p("luna", "Luna", "soft (female)"),
        _p("rosie", "Rosie", "bright (female)"),
        _p("hugo", "Hugo", "steady (male)"),
        _p("bruno", "Bruno", "deep (male)"),
        _p("kiki", "Kiki", "playful (female)"),
        _p("leo", "Leo", "clear (male)"),
    ),
    "piper": (
        _p("lessac", "en_US-lessac-medium", "provider default — balanced"),
        _p("amy", "en_US-amy-medium", "warm (female)"),
        _p("ryan", "en_US-ryan-high", "clear (male)"),
    ),
    "deepinfra": (
        _p("default", "default", "DeepInfra default voice"),
    ),
}

# Providers whose live catalog is worth fetching over the network.
_LIVE_PROVIDERS = frozenset({"edge"})


def provider_of(tts_config: Optional[Dict[str, Any]]) -> str:
    """The active TTS provider name (lower-cased; ``edge`` when unset/unreadable)."""
    provider = str((tts_config or {}).get("provider") or "").strip().lower()
    return provider or "edge"


def voice_key(provider: str) -> str:
    """Config key inside ``tts.<provider>`` that names the voice."""
    return VOICE_KEYS.get(str(provider or "").strip().lower(), "voice")


def presets(provider: str) -> List[Dict[str, Any]]:
    """Preset rows for ``provider`` (empty list for a provider with no presets — raw ids still work)."""
    return [dict(p) for p in PRESETS.get(str(provider or "").strip().lower(), ())]


def find(provider: str, token: str) -> Optional[Dict[str, Any]]:
    """Preset for ``token`` — its name (case-insensitive) or a 1-based index — else ``None``."""
    rows = presets(provider)
    wanted = str(token or "").strip().lower().lstrip("#")
    if not wanted:
        return None
    if wanted.isdigit():
        index = int(wanted)
        return rows[index - 1] if 1 <= index <= len(rows) else None
    for row in rows:
        if row["name"].lower() == wanted:
            return row
    return None


def section(tts_config: Optional[Dict[str, Any]], provider: str) -> Dict[str, Any]:
    """``tts.<provider>`` coerced to a dict (non-dict sections read as empty)."""
    value = (tts_config or {}).get(str(provider or "").strip().lower())
    return value if isinstance(value, dict) else {}


def current(tts_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """``{provider, key, voice, speed, pitch, preset}`` for the ACTIVE provider as configured."""
    provider = provider_of(tts_config)
    cfg = section(tts_config, provider)
    key = voice_key(provider)
    voice = str(cfg.get(key) or "").strip()
    if not voice:  # show what actually runs when nothing is configured — the provider default
        voice = provider_default(provider)
    speed = cfg.get("speed", (tts_config or {}).get("speed"))
    pitch = cfg.get("pitch")
    if pitch in ("", None, 0, "0"):  # a zero/absent pitch is "not set", not "+0Hz"
        pitch = None
    effects = str(cfg.get("effects") or "").strip() or None
    name = ""
    for row in presets(provider):
        if row["voice"] != voice:
            continue
        # A preset only names the current state when every knob it pins matches — mommy and
        # mommy-asmr share a voice id, and a voice with no knobs set is no preset at all.
        if "speed" in row and row["speed"] != speed:
            continue
        if "pitch" in row and row["pitch"] != (int(pitch) if pitch is not None else None):
            continue
        if "effects" in row and row["effects"] != effects:
            continue
        name = str(row["name"])
        break
    return {"provider": provider, "key": key, "voice": voice, "speed": speed,
            "pitch": pitch, "effects": effects, "preset": name}


def describe(preset: Dict[str, Any], provider: str = "") -> str:
    """One-line ``voice · speed · pitch · fx — note`` rendering for the picker."""
    bits = [str(preset.get("voice") or "")]
    if preset.get("speed") is not None:
        bits.append(f"speed {preset['speed']}")
    if preset.get("pitch") is not None and (not provider or provider in PITCH_PROVIDERS):
        bits.append(f"pitch {preset['pitch']:+d}Hz")
    if preset.get("effects") and (not provider or provider in EFFECT_PROVIDERS):
        bits.append(f"fx {preset['effects']}")
    tail = str(preset.get("note") or "").strip()
    return f"{' · '.join(bits)}{(' — ' + tail) if tail else ''}"


def changes(provider: str, *, voice: Optional[str] = None, speed: Optional[float] = None,
            pitch: Optional[int] = None, effects: Optional[str] = None) -> Dict[str, Any]:
    """Config dotpaths → values for a voice change (``{'tts.edge.voice': ..., ...}``).

    Only the keys actually supplied are returned, so a preset without ``speed``/``pitch``/
    ``effects`` leaves the existing knobs untouched instead of resetting them.
    """
    name = str(provider or "").strip().lower()
    out: Dict[str, Any] = {}
    if voice:
        out[f"tts.{name}.{voice_key(name)}"] = str(voice).strip()
    if speed is not None:
        out[f"tts.{name}.speed"] = round(max(0.25, min(4.0, float(speed))), 3)
    if pitch is not None and name in PITCH_PROVIDERS:
        out[f"tts.{name}.pitch"] = int(max(-50, min(50, int(pitch))))
    if effects is not None and name in EFFECT_PROVIDERS:
        # An explicit empty string is how the picker turns an effect OFF.
        out[f"tts.{name}.effects"] = str(effects).strip().lower()
    return out


def sample_text(label: str = "") -> str:
    """The audition line ``/voice voice test`` speaks."""
    where = f"the {label} voice" if label else "this voice"
    return (f"Hey Jay, it's Shiina. This is {where}, running through the CLI. "
            "Say the word and I'll switch to another one.")


# ── Live catalogs ─────────────────────────────────────────────────────────────────────────


def _cache_path(provider: str) -> Path:
    from shiina_constants import get_shiina_home
    return get_shiina_home() / "cache" / f"tts-voices-{provider}.json"


def _read_cache(provider: str) -> Optional[List[Dict[str, Any]]]:
    try:
        raw = json.loads(_cache_path(provider).read_text(encoding="utf-8"))
        if time.time() - float(raw.get("saved_at") or 0) < _CACHE_TTL_SECONDS:
            voices = raw.get("voices")
            if isinstance(voices, list) and voices:
                return voices
    except Exception:
        pass
    return None


def _write_cache(provider: str, voices: Iterable[Dict[str, Any]]) -> None:
    try:
        path = _cache_path(provider)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"saved_at": time.time(), "voices": list(voices)}),
                        encoding="utf-8")
    except Exception as exc:  # a cache miss must never break the picker
        logger.debug("tts voices: cache write failed: %s", exc)


def _edge_live_voices() -> List[Dict[str, Any]]:
    """Full edge catalog via the service (network). Raises on failure."""
    import asyncio
    import edge_tts

    raw = asyncio.run(edge_tts.list_voices())
    rows: List[Dict[str, Any]] = []
    for voice in raw or []:
        short = str(voice.get("ShortName") or "").strip()
        if not short:
            continue
        rows.append({"voice": short,
                     "locale": str(voice.get("Locale") or ""),
                     "gender": str(voice.get("Gender") or ""),
                     "note": ", ".join(voice.get("VoiceTag", {}).get("VoicePersonalities") or [])})
    return rows


def fetch_provider_voices(provider: str, *, refresh: bool = False) -> Tuple[List[Dict[str, Any]], str]:
    """``(voices, status)`` for a provider's live catalog.

    ``status`` is ``""`` on success, else a short reason the list is unavailable. Cached for a day
    so the picker stays instant offline; ``refresh`` bypasses the cache.
    """
    name = str(provider or "").strip().lower()
    if name not in _LIVE_PROVIDERS:
        return [], f"{name} has no live voice list — its presets are the catalog"
    if not refresh:
        cached = _read_cache(name)
        if cached is not None:
            return cached, ""
    try:
        voices = _edge_live_voices() if name == "edge" else []
    except Exception as exc:
        cached = _read_cache(name)
        if cached is not None:
            return cached, f"offline — showing the cached list ({type(exc).__name__})"
        return [], f"could not reach the voice service ({type(exc).__name__})"
    _write_cache(name, voices)
    return voices, ""

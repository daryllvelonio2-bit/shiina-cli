"""Named post-synthesis voice effects for TTS output (``tts.<provider>.effects``).

Speech services only expose prosody knobs (edge: rate + pitch), which is not enough for a deep,
close-mic read. These effects run the synthesized file through ``ffmpeg`` afterwards for the
things a bare TTS voice can't do: pitch down *without* changing tempo (``rubberband``), chest
warmth, a little air, gentle compression and a short room, then loudness-normalize so the result
sits at the same volume as an untouched utterance.

Everything here is best-effort: a missing ``ffmpeg``, a missing filter, or an unsupported container
returns False and the caller keeps the original audio.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Filters an effect needs beyond stock ffmpeg (checked once, then cached).
_REQUIRED_FILTERS = ("rubberband",)

# Container -> (encoder, bitrate). A container we can't re-encode is left alone.
_ENCODERS: Dict[str, tuple] = {
    ".mp3": ("libmp3lame", "160k"),
    ".ogg": ("libopus", "48k"),
    ".opus": ("libopus", "48k"),
    ".wav": ("pcm_s16le", None),
    ".m4a": ("aac", "128k"),
}

EFFECTS: Dict[str, Dict[str, Any]] = {
    "sultry": {
        "note": "deeper, warmer, close-mic — pitch down ~1.4 semitones with air and a short room",
        "params": {"pitch": 0.92},
        "filters": (
            "rubberband=pitch={pitch}",          # real pitch shift, tempo preserved
            "equalizer=f=180:t=q:w=1.0:g=4",     # chest warmth
            "equalizer=f=320:t=q:w=1.4:g=-1.5",  # trim boxiness
            "equalizer=f=6500:t=q:w=1.5:g=2.5",  # air / close-mic presence
            "acompressor=threshold=-20dB:ratio=3:attack=12:release=250:makeup=3",
            "aecho=0.8:0.85:70|130:0.13|0.09",   # subtle room
            "alimiter=limit=0.95",
            # Match the loudness of an untouched edge file (~-19.5 LUFS) so switching presets
            # never jumps in volume.
            "loudnorm=I=-19.5:TP=-1.5:LRA=11",
        ),
    },
}

_available_cache: Optional[bool] = None


def names() -> List[str]:
    """Every effect name this host could try to apply."""
    return sorted(EFFECTS)


def filtergraph(name: str) -> str:
    """The ffmpeg ``-af`` graph for ``name`` ("" when unknown)."""
    spec = EFFECTS.get(str(name or "").strip().lower())
    if not spec:
        return ""
    params = spec.get("params") or {}
    return ",".join(step.format(**params) for step in spec["filters"])


def note(name: str) -> str:
    """Human-readable one-liner for ``name`` ("" when unknown)."""
    spec = EFFECTS.get(str(name or "").strip().lower())
    return str(spec.get("note") or "") if spec else ""


def available(refresh: bool = False) -> bool:
    """True when ffmpeg and every required filter are present (probed once, then cached)."""
    global _available_cache
    if _available_cache is not None and not refresh:
        return _available_cache
    if shutil.which("ffmpeg") is None:
        _available_cache = False
        return _available_cache
    try:
        listed = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                capture_output=True, text=True, timeout=15).stdout
        _available_cache = all(f in listed for f in _REQUIRED_FILTERS)
    except Exception as exc:
        logger.debug("tts effects: ffmpeg probe failed: %s", exc)
        _available_cache = False
    return _available_cache


def applies_to(provider: str) -> bool:
    """Which providers run their output through the effects chain (edge is the wired one)."""
    return str(provider or "").strip().lower() == "edge"


def apply_effects(path: str, name: str, *, timeout: int = 120) -> bool:
    """Re-encode ``path`` in place through the ``name`` effect; False (original untouched) otherwise."""
    effect = str(name or "").strip().lower()
    graph = filtergraph(effect)
    if not graph:
        return False
    suffix = Path(path).suffix.lower()
    encoder = _ENCODERS.get(suffix)
    if encoder is None:
        logger.debug("tts effects: %s is not a container we re-encode — skipping", suffix or path)
        return False
    if not available():
        logger.debug("tts effects: ffmpeg/rubberband unavailable — leaving '%s' untouched", path)
        return False

    tmp = f"{path}.fx{suffix}"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", path, "-af", graph,
           "-c:a", encoder[0]] + (["-b:a", encoder[1]] if encoder[1] else []) + [tmp]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 or not os.path.getsize(tmp):
            logger.debug("tts effects: ffmpeg failed (%s) %s", proc.returncode, proc.stderr[-400:])
            return False
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.debug("tts effects '%s' failed: %s", effect, exc)
        return False
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

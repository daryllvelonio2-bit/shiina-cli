"""Tests for tools.tts_voices — the curated TTS voice catalog behind /voice voice."""

import json
import time

import pytest

from tools import tts_voices as tv


def test_every_preset_has_the_documented_shape():
    for provider, rows in tv.PRESETS.items():
        assert rows, f"{provider} has an empty preset table"
        for row in rows:
            assert row["name"] and row["voice"] and row["note"]
            assert row["name"] == row["name"].lower()
            if "speed" in row:
                assert 0.25 <= row["speed"] <= 4.0
            if "pitch" in row:
                assert -50 <= row["pitch"] <= 50


def test_preset_names_are_unique_per_provider():
    for provider, rows in tv.PRESETS.items():
        names = [row["name"] for row in rows]
        assert len(names) == len(set(names)), f"duplicate preset name in {provider}"


def test_edge_presets_name_real_microsoft_short_names():
    for row in tv.presets("edge"):
        assert row["voice"].count("-") >= 2, row  # locale-VoiceNeural
        assert row["voice"].endswith("Neural") or row["voice"].endswith("MultilingualNeural")


def test_mommy_preset_exists_and_is_the_soft_caring_voice():
    """The picker must ship the motherly preset the user asked for."""
    mommy = tv.find("edge", "mommy")
    assert mommy is not None
    assert mommy["voice"] == "en-US-AvaNeural"          # Microsoft's Expressive/Caring voice
    assert mommy["speed"] < 1.0 and mommy["pitch"] < 0  # slower + warmer than the default


def test_seductive_preset_is_the_slowest_and_lowest_read():
    """`seductive` = every lever at once: slow, low, pitch-shifted down post-synthesis."""
    sultry = tv.find("edge", "seductive")
    assert sultry is not None
    assert sultry["voice"] == "en-US-AvaNeural"
    assert sultry["speed"] == 0.75 and sultry["pitch"] == -14
    assert sultry["effects"] == "sultry"
    assert sultry["pitch"] <= min(row["pitch"] for row in tv.presets("edge") if "pitch" in row)


def test_find_by_name_index_and_miss():
    assert tv.find("edge", "MOMMY")["name"] == "mommy"
    assert tv.find("edge", "1")["name"] == tv.presets("edge")[0]["name"]
    assert tv.find("edge", "#3")["name"] == tv.presets("edge")[2]["name"]
    assert tv.find("edge", "99") is None
    assert tv.find("edge", "nope") is None
    assert tv.find("edge", "") is None
    assert tv.find("nope-provider", "mommy") is None


def test_current_reads_the_active_provider_section():
    state = tv.current({"provider": "edge", "edge": {"voice": "en-GB-SoniaNeural",
                                                     "speed": 0.9, "pitch": -4}})
    assert state == {"provider": "edge", "key": "voice", "voice": "en-GB-SoniaNeural",
                     "speed": 0.9, "pitch": -4, "effects": None, "preset": "sonia"}


def test_current_falls_back_to_the_provider_default_not_a_preset():
    """An unconfigured profile shows what actually runs (edge's default), not preset #1."""
    state = tv.current({"provider": "edge"})
    assert state["voice"] == tv.provider_default("edge") == "en-US-AriaNeural"
    assert state["preset"] == "aria"


def test_current_survives_a_non_dict_section_and_missing_provider():
    assert tv.current({"provider": "edge", "edge": "yes"})["provider"] == "edge"
    assert tv.current({})["provider"] == "edge"
    assert tv.current(None)["provider"] == "edge"


def test_changes_use_voice_id_for_sdk_vendors():
    assert tv.changes("elevenlabs", voice="abc") == {"tts.elevenlabs.voice_id": "abc"}
    assert tv.changes("minimax", voice="Wise_Woman") == {"tts.minimax.voice_id": "Wise_Woman"}
    assert tv.changes("edge", voice="en-US-AvaNeural") == {"tts.edge.voice": "en-US-AvaNeural"}


def test_changes_clamp_speed_and_pitch():
    assert tv.changes("edge", speed=99)["tts.edge.speed"] == 4.0
    assert tv.changes("edge", speed=0.01)["tts.edge.speed"] == 0.25
    assert tv.changes("edge", pitch=-500)["tts.edge.pitch"] == -50


def test_changes_drop_pitch_for_providers_without_one():
    plan = tv.changes("gemini", voice="Kore", pitch=-6)
    assert plan == {"tts.gemini.voice": "Kore"}


def test_changes_only_carry_what_was_supplied():
    """A preset without speed/pitch must not reset the knobs already in config."""
    assert tv.changes("edge", voice="en-US-AriaNeural") == {"tts.edge.voice": "en-US-AriaNeural"}
    assert tv.changes("edge", speed=1.2) == {"tts.edge.speed": 1.2}


def test_changes_with_nothing_supplied_is_empty():
    assert tv.changes("edge") == {}


def test_changes_carry_effects_and_only_edge_accepts_them():
    assert tv.changes("edge", effects="sultry") == {"tts.edge.effects": "sultry"}
    assert tv.changes("edge", effects="") == {"tts.edge.effects": ""}   # explicit off
    assert tv.changes("gemini", effects="sultry") == {}                 # provider has no chain
    assert tv.changes("edge") == {}                                     # effects=None -> untouched


def test_effects_participate_in_preset_matching():
    """The seductive preset pins an effect: same voice+knobs without it is not 'seductive'."""
    row = tv.find("edge", "seductive")
    cfg = {"provider": "edge", "edge": {"voice": row["voice"], "speed": row["speed"],
                                       "pitch": row["pitch"], "effects": row["effects"]}}
    assert tv.current(cfg)["preset"] == "seductive"
    cfg["edge"]["effects"] = ""
    assert tv.current(cfg)["preset"] == ""


def test_describe_renders_voice_knobs_and_note():
    assert tv.describe(tv.find("edge", "mommy"), "edge") == (
        "en-US-AvaNeural · speed 0.85 · pitch -6Hz — soft, warm, unhurried — the motherly one")
    assert tv.describe({"voice": "alloy", "note": "neutral"}, "openai") == "alloy — neutral"


def test_sample_text_names_the_voice():
    assert "mommy" in tv.sample_text("mommy")
    assert tv.sample_text().startswith("Hey Jay")


def test_live_list_is_cached_and_offline_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(tv, "_cache_path", lambda provider: tmp_path / f"{provider}.json")

    calls = []

    def _fake_live():
        calls.append(1)
        return [{"voice": "en-US-AriaNeural", "locale": "en-US", "gender": "Female", "note": ""}]

    monkeypatch.setattr(tv, "_edge_live_voices", _fake_live)
    voices, status = tv.fetch_provider_voices("edge")
    assert voices and status == "" and len(calls) == 1
    assert tv.fetch_provider_voices("edge")[0] == voices and len(calls) == 1  # served from cache

    def _boom():
        raise RuntimeError("no network")

    monkeypatch.setattr(tv, "_edge_live_voices", _boom)
    cached, status = tv.fetch_provider_voices("edge", refresh=True)
    assert cached == voices and "offline" in status

    (tmp_path / "edge.json").write_text(json.dumps({"saved_at": time.time() - 10 ** 6,
                                                   "voices": [{"voice": "stale"}]}))
    stale, status = tv.fetch_provider_voices("edge", refresh=True)
    assert stale == [] and status.startswith("could not reach")  # expired cache is no cache


def test_live_list_absent_for_providers_without_one():
    voices, status = tv.fetch_provider_voices("kittentts")
    assert voices == [] and "presets are the catalog" in status


def test_preset_name_is_only_claimed_when_the_knobs_match():
    """mommy and mommy-asmr share a voice id; the knobs decide which preset is in force."""
    base = {"provider": "edge", "edge": {"voice": "en-US-AvaNeural"}}
    assert tv.current(base)["preset"] == ""            # voice set, no knobs -> no preset
    mid = {"provider": "edge", "edge": {"voice": "en-US-AvaNeural", "speed": 0.7, "pitch": -4}}
    assert tv.current(mid)["preset"] == "mommy-asmr"
    warm = {"provider": "edge", "edge": {"voice": "en-US-AvaNeural", "speed": 0.85, "pitch": -6}}
    assert tv.current(warm)["preset"] == "mommy"


def test_zero_pitch_reads_as_unset():
    assert tv.current({"provider": "edge", "edge": {"voice": "en-US-AriaNeural", "pitch": 0}})["pitch"] is None

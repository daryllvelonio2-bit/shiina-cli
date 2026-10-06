"""Tests for tools.tts_effects — the post-synthesis voice effect chains."""

import shutil
import subprocess

import pytest

from tools import tts_effects as fx


def test_sultry_graph_pitches_down_without_touching_tempo():
    graph = fx.filtergraph("sultry")
    assert "rubberband=pitch=0.92" in graph      # real pitch shift, tempo preserved
    assert "atempo" not in graph                 # timing is edge's job, not the effect's
    assert "loudnorm" in graph and "alimiter" in graph


def test_unknown_effect_is_empty_not_a_crash():
    assert fx.filtergraph("nope") == "" and fx.note("nope") == ""
    assert fx.filtergraph("") == "" and fx.filtergraph(None) == ""


def test_names_and_note_describe_the_chain():
    assert "sultry" in fx.names()
    assert "pitch down" in fx.note("sultry")


def test_only_edge_runs_effects():
    assert fx.applies_to("edge") is True
    assert fx.applies_to("EDGE") is True
    assert fx.applies_to("openai") is False and fx.applies_to("") is False


def test_apply_is_a_noop_for_unknown_effect_or_container(tmp_path):
    target = tmp_path / "clip.mp3"
    target.write_bytes(b"not really audio")
    assert fx.apply_effects(str(target), "nope") is False
    assert fx.apply_effects(str(target), "") is False
    other = tmp_path / "clip.flac"
    other.write_bytes(b"x")
    assert fx.apply_effects(str(other), "sultry") is False
    assert target.read_bytes() == b"not really audio"  # never damaged


def test_missing_ffmpeg_is_reported_not_raised(tmp_path, monkeypatch):
    from types import SimpleNamespace

    # Patch the module's shutil reference (not the global module) so a probe can't see ffmpeg,
    # then restore and re-probe in `finally` — the availability cache is process-wide.
    monkeypatch.setattr(fx, "shutil", SimpleNamespace(which=lambda _name: None))
    try:
        target = tmp_path / "clip.mp3"
        target.write_bytes(b"original")
        assert fx.available(refresh=True) is False
        assert fx.apply_effects(str(target), "sultry") is False
        assert target.read_bytes() == b"original"
    finally:
        monkeypatch.undo()
        fx.available(refresh=True)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
@pytest.mark.skipif(not fx.available(refresh=True), reason="ffmpeg lacks rubberband")
def test_sultry_actually_lowers_the_pitch(tmp_path):
    """End-to-end proof the chain does what its name claims: same length, lower fundamental."""
    np = pytest.importorskip("numpy")
    src = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=200:duration=2", "-c:a", "libmp3lame", str(src)],
                   check=True)

    def f0(path):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
                              "-ac", "1", "-ar", "24000", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, dtype=np.float32)[: 24000 * 4]
        n = 2048
        ac = np.correlate(x - x.mean(), x - x.mean(), "full")[n - 1:]
        lag = 24000 // 400 + int(np.argmax(ac[24000 // 400: 24000 // 70]))
        return 24000 / lag

    before = f0(src)
    assert fx.apply_effects(str(src), "sultry") is True
    after = f0(src)
    assert after < before * 0.97, f"expected a deeper tone ({before:.1f}Hz -> {after:.1f}Hz)"

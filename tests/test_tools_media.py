"""Media file tools (TDD): trim/crop/speed/join/snapshot/split video + audio tools.

TDD record: this file was written FIRST against a nonexistent
`kumquat.tools_media` (RED: ModuleNotFoundError on collection),
then the module was implemented to make it GREEN.

Fixtures are 2 s files generated with ffmpeg (testsrc video + sine /
silence audio). Outputs are verified with ffprobe (durations, streams,
dims, channels) and volumedetect (bleep placement). Originals are never
modified (sha-pinned in every behaviour test). Absent ffmpeg raises
BackendMissing and tests SKIP — they never fail.
"""
import hashlib
import json
import re
import shutil
import subprocess

import pytest
from PIL import Image

from kumquat.tools_media import (
    BackendMissing,
    audio_visualizer,
    bleep_audio,
    change_speed,
    crop_video,
    join_mp4,
    mute_video,
    normalize_audio,
    snapshot_video,
    split_video,
    to_mono,
    trim_audio,
    trim_video,
)


def _need_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("backend missing: ffmpeg/ffprobe not installed")


def _run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_tone_wav(path, dur=2.0, freq=440.0, channels=1):
    """2 s sine wav fixture."""
    _need_ffmpeg()
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", f"sine=frequency={freq}:duration={dur}",
          "-ac", str(channels), "-t", str(dur), str(path)])


def _make_silence_wav(path, dur=2.0):
    """2 s digital-silence wav fixture (48 kHz to match sine fixtures)."""
    _need_ffmpeg()
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "anullsrc=r=48000:cl=mono", "-t", str(dur), str(path)])


def _make_mp4(path, dur=2.0, audio=True):
    """2 s testsrc mp4 fixture, optionally with a sine audio track."""
    _need_ffmpeg()
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i",
           f"testsrc=duration={dur}:size=128x128:rate=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}"]
    cmd += ["-t", str(dur), "-pix_fmt", "yuv420p", "-shortest", str(path)]
    _run(cmd)


def _probe(path):
    _need_ffmpeg()
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True)
    return json.loads(r.stdout)


def _dur(path):
    return float(_probe(path)["format"]["duration"])


def _streams(path, kind):
    return [s for s in _probe(path)["streams"] if s["codec_type"] == kind]


def _mean_volume(path, ss, t):
    """Mean volume dB of a window; None means digital silence (-inf)."""
    _need_ffmpeg()
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", str(ss), "-t", str(t),
         "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-inf|[-+]?[0-9]*\.?[0-9]+)\s*dB", r.stderr)
    assert m, f"no volumedetect reading:\n{r.stderr[-1500:]}"
    return None if m.group(1) == "-inf" else float(m.group(1))


# --- trim_video / trim_audio -------------------------------------------------

def test_trim_video_duration_and_name(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src)
    before = _sha(src)
    out = trim_video(src, tmp_path / "out", start=0.5, end=1.5)
    assert out.name == "clip-Trimmed.mp4"
    assert _dur(out) == pytest.approx(1.0, abs=0.2)
    assert len(_streams(out, "video")) == 1
    assert _sha(src) == before  # original untouched


def test_trim_audio_duration_and_name(tmp_path):
    src = tmp_path / "song.wav"
    _make_tone_wav(src)
    before = _sha(src)
    out = trim_audio(src, tmp_path / "out", start=0.0, end=1.0)
    assert out.name == "song-Trimmed.wav"
    assert _dur(out) == pytest.approx(1.0, abs=0.15)
    assert _sha(src) == before


def test_trim_rejects_bad_range(tmp_path):
    src = tmp_path / "song.wav"
    _make_tone_wav(src)
    with pytest.raises(ValueError):
        trim_audio(src, tmp_path / "o1", start=1.5, end=0.5)
    with pytest.raises(ValueError):
        trim_audio(src, tmp_path / "o2", start=-1.0, end=1.0)


# --- crop_video --------------------------------------------------------------

def test_crop_video_dims_and_name(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src, audio=False)
    before = _sha(src)
    out = crop_video(src, tmp_path / "out", box=(8, 8, 120, 120))
    assert out.name == "clip-Cropped.mp4"
    (v,) = _streams(out, "video")
    assert (v["width"], v["height"]) == (112, 112)
    assert _sha(src) == before


def test_crop_video_rejects_outside_box(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src, audio=False)
    with pytest.raises(ValueError):
        crop_video(src, tmp_path / "out", box=(0, 0, 999, 999))


# --- change_speed ------------------------------------------------------------

def test_change_speed_2x_halves_duration(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src)
    before = _sha(src)
    out = change_speed(src, tmp_path / "out", factor=2.0)
    assert out.name == "clip-Speed 2x.mp4"
    assert _dur(out) == pytest.approx(1.0, abs=0.2)
    assert _sha(src) == before


def test_change_speed_rejects_bad_factor(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src)
    with pytest.raises(ValueError):
        change_speed(src, tmp_path / "out", factor=0)


# --- join_mp4 ----------------------------------------------------------------

def test_join_mp4_sums_durations(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_mp4(a)
    _make_mp4(b)
    before = (_sha(a), _sha(b))
    out = join_mp4([a, b], tmp_path / "out")
    assert out.name == "a-joined.mp4"  # no tt() entry: first-stem fallback
    assert _dur(out) == pytest.approx(4.0, abs=0.3)
    assert (_sha(a), _sha(b)) == before


def test_join_mp4_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        join_mp4([], tmp_path / "out")


# --- snapshot_video ----------------------------------------------------------

def test_snapshot_video_png_dims(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src, audio=False)
    before = _sha(src)
    out = snapshot_video(src, tmp_path / "out", at=1.0)
    assert out.name == "clip-Snapshot.png"
    with Image.open(out) as im:
        assert im.size == (128, 128)
    assert _sha(src) == before


# --- split_video -------------------------------------------------------------

def test_split_video_clips_folder(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src, audio=False)
    before = _sha(src)
    parts = split_video(src, tmp_path / "out", segment_time=1.0)
    assert len(parts) == 2
    assert all(p.parent.name == "clip-Clips" for p in parts)  # Clips->folder
    assert [p.name for p in parts] == ["clip-1.mp4", "clip-2.mp4"]
    total = 0.0
    for p in parts:
        assert len(_streams(p, "video")) == 1
        total += _dur(p)
    assert total == pytest.approx(2.0, abs=0.3)
    assert _sha(src) == before


# --- normalize_audio (loudnorm) ----------------------------------------------

def test_normalize_audio_lufs_and_name(tmp_path):
    src = tmp_path / "song.wav"
    _make_tone_wav(src, freq=440.0)
    before = _sha(src)
    out = normalize_audio(src, tmp_path / "out")
    assert out.name == "song-Normalized.wav"
    assert _dur(out) == pytest.approx(2.0, abs=0.15)
    # Second loudnorm pass measures the result: must sit near the -24 LUFS
    # single-pass default target (proves the filter actually normalized).
    # reports "input_i"/"output_i"; older versions say "measured_I".
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(out),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    m = (re.search(r'"(?:input_i|measured_I)"\s*:\s*"([^"]+)"', r.stderr)
         or re.search(r'"output_i"\s*:\s*"([^"]+)"', r.stderr))
    assert m, f"no loudnorm stats:\n{r.stderr[-1500:]}"
    assert float(m.group(1)) == pytest.approx(-24.0, abs=3.0)
    assert _sha(src) == before


# --- to_mono -----------------------------------------------------------------

def test_to_mono_single_channel(tmp_path):
    src = tmp_path / "song.wav"
    _make_tone_wav(src, channels=2)
    (a,) = _streams(src, "audio")
    assert a["channels"] == 2  # fixture really stereo
    before = _sha(src)
    out = to_mono(src, tmp_path / "out")
    assert out.name == "song-Mono.wav"
    (m,) = _streams(out, "audio")
    assert m["channels"] == 1
    assert _dur(out) == pytest.approx(2.0, abs=0.15)
    assert _sha(src) == before


# --- bleep_audio -------------------------------------------------------------

def test_bleep_replaces_range_with_tone(tmp_path):
    src = tmp_path / "quiet.wav"
    _make_silence_wav(src)
    before = _sha(src)
    out = bleep_audio(src, tmp_path / "out", start=0.5, end=1.5, freq=880.0)
    assert out.name == "quiet-Bleeped.wav"
    assert _dur(out) == pytest.approx(2.0, abs=0.15)
    # Silence outside the range (inanimate dither floor sits near -91 dB —
    # the float->s16 downmix adds inaudible noise, so threshold, not -inf),
    # tone clearly present inside it (>= 40 dB separation).
    for ss, t in ((0.05, 0.35), (1.6, 0.3)):
        v = _mean_volume(out, ss, t)
        assert v is None or v < -80.0, f"leak at {ss}s: {v}"
    inside = _mean_volume(out, 0.6, 0.8)
    assert inside is not None and inside > -40.0  # tone inside the range
    assert _sha(src) == before


def test_bleep_rejects_bad_range(tmp_path):
    src = tmp_path / "quiet.wav"
    _make_silence_wav(src)
    with pytest.raises(ValueError):
        bleep_audio(src, tmp_path / "o", start=1.0, end=1.0)


# --- mute_video --------------------------------------------------------------

def test_mute_video_drops_audio_keeps_video(tmp_path):
    src = tmp_path / "clip.mp4"
    _make_mp4(src, audio=True)
    assert len(_streams(src, "audio")) == 1  # fixture really has audio
    before = _sha(src)
    out = mute_video(src, tmp_path / "out")
    assert out.name == "clip-Muted.mp4"
    assert _streams(out, "audio") == []
    assert len(_streams(out, "video")) == 1
    assert _dur(out) == pytest.approx(2.0, abs=0.2)
    assert _sha(src) == before


# --- audio_visualizer --------------------------------------------------------

def test_audio_visualizer_mp4_streams(tmp_path):
    src = tmp_path / "song.wav"
    _make_tone_wav(src)
    before = _sha(src)
    out = audio_visualizer(src, tmp_path / "out")
    assert out.name == "song-Visualizer.mp4"  # Visualizer->mp4
    (v,) = _streams(out, "video")
    assert (v["width"], v["height"]) == (320, 240)
    assert len(_streams(out, "audio")) == 1  # original audio kept
    assert _dur(out) == pytest.approx(2.0, abs=0.3)
    assert _sha(src) == before


# --- backend policy ----------------------------------------------------------

def test_missing_ffmpeg_raises_backend_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        trim_video(tmp_path / "in.mp4", tmp_path / "out", start=0, end=1)

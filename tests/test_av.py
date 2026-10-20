"""Audio/video conversions: registry routing + real conversions, originals untouched.

Tests needing an absent ffmpeg SKIP; they never fail.
"""
import hashlib
import shutil
import subprocess

import pytest

import kumquat.registry_av  # noqa: F401 -- registers AV rows
import kumquat.registry_data  # noqa: F401 -- registers image rows (pulls AV rows too)
from kumquat.converters_av import BackendMissing, convert_media
from kumquat.registry import REGISTRY, options_for

AUDIO_ROWS = [c for c in REGISTRY if c.category == "audio"]
VIDEO_ROWS = [c for c in REGISTRY if c.category == "video"]
AV_ROWS = [c for c in REGISTRY if c.category in ("audio", "video")]


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))


def _need_ffmpeg():
    if shutil.which("ffmpeg") is None:
        pytest.skip("backend missing: ffmpeg not installed (audio/video support)")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_wav(path):
    """Generate a 1s silent wav fixture; skips when ffmpeg is absent."""
    _need_ffmpeg()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", str(path)],
        check=True,
    )


def _make_mp4(path):
    """Generate a 1s testsrc mp4 (with audio) fixture; skips when absent."""
    _need_ffmpeg()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )


def test_registry_counts():
    assert len(AUDIO_ROWS) == 56  # q->q full matrix, self filtered
    assert len(VIDEO_ROWS) == 48  # T->[T,gif,mp3] (42) + gif->T (6)
    assert len(AV_ROWS) >= 60  # new rows this task
    assert len(REGISTRY) >= 117  # 57 image + 104 AV


def test_av_id_format():
    audio_ids = {c.id for c in AUDIO_ROWS}
    assert "audio-mp3-to-m4a" in audio_ids
    assert "audio-wav-to-flac" in audio_ids
    assert len(audio_ids) == 56
    video_ids = {c.id for c in VIDEO_ROWS}
    assert "video-mp4-to-mov" in video_ids
    assert "video-mp4-to-gif" in video_ids
    assert "video-mp4-to-mp3" in video_ids
    assert "video-gif-to-mp4" in video_ids
    assert len(video_ids) == 48


def test_av_labels_follow_E_rule():
    for c in AV_ROWS:
        dst = c.output_ext.lstrip(".")
        assert c.label == "Convert to " + ("GZIP" if dst == "gz" else dst.upper())


def test_registry_routes_audio_mp3():
    opts = options_for("a.mp3", "audio/mpeg")
    assert any(c.id == "audio-mp3-to-m4a" for c in opts)
    assert any(c.id == "audio-mp3-to-wav" for c in opts)


def test_registry_routes_video_edges():
    opts = options_for("a.mp4", "video/mp4")
    assert any(c.id == "video-mp4-to-mov" for c in opts)
    assert any(c.id == "video-mp4-to-gif" for c in opts)
    assert any(c.id == "video-mp4-to-mp3" for c in opts)
    gif_opts = options_for("a.gif", "image/gif")
    assert len(gif_opts) == 6  # gif->T only
    assert all(c.id.startswith("video-gif-to-") for c in gif_opts)


@pytest.mark.parametrize("row_id", [c.id for c in AV_ROWS])
def test_av_row_routes(row_id):
    row = next(c for c in AV_ROWS if c.id == row_id)
    opts = options_for("file" + row.inputs[0], "application/octet-stream")
    assert row in opts


def test_wav_converts_to_mp3(tmp_path):
    import magic

    src = tmp_path / "in.wav"
    _make_wav(src)
    before = _sha(src)
    out = _or_skip(convert_media, src, ".mp3", tmp_path / "out")
    assert out.exists() and out.suffix == ".mp3"
    assert magic.from_file(str(out), mime=True) == "audio/mpeg"
    assert _sha(src) == before  # original untouched


def test_mp4_converts_to_mp3(tmp_path):
    import magic

    src = tmp_path / "in.mp4"
    _make_mp4(src)
    before = _sha(src)
    out = _or_skip(convert_media, src, ".mp3", tmp_path / "out")
    assert out.exists() and out.suffix == ".mp3"
    assert magic.from_file(str(out), mime=True) == "audio/mpeg"
    assert _sha(src) == before  # original untouched


def test_mp4_converts_to_gif(tmp_path):
    import magic

    src = tmp_path / "in.mp4"
    _make_mp4(src)
    before = _sha(src)
    out = _or_skip(convert_media, src, ".gif", tmp_path / "out", extra=["-an"])
    assert out.exists() and out.suffix == ".gif"
    assert magic.from_file(str(out), mime=True) == "image/gif"
    assert _sha(src) == before  # original untouched


def test_missing_ffmpeg_raises_backend_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_media(tmp_path / "in.wav", ".mp3", tmp_path / "out")


def test_convert_media_reports_increasing_progress(tmp_path):
    import shutil as _sh

    if _sh.which("ffmpeg") is None:
        pytest.skip("ffmpeg missing")
    import subprocess as _sp

    src = tmp_path / "tone.wav"
    _sp.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=3", str(src)], check=True)
    updates = []
    out = convert_media(src, ".mp3", tmp_path / "out", progress=updates.append)
    assert out.exists()
    fractions = [u.fraction for u in updates if u.fraction is not None]
    assert fractions, "no measurable progress reported"
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_convert_media_without_progress_still_works(tmp_path):
    # existing call sites pass no progress kwarg
    src = tmp_path / "in.wav"
    _make_wav(src)
    out = _or_skip(convert_media, src, ".mp3", tmp_path / "out")
    assert out.exists() and out.suffix == ".mp3"


def test_convert_media_with_progress_raises_on_bad_input(tmp_path):
    """A failing ffmpeg run with progress raises CalledProcessError, as today."""
    _need_ffmpeg()
    src = tmp_path / "garbage.wav"
    src.write_text("this is not audio\n" * 50)
    updates = []
    with pytest.raises(subprocess.CalledProcessError) as info:
        convert_media(src, ".mp3", tmp_path / "out", progress=updates.append)
    assert info.value.returncode != 0
    assert info.value.stderr  # ffmpeg's error text is carried

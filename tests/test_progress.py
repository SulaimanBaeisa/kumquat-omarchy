"""Pure progress helpers: no GTK, no real ffmpeg needed."""
import subprocess

import pytest

from kumquat import progress as pg


def test_progress_text_for_fraction():
    assert pg.Progress(0.4237).text == "42 %"


def test_progress_text_indeterminate_uses_given_text():
    assert pg.Progress(None, "Working…").text == "Working…"


def test_fraction_is_clamped():
    assert pg.Progress(1.7).fraction == 1.0
    assert pg.Progress(-0.2).fraction == 0.0


@pytest.mark.parametrize(("line", "expected"), [
    ("out_time_us=5000000", 0.5),     # 5 s of 10 s
    ("out_time_ms=2500000", 0.25),    # ffmpeg's misnamed field: also µs
    ("out_time_us=N/A", None),
    ("frame=12", None),
    ("progress=end", 1.0),
])
def test_parse_ffmpeg_progress(line, expected):
    assert pg.parse_ffmpeg_progress(line, duration_s=10.0) == expected


def test_parse_without_duration_is_indeterminate():
    assert pg.parse_ffmpeg_progress("out_time_us=5000000", duration_s=None) is None


def test_media_duration_reads_ffprobe(monkeypatch, tmp_path):
    def fake_run(cmd, **_kw):
        assert cmd[0] == "ffprobe"
        return subprocess.CompletedProcess(cmd, 0, stdout="12.5\n", stderr="")
    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    assert pg.media_duration(tmp_path / "x.mp4") == 12.5


def test_media_duration_unknown_returns_none(monkeypatch, tmp_path):
    def fake_run(cmd, **_kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad")
    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    assert pg.media_duration(tmp_path / "x.mp4") is None

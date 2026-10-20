"""Audio/video conversion rows — data only, no logic.

Encodes the observed conversion matrix:
  q (audio in=out) = ["mp3","m4a","wav","flac","ogg","opus","aiff","wma"],
  q->q with self filtered: 8x7 = 56 rows.
  T (video) = ["mp4","mov","mkv","webm","avi","wmv"],
  T->[...T,"gif","mp3"] with self filtered: 6x7 = 42 rows;
  gif->T: 6 rows. Video category total: 48 rows.
Label rule E: gz->"GZIP" else UPPER (no gz here, kept for fidelity).
"""
from .registry import Conversion, register

_Q = ["mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff", "wma"]
_T = ["mp4", "mov", "mkv", "webm", "avi", "wmv"]

_AUDIO_EXTS = {
    "mp3": (".mp3",),
    "m4a": (".m4a",),
    "wav": (".wav",),
    "flac": (".flac",),
    "ogg": (".ogg",),
    "opus": (".opus",),
    "aiff": (".aiff", ".aif"),
    "wma": (".wma",),
}

_VIDEO_EXTS = {
    "mp4": (".mp4",),
    "mov": (".mov",),
    "mkv": (".mkv",),
    "webm": (".webm",),
    "avi": (".avi",),
    "wmv": (".wmv",),
    "gif": (".gif",),
}


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _src in _Q:
    for _dst in _Q:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"audio-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_AUDIO_EXTS[_src],
            output_ext="." + _dst,
            category="audio",
        ))

_VIDEO_OUTS = _T + ["gif", "mp3"]

for _src in _T:
    for _dst in _VIDEO_OUTS:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"video-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_VIDEO_EXTS[_src],
            output_ext="." + _dst,
            category="video",
        ))

for _dst in _T:
    register(Conversion(
        id=f"video-gif-to-{_dst}",
        label=_label(_dst),
        inputs=_VIDEO_EXTS["gif"],
        output_ext="." + _dst,
        category="video",
    ))

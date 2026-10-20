"""Audio/video conversion rows — data only, no logic.

Conversion matrix:
  audio (in = out) = ["mp3","m4a","wav","flac","ogg","opus","aiff","wma"],
  audio->audio with self filtered: 8x7 = 56 rows.
  video = ["mp4","mov","mkv","webm","avi","wmv"],
  video->[...video,"gif","mp3"] with self filtered: 6x7 = 42 rows;
  gif->video: 6 rows. Video category total: 48 rows.
Label rule: gz->"GZIP" else UPPER (no gz here; kept for consistency).
"""
from .registry import Conversion, register

_AUDIO_FORMATS = ["mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff", "wma"]
_VIDEO_FORMATS = ["mp4", "mov", "mkv", "webm", "avi", "wmv"]

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


for _src in _AUDIO_FORMATS:
    for _dst in _AUDIO_FORMATS:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"audio-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_AUDIO_EXTS[_src],
            output_ext="." + _dst,
            category="audio",
        ))

_VIDEO_OUTS = _VIDEO_FORMATS + ["gif", "mp3"]

for _src in _VIDEO_FORMATS:
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

for _dst in _VIDEO_FORMATS:
    register(Conversion(
        id=f"video-gif-to-{_dst}",
        label=_label(_dst),
        inputs=_VIDEO_EXTS["gif"],
        output_ext="." + _dst,
        category="video",
    ))

"""Audio/video file tools.

Originals are never modified — every function writes into ``dest_dir``
and leaves ``src`` bytes untouched.

Output naming follows the ``tt()`` rule:
``Muted / Trimmed / Bleeped / Speed 2x / Snapshot->png / Clips->folder /
Visualizer->mp4 / Mono / Normalized``; ``joinVideos`` has no ``tt()``
entry in the observed source, so join falls back to
``<first-stem>-joined.mp4`` (same convention as the pdf ``-merged`` and
image ``-Collage`` fallbacks).

Backend: ``ffmpeg``/``ffprobe`` (``shutil.which`` guard — present on
this host). Absent → ``BackendMissing`` (re-exported from
:mod:`kumquat.converters_av`); tests SKIP instead of failing.
"""
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from .converters_av import BackendMissing  # noqa: F401 -- re-exported
from .tools_images import unique_path, validate_boxes

__all__ = [
    "BackendMissing",
    "audio_visualizer",
    "bleep_audio",
    "change_speed",
    "crop_video",
    "join_mp4",
    "mute_video",
    "normalize_audio",
    "snapshot_video",
    "split_video",
    "to_mono",
    "trim_audio",
    "trim_video",
]


def _need_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise BackendMissing(
            "backend missing: ffmpeg not installed (audio/video support)")
    if shutil.which("ffprobe") is None:
        raise BackendMissing(
            "backend missing: ffprobe not installed (audio/video support)")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def _dest(dest_dir: Path, name: str) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return unique_path(dest_dir / name)


def _probe(path: Path) -> dict:
    _need_ffmpeg()
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout)


def _video_encoding(suffix: str) -> list[str]:
    """Choose codecs the output container actually permits."""
    if suffix.lower() == ".webm":
        return ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-c:a", "libopus"]
    if suffix.lower() == ".wmv":
        return ["-c:v", "wmv2", "-pix_fmt", "yuv420p", "-c:a", "wmav2"]
    return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]


def compress_media(src: Path, dest_dir: Path, quality: int = 75) -> Path:
    """Re-encode with container-compatible codecs; quality is 1 (low) to 100."""
    _need_ffmpeg()
    if not 1 <= quality <= 100:
        raise ValueError("quality must be 1-100")
    src = Path(src)
    suffix = src.suffix.lower()
    dest = _dest(dest_dir, f"{src.stem}-Compressed{src.suffix}")
    cmd = ["ffmpeg", "-n", "-v", "error", "-i", str(src)]
    if suffix == ".mp3":
        cmd += ["-q:a", str(round((100 - quality) * 9 / 99))]
    elif suffix == ".m4a":
        cmd += ["-c:a", "aac", "-b:a", f"{round(32 + quality * 2.88)}k"]
    elif suffix == ".flac":
        cmd += ["-c:a", "flac", "-compression_level", "12"]
    elif suffix == ".wav":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        cmd += _video_encoding(suffix)
        if suffix == ".wmv":
            cmd += ["-q:v", str(max(2, round((100 - quality) * 29 / 99 + 2)))]
        else:
            cmd += ["-crf", str(round((100 - quality) * 40 / 99 + 10))]
            if suffix == ".webm":
                cmd += ["-b:v", "0"]
    _run([*cmd, str(dest)])
    return dest


def strip_metadata(src: Path, dest_dir: Path) -> Path:
    """Remux without descriptive tags or chapters; container technical tags remain."""
    _need_ffmpeg()
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-No Metadata{src.suffix}")
    _run(["ffmpeg", "-n", "-v", "error", "-i", str(src), "-map", "0",
          "-c", "copy", "-map_metadata", "-1", "-map_metadata:s", "-1",
          "-map_chapters", "-1", "-fflags", "+bitexact", str(dest)])
    return dest


def _video_size(path: Path) -> tuple[int, int]:
    for s in _probe(path)["streams"]:
        if s["codec_type"] == "video":
            return int(s["width"]), int(s["height"])
    raise ValueError(f"no video stream: {path}")


def _audio_channels(path: Path) -> int:
    for s in _probe(path)["streams"]:
        if s["codec_type"] == "audio":
            return int(s.get("channels", 0))
    return 0


def _has_stream(path: Path, kind: str) -> bool:
    return any(s["codec_type"] == kind for s in _probe(path)["streams"])


def _duration(src: Path) -> float:
    try:
        duration = float(_probe(src)["format"].get("duration", "nan"))
    except (TypeError, ValueError) as exc:
        raise ValueError("input has no readable finite duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("input has no readable finite duration")
    return duration


def _check_range(start: float, end: float, src: Path) -> None:
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError(f"need finite 0 <= start < end, got {start=}, {end=}")
    duration = _duration(src)
    if end > duration + 0.001:
        raise ValueError(f"range {start}-{end}s outside input duration {duration}s")


# --- trim --------------------------------------------------------------------

def trim_video(src: Path, dest_dir: Path, start: float, end: float) -> Path:
    """Cut ``[start, end)`` seconds; output ``<stem>-Trimmed<ext>``."""
    _need_ffmpeg()
    _check_range(start, end, Path(src))
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Trimmed{src.suffix}")
    _run(["ffmpeg", "-y", "-v", "error",
          "-ss", str(start), "-to", str(end), "-i", str(src),
          *_video_encoding(src.suffix), str(dest)])
    return dest


def trim_audio(src: Path, dest_dir: Path, start: float, end: float) -> Path:
    """Cut ``[start, end)`` seconds; output ``<stem>-Trimmed<ext>``."""
    _need_ffmpeg()
    _check_range(start, end, Path(src))
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Trimmed{src.suffix}")
    _run(["ffmpeg", "-y", "-v", "error",
          "-ss", str(start), "-to", str(end), "-i", str(src), str(dest)])
    return dest


# --- crop / speed --------------------------------------------------------------

def crop_video(src: Path, dest_dir: Path,
               box: tuple[int, int, int, int]) -> Path:
    """Crop to ``box`` (l, upper, r, lower); ``<stem>-Cropped<ext>``."""
    _need_ffmpeg()
    src = Path(src)
    left, u, r, b = validate_boxes([box], _video_size(src))[0]
    if (r - left) % 2 or (b - u) % 2:
        raise ValueError("video crop width and height must be even for these codecs")
    dest = _dest(dest_dir, f"{src.stem}-Cropped{src.suffix}")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-vf", f"crop={r - left}:{b - u}:{left}:{u}:exact=1",
          *_video_encoding(src.suffix), str(dest)])
    return dest


def _atempo_chain(factor: float) -> str:
    """Split ``factor`` into atempo pieces (each filter spans 0.5–2.0)."""
    pieces: list[float] = []
    f = factor
    while f > 2.0:
        pieces.append(2.0)
        f /= 2.0
    while f < 0.5:
        pieces.append(0.5)
        f /= 0.5
    pieces.append(f)
    return ",".join(f"atempo={p}" for p in pieces)


def change_speed(src: Path, dest_dir: Path, factor: float) -> Path:
    """Respeed video+audio by ``factor``; ``<stem>-Speed <f>x<ext>``."""
    _need_ffmpeg()
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"speed factor must be finite and positive, got {factor}")
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Speed {factor:g}x{src.suffix}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if _has_stream(src, "video"):
        cmd += ["-vf", f"setpts={1.0 / factor}*PTS"]
    if _has_stream(src, "audio"):
        cmd += ["-af", _atempo_chain(factor)]
    cmd += [*_video_encoding(src.suffix), str(dest)]
    _run(cmd)
    return dest


# --- join / snapshot / split ---------------------------------------------------

def join_mp4(srcs: list[Path], dest_dir: Path) -> Path:
    """Concatenate mp4s in order (no ``tt()`` entry observed).

    Output named ``<first-stem>-joined.mp4``.
    """
    _need_ffmpeg()
    paths = [Path(s) for s in srcs]
    if not paths:
        raise ValueError("join_mp4 needs at least one input")
    dest = _dest(dest_dir, f"{paths[0].stem}-joined{paths[0].suffix}")
    # The concat grammar treats quotes/newlines as syntax. Staging symlinks
    # gives every real input a safe literal name without escaping user paths.
    with tempfile.TemporaryDirectory(prefix="kumquat-join-") as work:
        folder = Path(work)
        entries = []
        for index, path in enumerate(paths):
            alias = folder / f"input-{index}{path.suffix.lower()}"
            alias.symlink_to(path.resolve())
            entries.append(f"file '{alias.name}'\n")
        listing = folder / "inputs.txt"
        listing.write_text("".join(entries), encoding="utf-8")
        _run(["ffmpeg", "-n", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", str(listing), "-c", "copy", str(dest)])
    return dest


def snapshot_video(src: Path, dest_dir: Path, at: float = 0.0) -> Path:
    """Save the frame at ``at`` seconds as ``<stem>-Snapshot.png``."""
    _need_ffmpeg()
    if not math.isfinite(at) or at < 0:
        raise ValueError(f"snapshot time must be finite and >= 0, got {at}")
    src = Path(src)
    duration = _duration(src)
    if at >= duration:
        raise ValueError(f"snapshot time outside input duration {duration}s")
    dest = _dest(dest_dir, f"{src.stem}-Snapshot.png")
    _run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(src),
          "-frames:v", "1", str(dest)])
    return dest


def split_video(src: Path, dest_dir: Path,
                segment_time: float = 60.0) -> list[Path]:
    """Split into ``segment_time``-s chunks in a ``<stem>-Clips/`` folder."""
    _need_ffmpeg()
    if not math.isfinite(segment_time) or segment_time <= 0:
        raise ValueError(f"segment_time must be finite and positive, got {segment_time}")
    src = Path(src)
    folder = unique_path(Path(dest_dir) / f"{src.stem}-Clips")
    folder.mkdir(parents=True, exist_ok=False)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          *_video_encoding(src.suffix), "-bf", "0", "-fps_mode", "passthrough",
          "-shortest",
          "-force_key_frames", f"expr:gte(t,n_forced*{segment_time})",
          "-f", "segment", "-segment_time", str(segment_time),
          "-reset_timestamps", "1", "-segment_start_number", "1",
          str(folder / f"{src.stem}-%d{src.suffix}")])
    return sorted(folder.iterdir(), key=lambda path: int(path.stem.rsplit("-", 1)[1]))


# --- audio tools ---------------------------------------------------------------

def normalize_audio(src: Path, dest_dir: Path) -> Path:
    """EBU R128 loudness normalize (single-pass ``loudnorm``).

    Output named ``<stem>-Normalized<ext>``.
    """
    _need_ffmpeg()
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Normalized{src.suffix}")
    audio = next((s for s in _probe(src)["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        raise ValueError("normalization needs an audio stream")
    # Dynamic loudnorm upsamples to 192 kHz. Resample back before encoding:
    # FLAC otherwise receives an invalid oversized block on short inputs.
    _run(["ffmpeg", "-n", "-v", "error", "-i", str(src),
          "-af", f"loudnorm,aresample={audio['sample_rate']},asetnsamples=n=4096:p=0",
          "-ar", str(audio["sample_rate"]), str(dest)])
    return dest


def to_mono(src: Path, dest_dir: Path) -> Path:
    """Downmix to one channel; ``<stem>-Mono<ext>``."""
    _need_ffmpeg()
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Mono{src.suffix}")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-ac", "1", str(dest)])
    return dest


def bleep_audio(src: Path, dest_dir: Path, start: float, end: float,
                freq: float = 1000.0) -> Path:
    """Replace ``[start, end)`` with a ``freq`` Hz tone.

    Output named ``<stem>-Bleeped<ext>``.
    """
    _need_ffmpeg()
    _check_range(start, end, Path(src))
    if freq <= 0:
        raise ValueError(f"bleep freq must be positive, got {freq}")
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Bleeped{src.suffix}")
    ms = round(start * 1000)
    fc = (f"sine=frequency={freq}:duration={end - start}[t];"
          f"[t]adelay=delays={ms}:all=1[d];"
          f"[0:a]volume=0:enable='between(t,{start},{end})'[m];"
          f"[m][d]amix=inputs=2:duration=first:"
          f"dropout_transition=0:normalize=0[a]")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-filter_complex", fc, "-map", "[a]", str(dest)])
    return dest


def mute_video(src: Path, dest_dir: Path) -> Path:
    """Drop the audio stream, keep video; ``<stem>-Muted<ext>``."""
    _need_ffmpeg()
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Muted{src.suffix}")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-c:v", "copy", "-an", str(dest)])
    return dest


def redact_video(src: Path, dest_dir: Path, boxes: list | None = None) -> Path:
    """Black out pixel rectangles for the entire clip; audio is not redacted."""
    if not boxes:
        raise ValueError("redactVideo needs boxes=[(left, upper, right, lower), ...]")
    _need_ffmpeg()
    src = Path(src)
    regions = validate_boxes(boxes, _video_size(src))
    filters = ",".join(
        f"drawbox=x={left}:y={top}:w={right-left}:h={bottom-top}:color=black:t=fill"
        for left, top, right, bottom in regions)
    dest = _dest(dest_dir, f"{src.stem}-Redacted{src.suffix}")
    _run(["ffmpeg", "-n", "-v", "error", "-i", str(src),
          "-map", "0:v:0", "-map", "0:a?", "-vf", filters,
          *_video_encoding(src.suffix), "-map_metadata", "-1", str(dest)])
    return dest


def audio_visualizer(src: Path, dest_dir: Path,
                     size: str = "320x240") -> Path:
    """Render a waveform video keeping the audio.

    Output named ``<stem>-Visualizer.mp4``.
    """
    _need_ffmpeg()
    src = Path(src)
    dest = _dest(dest_dir, f"{src.stem}-Visualizer.mp4")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-filter_complex",
          f"[0:a]showwaves=s={size}:mode=line:rate=25[v]",
          "-map", "[v]", "-map", "0:a",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
          "-shortest", str(dest)])
    return dest

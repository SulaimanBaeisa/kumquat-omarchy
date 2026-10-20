"""Audio/video converters (ffmpeg backend). Originals are never modified."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from .converters_pdf import output_path
from .progress import Progress, ProgressCallback, media_duration, parse_ffmpeg_progress

_AUDIO_ONLY = {"mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff", "wma"}


class BackendMissing(RuntimeError):
    """Optional backend absent (ffmpeg). Tests SKIP on this."""


def _need_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise BackendMissing(
            "backend missing: ffmpeg not installed (audio/video support)")


def _run_with_progress(cmd: list[str], duration: float | None,
                       progress: ProgressCallback) -> None:
    """Run ffmpeg streaming `-progress pipe:1` lines into `progress`.

    stderr goes to an unbounded temp file so a chatty ffmpeg can never fill
    a pipe and deadlock the stdout reader. Fractions are only ever emitted
    strictly rising (ffmpeg repeats each time under two keys), and a
    successful run always ends on Progress(1.0). A non-zero
    exit raises CalledProcessError, exactly like the `subprocess.run` path.
    """
    last = -1.0
    with tempfile.TemporaryFile(mode="w+") as err:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err,
                              text=True) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                fraction = parse_ffmpeg_progress(line, duration)
                if fraction is not None and fraction > last:
                    last = fraction
                    progress(Progress(fraction))
            rc = proc.wait()
        if rc != 0:
            err.seek(0)
            raise subprocess.CalledProcessError(rc, cmd, stderr=err.read())
    if last < 1.0:
        progress(Progress(1.0))


def convert_media(src: Path, dest_ext: str, dest_dir: Path,
                  extra: list[str] | None = None,
                  progress: ProgressCallback | None = None) -> Path:
    """Convert src to dest_ext via ffmpeg; returns the output path.

    With `progress`, ffmpeg's machine-readable progress is streamed into it.
    """
    src, dest_dir = Path(src), Path(dest_dir)
    _need_ffmpeg()
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = dest_ext.lstrip(".").lower()
    if not key:
        raise ValueError(f"unsupported media output: {dest_ext!r}")
    dest = output_path(dest_dir / (src.stem + "." + key))
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if key in _AUDIO_ONLY:
        cmd.append("-vn")  # audio-only output: drop any video stream
    if key == "gif":
        cmd.append("-an")  # gif muxer takes no audio stream
    if key in ("webm", "mp4", "mov", "mkv") and not extra:
        # VP9/x264 reject alpha-bearing pixel formats (a GIF decodes to
        # gbrap); normalise so any input converts.
        cmd.extend(["-pix_fmt", "yuv420p"])
    if extra:
        cmd.extend(extra)
    cmd.append(str(dest))
    if progress is None:
        subprocess.run(cmd, check=True)
        return dest
    cmd[2:2] = ["-progress", "pipe:1", "-nostats"]  # right after "-y"
    _run_with_progress(cmd, media_duration(src), progress)
    return dest

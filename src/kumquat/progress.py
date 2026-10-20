"""Progress reporting shared by converters, the job runner and the GUI.

`Progress.fraction` is 0..1 when the backend can measure work, or None when
it cannot (LibreOffice, pandoc, 7z): the GUI then pulses and shows elapsed
time so the user can still tell "working" from "crashed".
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_US_PER_S = 1_000_000
_FFPROBE_TIMEOUT_S = 20
_TIME_KEYS = ("out_time_us=", "out_time_ms=")  # both carry microseconds


@dataclass(frozen=True)
class Progress:
    """One progress update."""

    fraction: float | None
    message: str = ""

    def __post_init__(self) -> None:
        if self.fraction is not None:
            object.__setattr__(self, "fraction", min(1.0, max(0.0, self.fraction)))

    @property
    def text(self) -> str:
        """`42 %` for measured work, otherwise the message."""
        if self.fraction is None:
            return self.message
        return f"{round(self.fraction * 100)} %"


ProgressCallback = Callable[[Progress], None]


def media_duration(src: Path) -> float | None:
    """Duration in seconds via ffprobe, or None when it cannot be read."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(src)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_FFPROBE_TIMEOUT_S, check=False)
        return float(done.stdout.strip()) if done.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def parse_ffmpeg_progress(line: str, duration_s: float | None) -> float | None:
    """Turn one `-progress pipe:1` line into a fraction, or None."""
    line = line.strip()
    if line == "progress=end":
        return 1.0
    if not duration_s:
        return None
    for key in _TIME_KEYS:
        if line.startswith(key):
            value = line[len(key):]
            if not value.isdigit():
                return None
            return min(1.0, int(value) / _US_PER_S / duration_s)
    return None

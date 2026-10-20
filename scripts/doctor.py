#!/usr/bin/env python3
"""Check that Kumquat can run on this machine, and say what is missing.

    python3 scripts/doctor.py

Prints one line per check: ``OK``, ``FAIL`` (Kumquat will not work until fixed) or
``note`` (optional, or only informational). The exit status is 1 if any check
failed. It only reads: it installs nothing and edits no configuration.
Set KUMQUAT_PYTHON to test another interpreter, as ``bin/kumquat`` does.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ID = "io.github.sulaimanbaeisa.kumquat"
ROOT = Path(__file__).resolve().parents[1]

OK, FAIL, NOTE = "OK", "FAIL", "note"

# (executable names, pacman package, what for). Any one name is enough.
REQUIRED_TOOLS = (
    (("ffmpeg",), "ffmpeg", "audio and video"),
    (("ffprobe",), "ffmpeg", "media info"),
)
OPTIONAL_TOOLS = (
    (("soffice", "libreoffice"), "libreoffice-still", "Word, Excel, PowerPoint"),
    (("pandoc",), "pandoc", "Markdown and EPUB"),
    (("7z", "bsdtar"), "7zip or libarchive", "RAR archives"),
    (("wl-copy",), "wl-clipboard", "Copy and Share actions"),
    (("localsend", "localsend_app", "localsend-cli"), "localsend", "the Share action"),
)
# (import name, distribution name, what for): optional Python modules.
OPTIONAL_MODULES = (
    ("openpyxl", "python-openpyxl", "CSV / TSV to XLSX"),
    ("cairosvg", "python-cairosvg", "SVG input"),
    ("pillow_heif", "python-pillow-heif", "HEIC / HEIF / AVIF"),
    ("magic", "python-magic", "file-type detection"),
)


def _python() -> str:
    candidate = os.environ.get("KUMQUAT_PYTHON") or "/usr/bin/python3"
    if os.access(candidate, os.X_OK):
        return candidate
    return shutil.which("python3") or candidate


def _run(command: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


def check_gtk(python: str) -> tuple[str, str, str]:
    code = (
        "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; "
        "print('.'.join(str(f()) for f in (Gtk.get_major_version, "
        "Gtk.get_minor_version, Gtk.get_micro_version))); "
        "raise SystemExit(0 if Gtk.get_minor_version() >= 12 else 3)"
    )
    try:
        done = _run([python, "-c", code])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return FAIL, "Python with GTK 4.12+", f"{python}: {exc}"
    if done.returncode == 0:
        return OK, "Python with GTK 4.12+", f"{python}, GTK {done.stdout.strip()}"
    if done.returncode == 3:
        return FAIL, "Python with GTK 4.12+", f"GTK {done.stdout.strip()} is too old"
    return (
        FAIL,
        "Python with GTK 4.12+",
        f"{_last_line(done.stderr)} (install: gtk4 python-gobject; "
        "a virtualenv does not provide them)",
    )


def check_python_modules(python: str) -> tuple[str, str, str]:
    label = "Python modules Pillow and PyMuPDF"
    code = "import PIL, fitz"
    try:
        done = _run([python, "-c", code])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return FAIL, label, str(exc)
    if done.returncode == 0:
        return OK, label, python
    return (
        FAIL,
        label,
        f"{_last_line(done.stderr)} (install: python-pillow python-pymupdf)",
    )


def check_optional_modules(python: str) -> list[tuple[str, str, str]]:
    results = []
    for module, package, purpose in OPTIONAL_MODULES:
        label = f"Python module {module} ({purpose})"
        try:
            done = _run([python, "-c", f"import {module}"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append((NOTE, label, str(exc)))
            continue
        if done.returncode == 0:
            results.append((OK, label, python))
        else:
            results.append((NOTE, label, f"optional, not installed (package: {package})"))
    return results


def check_tools() -> list[tuple[str, str, str]]:
    results = []
    for names, package, purpose in REQUIRED_TOOLS:
        found = next((shutil.which(name) for name in names if shutil.which(name)), None)
        label = f"{names[0]} ({purpose})"
        if found:
            results.append((OK, label, found))
        else:
            results.append((FAIL, label, f"not found (install: {package})"))
    for names, package, purpose in OPTIONAL_TOOLS:
        found = next((shutil.which(name) for name in names if shutil.which(name)), None)
        label = f"{names[0]} ({purpose})"
        if found:
            results.append((OK, label, found))
        else:
            results.append((NOTE, label, f"optional, not installed (package: {package})"))
    return results


def check_launcher() -> tuple[str, str, str]:
    label = "bin/kumquat starts and lists conversions"
    launcher = ROOT / "bin/kumquat"
    if not launcher.is_file():
        return FAIL, label, f"{launcher} is missing"
    with tempfile.TemporaryDirectory(prefix="kumquat-doctor-") as work:
        sample = Path(work) / "photo.jpg"
        sample.write_bytes(b"not a real picture; only the name is used")
        try:
            done = _run(["/bin/sh", str(launcher), "--files", str(sample), "--list"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            return FAIL, label, str(exc)
    if done.returncode == 0 and "Convert to PNG" in done.stdout:
        return OK, label, str(launcher)
    return FAIL, label, _last_line(done.stderr or done.stdout)


def check_omarchy() -> list[tuple[str, str, str]]:
    omarchy = shutil.which("omarchy")
    if omarchy is None:
        return [(NOTE, "omarchy command", "not found (not an Omarchy machine?)")]
    try:
        done = _run([omarchy, "plugin", "list"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [(NOTE, "omarchy plugin list", str(exc))]
    if done.returncode != 0:
        return [(NOTE, "omarchy plugin list", _last_line(done.stderr or done.stdout))]
    listed = next((line for line in done.stdout.splitlines() if PLUGIN_ID in line), None)
    if listed is None:
        return [
            (
                NOTE,
                "plugin registered with Omarchy",
                "not listed; add it: omarchy plugin add "
                "https://github.com/SulaimanBaeisa/omarchy-plugin-kumquat.git --enable",
            )
        ]
    return [(OK, "plugin registered with Omarchy", " ".join(listed.split()))]


def check_session() -> tuple[str, str, str]:
    if os.environ.get("WAYLAND_DISPLAY"):
        return OK, "Wayland session", os.environ["WAYLAND_DISPLAY"]
    return (
        NOTE,
        "Wayland session",
        "WAYLAND_DISPLAY is not set; the window needs a session",
    )


def run_checks() -> list[tuple[str, str, str]]:
    python = _python()
    return [
        check_gtk(python),
        check_python_modules(python),
        *check_tools(),
        *check_optional_modules(python),
        check_launcher(),
        *check_omarchy(),
        check_session(),
    ]


def main() -> int:
    results = run_checks()
    width = max(len(label) for _, label, _ in results)
    for status, label, detail in results:
        print(f"[{status:>4}] {label:<{width}}  {detail}")
    failed = [label for status, label, _ in results if status == FAIL]
    if failed:
        print(
            f"\n{len(failed)} required check(s) failed; fix these before using Kumquat."
        )
        return 1
    print("\nAll required checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

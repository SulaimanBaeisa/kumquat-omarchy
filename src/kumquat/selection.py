"""File selection helpers: MIME sniffing, clipboard pickup, wheel listings.

Pure logic only. Nothing here imports GTK, so it is safe to use from
`--list`, from tests, and from the GUI layer alike.
"""
from __future__ import annotations

import mimetypes
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import registry_data as _registry_data  # noqa: F401 -- populates REGISTRY (275 rows)
from .registry import ACTIONS, options_for

__all__ = [
    "ACTIONS",
    "ACTION_TITLES",
    "EMPTY_STATE",
    "KEY_HINT",
    "PROMPTS",
    "TOOLS",
    "TOOL_TITLES",
    "clipboard_files",
    "detect_mime",
    "files_listing",
    "format_listing",
    "tools_for",
]

# Type aliases for the wheel listing: one (id, label) row, one mode's rows,
# and the per-file sections keyed by mode.
Row = tuple[str, str]
Rows = list[Row]
Sections = dict[str, Rows]
Listing = list[tuple[str, Sections]]

# --- 26 tool ids + wheel titles ----------------------------------------

TOOL_TITLES = {
    "compress": "COMPRESS",
    "removeMetadata": "METADATA",
    "editImage": "EDIT",
    "annotateImage": "ANNOTATE",
    "frameImage": "ADD BG",
    "cropImage": "CROP",
    "redactImage": "REDACT",
    "createCollage": "COLLAGE",
    "trimVideo": "TRIM",
    "cropVideo": "CROP",
    "changeVideoSpeed": "SPEED",
    "joinVideos": "JOIN",
    "videoSnapshots": "SNAPSHOT",
    "splitVideo": "SPLIT",
    "redactVideo": "REDACT",
    "muteVideo": "MUTE",
    "normalizeAudio": "NORMALIZE",
    "audioToVideo": "VISUALIZE",
    "trimAudio": "TRIM",
    "audioChannels": "CHANNELS",
    "redactAudio": "BLEEP",
    "mergePDF": "MERGE PDF",
    "organizePDF": "ORGANIZE",
    "splitPDF": "SPLIT",
    "extractArchive": "EXTRACT",
    "createPDF": "CREATE PDF",
}

TOOLS = [
    "compress", "removeMetadata", "editImage", "annotateImage",
    "frameImage", "cropImage", "redactImage", "createCollage",
    "trimVideo", "cropVideo", "changeVideoSpeed", "joinVideos",
    "videoSnapshots", "splitVideo", "redactVideo", "muteVideo",
    "normalizeAudio", "audioToVideo", "trimAudio", "audioChannels",
    "redactAudio",
    "mergePDF", "organizePDF", "splitPDF",
    "extractArchive", "createPDF",
]
assert len(TOOLS) == 26 and set(TOOLS) == set(TOOL_TITLES)

# --- 6 file actions + wheel titles ----------------------------------------

ACTION_TITLES = {
    "share": "LOCALSEND",
    "float": "FLOAT",
    "copy": "COPY",
    "move": "MOVE",
    "copy-path": "COPY PATH",
    "open-terminal": "TERMINAL",
}
assert list(ACTION_TITLES) == ACTIONS

# --- single-select tool table ----------------------------------------------

_IMAGE_TOOL_SINGLE = ["compress", "removeMetadata", "editImage",
                      "annotateImage", "frameImage", "cropImage",
                      "redactImage"]
_AUDIO_TOOLS = ["compress", "removeMetadata", "normalizeAudio",
                "audioToVideo", "trimAudio", "audioChannels",
                "redactAudio"]
_VIDEO_SINGLE = ["compress", "removeMetadata", "muteVideo", "trimVideo",
                 "cropVideo", "changeVideoSpeed", "videoSnapshots",
                 "splitVideo", "redactVideo"]
_PDF_SINGLE = ["compress", "removeMetadata", "splitPDF", "organizePDF"]

_IMAGES = {"jpg", "jpeg", "png", "webp", "heic", "heif", "tiff", "tif",
           "svg", "avif", "bmp"}
_AUDIO_TOOLFUL = {"mp3", "m4a", "wav", "flac"}  # ogg/opus/aiff/wma: conversions only
_VIDEO = {"mp4", "mov", "mkv", "webm", "avi", "wmv", "gif"}
_ARCHIVES = {"zip", "tar", "gz", "tgz", "rar"}

# Multi-select allowlist (11 ids; everything else is dropped for >1 file).
MULTI_ALLOW = {"compress", "removeMetadata", "cropImage", "normalizeAudio",
            "muteVideo", "splitPDF", "extractArchive", "createPDF",
            "mergePDF", "joinVideos", "createCollage"}

# Multi-select tool lists, per family. Each equals the allowlist-filtered
# single list plus additions — EXCEPT video, which also keeps
# trimVideo/cropVideo/changeVideoSpeed (absent from the allowlist): the
# single list minus videoSnapshots, splitVideo and redactVideo. In pdf,
# mergePDF swaps in for organizePDF.
# svg multi: createPDF/createCollage only. joinVideos is multi-only
# (needs >1 input; no single list contains it).
_MULTI = {
    "images": ["compress", "removeMetadata", "cropImage",
               "createPDF", "createCollage"],
    "audio": ["compress", "removeMetadata", "normalizeAudio"],
    "video": ["compress", "removeMetadata", "muteVideo", "trimVideo",
              "cropVideo", "changeVideoSpeed", "joinVideos"],
    "pdf": ["compress", "removeMetadata", "splitPDF", "mergePDF"],
    "archives": ["extractArchive"],
}


def _format_key(filename: str) -> str:
    """Extension key for the tool tables: 'photo.JPG'->'jpg', 'a.tar.gz'->'gz'."""
    name = filename.lower()
    if name.endswith(".tar.gz"):
        return "gz"
    suffix = Path(name).suffix
    key = suffix[1:] if suffix.startswith(".") else ""
    return {"tgz": "gz", "tif": "tiff", "jpeg": "jpg", "heif": "heic",
            "aif": "aiff"}.get(key, key)


def _single_tools(key: str) -> tuple[str, list[str]]:
    """(family, single-select tool ids) for a single file."""
    if key in _IMAGES:
        if key == "svg":
            return "images", []  # svg: multi only
        return "images", list(_IMAGE_TOOL_SINGLE)
    if key in _AUDIO_TOOLFUL:
        return "audio", list(_AUDIO_TOOLS)
    if key in _VIDEO:
        if key == "gif":
            return "video", ["removeMetadata"]
        return "video", list(_VIDEO_SINGLE)
    if key == "pdf":
        return "pdf", list(_PDF_SINGLE)
    if key in _ARCHIVES:
        return "archives", ["extractArchive"]
    return "", []


def tools_for(filename: str, multi: bool = False) -> list[str]:
    """Tool ids for one file; multi=True uses the explicit multi-select list."""
    family, single = _single_tools(_format_key(filename))
    if not multi:
        return single
    if not family:
        return []
    if family == "images" and _format_key(filename) == "svg":
        return ["createPDF", "createCollage"]  # svg: multi only
    return list(_MULTI[family])


def files_listing(files: list[str], mimes: list[str] | None = None) -> Listing:
    """Per-file wheel sections: [(filename, {conversions/tools/actions})].

    conversions: [(conversion id, label)] from options_for.
    tools: [(tool id, wheel title)] from the tool tables and allowlist.
    actions: [(action id, wheel title)] always all six.
    """
    multi = len(files) > 1
    if mimes is None:
        mimes = [detect_mime(f) for f in files]
    out = []
    for filename, mime in zip(files, mimes, strict=False):
        convs = [(c.id, c.label)
                 for c in options_for(Path(filename).name, mime or "")]
        tools = [(t, TOOL_TITLES[t]) for t in tools_for(filename, multi)]
        actions = [(a, ACTION_TITLES[a]) for a in ACTIONS]
        out.append((filename, {"conversions": convs, "tools": tools,
                               "actions": actions}))
    return out


def detect_mime(filename: str) -> str:
    """Best-effort mime for --list; extension match in options_for wins anyway."""
    path = Path(filename)
    if path.is_file():
        try:
            import magic
            return magic.from_file(str(path), mime=True)
        except Exception:
            pass
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def clipboard_files() -> list[str]:
    """Files the user copied in their file manager (Wayland ``text/uri-list``).

    A compositor does not let a normal app read another window's selection,
    so the hotkey has no way to know what is selected in Files/Nautilus.
    Copying the file (Ctrl+C) puts ``file://`` URIs on the clipboard, which
    IS readable — that is the bridge this function uses.
    """
    if not shutil.which("wl-paste"):
        return []
    try:
        types = subprocess.run(
            ["wl-paste", "--list-types"], capture_output=True,
            text=True, timeout=3).stdout
        if "text/uri-list" not in types:
            return []
        raw = subprocess.run(
            ["wl-paste", "--type", "text/uri-list"], capture_output=True,
            text=True, timeout=3).stdout
    except Exception:
        return []
    files: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("file://"):
            continue
        path = unquote(urlparse(line).path)
        if Path(path).exists():
            files.append(path)
    return files


EMPTY_STATE = ("No conversions for this format. "
               "Tap Control for file actions.")
PROMPTS = {
    "conversions": "Choose a conversion format",
    "tools": "Choose a file tool",
    "actions": "Choose a file action",
}
KEY_HINT = ("Hold Shift for conversions, Super/Meta for tools, "
            "Control for actions. Enter applies, arrows move, Escape cancels.")


def format_listing(listing: Listing) -> str:
    """Render the text wheel."""
    lines = []
    for filename, sections in listing:
        lines.append(f"== {filename} ==")
        lines.append(f"{PROMPTS['conversions']} ({KEY_HINT}):")
        if sections["conversions"]:
            for cid, label in sections["conversions"]:
                lines.append(f"  {label} [{cid}]")
        else:
            lines.append(f"  {EMPTY_STATE}")
        lines.append(f"{PROMPTS['tools']}:")
        if sections["tools"]:
            for tid, title in sections["tools"]:
                lines.append(f"  {title} [{tid}]")
        else:
            lines.append("  No file tools for this format.")
        lines.append(f"{PROMPTS['actions']}:")
        for aid, title in sections["actions"]:
            lines.append(f"  {title} [{aid}]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

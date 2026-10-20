"""File actions (Linux/Wayland backends).

Implements the 6 file actions for
Omarchy/Hyprland:

- ``copy`` → :func:`copy_files` (``wl-copy -t text/uri-list``)
- ``copyPath`` → :func:`copy_paths` (``wl-copy`` plain text, one per line)
- ``move`` → :func:`move_files` (stdlib move, returns new paths)
- ``openTerminal`` → :func:`open_terminal` (``$TERMINAL`` or fallback)
- ``airDrop`` → :func:`share` (the installed LocalSend app, else its CLI)
- ``float`` → :func:`float_shelf` (shelf manifest + ``hyprctl`` pin)

Desktop integrations require their real executables and raise BackendMissing
when absent. Unit tests intercept external processes; the effect sweep never
changes the real clipboard, compositor, or sharing state. Move tests use only
disposable generated copies.
"""
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.request import pathname2url

__all__ = [
    "BackendMissing",
    "ShareResult",
    "copy_files",
    "copy_paths",
    "float_shelf",
    "move_files",
    "open_terminal",
    "share",
]

class BackendMissing(RuntimeError):
    """Optional backend absent (wl-copy, hyprctl, terminal). Tests SKIP."""


def _need(exe: str, what: str) -> str:
    path = shutil.which(exe)
    if path is None:
        raise BackendMissing(f"backend missing: {exe} not installed ({what})")
    return path


def copy_paths(paths: list[Path]) -> str:
    """Copy full paths as text, one per line."""
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("copy_paths needs at least one path")
    _need("wl-copy", "copy paths to clipboard")
    text = "\n".join(str(p) for p in paths)
    subprocess.run(["wl-copy"], input=text.encode(), check=True)
    return text


def copy_files(paths: list[Path]) -> str:
    """Copy files to clipboard, ready to paste.

    Uses the ``text/uri-list`` MIME type (``file://`` URIs, one per
    line) so Wayland file managers paste real files. ``pathname2url``
    already emits the leading ``///`` for absolute paths, so the
    prefix is ``file:`` + that (== ``file:///abs/path``).
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("copy_files needs at least one path")
    _need("wl-copy", "copy files to clipboard")
    payload = "\n".join("file:" + pathname2url(str(p)) for p in paths)
    subprocess.run(["wl-copy", "-t", "text/uri-list"],
                   input=payload.encode(), check=True)
    return payload

def move_files(paths: list[Path], dest_dir: Path) -> list[Path]:
    """Move originals into ``dest_dir``; returns new paths.

    Preflight validation: every source must exist and no same-named file may
    already sit in ``dest_dir`` — both are validated *before* anything
    moves, so a missing Nth source (``FileNotFoundError``) or a target
    collision (``FileExistsError``, never silent overwrite) leaves the
    whole selection untouched. Runtime I/O failures are not transactional.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("move_files needs at least one path")
    dest_dir = Path(dest_dir)
    for src in paths:
        if not src.exists() and not src.is_symlink():
            raise FileNotFoundError(f"move source missing: {src}")
        resolved = src.resolve()
        if src.is_dir() and (dest_dir.resolve() == resolved
                             or resolved in dest_dir.resolve().parents):
            raise ValueError("cannot move a directory into itself or inside itself")
    targets = [dest_dir / src.name for src in paths]
    if len(set(targets)) != len(targets):
        raise FileExistsError("selected files have a same-name destination collision")
    resolved_sources = [src.resolve() for src in paths]
    if any(src in other.parents
           for src in resolved_sources for other in resolved_sources):
        raise ValueError("cannot move both a directory and its selected contents")
    for target in targets:
        if target.exists() or target.is_symlink():
            raise FileExistsError(
                f"move target exists, refusing to overwrite: {target}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    return [
        Path(shutil.move(str(src), str(target)))
        for src, target in zip(paths, targets, strict=False)
    ]


def _detect_terminal() -> str:
    """``$TERMINAL`` first, then common Wayland terminals."""
    env = os.environ.get("TERMINAL", "").strip()
    if env:
        first = env.split()[0]
        if shutil.which(first) is None:
            raise BackendMissing(
                f"backend missing: $TERMINAL={env!r} not installed "
                "(open terminal)")
        return env
    for cand in ("kitty", "foot", "alacritty", "ghostty", "wezterm",
                 "gnome-terminal", "xterm"):
        if shutil.which(cand) is not None:
            return cand
    raise BackendMissing(
        "backend missing: no terminal found ($TERMINAL unset; tried "
        "kitty/foot/alacritty/ghostty/wezterm/gnome-terminal/xterm)")


def open_terminal(path: Path) -> list[str]:
    """Open ``path`` (or its containing folder) in a terminal.

    Returns the argv spawned (detached via ``Popen``).
    """
    path = Path(path)
    cwd = path if path.is_dir() else path.parent
    argv = shlex.split(_detect_terminal())
    subprocess.Popen(argv, cwd=str(cwd),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return argv

@dataclass(frozen=True)
class ShareResult:
    """How a share hand-off happened, so the UI can tell the user what to do next."""

    argv: list[str]
    app: str  # "app": the installed LocalSend window; "cli": a terminal device list
    on_clipboard: bool  # the selected files were also copied for pasting


def share(paths: list[Path]) -> ShareResult:
    """Hand the selection to the user's installed LocalSend.

    The desktop app is preferred: it is normally already running in the tray and
    owns LocalSend's network port, so a second ``localsend-cli`` would fail with
    "Address already in use". Launching ``localsend`` again just surfaces that
    running instance, and the selected files are put on the Wayland clipboard
    so they can be pasted or dragged in. Without the app, ``localsend-cli -f``
    (a text device picker) is opened in a terminal. Neither installed raises
    ``BackendMissing``.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("share needs at least one path")
    if shutil.which("localsend") is not None:
        copied = _try_copy_files(paths)
        argv = ["localsend"]
        # A new session keeps the tray app alive after this window closes.
        subprocess.Popen(argv, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ShareResult(argv, "app", copied)
    if shutil.which("localsend-cli") is None:
        raise BackendMissing(
            "backend missing: no share target (LocalSend is not installed)")
    argv = shlex.split(_detect_terminal()) + ["localsend-cli"]
    for p in paths:
        argv += ["-f", str(p)]
    subprocess.Popen(argv, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ShareResult(argv, "cli", False)


def _try_copy_files(paths: list[Path]) -> bool:
    """Best-effort clipboard copy; a missing ``wl-copy`` only skips the bonus."""
    try:
        copy_files(paths)
    except BackendMissing:
        return False
    return True


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    cache = Path(base) if base else Path.home() / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def float_shelf(paths: list[Path]) -> Path:
    """Keep files in a floating shelf.

    Writes the selection to ``~/.cache/kumquat-shelf.json`` and
    floats the active window (``hyprctl dispatch togglefloating``)
    so it can be pinned to a screen edge; returns the manifest path.
    No ``hyprctl`` → ``BackendMissing``.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("float_shelf needs at least one path")
    _need("hyprctl", "float shelf window")
    manifest = _cache_dir() / "kumquat-shelf.json"
    manifest.write_text(
        json.dumps({"files": [str(p) for p in paths]}, indent=2) + "\n",
        encoding="utf-8")
    subprocess.run(["hyprctl", "dispatch", "togglefloating"], check=True)
    return manifest

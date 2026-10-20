"""File actions (TDD): copy-paths / copy-files / move / terminal / share / shelf.

TDD record: this file was written FIRST against a nonexistent
`kumquat.actions` (RED: ModuleNotFoundError on collection),
then the module was implemented to make it GREEN.

Every external subprocess/which call is monkeypatched here regardless of
whether a desktop backend is installed. Tests never touch the real clipboard,
compositor, or network.
Only move_files/copy_paths payload assertions use real local files
(moves inside tmp_path, clipboard bytes captured by a fake).
Absent backends raise BackendMissing and tests assert the raise —
they never fail.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kumquat.actions import (
    BackendMissing,
    copy_files,
    copy_paths,
    float_shelf,
    move_files,
    open_terminal,
    share,
)


def _mk(path: Path, text: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _which_map(mapping: dict, monkeypatch) -> None:
    """Fake shutil.which: present iff name in mapping (name -> path)."""
    monkeypatch.setattr(
        shutil, "which", lambda name: mapping.get(name))


class _RunCapture:
    """Stand-in for subprocess.run/Popen capturing argv + stdin."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": kwargs})

    def popen(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": kwargs})

        class _P:
            pid = 1234

        return _P()


# --- copy_paths ------------------------------------------------------

def test_copy_paths_copies_newline_joined_paths(tmp_path, monkeypatch):
    a = _mk(tmp_path / "a.txt")
    b = _mk(tmp_path / "b.txt")
    cap = _RunCapture()
    _which_map({"wl-copy": "/usr/bin/wl-copy"}, monkeypatch)
    monkeypatch.setattr(subprocess, "run", cap.run)
    text = copy_paths([a, b])
    assert text == f"{a}\n{b}"
    assert cap.calls[0]["argv"] == ["wl-copy"]
    assert cap.calls[0]["kwargs"]["input"] == text.encode()


def test_copy_paths_rejects_empty(tmp_path, monkeypatch):
    _which_map({"wl-copy": "/usr/bin/wl-copy"}, monkeypatch)
    with pytest.raises(ValueError):
        copy_paths([])


def test_copy_paths_missing_wl_copy_raises(tmp_path, monkeypatch):
    _which_map({}, monkeypatch)
    with pytest.raises(BackendMissing, match="wl-copy"):
        copy_paths([tmp_path / "a.txt"])

# --- copy_files ------------------------------------------------------

def test_copy_files_uses_uri_list(tmp_path, monkeypatch):
    from urllib.parse import unquote, urlparse

    a = _mk(tmp_path / "a.txt")
    b = _mk(tmp_path / "sp ace.txt")
    cap = _RunCapture()
    _which_map({"wl-copy": "/usr/bin/wl-copy"}, monkeypatch)
    monkeypatch.setattr(subprocess, "run", cap.run)
    payload = copy_files([a, b])
    call = cap.calls[0]
    assert call["argv"] == ["wl-copy", "-t", "text/uri-list"]
    assert call["kwargs"]["input"] == payload.encode()
    got = [unquote(urlparse(line).path)
           for line in payload.splitlines()]
    assert got == [str(a), str(b)]


def test_copy_files_rejects_empty(tmp_path, monkeypatch):
    _which_map({"wl-copy": "/usr/bin/wl-copy"}, monkeypatch)
    with pytest.raises(ValueError):
        copy_files([])


def test_copy_files_missing_wl_copy_raises(tmp_path, monkeypatch):
    _which_map({}, monkeypatch)
    with pytest.raises(BackendMissing, match="wl-copy"):
        copy_files([tmp_path / "a.txt"])


# --- move_files ------------------------------------------------------

def test_move_files_moves_and_returns_new_paths(tmp_path):
    src1 = _mk(tmp_path / "src" / "a.txt")
    src2 = _mk(tmp_path / "src" / "b.txt")
    dest = tmp_path / "dest"
    moved = move_files([src1, src2], dest)
    assert moved == [dest / "a.txt", dest / "b.txt"]
    for p in moved:
        assert p.read_text(encoding="utf-8") == "data"
    assert not src1.exists() and not src2.exists()


def test_move_files_creates_dest_dir(tmp_path):
    src = _mk(tmp_path / "a.txt")
    dest = tmp_path / "new" / "nested"
    (moved,) = move_files([src], dest)
    assert moved == dest / "a.txt" and moved.exists()


def test_move_files_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        move_files([], tmp_path / "dest")


def test_move_files_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        move_files([tmp_path / "ghost.txt"], tmp_path / "dest")


def test_move_files_refuses_overwrite(tmp_path):
    # Final-review must-fix #2: same-named file in dest must raise,
    # never be silently overwritten.
    src = _mk(tmp_path / "src" / "a.txt")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        move_files([src], dest)
    assert src.read_text(encoding="utf-8") == "data"  # source untouched
    assert (dest / "a.txt").read_text(encoding="utf-8") == "keep me"


def test_move_refuses_colliding_selected_names_before_any_move(tmp_path):
    first = _mk(tmp_path / "a" / "same.txt", "first bytes")
    second = _mk(tmp_path / "b" / "same.txt", "second bytes")
    with pytest.raises(FileExistsError, match="same|collision"):
        move_files([first, second], tmp_path / "dest")
    assert first.read_text() == "first bytes"
    assert second.read_text() == "second bytes"


def test_move_refuses_dangling_target_symlink(tmp_path):
    src = _mk(tmp_path / "source" / "data.txt")
    dest = tmp_path / "dest"
    dest.mkdir()
    link = dest / src.name
    link.symlink_to(tmp_path / "missing-target")
    with pytest.raises(FileExistsError):
        move_files([src], dest)
    assert src.read_text() == "data" and link.is_symlink()


def test_move_refuses_destination_inside_source_without_creating_it(tmp_path):
    directory = tmp_path / "source"
    _mk(directory / "data.txt")
    dest = directory / "new" / "nested"
    with pytest.raises(ValueError, match="inside|itself"):
        move_files([directory], dest)
    assert not dest.exists()
    assert (directory / "data.txt").read_text() == "data"


def test_move_files_all_or_nothing_on_missing(tmp_path):
    # Final-review must-fix #2: a missing Nth source leaves NOTHING moved.
    src1 = _mk(tmp_path / "src" / "a.txt")
    dest = tmp_path / "dest"
    with pytest.raises(FileNotFoundError):
        move_files([src1, tmp_path / "src" / "ghost.txt"], dest)
    assert src1.exists()  # first file NOT half-moved

# --- open_terminal ---------------------------------------------------

def test_open_terminal_dir_uses_terminal_env(tmp_path, monkeypatch):
    target = tmp_path / "proj"
    target.mkdir()
    cap = _RunCapture()
    _which_map({"myterm": "/usr/bin/myterm"}, monkeypatch)
    monkeypatch.setenv("TERMINAL", "myterm")
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    argv = open_terminal(target)
    assert argv == ["myterm"]
    assert cap.calls[0]["kwargs"]["cwd"] == str(target)


def test_open_terminal_file_opens_containing_dir(tmp_path, monkeypatch):
    (tmp_path / "proj").mkdir(parents=True, exist_ok=True)
    src = _mk(tmp_path / "proj" / "note.txt")
    cap = _RunCapture()
    _which_map({"myterm": "/usr/bin/myterm"}, monkeypatch)
    monkeypatch.setenv("TERMINAL", "myterm")
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    open_terminal(src)
    assert cap.calls[0]["kwargs"]["cwd"] == str(src.parent)


def test_open_terminal_falls_back_to_kitty(tmp_path, monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    cap = _RunCapture()
    _which_map({"kitty": "/usr/bin/kitty"}, monkeypatch)
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    assert open_terminal(tmp_path) == ["kitty"]


def test_open_terminal_no_terminal_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    _which_map({}, monkeypatch)
    with pytest.raises(BackendMissing, match="no terminal"):
        open_terminal(tmp_path)


# --- share -----------------------------------------------------------

def test_share_opens_the_installed_app_and_copies_the_files(tmp_path, monkeypatch):
    a = _mk(tmp_path / "a.txt")
    b = _mk(tmp_path / "b.txt")
    cap = _RunCapture()
    _which_map({"localsend": "/usr/bin/localsend",
                "localsend-cli": "/usr/bin/localsend-cli",
                "wl-copy": "/usr/bin/wl-copy"}, monkeypatch)
    monkeypatch.setattr(subprocess, "run", cap.run)
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    result = share([a, b])
    assert result.app == "app" and result.on_clipboard is True
    assert result.argv == ["localsend"]
    clip, launch = cap.calls[0], cap.calls[1]
    assert clip["argv"][0] == "wl-copy"
    assert launch["argv"] == ["localsend"]
    # the already-running tray instance must not die with this process
    assert launch["kwargs"].get("start_new_session") is True


def test_share_app_still_opens_without_a_clipboard_tool(tmp_path, monkeypatch):
    cap = _RunCapture()
    _which_map({"localsend": "/usr/bin/localsend"}, monkeypatch)
    monkeypatch.setattr(subprocess, "run", cap.run)
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    result = share([_mk(tmp_path / "a.txt")])
    assert result.app == "app" and result.on_clipboard is False
    assert [c["argv"] for c in cap.calls] == [["localsend"]]


def test_share_uses_the_cli_in_a_terminal_when_no_app_is_installed(
        tmp_path, monkeypatch):
    a = _mk(tmp_path / "a.txt")
    b = _mk(tmp_path / "b.txt")
    cap = _RunCapture()
    _which_map({"localsend-cli": "/usr/bin/localsend-cli",
                "xdg-terminal-exec": "/usr/bin/xdg-terminal-exec"}, monkeypatch)
    monkeypatch.setenv("TERMINAL", "xdg-terminal-exec")
    monkeypatch.setattr(subprocess, "Popen", cap.popen)
    result = share([a, b])
    assert result.app == "cli" and result.on_clipboard is False
    assert result.argv == ["xdg-terminal-exec", "localsend-cli",
                           "-f", str(a), "-f", str(b)]
    assert cap.calls[0]["argv"] == result.argv


def test_share_cli_without_any_terminal_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    _which_map({"localsend-cli": "/usr/bin/localsend-cli"}, monkeypatch)
    with pytest.raises(BackendMissing, match="no terminal"):
        share([_mk(tmp_path / "a.txt")])


def test_share_rejects_empty(tmp_path, monkeypatch):
    _which_map({"localsend": "/usr/bin/localsend"}, monkeypatch)
    with pytest.raises(ValueError):
        share([])


def test_share_missing_backend_raises(tmp_path, monkeypatch):
    _which_map({}, monkeypatch)
    with pytest.raises(BackendMissing, match="no share target"):
        share([tmp_path / "a.txt"])


# --- float_shelf -----------------------------------------------------

def test_float_shelf_writes_manifest_and_pins(tmp_path, monkeypatch):
    a = _mk(tmp_path / "a.txt")
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    cap = _RunCapture()
    _which_map({"hyprctl": "/usr/bin/hyprctl"}, monkeypatch)
    monkeypatch.setattr(subprocess, "run", cap.run)
    manifest = float_shelf([a])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["files"] == [str(a)]
    assert manifest == cache / "kumquat-shelf.json"
    assert cap.calls[0]["argv"] == [
        "hyprctl", "dispatch", "togglefloating"]


def test_float_shelf_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _which_map({"hyprctl": "/usr/bin/hyprctl"}, monkeypatch)
    with pytest.raises(ValueError):
        float_shelf([])


def test_float_shelf_missing_hyprctl_raises(tmp_path, monkeypatch):
    a = _mk(tmp_path / "a.txt")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _which_map({}, monkeypatch)
    with pytest.raises(BackendMissing, match="hyprctl"):
        float_shelf([a])

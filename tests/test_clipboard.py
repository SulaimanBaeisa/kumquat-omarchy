"""Explicit legacy clipboard pickup via ``--from-clipboard``.

Copying a file in the file manager (Ctrl+C) puts ``text/uri-list`` entries
there. Bare ``--gui`` and the Nautilus-selection workflow never consult it.
"""

from __future__ import annotations

import subprocess

from kumquat import cli


class _Proc:
    def __init__(self, out: str):
        self.stdout = out
        self.returncode = 0


def _fake_wl(uri: str = "", types: str = "text/uri-list\n", calls=None):
    """Stub wl-paste: --list-types answers `types`, --type answers `uri`."""
    def run(cmd, **kw):
        if calls is not None:
            calls.append(cmd)
        if "--list-types" in cmd:
            return _Proc(types)
        if "--type" in cmd:
            return _Proc(uri)
        return _Proc("")
    return run


def test_returns_file_paths_from_uri_list(tmp_path, monkeypatch):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    uri = f"file://{f}\r\n"
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")
    monkeypatch.setattr(cli.subprocess, "run", _fake_wl(uri))
    assert cli.clipboard_files() == [str(f)]


def test_percent_encoding_is_decoded(tmp_path, monkeypatch):
    f = tmp_path / "my photo.png"
    f.write_bytes(b"x")
    encoded = str(f).replace(" ", "%20")
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")
    monkeypatch.setattr(cli.subprocess, "run",
                        _fake_wl(f"file://{encoded}\r\n"))
    assert cli.clipboard_files() == [str(f)]


def test_ignores_non_file_uris(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")
    monkeypatch.setattr(cli.subprocess, "run",
                        _fake_wl("https://example.com/a.png\r\n"))
    assert cli.clipboard_files() == []


def test_ignores_missing_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")
    monkeypatch.setattr(cli.subprocess, "run",
                        _fake_wl(f"file://{tmp_path}/gone.jpg\r\n"))
    assert cli.clipboard_files() == []


def test_returns_empty_when_clipboard_has_no_uri_list(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")
    monkeypatch.setattr(cli.subprocess, "run",
                        _fake_wl(types="image/png\n"))
    assert cli.clipboard_files() == []


def test_returns_empty_without_wl_paste(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _e: None)
    assert cli.clipboard_files() == []


def test_survives_subprocess_failure(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _e: "/usr/bin/wl-paste")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="wl-paste", timeout=3)

    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli.clipboard_files() == []


def test_convert_flag_uses_clipboard(tmp_path, monkeypatch):
    """--from-clipboard feeds --convert without an explicit --files."""
    src = tmp_path / "in.jpg"
    from PIL import Image
    Image.new("RGB", (8, 8), "red").save(src, "JPEG")

    monkeypatch.setattr(cli, "clipboard_files", lambda: [str(src)])
    out = tmp_path / "out"
    rc = cli.main(["--from-clipboard", "--convert",
                   "image-jpg-to-png", "--out", str(out)])
    assert rc == 0
    assert (out / "in.png").exists()


def test_explicit_clipboard_gui_remains_supported(tmp_path, monkeypatch):
    source = tmp_path / "copied.jpg"
    source.touch()
    monkeypatch.setattr(cli, "clipboard_files", lambda: [str(source)])
    calls = []
    monkeypatch.setattr(cli, "run_gui", lambda files, from_clipboard=False:
                        calls.append((files, from_clipboard)))
    assert cli.main(["--gui", "--from-clipboard"]) == 0
    assert calls == [([str(source)], True)]

"""Pure helpers of the embedded file browser, tested without GTK.

The picker widget cannot be built in this venv (`gi` is absent), so the
testable core is the pure layer of ``kumquat.gui.picker``:

- ``Entry`` / ``list_entries()``: what a directory listing shows — folders
  first, case-insensitive order, dot-files hidden unless asked for, broken
  symlinks skipped, absolute paths, and ``[]`` for missing/unreadable dirs;
- ``parent_dir()``: one level up, with ``/`` staying ``/``;
- ``display_path()``: the header label text, ``$HOME`` shortened to ``~``;
- ``paths_from_files()``: local paths from ``Gio.File``-like objects —
  ``None``, path-less, non-string, empty and duplicate entries dropped.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kumquat.gui.picker import (
    Entry,
    display_path,
    list_entries,
    parent_dir,
    paths_from_files,
)

SRC = str(Path(__file__).resolve().parents[1] / "src")


class FakeFile:
    """Stand-in for a `Gio.File`: only `get_path()` matters here."""

    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


def test_module_imports_without_gtk():
    """Importing picker.py must not pull in gi/GTK (the venv has no gi)."""
    code = (
        "import sys; import kumquat.gui.picker; "
        "assert 'gi' not in sys.modules, 'picker.py imported GTK eagerly'"
    )
    env = dict(os.environ, PYTHONPATH=SRC)
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr


def test_create_picker_is_exposed_without_gtk():
    """``create_picker`` must be importable headlessly; GTK loads on call."""
    from kumquat.gui.picker import create_picker

    assert callable(create_picker)


def _make_tree(root: Path) -> None:
    """Populate ``root`` with dirs, files, dot-files and a broken symlink."""
    (root / "beta").mkdir()
    (root / "Alpha").mkdir()
    (root / ".hidden_dir").mkdir()
    (root / "zeta.txt").write_text("z")
    (root / "Bravo.jpg").write_text("b")
    (root / "alpha.md").write_text("a")
    (root / ".secret").write_text("s")
    (root / "dangling").symlink_to(root / "does-not-exist")


def test_entry_is_frozen_dataclass():
    entry = Entry(name="a.jpg", path="/tmp/a.jpg", is_dir=False)
    with pytest.raises(AttributeError):
        entry.name = "b.jpg"  # type: ignore[misc]


def test_list_entries_dirs_first_case_insensitive(tmp_path):
    _make_tree(tmp_path)
    names = [e.name for e in list_entries(tmp_path)]
    assert names == ["Alpha", "beta", "alpha.md", "Bravo.jpg", "zeta.txt"]


def test_list_entries_marks_directories(tmp_path):
    _make_tree(tmp_path)
    kinds = {e.name: e.is_dir for e in list_entries(tmp_path)}
    assert kinds["Alpha"] is True
    assert kinds["zeta.txt"] is False


def test_list_entries_paths_are_absolute(tmp_path):
    _make_tree(tmp_path)
    for entry in list_entries(str(tmp_path)):
        assert os.path.isabs(entry.path)
        assert entry.path == str(tmp_path / entry.name)


def test_list_entries_shows_hidden_on_request(tmp_path):
    _make_tree(tmp_path)
    names = [e.name for e in list_entries(tmp_path, show_hidden=True)]
    assert names == [
        ".hidden_dir", "Alpha", "beta", ".secret", "alpha.md", "Bravo.jpg", "zeta.txt",
    ]


def test_list_entries_skips_broken_symlinks(tmp_path):
    _make_tree(tmp_path)
    assert "dangling" not in [e.name for e in list_entries(tmp_path, show_hidden=True)]


def test_list_entries_follows_symlinked_dir(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    kinds = {e.name: e.is_dir for e in list_entries(tmp_path)}
    assert kinds == {"link": True, "real": True}


def test_list_entries_missing_dir_is_empty(tmp_path):
    assert list_entries(tmp_path / "nope") == []


def test_list_entries_file_instead_of_dir_is_empty(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    assert list_entries(target) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_list_entries_unreadable_dir_is_empty(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "inside.txt").write_text("x")
    locked.chmod(0)
    try:
        assert list_entries(locked) == []
    finally:
        locked.chmod(0o755)


def test_parent_dir_goes_up_one_level():
    assert parent_dir("/home/user/docs") == "/home/user"


def test_parent_dir_accepts_path_objects():
    assert parent_dir(Path("/tmp/qa-fixtures")) == "/tmp"


def test_parent_dir_of_root_is_root():
    assert parent_dir("/") == "/"


def test_display_path_shortens_home():
    assert display_path("/home/user/Pictures", home="/home/user") == "~/Pictures"


def test_display_path_home_itself_is_tilde():
    assert display_path("/home/user", home="/home/user") == "~"


def test_display_path_leaves_lookalike_prefix_alone():
    assert display_path("/home/username", home="/home/user") == "/home/username"


def test_display_path_outside_home_is_unchanged():
    assert display_path("/tmp/qa-fixtures", home="/home/user") == "/tmp/qa-fixtures"


def test_keeps_local_paths():
    files = [FakeFile("/tmp/a.jpg"), FakeFile("/tmp/b.wav")]
    assert paths_from_files(files) == ["/tmp/a.jpg", "/tmp/b.wav"]


def test_drops_virtual_entries_without_path():
    files = [FakeFile("/tmp/a.jpg"), FakeFile(None)]
    assert paths_from_files(files) == ["/tmp/a.jpg"]


def test_drops_none_items():
    assert paths_from_files([None, FakeFile("/tmp/c.png")]) == ["/tmp/c.png"]


def test_drops_non_string_paths():
    files = [FakeFile(b"/tmp/bytes.jpg"), FakeFile(42), FakeFile("/tmp/ok.pdf")]
    assert paths_from_files(files) == ["/tmp/ok.pdf"]


def test_drops_empty_paths():
    assert paths_from_files([FakeFile(""), FakeFile("/tmp/d.gif")]) == ["/tmp/d.gif"]


def test_drops_objects_without_get_path():
    assert paths_from_files([object(), FakeFile("/tmp/e.webp")]) == ["/tmp/e.webp"]


def test_deduplicates_preserving_order():
    files = [
        FakeFile("/tmp/a.jpg"),
        FakeFile("/tmp/b.wav"),
        FakeFile("/tmp/a.jpg"),
    ]
    assert paths_from_files(files) == ["/tmp/a.jpg", "/tmp/b.wav"]


def test_empty_is_empty():
    assert paths_from_files([]) == []

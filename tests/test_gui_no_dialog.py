"""The wheel never opens a separate file-chooser dialog.

The user's bug: SUPER+E opened GTK's chooser, where one click on a file only
navigated. The fix embeds a custom browser in the wheel window, so the GTK
chooser classes are banned from the source tree, and the CLI holds no GTK.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "kumquat"
BANNED = ("Gtk.FileChooserDialog(", "Gtk.FileDialog(", "Gtk.FileChooserWidget(")


def _sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_source_tree_is_scanned():
    names = {p.name for p in _sources()}
    assert {"cli.py", "wheel.py", "app.py"} <= names


@pytest.mark.parametrize("banned", BANNED)
def test_no_file_chooser_dialogs_in_src(banned):
    offenders = [str(p.relative_to(SRC)) for p in _sources()
                 if banned in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_cli_has_no_gtk():
    assert "Gtk." not in (SRC / "cli.py").read_text(encoding="utf-8")

"""The pure selection layer: importable without GTK, behaviour unchanged.

`src/kumquat/selection.py` is the no-GTK half of the wheel: extension
tables, tool lists, clipboard pickup and the text renderer. These tests
mostly guard the extraction itself, so they exercise the public names the
GUI layer and `cli.py` rely on.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter that can import ``kumquat``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SRC), env.get("PYTHONPATH", "")) if part
    )
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env)


def test_selection_imports_without_gtk():
    """Importing selection.py must not pull in gi/GTK."""
    code = (
        "import sys; import kumquat.selection; "
        "assert 'gi' not in sys.modules, 'selection.py imported GTK'"
    )
    result = _run_isolated(code)
    assert result.returncode == 0, result.stderr


def test_detect_mime_is_public():
    from kumquat.selection import detect_mime

    assert callable(detect_mime)


def test_clipboard_files_returns_list():
    from kumquat.selection import clipboard_files

    assert isinstance(clipboard_files(), list)


def test_tools_for_follows_the_wheel_tables():
    from kumquat.selection import tools_for

    assert "compress" in tools_for("photo.jpg")
    assert tools_for("photo.jpg", multi=True) == [
        "compress", "removeMetadata", "cropImage", "createPDF",
        "createCollage",
    ]
    assert tools_for("song.wma") == []          # conversions only
    assert tools_for("backup.unknown") == []


def test_files_listing_shape_is_unchanged():
    from kumquat.selection import files_listing

    listing = files_listing(["photo.jpg"], ["image/jpeg"])

    name, sections = listing[0]
    assert name == "photo.jpg"
    assert ("image-jpg-to-png", "Convert to PNG") in sections["conversions"]
    assert sections["actions"][0] == ("share", "LOCALSEND")


def test_format_listing_starts_with_the_verbatim_header():
    from kumquat.selection import files_listing, format_listing

    text = format_listing(files_listing(["pic.jpg"], ["image/jpeg"]))

    assert text.startswith("== pic.jpg ==\nChoose a conversion format")

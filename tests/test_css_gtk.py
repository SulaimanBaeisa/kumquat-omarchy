"""The generated stylesheet must parse cleanly in real GTK 4.

The project virtualenv has no ``gi`` bindings, so the parsing happens in a
subprocess running the system interpreter, which has PyGObject and GTK 4.
Each palette's CSS is loaded into a ``Gtk.CssProvider`` and every
``parsing-error`` signal is collected; the test then asserts none fired.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from kumquat.gui.css import CONTRACT_SELECTORS, build_css
from kumquat.gui.theme import COLORS_FILE, load_palette

SYSTEM_PYTHON = Path("/usr/bin/python3")
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
THEMES_DIR = Path.home() / ".config/omarchy/themes"
STOCK_THEMES_DIR = Path("/usr/share/omarchy/themes")
SUBPROCESS_TIMEOUT_S = 60
LIGHT_ONLY = "light-mode-fallback"
APPEARANCES = (("opaque", 0.90), ("glass", 0.75), ("glass", 0.90), ("glass", 1.0))

# Runs under the system interpreter. argv[1] is a JSON object
# {case_name: colors_path}; prints {case_name: [error messages]}.
_GTK_PROBE = r"""
import json
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from kumquat.gui.css import build_css
from kumquat.gui.theme import load_palette

def parse_errors(css):
    errors = []
    provider = Gtk.CssProvider()
    provider.connect(
        "parsing-error",
        lambda _p, section, error: errors.append(
            f"{section.to_string()}: {error.message}"),
    )
    provider.load_from_string(css)
    return errors

cases = json.loads(sys.argv[1])
result = {}
for name, path in cases.items():
    palette = load_palette(Path(path))
    for style, opacity in json.loads(sys.argv[2]):
        key = f"{name}/{style}/{opacity}"
        result[key] = parse_errors(build_css(palette, appearance=style, opacity=opacity))
result["__control__"] = parse_errors("window { colour: nonsense; }")
print(json.dumps(result))
"""


def _system_gtk_available() -> bool:
    if not SYSTEM_PYTHON.exists():
        return False
    probe = 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk'
    completed = subprocess.run([str(SYSTEM_PYTHON), "-c", probe],
                               capture_output=True, timeout=SUBPROCESS_TIMEOUT_S,
                               check=False)
    return completed.returncode == 0


def _cases(light_file: Path) -> dict[str, str]:
    """Theme name -> colors.toml path for the live and every installed theme."""
    cases = {"live": str(COLORS_FILE), "missing-file": "/nonexistent/colors.toml",
             LIGHT_ONLY: str(light_file)}
    for origin, root in (("stock", STOCK_THEMES_DIR), ("user", THEMES_DIR)):
        for colors in sorted(root.glob("*/colors.toml")):
            cases[f"{origin}/{colors.parent.name}"] = str(colors)
    return cases


@pytest.fixture(scope="module")
def gtk_results(tmp_path_factory) -> dict[str, list[str]]:
    """Parse every case's CSS in one system-Python GTK subprocess."""
    if not _system_gtk_available():
        pytest.skip("system python3 has no GTK 4 bindings")
    light_file = tmp_path_factory.mktemp("light") / "colors.toml"
    light_file.write_text('mode = "light"\n')
    env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    completed = subprocess.run(
        [str(SYSTEM_PYTHON), "-c", _GTK_PROBE, json.dumps(_cases(light_file)),
         json.dumps(APPEARANCES)],
        capture_output=True, text=True, env=env, timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _case_names() -> list[str]:
    return [f"{name}/{style}/{opacity}"
            for name in _cases(Path("unused")) for style, opacity in APPEARANCES]


def test_probe_detects_parse_errors(gtk_results):
    """Sanity check: the harness really reports broken CSS."""
    assert gtk_results["__control__"]


@pytest.mark.parametrize("case", _case_names())
def test_css_parses_without_errors_in_gtk(gtk_results, case):
    assert gtk_results[case] == []


@pytest.mark.parametrize("selector", CONTRACT_SELECTORS)
def test_contract_selector_present(selector):
    css = build_css(load_palette())
    assert selector in css

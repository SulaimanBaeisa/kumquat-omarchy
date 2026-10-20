"""The plugin's QML, checked with Qt's own tools and executed against stubs.

`qmllint` resolves every name in Overlay.qml and BarWidget.qml against the stub
modules in tests/qml_stubs (which copy the Omarchy shell's interfaces), and the
harness then runs both entry points in a real Qt QML engine and asserts what they
start. Neither proves the live shell loads the plugin; see tests/qml_stubs/README.md.

Needs `pip install PySide6-Essentials`; skipped without it.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
except ImportError as exc:  # PySide6 missing, or Qt's system libraries (libEGL...) are
    pytest.skip(f"Qt for Python is not usable here: {exc}", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
STUBS = ROOT / "tests/qml_stubs"
PLUGIN_ID = json.loads((ROOT / "manifest.json").read_text())["id"]
QML_FILES = ("Overlay.qml", "BarWidget.qml")


@pytest.fixture(scope="session")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def _qmllint():
    found = shutil.which("qmllint") or shutil.which("pyside6-qmllint")
    if found:
        return found
    candidate = Path(QtCore.__file__).parent / "qmllint"
    return str(candidate) if candidate.exists() else None


def test_qmllint_is_clean():
    exe = _qmllint()
    if exe is None:
        pytest.skip("qmllint is not installed")
    cmd = [exe, "-I", str(STUBS), "-W", "0", *(str(ROOT / name) for name in QML_FILES)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


class Harness:
    """Drives tests/qml_stubs/Harness.qml, which hosts the plugin's real QML."""

    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.engine = QQmlEngine()
        self.engine.addImportPath(str(STUBS))
        self.component = QQmlComponent(
            self.engine, QUrl.fromLocalFile(str(STUBS / "Harness.qml"))
        )
        self.item = self.component.create()
        assert self.item is not None, [e.toString() for e in self.component.errors()]
        self.item.setProperty("pluginUrl", QUrl.fromLocalFile(str(plugin_dir)))

    def _send(self, action: str, argument: str = "") -> dict:
        self.item.setProperty("action", "")  # so the same action can fire twice
        self.item.setProperty("argument", argument)
        self.item.setProperty("action", action)
        return json.loads(self.item.property("response") or "{}")

    def do(self, action: str, argument: str = "") -> dict:
        """Run one action, let queued Qt.callLater() work run, return the state."""
        first = self._send(action, argument)
        assert "error" not in first, first["error"]
        return self.settle()

    def settle(self) -> dict:
        QCoreApplication.processEvents()
        return self._send("snapshot")


@pytest.fixture
def plugin_copy(tmp_path):
    """A copy of the plugin in a folder whose name needs URL escaping."""
    dest = tmp_path / "my plugin é"
    dest.mkdir()
    for name in (*QML_FILES, "Launch.js", "manifest.json"):
        shutil.copy2(ROOT / name, dest / name)
    (dest / "bin").mkdir()
    return dest


@pytest.fixture(params=["repo", "copy"])
def harness(request, app, plugin_copy):
    return Harness(ROOT if request.param == "repo" else plugin_copy), (
        ROOT if request.param == "repo" else plugin_copy
    )


def test_overlay_launches_kumquat_then_hides_itself(harness):
    h, plugin = harness
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    out = h.do("overlay.open", "")
    assert out["calls"] == [["/bin/sh", str(plugin / "bin/kumquat"), "--gui"]]
    # do() already let Qt.callLater() run, so the overlay has closed itself.
    assert out["hidden"] == [PLUGIN_ID]
    assert out["opened"] is False


def test_overlay_forwards_files_and_tab(harness):
    h, plugin = harness
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    payload = json.dumps({"files": ["/tmp/a b.jpg", "/tmp/c.pdf"], "tab": "actions"})
    out = h.do("overlay.open", payload)
    assert out["calls"] == [
        [
            "/bin/sh",
            str(plugin / "bin/kumquat"),
            "--gui",
            "--tab",
            "actions",
            "--files",
            "/tmp/a b.jpg",
            "/tmp/c.pdf",
        ]
    ]


def test_overlay_survives_a_bad_payload_and_still_opens(app):
    h = Harness(ROOT)
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    out = h.do("overlay.open", "{not json")
    assert out["calls"] == [["/bin/sh", str(ROOT / "bin/kumquat"), "--gui"]]


def test_overlay_without_a_payload_argument(app):
    h = Harness(ROOT)
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    out = h.do("overlay.open", "<undefined>")
    assert out["calls"] == [["/bin/sh", str(ROOT / "bin/kumquat"), "--gui"]]


def test_overlay_hides_by_its_own_id_even_if_the_shell_gives_no_manifest(app):
    h = Harness(ROOT)
    h.do("overlay.create-bare")  # shell injected nothing: shell stays null
    out = h.do("overlay.open", "")
    assert len(out["calls"]) == 1  # no shell facade: it must not crash
    assert out["hidden"] == []


def test_overlay_close_is_harmless(app):
    h = Harness(ROOT)
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    assert h.do("overlay.close")["opened"] is False


def test_each_open_starts_one_launch(app):
    h = Harness(ROOT)
    h.do("overlay.create", json.dumps({"id": PLUGIN_ID}))
    h.do("overlay.open", "")
    out = h.do("overlay.open", "")
    assert len(out["calls"]) == 2


def test_widget_press_starts_the_picker(harness):
    h, plugin = harness
    h.do("widget.create", "{}")
    for button in (1, 2, 4):  # left, right, middle
        out = h.do("widget.press", str(button))
    assert out["calls"] == [["/bin/sh", str(plugin / "bin/kumquat"), "--gui"]] * 3


def test_widget_shape_and_default_icon(app):
    h = Harness(ROOT)
    out = h.do("widget.create", "{}")
    assert out["widget"]["moduleName"] == PLUGIN_ID
    assert out["widget"]["text"] == "\U0001f34a"
    assert out["widget"]["tooltip"] == "Kumquat: convert files"


def test_widget_icon_can_be_overridden_inline(app):
    h = Harness(ROOT)
    out = h.do("widget.create", json.dumps({"icon": ""}))
    assert out["widget"]["text"] == ""

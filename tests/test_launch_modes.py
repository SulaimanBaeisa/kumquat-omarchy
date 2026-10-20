"""Explicit browser and current Nautilus-selection launch workflows."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kumquat import cli


@pytest.mark.parametrize("mode", ["conversions", "tools", "actions"])
def test_cli_forwards_requested_tab_only_when_nondefault(monkeypatch, mode):
    calls = []
    monkeypatch.setattr(
        cli, "run_gui", lambda files, **kwargs: calls.append((files, kwargs))
    )
    assert cli.main(["--gui", "--files", "selected.jpg", "--tab", mode]) == 0
    expected = {"from_clipboard": False}
    if mode != "conversions":
        expected["initial_mode"] = mode
    assert calls == [(["selected.jpg"], expected)]


def test_invalid_tab_rejected_before_launch(monkeypatch):
    monkeypatch.setattr(cli, "run_gui", lambda *a, **kw: pytest.fail("popup"))
    with pytest.raises(SystemExit) as error:
        cli.main(["--gui", "--tab", "unknown"])
    assert error.value.code == 2


def test_bare_gui_browses_without_reading_stale_clipboard(monkeypatch):
    calls = []

    def stale_clipboard():
        raise AssertionError("bare --gui must not read even a stale clipboard")

    monkeypatch.setattr(cli, "clipboard_files", stale_clipboard)
    monkeypatch.setattr(
        cli,
        "run_gui",
        lambda files, from_clipboard=False: calls.append((files, from_clipboard)),
    )
    assert cli.main(["--gui"]) == 0
    assert calls == [([], False)]


@pytest.mark.parametrize(
    "files, mode",
    [
        (["current.jpg"], "actions"),
        (["current.jpg"], "tools"),
        (["current.jpg"], "conversions"),
        ([], "actions"),
    ],
)
def test_gui_initial_mode_is_set_after_adopt_before_present(monkeypatch, files, mode):
    from kumquat.gui import app
    from kumquat.gui.wheel import MODES

    events = []
    applications = []
    non_unique = object()

    class Application:
        def __init__(self, **kwargs):
            applications.append(kwargs)

        def connect(self, signal, callback):
            assert signal == "activate"
            self.callback = callback

        def run(self, argv):
            assert argv == []
            self.callback(self)
            self.callback(self)  # one popup per invocation, not per activate

    class Window:
        def __init__(self, application, paths, from_clipboard):
            events.append(("construct", paths, from_clipboard))
            self.mode = 0  # existing constructor/adopt resets the mode

        def set_mode(self, index):
            self.mode = index
            events.append(("mode", index))

        def present(self):
            events.append(("present", self.mode))

    monkeypatch.setattr(
        app, "_require_gtk", lambda: SimpleNamespace(Application=Application)
    )
    monkeypatch.setitem(
        sys.modules,
        "gi.repository",
        SimpleNamespace(
            Gio=SimpleNamespace(ApplicationFlags=SimpleNamespace(NON_UNIQUE=non_unique))
        ),
    )
    monkeypatch.setattr(app, "WheelWindow", Window)
    app.run_gui(files, initial_mode=mode)
    expected_mode = MODES.index(mode) if files else 0
    expected = [("construct", files, False)]
    if files:
        expected.append(("mode", expected_mode))
    expected.extend([("present", expected_mode), ("present", expected_mode)])
    assert events == expected
    assert applications == [{"application_id": app.APP_ID, "flags": non_unique}]


def test_gui_default_launch_is_nonunique(monkeypatch):
    from kumquat.gui import app

    seen = []

    class Application:
        def __init__(self, **kwargs):
            seen.append(kwargs)

        def connect(self, *args):
            pass

        def run(self, *args):
            pass

    monkeypatch.setattr(
        app, "_require_gtk", lambda: SimpleNamespace(Application=Application)
    )
    monkeypatch.setitem(
        sys.modules,
        "gi.repository",
        SimpleNamespace(
            Gio=SimpleNamespace(ApplicationFlags=SimpleNamespace(NON_UNIQUE=32))
        ),
    )
    app.run_gui([])
    assert seen == [{"application_id": app.APP_ID, "flags": 32}]


def test_nautilus_launch_uses_current_selection_on_actions(tmp_path, monkeypatch):
    selected = tmp_path / "current file.jpg"
    selected.touch()
    monkeypatch.setenv("NAUTILUS_SCRIPT_SELECTED_URIS", selected.as_uri() + "\n")
    monkeypatch.setattr(
        cli, "clipboard_files", lambda: pytest.fail("stale clipboard read")
    )
    calls = []
    monkeypatch.setattr(
        cli, "run_gui", lambda files, **kwargs: calls.append((files, kwargs))
    )
    assert cli.main(["--gui", "--from-nautilus", "--tab", "actions"]) == 0
    assert calls == [
        ([str(selected)], {"from_clipboard": False, "initial_mode": "actions"})
    ]


def test_nautilus_helper_decodes_once_preserves_order_and_directories(tmp_path):
    from kumquat.nautilus_selection import nautilus_files

    paths = [
        tmp_path / name for name in ["日本語 space # %.txt", "%20.txt", "line\nbreak"]
    ]
    for path in paths:
        path.touch()
    folder = tmp_path / "directory"
    folder.mkdir()
    paths.append(folder)
    uris = [path.as_uri() for path in paths]
    uris[1] = uris[1].replace("file:///", "file://localhost/")
    env = {"NAUTILUS_SCRIPT_SELECTED_URIS": "\n".join([*uris, uris[0]]) + "\n"}
    assert nautilus_files(env) == [str(path) for path in paths]


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "\n",
        "https://example.com/a",
        "smb://server/file",
        "file://remote/tmp/a",
        "file://user@localhost/tmp/a",
        "file://localhost:80/tmp/a",
        "file:relative",
        "file:/tmp/a",
        "file://localhost",
        "file:///definitely-missing-kumquat-file",
        "file:///tmp/bad%",
        "file:///tmp/bad%2",
        "file:///tmp/bad%GG",
        "file:///tmp/bad%FF",
        "file:///tmp/bad%00",
        "file:///tmp/a?query",
        "file:///tmp/a#fragment",
        "file://[broken/tmp/a",
    ],
)
@pytest.mark.parametrize("mixed", [False, True])
def test_nautilus_rejects_entire_invalid_selection(tmp_path, uri, mixed):
    from kumquat.nautilus_selection import nautilus_files

    selected = tmp_path / "valid.jpg"
    selected.touch()
    value = selected.as_uri() + "\n" + uri if mixed and uri.strip() else uri
    with pytest.raises(ValueError, match="Nautilus"):
        nautilus_files({"NAUTILUS_SCRIPT_SELECTED_URIS": value})


@pytest.mark.parametrize("value", [None, "", "file://remote/tmp/file", "file:///missing"])
def test_nautilus_invalid_launch_never_opens_popup_or_clipboard(
    monkeypatch, capsys, value
):
    monkeypatch.delenv("NAUTILUS_SCRIPT_SELECTED_FILE_PATHS", raising=False)
    if value is None:
        monkeypatch.delenv("NAUTILUS_SCRIPT_SELECTED_URIS", raising=False)
    else:
        monkeypatch.setenv("NAUTILUS_SCRIPT_SELECTED_URIS", value)
    monkeypatch.setattr(cli, "run_gui", lambda *a, **kw: pytest.fail("popup"))
    monkeypatch.setattr(
        cli, "clipboard_files", lambda: pytest.fail("stale clipboard read")
    )
    assert cli.main(["--gui", "--from-nautilus", "--tab", "actions"]) != 0
    assert "Nautilus" in capsys.readouterr().err


@pytest.mark.parametrize("source", [["--files", "file.jpg"], ["--from-clipboard"]])
def test_nautilus_conflicting_sources_are_parser_errors(monkeypatch, capsys, source):
    monkeypatch.setattr(cli, "nautilus_files", lambda env: pytest.fail("selection read"))
    monkeypatch.setattr(cli, "clipboard_files", lambda: pytest.fail("clipboard read"))
    monkeypatch.setattr(cli, "run_gui", lambda *a, **kw: pytest.fail("popup"))
    with pytest.raises(SystemExit) as error:
        cli.main(["--gui", "--from-nautilus", *source])
    assert error.value.code == 2
    assert "--from-nautilus" in capsys.readouterr().err


def test_nautilus_path_fallback_is_literal_when_uri_variable_absent(tmp_path):
    from kumquat.nautilus_selection import nautilus_files

    paths = [tmp_path / "$(touch SHOULD-NOT-EXIST); # %.txt", tmp_path / "日本語 space"]
    for path in paths:
        path.touch()
    env = {
        "NAUTILUS_SCRIPT_SELECTED_FILE_PATHS": "\n".join(map(str, [*paths, paths[0]]))
        + "\n"
    }
    assert nautilus_files(env) == list(map(str, paths))


@pytest.mark.parametrize("value", ["", "relative.txt", "/missing-kumquat-selection"])
def test_nautilus_path_fallback_requires_absolute_existing_selection(value):
    from kumquat.nautilus_selection import nautilus_files

    with pytest.raises(ValueError, match="Nautilus"):
        nautilus_files({"NAUTILUS_SCRIPT_SELECTED_FILE_PATHS": value})


def test_nautilus_empty_uri_variable_never_falls_back_to_paths(tmp_path):
    from kumquat.nautilus_selection import nautilus_files

    selected = tmp_path / "stale file"
    selected.touch()
    with pytest.raises(ValueError, match="Nautilus"):
        nautilus_files(
            {
                "NAUTILUS_SCRIPT_SELECTED_URIS": "",
                "NAUTILUS_SCRIPT_SELECTED_FILE_PATHS": str(selected),
            }
        )


@pytest.mark.parametrize(
    "transform",
    [
        lambda uri: uri.replace("file:///", "file://remote/"),
        lambda uri: uri + "?ignored",
        lambda uri: uri + "#ignored",
        lambda uri: uri.replace("valid.jpg", "va\tlid.jpg"),
    ],
)
def test_nautilus_never_reinterprets_uri_as_existing_different_selection(
    tmp_path, transform
):
    from kumquat.nautilus_selection import nautilus_files

    selected = tmp_path / "valid.jpg"
    selected.touch()
    with pytest.raises(ValueError, match="Nautilus"):
        nautilus_files({"NAUTILUS_SCRIPT_SELECTED_URIS": transform(selected.as_uri())})


@pytest.mark.parametrize("actions", [False, True])
def test_real_gtk_popup_launch_state_without_keyboard(tmp_path, actions):
    """Exercise the actual constructor/adopt/tab path using system GTK4."""
    python = Path("/usr/bin/python3")
    if not python.exists() or not any(
        os.environ.get(k) for k in ("DISPLAY", "WAYLAND_DISPLAY")
    ):
        pytest.skip("requires system Python GTK4 and a display")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    probe = subprocess.run(
        [
            str(python),
            "-c",
            """
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gtk
assert Gdk.Display.get_default() is not None
""",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if probe.returncode:
        pytest.skip("system GTK4/display unavailable: " + probe.stderr)
    selected = tmp_path / "current # 日本語.jpg"
    selected.touch()
    env["NAUTILUS_SCRIPT_SELECTED_URIS"] = selected.as_uri()
    program = """
import json
import sys
from kumquat import cli
from kumquat.gui import app, wheel

records = []
# Keep this short-lived verification popup a normal toplevel, not an overlay.
wheel._init_layer_shell = lambda win: None

class InspectWindow(wheel.WheelWindow):
    def present(self):
        super().present()
        def inspect():
            before = self.mode
            self.handle_key('Super_L', False)
            self.handle_key('Shift_L', False)
            records.append({
                'mode': self.mode, 'before_release': before,
                'files': self.files, 'page': self.stack.get_visible_child_name(),
                'prompt': self.prompt.get_text(),
                'active_tabs': [tab.get_active() for tab in self.tabs],
                'flags': int(self.app.get_flags()), 'busy': self.busy,
            })
            self.close()
            self.app.quit()
            return False
        self._glib.idle_add(inspect)

    def apply_selected(self):
        raise AssertionError('launch must not apply an action')

app.WheelWindow = InspectWindow
cli.clipboard_files = lambda: (_ for _ in ()).throw(AssertionError('clipboard read'))
assert cli.main(sys.argv[1:]) == 0
assert len(records) == 1
print(json.dumps(records[0]))
"""
    args = ["--gui", "--from-nautilus", "--tab", "actions"] if actions else ["--gui"]
    proc = subprocess.run(
        [str(python), "-c", program, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    state = json.loads(proc.stdout.splitlines()[-1])
    assert state["flags"] & 32  # Gio.ApplicationFlags.NON_UNIQUE
    assert state["busy"] is False
    assert state["files"] == ([str(selected)] if actions else [])
    assert state["page"] == ("wheel" if actions else "picker")
    assert state["mode"] == state["before_release"] == (2 if actions else 0)
    assert state["active_tabs"] == (
        [False, False, True] if actions else [True, False, False]
    )
    if actions:
        assert state["prompt"] == "Choose a file action"

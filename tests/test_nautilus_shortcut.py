"""Focus-local key routing; real native/action/key coverage is in desktop E2E."""

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

EXTENSION = Path(__file__).resolve().parents[1] / "extensions/nautilus-kumquat.py"


@pytest.fixture
def extension(monkeypatch):
    class Widget:
        def __init__(self, parent=None):
            self.parent = parent
            self.calls = []

        def get_parent(self):
            return self.parent

        def activate_action(self, name, args):
            self.calls.append((name, args))
            return True

    class Application:
        @staticmethod
        def get_default():
            return None

    gtk = SimpleNamespace(
        **{
            name: type(name, (Widget,), {})
            for name in (
                "ColumnView",
                "GridView",
                "Editable",
                "TextView",
                "Popover",
                "ListView",
            )
        }
    )
    gtk.Widget = Widget
    gtk.Application = Application
    gtk.EventControllerKey = SimpleNamespace(new=lambda: None)
    gtk.PropagationPhase = SimpleNamespace(CAPTURE=1)
    gdk = SimpleNamespace(
        KEY_E=69,
        KEY_e=101,
        ModifierType=SimpleNamespace(
            SHIFT_MASK=1, LOCK_MASK=2, CONTROL_MASK=4, ALT_MASK=8, SUPER_MASK=64
        ),
    )
    repo = SimpleNamespace(
        Gtk=gtk,
        Gdk=gdk,
        GLib=SimpleNamespace(
            idle_add=lambda f: None,
            get_user_data_dir=lambda: "/home/test/.local/share",
            uri_escape_string=lambda s, allowed, utf8: quote(s, safe=""),
        ),
        Gio=SimpleNamespace(Application=Application),
        Nautilus=SimpleNamespace(MenuProvider=type("MenuProvider", (), {})),
        GObject=SimpleNamespace(GObject=type("GObject", (), {})),
    )
    monkeypatch.setitem(
        sys.modules, "gi", SimpleNamespace(require_version=lambda *a: None)
    )
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    api = runpy.run_path(str(EXTENSION))
    instance = api["KumquatWheelExtension"]()
    return instance, gtk, gdk


def press(extension, focus, key=69, modifiers=1):
    instance, _, _ = extension
    window = SimpleNamespace(get_focus=lambda: focus)
    controller = SimpleNamespace(get_widget=lambda: window)
    return instance._on_key(controller, key, 26, modifiers)


def test_shift_e_activates_native_script_from_focused_file_view(extension):
    _, gtk, _ = extension
    focus = gtk.Widget(gtk.ColumnView())
    assert press(extension, focus)
    assert focus.calls == [
        (
            "view.script_file%3A%2F%2F%2Fhome%2Ftest%2F.local%2Fshare%2Fnautilus%2Fscripts%2FKumquat%2520Actions",
            None,
        )
    ]


@pytest.mark.parametrize("kind", ["ColumnView", "GridView"])
def test_both_file_views_resolve_native_action(extension, kind):
    _, gtk, _ = extension
    focus = gtk.Widget(getattr(gtk, kind)())
    assert press(extension, focus)
    assert len(focus.calls) == 1


@pytest.mark.parametrize("kind", ["Editable", "TextView", "Popover"])
def test_editing_and_popovers_never_intercept_uppercase_e(extension, kind):
    _, gtk, _ = extension
    focus = gtk.Widget(getattr(gtk, kind)(gtk.ColumnView()))
    assert press(extension, focus) is False
    assert focus.calls == []


def test_checks_ancestors_even_above_file_view(extension):
    _, gtk, _ = extension
    focus = gtk.Widget(gtk.ColumnView(gtk.Editable()))
    assert press(extension, focus) is False
    assert focus.calls == []


@pytest.mark.parametrize("kind", ["Widget", "ListView"])
def test_sidebar_and_other_controls_keep_typing(extension, kind):
    _, gtk, _ = extension
    focus = getattr(gtk, kind)()
    assert press(extension, focus) is False
    assert focus.calls == []


def test_no_focus_keeps_event_unhandled(extension):
    assert press(extension, None) is False


@pytest.mark.parametrize("key, modifiers", [(101, 1), (69, 3)])
def test_shift_e_and_shift_caps_e_are_supported(extension, key, modifiers):
    _, gtk, _ = extension
    assert press(extension, gtk.GridView(), key, modifiers)


@pytest.mark.parametrize(
    "key, modifiers",
    [
        (101, 0),
        (69, 0),
        (69, 4),
        (69, 5),
        (69, 9),
        (69, 65),
        (69, 129),
        (70, 1),
    ],
)
def test_other_chords_are_not_consumed(extension, key, modifiers):
    _, gtk, _ = extension
    focus = gtk.Widget(gtk.ColumnView())
    assert press(extension, focus, key, modifiers) is False
    assert focus.calls == []


def test_unavailable_native_action_is_not_claimed_as_handled(extension):
    _, gtk, _ = extension
    focus = gtk.Widget(gtk.GridView())
    focus.activate_action = lambda name, args: False
    assert press(extension, focus) is False


def test_attach_capture_controller_once_per_window(extension):
    instance, gtk, _ = extension

    class Controller:
        def set_propagation_phase(self, phase):
            self.phase = phase

        def connect(self, name, callback):
            self.connection = (name, callback)

    class Window:
        def __init__(self):
            self.controllers = []

        def add_controller(self, controller):
            self.controllers.append(controller)

    gtk.EventControllerKey.new = Controller
    window = Window()
    instance._window_added(None, window)
    instance._window_added(None, window)
    assert len(window.controllers) == 1
    controller = window.controllers[0]
    assert controller.phase == gtk.PropagationPhase.CAPTURE
    assert controller.connection == ("key-pressed", instance._on_key)


def test_installs_current_and_future_windows(extension):
    instance, gtk, _ = extension
    windows = [object(), object()]
    connected, installed = [], []
    app = SimpleNamespace(
        connect=lambda name, callback: connected.append((name, callback)),
        get_windows=lambda: windows,
    )
    gtk.Application.get_default = staticmethod(lambda: app)
    instance._window_added = lambda app, window: installed.append(window)
    assert instance._install_shortcuts() is False
    assert installed == windows
    assert connected == [("window-added", instance._window_added)]

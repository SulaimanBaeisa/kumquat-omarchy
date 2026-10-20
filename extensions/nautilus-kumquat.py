"""Nautilus context menu and focus-local Shift+E native script routing.

The script action is owned by Nautilus: it obtains the selection at activation
and sets NAUTILUS_SCRIPT_SELECTED_URIS. Never cache MenuProvider selections or
copy files to the clipboard. Requires Nautilus 4 / nautilus-python and GTK4.
"""

import subprocess
import weakref
from pathlib import Path

try:
    import gi

    gi.require_version("Nautilus", "4.1")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, GObject, Gtk, Nautilus

    class KumquatWheelExtension(GObject.GObject, Nautilus.MenuProvider):
        def __init__(self):
            super().__init__()
            self._windows = weakref.WeakSet()
            # Extensions may be instantiated before the first window exists.
            GLib.idle_add(self._install_shortcuts)

        def _install_shortcuts(self):
            app = Gtk.Application.get_default()
            if app is not None:
                app.connect("window-added", self._window_added)
                for window in app.get_windows():
                    self._window_added(app, window)
            return False

        def _window_added(self, _app, window):
            if window in self._windows:
                return
            self._windows.add(window)
            controller = Gtk.EventControllerKey.new()
            controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            controller.connect("key-pressed", self._on_key)
            window.add_controller(controller)

        def _on_key(self, controller, keyval, _keycode, state):
            mods = Gdk.ModifierType
            if keyval not in (Gdk.KEY_e, Gdk.KEY_E):
                return False
            if not state & mods.SHIFT_MASK or state & ~(mods.SHIFT_MASK | mods.LOCK_MASK):
                return False
            focus = controller.get_widget().get_focus()
            ancestor = focus
            in_file_view = False
            while ancestor is not None:
                # Check the entire chain: rename popovers can be under a view.
                if isinstance(ancestor, (Gtk.Editable, Gtk.TextView, Gtk.Popover)):
                    return False
                if isinstance(ancestor, (Gtk.ColumnView, Gtk.GridView)):
                    in_file_view = True
                ancestor = ancestor.get_parent()
            if not in_file_view:
                return False
            script = Path(GLib.get_user_data_dir()) / "nautilus/scripts/Kumquat Actions"
            action = "view.script_" + GLib.uri_escape_string(script.as_uri(), None, True)
            # Resolve from the focused list descendant, not from the window:
            # the native 'view' action group belongs to its enclosing FilesView.
            return focus.activate_action(action, None)

        def get_file_items(self, files):
            paths = [f.get_location().get_path() for f in files]
            paths = [p for p in paths if p]
            if not paths:
                return []
            item = Nautilus.MenuItem(
                name="KumquatWheel::Open",
                label="Open in Kumquat",
                tip="Open the selected files in Kumquat",
            )
            item.connect("activate", self._open, paths)
            return [item]

        def _open(self, _menu, paths):
            subprocess.Popen(["kumquat", "--files", *paths, "--gui"])
except ImportError:
    pass

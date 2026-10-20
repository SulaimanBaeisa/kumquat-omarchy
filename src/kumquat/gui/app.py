"""`run_gui`: start the GTK application that hosts one `WheelWindow`.

GTK is imported only when `run_gui` runs, so `--list` and the test venv (which
has no `gi`) never touch display code. Without GTK or a display, `run_gui`
raises `RuntimeError` pointing at the headless `--list` wheel.
"""
from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from .wheel import MODES, WheelWindow

APP_ID = "dev.kumquat.app"
HEADLESS_HINT = "Use --list for the headless text wheel."
DISPLAY_VARS = ("DISPLAY", "WAYLAND_DISPLAY")


def _require_gtk() -> Any:
    """Return the `Gtk` module, or raise RuntimeError when it cannot be used."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
    except Exception as exc:
        raise RuntimeError(
            f"GTK wheel unavailable (no gi/GTK4 or no display): {exc}. "
            f"{HEADLESS_HINT}") from exc
    if not any(os.environ.get(var) for var in DISPLAY_VARS):
        raise RuntimeError(
            f"GTK wheel unavailable: no display (headless). {HEADLESS_HINT}")
    return Gtk


def run_gui(files: Sequence[str], from_clipboard: bool = False,
            initial_mode: str = "conversions") -> None:
    """Open the wheel window and block until it closes.

    With ``files`` it opens on the option list; without, on the embedded file
    browser. ``from_clipboard`` labels the files as picked up from the clipboard.
    ``initial_mode`` selects a tab after the selected files have been adopted.
    """
    gtk = _require_gtk()
    from gi.repository import Gio

    # Each shortcut invocation must own its selection, not activate an old popup.
    app = gtk.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    windows: list[WheelWindow] = []

    def on_activate(application: Any) -> None:
        if not windows:  # repeated activation within this invocation reuses it
            window = WheelWindow(application, list(files), from_clipboard)
            if files:
                window.set_mode(MODES.index(initial_mode))
            windows.append(window)
        windows[0].present()

    app.connect("activate", on_activate)
    app.run([])

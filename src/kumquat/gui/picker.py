"""Embedded file browser for the wheel window.

One click on a folder enters it; one click on a file accepts it. The browser
is a plain ``Gtk.ListBox`` living inside the wheel window — no dialogs, no
portal, no second surface that could lose focus.

The module has two layers:

* pure helpers (:class:`Entry`, :func:`list_entries`, :func:`parent_dir`,
  :func:`display_path`, :func:`paths_from_files`) that import without GTK
  and are unit-tested in the venv, which has no ``gi``;
* :func:`create_picker`, which imports GTK only when called and builds the
  widget class once, on first use.
"""
from __future__ import annotations

import functools
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = "/"
HOME_ALIAS = "~"
HIDDEN_PREFIX = "."

ICON_DIR = "📁"
ICON_FILE = "📄"
LABEL_UP = "↑"
LABEL_HOME = "⌂"
LABEL_CANCEL = "Cancel"
LABEL_EMPTY = "This folder is empty"

SPACING = 8
FIRST_ROW = 0
SCROLL_TOP = 0.0

AcceptCallback = Callable[[list[str]], None]
CancelCallback = Callable[[], None]


@dataclass(frozen=True)
class Entry:
    """One row of a directory listing.

    Attributes:
        name: File or folder name as shown to the user.
        path: Absolute path of the entry.
        is_dir: True for folders, including symlinks to folders.
    """

    name: str
    path: str
    is_dir: bool


def _entry_from_dirent(dirent: os.DirEntry[str]) -> Entry | None:
    """Turn a scandir entry into an :class:`Entry`, or ``None`` if unusable.

    Symlinks are followed, so a broken symlink (``stat`` fails) is dropped.
    """
    try:
        dirent.stat()
        is_dir = dirent.is_dir()
    except OSError:
        return None
    return Entry(name=dirent.name, path=os.path.abspath(dirent.path), is_dir=is_dir)


def _sort_key(entry: Entry) -> tuple[bool, str, str]:
    """Order folders before files, then by case-insensitive name."""
    return (not entry.is_dir, entry.name.casefold(), entry.name)


def list_entries(directory: Path | str, show_hidden: bool = False) -> list[Entry]:
    """List a directory the way the picker shows it.

    Args:
        directory: Folder to list.
        show_hidden: Include dot-files and dot-folders when True.

    Returns:
        Folders first, then files, each group sorted case-insensitively.
        Broken symlinks are skipped. A missing, non-directory or unreadable
        ``directory`` yields an empty list.
    """
    entries: list[Entry] = []
    try:
        with os.scandir(directory) as dirents:
            for dirent in dirents:
                if not show_hidden and dirent.name.startswith(HIDDEN_PREFIX):
                    continue
                entry = _entry_from_dirent(dirent)
                if entry is not None:
                    entries.append(entry)
    except OSError:
        return []
    return sorted(entries, key=_sort_key)


def parent_dir(directory: Path | str) -> str:
    """Return the parent folder of ``directory``; the root stays the root."""
    return str(Path(os.path.abspath(directory)).parent)


def display_path(directory: Path | str, home: Path | str | None = None) -> str:
    """Format ``directory`` for the header, shortening ``home`` to ``~``.

    Args:
        directory: Absolute folder path.
        home: Home folder to abbreviate; defaults to ``Path.home()``.
    """
    path = Path(directory)
    home_path = Path(home) if home is not None else Path.home()
    if path == home_path:
        return HOME_ALIAS
    if home_path in path.parents:
        return f"{HOME_ALIAS}{os.sep}{path.relative_to(home_path)}"
    return str(path)


def paths_from_files(files: Iterable[object]) -> list[str]:
    """Extract local paths, dropping virtual entries and duplicates.

    Args:
        files: ``Gio.File``-like objects; may contain ``None`` and objects
            without a usable ``get_path()``.

    Returns:
        Local paths as strings, first-seen order preserved, duplicates
        removed.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for entry in files:
        if entry is None:
            continue
        getter = getattr(entry, "get_path", None)
        path = getter() if callable(getter) else None
        if isinstance(path, str) and path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def create_picker(
    on_accept: AcceptCallback,
    on_cancel: CancelCallback,
    start_dir: Path | str | None = None,
) -> Any:
    """Build the embedded file browser widget (imports GTK on call).

    Args:
        on_accept: Called with ``[path]`` when the user clicks a file.
        on_cancel: Called on Escape or the Cancel button.
        start_dir: Folder shown first; defaults to ``Path.home()``.

    Returns:
        A vertical ``Gtk.Box`` with CSS class ``kumquat-picker`` exposing
        ``current_dir``, ``entries``, ``navigate()``, ``activate_index()``,
        ``go_up()`` and ``focus_list()``.
    """
    picker_class = _picker_class()
    return picker_class(on_accept, on_cancel, start_dir or Path.home())


@functools.cache
def _picker_class() -> type:
    """Define the GTK-bound picker class once, on first use.

    Subclassing ``Gtk.Box`` needs GTK at class-creation time, so the class
    lives here to keep importing this module GTK-free.
    """
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk, Pango

    def make_button(label: str, css_class: str, action: Callable[[], None]) -> Gtk.Button:
        """Create a header button that runs ``action`` when clicked."""
        button = Gtk.Button(label=label)
        button.add_css_class(css_class)
        button.connect("clicked", lambda _button: action())
        return button

    def make_row(entry: Entry) -> Gtk.ListBoxRow:
        """Create one list row: icon label followed by the entry name."""
        icon = Gtk.Label(label=ICON_DIR if entry.is_dir else ICON_FILE)
        icon.add_css_class("kumquat-picker-icon")
        name = Gtk.Label(label=entry.name, xalign=0.0, hexpand=True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.add_css_class("kumquat-picker-name")

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACING)
        content.append(icon)
        content.append(name)

        row = Gtk.ListBoxRow()
        row.add_css_class("kumquat-picker-row")
        if entry.is_dir:
            row.add_css_class("is-dir")
        row.set_child(content)
        return row

    class FilePicker(Gtk.Box):
        """Header (up / path / home / cancel) above a single-click file list."""

        def __init__(
            self,
            on_accept: AcceptCallback,
            on_cancel: CancelCallback,
            start_dir: Path | str,
        ) -> None:
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=SPACING)
            self.add_css_class("kumquat-picker")
            self._on_accept = on_accept
            self._on_cancel = on_cancel
            self.current_dir: str = ""
            self.entries: list[Entry] = []

            self.append(self._build_header())
            self.append(self._build_list())
            self._install_keys()
            self.navigate(start_dir)

        # -- construction -------------------------------------------------

        def _build_header(self) -> Gtk.Box:
            """Create the header row: Up, path label, Home, Cancel."""
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACING)
            header.add_css_class("kumquat-picker-header")

            self._path_label = Gtk.Label(xalign=0.0, hexpand=True)
            self._path_label.set_ellipsize(Pango.EllipsizeMode.START)
            self._path_label.add_css_class("kumquat-picker-path")

            header.append(make_button(LABEL_UP, "kumquat-picker-up", self.go_up))
            header.append(self._path_label)
            header.append(make_button(LABEL_HOME, "kumquat-picker-home", self._go_home))
            header.append(
                make_button(LABEL_CANCEL, "kumquat-picker-cancel", self._on_cancel)
            )
            return header

        def _build_list(self) -> Gtk.ScrolledWindow:
            """Create the scrollable single-click list of entries."""
            self._list = Gtk.ListBox()
            self._list.add_css_class("kumquat-picker-list")
            self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self._list.set_activate_on_single_click(True)
            self._list.set_placeholder(Gtk.Label(label=LABEL_EMPTY))
            self._list.connect("row-activated", self._on_row_activated)

            self._scroller = Gtk.ScrolledWindow(vexpand=True)
            self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self._scroller.set_child(self._list)
            return self._scroller

        def _install_keys(self) -> None:
            """Handle navigation keys before child widgets consume them."""
            keys = Gtk.EventControllerKey()
            keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keys.connect("key-pressed", self._on_key_pressed)
            self.add_controller(keys)

        # -- public API ---------------------------------------------------

        def navigate(self, path: Path | str) -> None:
            """Show ``path``, select its first row and scroll to the top."""
            self.current_dir = os.path.abspath(os.path.expanduser(str(path)))
            self.entries = list_entries(self.current_dir)
            self._path_label.set_text(display_path(self.current_dir))
            self._path_label.set_tooltip_text(self.current_dir)

            self._list.remove_all()
            for entry in self.entries:
                self._list.append(make_row(entry))
            self._list.select_row(self._list.get_row_at_index(FIRST_ROW))
            self._scroller.get_vadjustment().set_value(SCROLL_TOP)

        def activate_index(self, index: int) -> None:
            """Act like a click on row ``index``: enter folder or accept file."""
            if not 0 <= index < len(self.entries):
                return
            entry = self.entries[index]
            if entry.is_dir:
                self.navigate(entry.path)
            else:
                self._on_accept([entry.path])

        def go_up(self) -> None:
            """Show the parent folder; does nothing at the root."""
            if self.current_dir != ROOT_DIR:
                self.navigate(parent_dir(self.current_dir))

        def focus_list(self) -> None:
            """Give keyboard focus to the selected row, or to the list itself."""
            row = self._list.get_selected_row()
            (row or self._list).grab_focus()

        # -- signal handlers ----------------------------------------------

        def _go_home(self) -> None:
            """Jump to the user's home folder."""
            self.navigate(Path.home())

        def _on_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
            """Forward a single click (or Enter) on a row."""
            self.activate_index(row.get_index())

        def _activate_selected(self) -> None:
            """Activate the currently selected row, if any."""
            row = self._list.get_selected_row()
            if row is not None:
                self.activate_index(row.get_index())

        def _on_key_pressed(
            self,
            _controller: Gtk.EventControllerKey,
            keyval: int,
            _keycode: int,
            state: Gdk.ModifierType,
        ) -> bool:
            """Map Return, BackSpace, Alt+Up and Escape to picker actions."""
            alt_up = keyval == Gdk.KEY_Up and bool(state & Gdk.ModifierType.ALT_MASK)
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self._activate_selected()
            elif keyval == Gdk.KEY_BackSpace or alt_up:
                self.go_up()
            elif keyval == Gdk.KEY_Escape:
                self._on_cancel()
            else:
                return False
            return True

    return FilePicker

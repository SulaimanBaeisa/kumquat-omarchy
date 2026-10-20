"""The wheel window: an embedded file browser and the option list, one window.

A `Gtk.Stack` holds two pages. ``"picker"`` is the custom browser from
`gui.picker` (one click on a folder enters it, one click on a file picks it).
``"wheel"`` lists the conversions, tools or actions for the picked files.
There is no file-chooser dialog, portal or second window.

Keyboard: hold Shift for conversions, Super/Meta for tools,
Control for actions; exactly one held modifier switches the mode, two at once
do not. Left/Right or A/D cycle the bottom Convert/Tools/Actions tabs. Enter
(or Space, or a double-click on a row) applies the selected option, Up/Down
move, Escape closes the window.

An applied option runs as a background `Job`; the wheel shows a progress bar
(a percentage when the converter measures it, otherwise a pulse and the
elapsed time) and refuses to apply again or close until the job is done.

Everything that does not draw lives at module level and imports no GTK, so it
is unit-tested in a virtualenv without `gi`. `WheelWindow` imports GTK when it
is constructed.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from .. import actions as _actions
from .. import apply as _apply
from ..jobs import Job
from ..progress import Progress, ProgressCallback
from ..selection import EMPTY_STATE, PROMPTS, Listing, detect_mime, files_listing
from .appearance import load_appearance
from .css import build_css
from .theme import Palette, load_palette

MODES: tuple[str, ...] = ("conversions", "tools", "actions")
MODE_KEYS: dict[str, int] = {
    "Shift_L": 0, "Shift_R": 0,
    "Meta_L": 1, "Meta_R": 1, "Super_L": 1, "Super_R": 1,
    "Control_L": 2, "Control_R": 2,
}
APPLY_KEYS = frozenset({"Return", "KP_Enter", "space"})
MOVE_KEYS: dict[str, int] = {"Up": -1, "Down": 1}
TAB_KEYS: dict[str, int] = {"Left": -1, "Right": 1, "a": -1, "A": -1,
                            "d": 1, "D": 1}
TAB_LABELS: tuple[str, ...] = ("Convert", "Tools", "Actions")  # same order as MODES
CLOSE_KEY = "Escape"

PAGE_PICKER = "picker"
PAGE_WHEEL = "wheel"
PAGE_OPTIONS = "options"
WINDOW_TITLE = "Kumquat"
WINDOW_SIZE = (420, 520)
MARGIN = 12
SPACING = 6
PAGE_TRANSITION_MS = 120
SUMMARY_NAMES = 3
CHANGE_FILES_LABEL = "Change files…"
NO_SELECTION = "Pick an option with the arrow keys first."
CLIPBOARD_ORIGIN = " (from clipboard)"
PULSE_MS = 100
BUSY_HINT = "Still working — wait for it to finish."
_SECONDS_PER_MIN = 60

# CSS goes onto each display once, however many windows are built.
_styled_displays: set[str] = set()


# --- pure logic ---------------------------------------------------------------


def mode_for_held(held: Iterable[str]) -> int | None:
    """Mode index for the held key names, or None unless exactly one kind is held."""
    kinds = {MODE_KEYS[name] for name in held if name in MODE_KEYS}
    return kinds.pop() if len(kinds) == 1 else None


def step_index(current: int | None, delta: int, count: int) -> int | None:
    """Row index after moving ``delta`` rows, clamped; None for an empty list."""
    if count <= 0:
        return None
    if current is None:
        return 0
    return max(0, min(count - 1, current + delta))


def cycle_mode(mode: int, delta: int) -> int:
    """Next tab index after moving ``delta`` tabs, wrapping around."""
    return (mode + delta) % len(MODES)


def elapsed_text(seconds: float) -> str:
    """Human-readable elapsed time for jobs that cannot report a percentage."""
    whole = int(seconds)
    if whole < _SECONDS_PER_MIN:
        return f"Working… {whole} s"
    return f"Working… {whole // _SECONDS_PER_MIN} min {whole % _SECONDS_PER_MIN} s"


def files_summary(files: Sequence[str], from_clipboard: bool) -> str:
    """Name the files being worked on, so a clipboard pickup is never silent."""
    names = ", ".join(Path(f).name for f in files[:SUMMARY_NAMES])
    extra = f" +{len(files) - SUMMARY_NAMES}" if len(files) > SUMMARY_NAMES else ""
    origin = CLIPBOARD_ORIGIN if from_clipboard else ""
    return f"{names}{extra}{origin}"


def empty_message(mode: str) -> str:
    """An empty tab must describe its own capability, not another tab's."""
    return {
        "conversions": EMPTY_STATE,
        "tools": "No tools available for this selection. Try Convert or Actions.",
        "actions": "No actions available for this selection.",
    }[mode]


@dataclass(frozen=True)
class SelectionResult:
    """An operation message and actual backend paths to adopt on the UI thread."""

    message: str
    selection: tuple[str, ...]


def _share_message(result: _actions.ShareResult) -> str:
    """Say what the LocalSend hand-off did, and what the user does next."""
    if result.app == "cli":
        return "LocalSend device list opened in a terminal: pick a device to send."
    if result.on_clipboard:
        return ("LocalSend opened. Your files are on the clipboard: press Ctrl+V "
                "there, or drag them in.")
    return "LocalSend opened. Drag your files into it (clipboard tool not found)."


def run_action(action_id: str, files: Sequence[str],
               options: dict[str, Any] | None = None) -> str | SelectionResult:
    """Return a status, plus the new selection when an action moves originals."""
    options = options or {}
    paths = [Path(f) for f in files]
    if action_id == "copy-path":
        _actions.copy_paths(paths)
        return "Paths copied to clipboard."
    if action_id == "copy":
        _actions.copy_files(paths)
        return "Files copied to clipboard."
    if action_id == "open-terminal":
        _actions.open_terminal(paths[0])
        return "Terminal opened."
    if action_id == "float":
        return f"Shelf: {_actions.float_shelf(paths)}"
    if action_id == "move":
        destination = options.get("destination")
        if not destination:
            raise ValueError("Choose a destination folder before moving files.")
        moved = _actions.move_files(paths, Path(destination))
        return SelectionResult(f"Moved {len(paths)} file(s) to {destination}",
                               tuple(str(path) for path in moved))
    if action_id == "share":
        return _share_message(_actions.share(paths))
    return f"Unknown action {action_id}"


def apply_option(mode: str, opt_id: str, files: Sequence[str],
                 progress: ProgressCallback | None = None,
                 options: dict[str, Any] | None = None) -> str | SelectionResult:
    """Apply one option to ``files``, saving next to the first; return the status.

    ``progress`` reaches the converter (conversions only); tools and actions
    report nothing measurable. Exceptions propagate; the window reports them.
    """
    src = Path(files[0])
    if mode == "conversions":
        out = _apply.apply_conversion(opt_id, src, src.parent, progress=progress)
        return f"Saved {Path(out).name}"
    if mode == "tools":
        out = _apply.apply_tool(opt_id, [Path(f) for f in files], src.parent,
                                **(options or {}))
        name = Path(out).name if isinstance(out, (str, Path)) else f"{len(out)} files"
        return f"Saved {name}"
    if options is not None:
        return run_action(opt_id, files, options)
    return run_action(opt_id, files)


def _idle_once(glib: Any) -> Callable[..., None]:
    """A `Job` ``post`` that runs each callback once on the GLib main loop.

    ``GLib.idle_add`` repeats a source while it returns a truthy value, so the
    callback is wrapped to always return ``False`` (``GLib.SOURCE_REMOVE``).
    """
    def post(fn: Callable[..., Any], *args: Any) -> None:
        def once() -> bool:
            fn(*args)
            return False
        glib.idle_add(once)
    return post


# --- GTK window ---------------------------------------------------------------


class WheelWindow:
    """One `Gtk.ApplicationWindow` with a ``"picker"`` and a ``"wheel"`` page."""

    def __init__(self, app: Any, files: Sequence[str], from_clipboard: bool = False,
                 palette: Palette | None = None,
                 start_dir: str | Path | None = None) -> None:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, GLib, Gtk

        self._gtk: Any = Gtk
        self._gdk: Any = Gdk
        self._glib: Any = GLib
        self.app = app
        self.files: list[str] = []
        self.from_clipboard = False
        self.mode = 0
        self.tabs: list[Any] = []
        self._held: set[str] = set()
        self._listing: Listing = []
        self._job: Job | None = None
        self._started = 0.0
        self._pulse_id = 0
        self._measured = False
        self.options_page: Any = None
        self._install_css(palette or load_palette())
        self.win = self._build_window()
        self.picker = self._build_picker(start_dir)
        self.stack = self._build_stack(self._build_wheel_page())
        self.win.set_child(self.stack)
        self._add_key_controller()
        if files:
            self.adopt(files, from_clipboard)
        else:
            self.show_picker()

    # -- construction --

    def _install_css(self, palette: Palette) -> None:
        display = self._gdk.Display.get_default()
        if display is None or display.get_name() in _styled_displays:
            return
        provider = self._gtk.CssProvider()
        appearance = load_appearance()
        provider.load_from_string(build_css(
            palette, appearance=appearance.style, opacity=appearance.opacity))
        self._gtk.StyleContext.add_provider_for_display(
            display, provider, self._gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _styled_displays.add(display.get_name())

    def _build_window(self) -> Any:
        win = self._gtk.ApplicationWindow(application=self.app, title=WINDOW_TITLE)
        win.set_default_size(*WINDOW_SIZE)
        win.add_css_class("kumquat")
        win.connect("close-request", self._on_close_request)
        _init_layer_shell(win)
        return win

    def _frame_as_panel(self, widget: Any) -> Any:
        """Give a stack page the opaque, rounded panel frame.

        The window itself is transparent so the panel's rounded corners
        show; any page left unframed lets the desktop bleed through.
        """
        widget.add_css_class("kumquat-panel")
        for side in ("top", "bottom", "start", "end"):
            getattr(widget, f"set_margin_{side}")(MARGIN)
        return widget

    def _build_picker(self, start_dir: str | Path | None) -> Any:
        from .picker import create_picker

        picker = create_picker(self.adopt, self._on_picker_cancel, start_dir=start_dir)
        return self._frame_as_panel(picker)

    def _build_wheel_page(self) -> Any:
        """Header, option list, progress bar, status, then the tab bar last."""
        gtk = self._gtk
        box = self._frame_as_panel(
            gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=SPACING))
        self.progress_bar = gtk.ProgressBar()
        self.progress_bar.add_css_class("kumquat-progress")
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_visible(False)
        self.status = _label(gtk, "kumquat-status", xalign=0.0)
        for child in (self._build_header(), self._build_option_list(),
                      self.progress_bar, self.status, self._build_tab_bar()):
            box.append(child)
        return box

    def _build_header(self) -> Any:
        """The prompt with the "Change files…" button beside it."""
        gtk = self._gtk
        header = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=SPACING)
        self.prompt = _label(gtk, "kumquat-prompt", xalign=0.0)
        self.prompt.set_hexpand(True)
        change = gtk.Button(label=CHANGE_FILES_LABEL)
        change.add_css_class("flat")
        change.add_css_class("kumquat-change")
        change.set_valign(gtk.Align.CENTER)
        change.set_can_focus(False)  # arrows and Enter stay on the option list
        change.connect("clicked", lambda _btn: self.show_picker())
        header.append(self.prompt)
        header.append(change)
        return header

    def _build_option_list(self) -> Any:
        """The scrolled option list: a click selects, a double-click applies."""
        gtk = self._gtk
        self.listbox = gtk.ListBox()
        self.listbox.add_css_class("kumquat-list")
        self.listbox.set_selection_mode(gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.connect("row-activated", self._on_row_activated)
        scroll = gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.listbox)
        return scroll

    def _build_tab_bar(self) -> Any:
        """Linked Convert/Tools/Actions toggle buttons; exactly one is active."""
        gtk = self._gtk
        bar = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, homogeneous=True)
        bar.add_css_class("kumquat-tabs")
        bar.add_css_class("linked")  # GTK joins adjacent buttons into one segment
        for index, label in enumerate(TAB_LABELS):
            tab = gtk.ToggleButton(label=label)
            tab.add_css_class("kumquat-tab")
            tab.set_can_focus(False)  # arrows stay on the option list
            if self.tabs:
                tab.set_group(self.tabs[0])
            tab.set_active(index == self.mode)
            tab.connect("toggled", self._on_tab_toggled, index)
            self.tabs.append(tab)
            bar.append(tab)
        self.tab_bar = bar
        return bar

    def _build_stack(self, wheel_page: Any) -> Any:
        stack = self._gtk.Stack()
        stack.set_transition_type(self._gtk.StackTransitionType.CROSSFADE)
        stack.set_transition_duration(PAGE_TRANSITION_MS)
        stack.add_named(self.picker, PAGE_PICKER)
        stack.add_named(wheel_page, PAGE_WHEEL)
        return stack

    def _add_key_controller(self) -> None:
        keys = self._gtk.EventControllerKey()
        # Capture phase: the wheel sees Enter/arrows before any focused child.
        keys.set_propagation_phase(self._gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key, True)
        keys.connect("key-released", self._on_key, False)
        self.win.add_controller(keys)

    # -- pages --

    def present(self) -> None:
        """Show the window and focus the visible page."""
        self.win.present()
        self._focus_page()

    def close(self) -> None:
        """Close the window unless a job is running (see `_on_close_request`)."""
        self.win.close()

    def _on_close_request(self, _win: Any) -> bool:
        """Refuse to close mid-job so no half-written output is orphaned."""
        if self.busy:
            self.status.set_text(BUSY_HINT)
            return True
        return False

    def show_picker(self) -> None:
        """Switch to the embedded file browser."""
        if self.busy:
            self.status.set_text(BUSY_HINT)
            return
        self.stack.set_visible_child_name(PAGE_PICKER)
        self._focus_page()

    def show_wheel(self) -> None:
        """Switch to the option list."""
        self.stack.set_visible_child_name(PAGE_WHEEL)
        self._focus_page()

    def _focus_page(self) -> None:
        if self.stack.get_visible_child_name() == PAGE_PICKER:
            self.picker.focus_list()
        else:
            self.listbox.grab_focus()

    def _on_picker_cancel(self) -> None:
        if self.files:
            self.show_wheel()
        else:
            self.close()

    # -- state --

    def adopt(self, paths: Sequence[str], from_clipboard: bool = False) -> None:
        """Work on ``paths``: conversions mode, first row selected, wheel page."""
        self.files = [str(p) for p in paths]
        self.from_clipboard = from_clipboard
        self._held.clear()
        if not self.files:
            self.show_picker()
            return
        self._listing = files_listing(self.files, [detect_mime(f) for f in self.files])
        self.set_mode(0)
        self.show_wheel()

    def set_mode(self, index: int) -> None:
        """Show mode ``index``: the one entry point for tabs, keys and `adopt`.

        Activating the tab re-enters `_on_tab_toggled`, which is a no-op once
        ``self.mode`` already equals ``index``, so the list renders once.
        """
        self.mode = index
        if not self.tabs[index].get_active():
            self.tabs[index].set_active(True)
        self.render()

    def _on_tab_toggled(self, tab: Any, index: int) -> None:
        if tab.get_active() and index != self.mode:
            self.set_mode(index)

    def _switch_tab(self, delta: int) -> None:
        self.set_mode(cycle_mode(self.mode, delta))

    def current_items(self) -> list[tuple[str, str]]:
        """``(id, label)`` options for the active mode; empty with no files."""
        if not self._listing:
            return []
        _name, sections = self._listing[0]
        return sections[MODES[self.mode]]

    def render(self) -> None:
        """Rebuild the option list for the current mode."""
        mode = MODES[self.mode]
        while (row := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(row)
        self.prompt.set_text(PROMPTS[mode])
        items = self.current_items()
        self.listbox.set_sensitive(bool(items))
        if not items:
            message = empty_message(mode)
            hint = self._row(message, message)
            hint.set_selectable(False)
            hint.set_activatable(False)
            self.listbox.append(hint)
            self.listbox.unselect_all()
            if not self.busy:
                self.status.set_text(files_summary(self.files, self.from_clipboard))
            return
        for _opt_id, label in items:
            self.listbox.append(self._row(label, label))
        self.listbox.select_row(self.listbox.get_row_at_index(0))
        if not self.busy:  # mid-job the status line belongs to the job
            self.status.set_text(files_summary(self.files, self.from_clipboard))

    def _row(self, text: str, accessible_name: str) -> Any:
        gtk = self._gtk
        row = gtk.ListBoxRow()
        row.set_child(gtk.Label(label=text, xalign=0.0))
        row.update_property([gtk.AccessibleProperty.LABEL], [accessible_name])
        return row

    def _selected_id(self) -> str | None:
        row = self.listbox.get_selected_row()
        items = self.current_items()
        if row is None or not 0 <= row.get_index() < len(items):
            return None
        return items[row.get_index()][0]

    @property
    def busy(self) -> bool:
        """True from `apply_selected` until the job's result is shown.

        Cleared in `_on_done` rather than when the worker thread exits, so a
        new job can never start before the previous one has reported.
        """
        return self._job is not None

    def apply_selected(self) -> None:
        """Start the chosen option in the background and show its progress."""
        if not self.files:
            self.show_picker()
            return
        if self.busy:
            self.status.set_text(BUSY_HINT)
            return
        opt_id = self._selected_id()
        if opt_id is None:
            self.status.set_text(NO_SELECTION)
            return
        mode, files = MODES[self.mode], list(self.files)
        from .tool_options import requires_options

        if mode in ("tools", "actions") and requires_options(opt_id):
            self._show_options(mode, opt_id, files)
        else:
            self._start_option(mode, opt_id, files)

    def _show_options(self, mode: str, opt_id: str, files: list[str]) -> None:
        """Collect choices inside the same window, before launching any worker."""
        from .tool_options import create_tool_options

        if self.options_page is not None:
            self.stack.remove(self.options_page)
        self._held.clear()
        self.options_page = self._frame_as_panel(create_tool_options(
            opt_id, files,
            lambda options: self._apply_options(mode, opt_id, files, options),
            self.show_wheel))
        self.stack.add_named(self.options_page, PAGE_OPTIONS)
        self.stack.set_visible_child_name(PAGE_OPTIONS)

    def _apply_options(self, mode: str, opt_id: str, files: list[str],
                       options: dict[str, Any]) -> None:
        self.show_wheel()
        self._start_option(mode, opt_id, files, options)

    def _start_option(self, mode: str, opt_id: str, files: list[str],
                      options: dict[str, Any] | None = None) -> None:
        """Run a frozen selection and its validated options off the GTK thread."""
        if self.busy:
            self.status.set_text(BUSY_HINT)
            return
        self._job = Job(
            lambda progress: apply_option(
                mode, opt_id, files, progress=progress, options=options),
            on_progress=self._on_progress, on_done=self._on_done,
            post=_idle_once(self._glib))
        self._start_progress()
        self._job.start()

    def _on_row_activated(self, _listbox: Any, row: Any) -> None:
        self.listbox.select_row(row)
        self.apply_selected()

    # -- progress --

    def _start_progress(self) -> None:
        self._started = time.monotonic()
        self._measured = False
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(elapsed_text(0))
        self.progress_bar.set_visible(True)
        self._pulse_id = self._glib.timeout_add(PULSE_MS, self._tick)

    def _tick(self) -> bool:
        """Pulse and count seconds until a measured fraction arrives."""
        if not self._measured:
            self.progress_bar.pulse()
            self.progress_bar.set_text(elapsed_text(time.monotonic() - self._started))
        return True  # the source is removed in _stop_progress

    def _on_progress(self, update: Progress) -> None:
        if update.fraction is None:
            return
        self._measured = True
        self.progress_bar.set_fraction(update.fraction)
        self.progress_bar.set_text(update.text)

    def _on_done(self, result: Any, error: BaseException | None) -> None:
        """Hide the bar and report the outcome; a failure is never silent."""
        self._stop_progress()
        self._job = None
        if error is not None:
            self.status.set_text(f"Failed: {type(error).__name__}: {error}")
        else:
            if isinstance(result, SelectionResult):
                # The worker reports actual moved paths; GTK adopts them only
                # here, after the job is cleared, then keeps its success message.
                self.adopt(result.selection)
                self.status.set_text(result.message)
            else:
                self.status.set_text(result)

    def _stop_progress(self) -> None:
        if self._pulse_id:
            self._glib.source_remove(self._pulse_id)
            self._pulse_id = 0
        self.progress_bar.set_visible(False)

    # -- keys --

    def _on_key(self, _ctl: Any, keyval: int, _code: int, _state: Any,
                pressed: bool) -> bool:
        page = self.stack.get_visible_child_name()
        name = self._gdk.keyval_name(keyval) or ""
        if page == PAGE_OPTIONS:
            # Text fields own letters/arrows/Enter; Escape goes back without work.
            if name == CLOSE_KEY:
                if pressed:
                    self.show_wheel()
                return True
            return False
        if page != PAGE_WHEEL:
            return False  # the picker handles its own keys
        return self.handle_key(name, pressed)

    def handle_key(self, name: str, pressed: bool) -> bool:
        """Act on one key event on the wheel page; True when it was consumed."""
        if name in MODE_KEYS:
            self._track_modifier(name, pressed)
            return True
        action = self._key_action(name)
        if action is None:
            return False
        if pressed:  # releases are swallowed so a picker key never leaks in
            action()
        return True

    def _key_action(self, name: str) -> Callable[[], None] | None:
        if name == CLOSE_KEY:
            return self.close
        if name in APPLY_KEYS:
            return self.apply_selected
        if name in MOVE_KEYS:
            return partial(self._move, MOVE_KEYS[name])
        if name in TAB_KEYS:
            return partial(self._switch_tab, TAB_KEYS[name])
        return None

    def _track_modifier(self, name: str, pressed: bool) -> None:
        if not pressed:
            self._held.discard(name)
            return
        self._held.add(name)
        mode = mode_for_held(self._held)
        if mode is not None:
            self.set_mode(mode)

    def _move(self, delta: int) -> None:
        row = self.listbox.get_selected_row()
        count = len(self.current_items())
        index = step_index(row.get_index() if row else None, delta, count)
        if index is None:
            return
        target = self.listbox.get_row_at_index(index)
        self.listbox.select_row(target)
        target.grab_focus()


def _label(gtk: Any, css_class: str, xalign: float = 0.5) -> Any:
    """A wrapping label with one CSS class."""
    label = gtk.Label(xalign=xalign)
    label.set_wrap(True)
    label.add_css_class(css_class)
    return label


def _init_layer_shell(win: Any) -> None:
    """Make ``win`` an exclusive-keyboard overlay when GtkLayerShell exists."""
    import gi

    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except (ImportError, ValueError):
        return  # plain toplevel window; Hyprland window rules still apply
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)

"""Render the real Kumquat window to PNG files for the README.

Every scene builds a real `kumquat.gui.wheel.WheelWindow` and drives it
through its public API only (``adopt``/``set_mode``/``apply_selected``).
The PNG comes from GTK's own `Gtk.WidgetPaintable` -> `Gtk.Snapshot` ->
renderer texture, i.e. from the widget tree itself: no screen grab, so the
user's desktop can never end up in an image.

The window is forced to 520x640, the size Omarchy's window rule gives
``dev.kumquat.app``. All demo files live in a fresh, neutral folder
(``$TMPDIR/kumquat-demo``) that is deleted afterwards; no real user folder
is ever shown.

Usage:
    PYTHONPATH=src WAYLAND_DISPLAY=wayland-1 \\
        /usr/bin/python3 tests/make_screenshots.py [OUTDIR] \\
        [--theme NAME_OR_colors.toml] [--scenes picker,modes,progress,crop,pdf,convert]

``--theme`` draws with a stock Omarchy theme from /usr/share/omarchy/themes (or
any colors.toml path) instead of the active one; the stylesheet is installed
once per process, so render one theme per run (tests/make_theme_gallery.py does).
The look is always the shipped opaque style, never a personal appearance.toml.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kumquat.gui import picker as _picker  # noqa: E402
from kumquat.gui import wheel as _wheel  # noqa: E402
from kumquat.gui.appearance import Appearance  # noqa: E402
from kumquat.gui.theme import load_palette  # noqa: E402
from kumquat.gui.wheel import WheelWindow  # noqa: E402

STOCK_THEMES = Path("/usr/share/omarchy/themes")
PALETTE = None  # set from --theme; None means the active Omarchy theme
# Never let a personal ~/.config/kumquat/appearance.toml leak into README images.
_wheel.load_appearance = lambda: Appearance()

WIDTH, HEIGHT = 520, 640
APP_ID = "dev.kumquat.app"  # same class as the real window, so the rule applies
DEMO_DIR = Path(tempfile.gettempdir()) / "kumquat-demo"
# README images must not reveal where the demo folder really lives (a scratch
# path names local tooling), so the header abbreviates relative to its parent.
_real_display_path = _picker.display_path
_picker.display_path = lambda directory, home=None: _real_display_path(
    directory, DEMO_DIR.parent)
PICTURE = "holiday.jpg"
VIDEO = "weekend.mov"
DEMO_FILES = (PICTURE, "mixtape.mp3", "field-notes.pdf", VIDEO)
DEMO_SUBFOLDER = "Projects"
# testsrc2 at 720p keeps the WEBM encoder busy for several seconds, so the
# progress bar spends long enough between 30 % and 80 % to be photographed.
TEST_VIDEO = "testsrc2=duration=8:size=1280x720:rate=30"
PROGRESS_OPTION = "Convert to WEBM"
PROGRESS_RANGE = (0.3, 0.8)
SETTLE_S = 0.4  # longer than the 120 ms page crossfade
LAYOUT_TIMEOUT_S = 10.0
JOB_TIMEOUT_S = 180.0
POLL_S = 0.01
FFMPEG_TIMEOUT_S = 120


# --- fixtures ---------------------------------------------------------------

def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True,
                   timeout=FFMPEG_TIMEOUT_S)


def _make_pdf(out: Path) -> None:
    import fitz  # PyMuPDF

    doc = fitz.open()
    shades = ((0.86, 0.93, 1.0), (1.0, 0.92, 0.82),
              (0.88, 0.97, 0.88), (0.97, 0.88, 0.95))
    for number, shade in enumerate(shades, start=1):
        page = doc.new_page(width=300, height=400)
        page.draw_rect(page.rect, color=None, fill=shade)
        page.insert_text((40, 110), "Field notes", fontsize=26)
        page.insert_text((120, 280), str(number), fontsize=120)
    doc.save(str(out))
    doc.close()


def build_demo_dir() -> Path:
    """Generate only synthetic inputs under TMPDIR, with an empty Projects."""
    DEMO_DIR.mkdir()
    (DEMO_DIR / DEMO_SUBFOLDER).mkdir()
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=800x600", "-frames:v", "1",
            str(DEMO_DIR / PICTURE))
    _ffmpeg("-f", "lavfi", "-i", "sine=duration=3",
            str(DEMO_DIR / "mixtape.mp3"))
    _make_pdf(DEMO_DIR / "field-notes.pdf")
    _ffmpeg("-f", "lavfi", "-i", TEST_VIDEO, "-pix_fmt", "yuv420p",
            str(DEMO_DIR / VIDEO))
    return DEMO_DIR


# --- main-loop helpers ------------------------------------------------------

def pump_until(done: Callable[[], bool], timeout: float) -> bool:
    """Iterate the default main context until ``done()`` or ``timeout``."""
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not done():
        if time.monotonic() > deadline:
            return False
        if not ctx.iteration(False):
            time.sleep(POLL_S)
    return True


def pump_for(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    pump_until(lambda: time.monotonic() > deadline, seconds + 1)


def wait_painted(win: Gtk.Window, frames: int = 2) -> None:
    """Wait until ``win`` has painted ``frames`` more frames."""
    clock = win.get_frame_clock()
    painted = {"n": 0}

    def count(_clock) -> None:
        painted["n"] += 1

    handler = clock.connect("after-paint", count)
    win.queue_draw()
    pump_until(lambda: painted["n"] >= frames, LAYOUT_TIMEOUT_S)
    clock.disconnect(handler)


def open_window(app: Gtk.Application, files: list[str]) -> WheelWindow:
    """Build, size and present a real wheel; return once it is laid out."""
    w = WheelWindow(app, files=files, start_dir=str(DEMO_DIR), palette=PALETTE)
    w.win.set_default_size(WIDTH, HEIGHT)
    w.win.set_size_request(WIDTH, HEIGHT)
    w.present()
    laid_out = pump_until(lambda: w.win.get_mapped()
                          and (w.win.get_width(), w.win.get_height()) == (WIDTH, HEIGHT),
                          LAYOUT_TIMEOUT_S)
    if not laid_out:
        raise RuntimeError(f"window is {w.win.get_width()}x{w.win.get_height()}, "
                           f"expected {WIDTH}x{HEIGHT}")
    pump_for(SETTLE_S)
    wait_painted(w.win)
    return w


def save(win: Gtk.Window, out: Path) -> None:
    """Snapshot the realized window's own widget tree into a 520x640 PNG."""
    paintable = Gtk.WidgetPaintable.new(win)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, WIDTH, HEIGHT)
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"empty render for {out.name}")
    texture = win.get_native().get_renderer().render_texture(node, None)
    texture.save_to_png(str(out))
    print(f"wrote {out} ({texture.get_width()}x{texture.get_height()})")


# --- scenes -----------------------------------------------------------------

def expect_page(w: WheelWindow, mode: int, first_label_start: str) -> None:
    """Refuse to photograph the wrong tab (a stale page once slipped through)."""
    w.set_mode(mode)
    pump_for(SETTLE_S)
    wait_painted(w.win)
    labels = [label for _id, label in w.current_items()]
    if (w.stack.get_visible_child_name() == "options" or not labels
            or not labels[0].upper().startswith(first_label_start.upper())):
        page = w.stack.get_visible_child_name()
        raise RuntimeError(f"mode {mode}: expected a list starting "
                           f"{first_label_start!r}, got {labels[:2]} on page {page!r}")


def shoot_picker(app: Gtk.Application, outdir: Path) -> None:
    w = open_window(app, [])
    save(w.win, outdir / "wheel-picker.png")
    w.win.destroy()


def shoot_modes(app: Gtk.Application, outdir: Path) -> None:
    w = open_window(app, [str(DEMO_DIR / PICTURE)])
    for mode, name, first in (
            (1, "wheel-tools", "COMPRESS"),  # leave Convert and come back so the
            (0, "wheel-conversions", "Convert to"),  # first shot is a fresh paint
            (2, "wheel-actions", "LOCALSEND")):
        expect_page(w, mode, first)
        save(w.win, outdir / f"{name}.png")
    w.win.destroy()


def shoot_convert(app: Gtk.Application, outdir: Path) -> None:
    """One Convert page; the theme gallery renders this once per theme."""
    w = open_window(app, [str(DEMO_DIR / PICTURE)])
    expect_page(w, 1, "COMPRESS")
    expect_page(w, 0, "Convert to")
    save(w.win, outdir / "wheel-convert.png")
    w.win.destroy()


def shoot_pdf(app: Gtk.Application, outdir: Path) -> None:
    """Organize PDF with the page-thumbnail strip, pages already reordered."""
    w = open_window(app, [str(DEMO_DIR / "field-notes.pdf")])
    expect_page(w, 1, "")
    ids = [option_id for option_id, _label in w.current_items()]
    w.listbox.select_row(w.listbox.get_row_at_index(ids.index("organizePDF")))
    w.apply_selected()
    if w.stack.get_visible_child_name() != "options":
        raise RuntimeError("Organize PDF did not open its settings page")
    w.options_page.set_value("page_order", "3, 1, 4, 2")
    pump_for(SETTLE_S)
    wait_painted(w.win)
    save(w.win, outdir / "wheel-pdf.png")
    w.win.destroy()


def shoot_progress(app: Gtk.Application, outdir: Path) -> None:
    """Start the WEBM encode and photograph the bar between 30 % and 80 %."""
    w = open_window(app, [str(DEMO_DIR / VIDEO)])
    labels = [label for _id, label in w.current_items()]
    if PROGRESS_OPTION not in labels:
        raise RuntimeError(f"{PROGRESS_OPTION!r} not offered for {VIDEO}")
    w.listbox.select_row(w.listbox.get_row_at_index(labels.index(PROGRESS_OPTION)))
    w.apply_selected()
    low, high = PROGRESS_RANGE
    bar = w.progress_bar

    def in_range() -> bool:
        return (bar.get_text() or "").endswith("%") and low < bar.get_fraction() < high

    if not pump_until(in_range, JOB_TIMEOUT_S):
        raise RuntimeError(f"progress never reached {low}-{high} ({bar.get_text()!r})")
    wait_painted(w.win)
    if not in_range():
        raise RuntimeError(f"progress left the range before the shot "
                           f"({bar.get_text()!r})")
    save(w.win, outdir / "wheel-progress.png")
    print(f"progress shot at {bar.get_text()} (fraction {bar.get_fraction():.2f})")
    if not pump_until(lambda: not w.busy, JOB_TIMEOUT_S):
        raise RuntimeError("video job did not finish")
    w.win.destroy()


def shoot_crop(app: Gtk.Application, outdir: Path) -> None:
    """Show the real, usable Crop settings page rather than a mock dialog."""
    w = open_window(app, [str(DEMO_DIR / PICTURE)])
    w.set_mode(1)
    ids = [option_id for option_id, _label in w.current_items()]
    w.listbox.select_row(w.listbox.get_row_at_index(ids.index("cropImage")))
    w.apply_selected()
    if w.stack.get_visible_child_name() != "options":
        raise RuntimeError("Crop did not open its settings page")
    pump_for(SETTLE_S)
    wait_painted(w.win)
    save(w.win, outdir / "wheel-crop.png")
    w.win.destroy()


SCENES = {"picker": shoot_picker, "modes": shoot_modes, "progress": shoot_progress,
          "crop": shoot_crop, "pdf": shoot_pdf, "convert": shoot_convert}
DEFAULT_SCENES = ("picker", "modes", "progress", "crop", "pdf")


def main(argv: list[str]) -> int:
    global PALETTE
    args = argv[1:]
    options = {}
    for flag in ("--theme", "--scenes"):
        if flag in args:
            at = args.index(flag)
            options[flag] = args[at + 1]
            del args[at:at + 2]
    outdir = Path(args[0]) if args else Path("docs/images")
    names = options["--scenes"].split(",") if "--scenes" in options else DEFAULT_SCENES
    scenes = [SCENES[name] for name in names]
    if "--theme" in options:
        theme = options["--theme"]
        path = (Path(theme) if theme.endswith(".toml")
                else STOCK_THEMES / theme / "colors.toml")
        if not path.is_file():
            print(f"theme not found: {path}")
            return 2
        PALETTE = load_palette(path)
    outdir.mkdir(parents=True, exist_ok=True)
    if DEMO_DIR.exists():  # never delete a folder this script did not create
        print(f"{DEMO_DIR} already exists; remove it first")
        return 1
    app = Gtk.Application(application_id=APP_ID,
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    result = {"code": 1}

    def on_activate(_app: Gtk.Application) -> None:
        app.hold()
        try:
            build_demo_dir()
            for scene in scenes:
                scene(app, outdir)
            result["code"] = 0
            print("done:", outdir)
        finally:
            for win in list(app.get_windows()):
                win.destroy()
            shutil.rmtree(DEMO_DIR, ignore_errors=True)
            app.release()
            app.quit()

    app.connect("activate", on_activate)
    app.run([])
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

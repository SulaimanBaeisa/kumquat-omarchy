"""Real GTK proof of the draw-on-image crop (synthetic image, no desktop access).

Drives the real `CropCanvas` inside the real wheel window: opens Crop, draws,
moves, resizes, locks a ratio, nudges with the keyboard, applies, and checks
the saved file's size AND pixel colours. Gesture handlers are called directly,
so this is component coverage of the dragging code, not a physical mouse test.

Run: PYTHONPATH=src /usr/bin/python3 tests/crop_canvas_e2e.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import time
from pathlib import Path

FULL = (600, 400)
RED, GREEN, BLUE, YELLOW = (255, 0, 0), (0, 200, 0), (0, 0, 255), (255, 255, 0)


def main() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk
    from PIL import Image

    from kumquat.gui import wheel

    wheel._init_layer_shell = lambda _win: None
    checks: list[bool] = []

    def check(name, condition):
        checks.append(bool(condition))
        print(f"{'PASS' if condition else 'FAIL'}: {name}", flush=True)

    def pump_until(predicate, timeout=10.0):
        until = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def near(a, b, slack=1):
        return all(abs(x - y) <= slack for x, y in zip(a, b, strict=True))

    def box_of(page):
        c = page.controls
        x, y = int(c["x"].get_text()), int(c["y"].get_text())
        return x, y, x + int(c["width"].get_text()), y + int(c["height"].get_text())

    def drag(canvas, start_img, end_img):
        """A real press-move-release between two image points."""
        view = canvas.view()
        sx, sy = view.to_view(*start_img)
        ex, ey = view.to_view(*end_img)
        canvas.begin_drag(sx, sy)
        canvas.update_drag((ex - sx) / 2, (ey - sy) / 2)
        canvas.update_drag(ex - sx, ey - sy)
        canvas.end_drag()

    app = Gtk.Application(
        application_id="dev.kumquat.cropproof", flags=Gio.ApplicationFlags.NON_UNIQUE
    )
    app.register(None)
    with tempfile.TemporaryDirectory(prefix="kumquat-crop-proof-") as directory:
        root = Path(directory)
        src = root / "Four colours.png"
        image = Image.new("RGB", FULL, RED)
        image.paste(GREEN, (300, 0, 600, 200))
        image.paste(BLUE, (0, 200, 300, 400))
        image.paste(YELLOW, (300, 200, 600, 400))
        image.save(src)
        before = hashlib.sha256(src.read_bytes()).hexdigest()

        window = wheel.WheelWindow(app, [str(src)])
        window.present()
        pump_until(lambda: window.win.get_mapped())
        try:
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            window.listbox.select_row(
                window.listbox.get_row_at_index(ids.index("cropImage"))
            )
            window.apply_selected()
            page = window.options_page
            canvas = page.canvas
            check(
                "Crop opens a settings page with a picture canvas",
                window.stack.get_visible_child_name() == "options" and canvas is not None,
            )
            if canvas is None:
                return 1
            pump_until(lambda: canvas.get_width() > 100 and canvas.get_height() > 100)
            check(
                "page starts in Draw on image mode",
                page._raw()["crop_mode"] == "draw" and canvas.get_visible(),
            )
            check(
                "pixel fields and ratio rows are hidden while drawing",
                not page.rows["x"].get_visible()
                and not page.rows["aspect"].get_visible()
                and page.rows["lock"].get_visible(),
            )
            check(
                "starts with a centred box and a readout",
                box_of(page) == (60, 40, 540, 360)
                and "Keeping 480 × 320 px of 600 × 400" in page.readout.get_text(),
            )
            view = canvas.view()
            check(
                "picture fits inside the canvas with no distortion",
                view.scale > 0
                and view.ox >= 0
                and view.oy >= 0
                and abs((FULL[0] * view.scale) / (FULL[1] * view.scale) - 1.5) < 1e-9,
            )

            drag(canvas, (10, 10), (300, 200))
            check(
                "dragging outside the box draws a new one",
                near(box_of(page), (10, 10, 300, 200)),
            )
            check(
                "readout follows the drag",
                "Keeping 290 × 190 px" in page.readout.get_text(),
            )

            before_move = box_of(page)
            view = canvas.view()
            cx, cy = view.to_view(155, 105)  # inside the box, away from every handle
            canvas.begin_drag(cx, cy)
            canvas.update_drag(24, 16)
            canvas.end_drag()
            moved = box_of(page)
            check(
                "dragging inside moves the box without resizing it",
                moved[2] - moved[0] == before_move[2] - before_move[0]
                and moved[3] - moved[1] == before_move[3] - before_move[1]
                and moved[0] > before_move[0]
                and moved[1] > before_move[1],
            )
            drag(canvas, (moved[0] + 50, moved[1] + 40), (-5000, -5000))
            check(
                "a box cannot be dragged off the picture",
                box_of(page)[0] >= 0 and box_of(page)[1] >= 0,
            )

            drag(canvas, (590, 390), (5000, 5000))
            check(
                "dragging from the corner resizes within the picture",
                box_of(page)[2] <= FULL[0] and box_of(page)[3] <= FULL[1],
            )

            page.set_value("lock", "1:1")
            check(
                "locking 1:1 reshapes the box to a square",
                abs(
                    (box_of(page)[2] - box_of(page)[0])
                    - (box_of(page)[3] - box_of(page)[1])
                )
                <= 1,
            )
            drag(canvas, (20, 20), (500, 300))
            width = box_of(page)[2] - box_of(page)[0]
            height = box_of(page)[3] - box_of(page)[1]
            check("a locked ratio is kept while drawing", abs(width - height) <= 1)
            page.set_value("lock", "16:9")
            width = box_of(page)[2] - box_of(page)[0]
            height = box_of(page)[3] - box_of(page)[1]
            check(
                "switching to 16:9 re-shapes the existing box",
                abs(width / height - 16 / 9) < 0.03,
            )
            page.set_value("lock", "free")

            drag(canvas, (100, 100), (200, 180))
            start = box_of(page)
            click_x, click_y = canvas.view().to_view(450, 350)
            canvas.begin_drag(click_x, click_y)
            canvas.end_drag()
            check("a plain click keeps the existing box", box_of(page) == start)

            canvas.nudge(10, 0)
            after = box_of(page)
            check("keyboard nudge moves the box", after[0] == start[0] + 10)
            check(
                "arrow keys are handled by the canvas",
                canvas._on_key(
                    None, 0xFF51, 0, type("S", (), {"__and__": lambda s, o: 0})()
                ),
            )
            check(
                "the Left arrow moved the box left by 3 px (1/200 of the width)",
                box_of(page)[0] == after[0] - 3,
            )
            after = box_of(page)

            page.set_value("crop_mode", "box")
            check(
                "pixel mode shows the pixel fields and hides the picture",
                page.rows["x"].get_visible() and not page.canvas_box.get_visible(),
            )
            check(
                f"pixel mode keeps the same numbers ({box_of(page)} vs {after})",
                box_of(page) == after,
            )
            page.set_value("x", "50")
            page.set_value("width", "300")
            page.set_value("y", "40")
            page.set_value("height", "100")
            page.set_value("crop_mode", "draw")
            check(
                "typed pixels carry back into the drawn box",
                near(canvas.box(), (50, 40, 350, 140)),
            )

            check("drawn box starts a background job", page.submit() and window.busy)
            check("crop job finishes", pump_until(lambda: not window.busy))
            outputs = [p for p in root.glob("*.png") if p != src]
            check(
                "crop reports a real output",
                len(outputs) == 1 and window.status.get_text().startswith("Saved "),
            )
            if outputs:
                with Image.open(outputs[0]) as out:
                    rgb = out.convert("RGB")
                    check("saved file has exactly the drawn size", out.size == (300, 100))
                    check(
                        "saved pixels come from the drawn area",
                        rgb.getpixel((0, 0)) == RED
                        and rgb.getpixel((249, 50)) == RED
                        and rgb.getpixel((250, 50)) == GREEN
                        and rgb.getpixel((299, 99)) == GREEN,
                    )
            check(
                "original image untouched",
                hashlib.sha256(src.read_bytes()).hexdigest() == before,
            )
            window.show_wheel()

            second = root / "Second.png"
            Image.new("RGB", (50, 50), BLUE).save(second)
            window.adopt([str(src), str(second)])
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            window.listbox.select_row(
                window.listbox.get_row_at_index(ids.index("cropImage"))
            )
            window.apply_selected()
            multi = window.options_page
            check(
                "several images: no canvas and a ratio crop by default",
                multi.canvas is None and multi._raw()["crop_mode"] == "aspect",
            )
            multi.set_value("crop_mode", "draw")
            check(
                "choosing Draw with several images explains why it cannot",
                multi.draw_note.get_visible()
                and "exactly one image" in multi.draw_note.get_text(),
            )
            check(
                "Apply refuses Draw without a box",
                not multi.submit()
                and "Drag on the picture" in multi.error_label.get_text(),
            )
            window.show_wheel()

            broken = root / "broken.png"
            broken.write_bytes(b"not an image")
            window.adopt([str(broken)])
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            if "cropImage" in ids:
                window.listbox.select_row(
                    window.listbox.get_row_at_index(ids.index("cropImage"))
                )
                window.apply_selected()
                bad = window.options_page
                bad.set_value("crop_mode", "draw")
                check(
                    "an unreadable image degrades to a message, not a crash",
                    bad.canvas is None
                    and "Preview unavailable" in bad.draw_note.get_text(),
                )
        finally:
            window.win.destroy()
            pump_until(lambda: not app.get_windows())
    print(f"{sum(checks)}/{len(checks)} checks passed", flush=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

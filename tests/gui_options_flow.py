"""Real GTK wheel -> options -> worker -> file proof (synthetic inputs only).

This exercises actual widget callbacks and the converter; physical desktop
shortcut routing is verified separately by desktop_shortcut_e2e.py.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk
    from PIL import Image

    from kumquat.gui import wheel

    wheel._init_layer_shell = lambda _win: None
    checks = []

    def check(name, condition):
        checks.append(bool(condition))
        print(f"{'PASS' if condition else 'FAIL'}: {name}", flush=True)

    def pump_until(predicate, timeout=10):
        until = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            for _ in range(50):
                if not context.pending():
                    break
                context.iteration(False)
            if predicate():
                return True
            time.sleep(0.01)
        return False

    app = Gtk.Application(
        application_id="dev.kumquat.optionsproof", flags=Gio.ApplicationFlags.NON_UNIQUE
    )
    app.register(None)
    with tempfile.TemporaryDirectory(prefix="kumquat-options-flow-") as directory:
        root = Path(directory)
        src = root / "Photo with spaces.png"
        Image.new("RGB", (160, 90), "teal").save(src)
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
            check(
                "Crop opens options rather than a failing job",
                window.stack.get_visible_child_name() == "options" and not window.busy,
            )
            if not checks[-1]:
                return 1
            page = window.options_page
            page.set_value("crop_mode", "box")
            page.set_value("width", "wrong")
            page.set_value("height", "40")
            check(
                "invalid crop stays on options without processing",
                not page.submit() and page.error_label.get_visible() and not window.busy,
            )
            page.set_value("crop_mode", "aspect")
            page.set_value("aspect", "1:1")
            check("valid choices start background job", page.submit() and window.busy)
            check(
                "job returns to wheel", window.stack.get_visible_child_name() == "wheel"
            )
            check("crop job finishes", pump_until(lambda: not window.busy))
            outputs = [p for p in root.glob("*.png") if p != src]
            check(
                "crop reports a real output",
                len(outputs) == 1 and window.status.get_text().startswith("Saved "),
            )
            if outputs:
                with Image.open(outputs[0]) as image:
                    check(
                        "square crop actually changed dimensions", image.size == (90, 90)
                    )
            check(
                "conversion original untouched",
                hashlib.sha256(src.read_bytes()).hexdigest() == before,
            )
            window.apply_selected()
            check(
                "opening Crop again collects choices again",
                window.stack.get_visible_child_name() == "options" and not window.busy,
            )
            window.options_page.back_button.emit("clicked")
            check(
                "Back returns without another output",
                window.stack.get_visible_child_name() == "wheel"
                and len(list(root.glob("*.png"))) == 2,
            )
            window.set_mode(2)
            ids = [item[0] for item in window.current_items()]
            window.listbox.select_row(window.listbox.get_row_at_index(ids.index("move")))
            window.apply_selected()
            check(
                "Move asks for destination",
                window.stack.get_visible_child_name() == "options" and not window.busy,
            )
            window.options_page.set_value("destination", str(root / "Destination"))
            check("Move starts only on explicit Apply", window.options_page.submit())
            check("Move finishes", pump_until(lambda: not window.busy))
            check(
                "Move really moves selected file",
                (root / "Destination" / src.name).is_file()
                and not src.exists()
                and window.status.get_text().startswith("Moved "),
            )
            moved = root / "Destination" / src.name
            check("Move updates the active selection", window.files == [str(moved)])
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            window.listbox.select_row(
                window.listbox.get_row_at_index(ids.index("cropImage"))
            )
            window.apply_selected()
            window.options_page.set_value("crop_mode", "aspect")
            window.options_page.set_value("aspect", "1:1")
            check("Crop after Move starts", window.options_page.submit())
            check("Crop after Move finishes", pump_until(lambda: not window.busy))
            moved_outputs = [p for p in moved.parent.glob("*.png") if p != moved]
            check(
                "Crop after Move saves beside the moved file",
                len(moved_outputs) == 1 and window.status.get_text().startswith("Saved "),
            )
            if moved_outputs:
                with Image.open(moved_outputs[0]) as image:
                    check(
                        "Crop after Move has the requested dimensions",
                        image.size == (90, 90),
                    )
            check(
                "Crop after Move preserves the moved original",
                hashlib.sha256(moved.read_bytes()).hexdigest() == before,
            )
            deck = root / "Lecture.pptx"
            deck.write_bytes(b"synthetic file-name capability test")
            window.adopt([str(deck)])
            window.set_mode(1)
            hint = window.listbox.get_row_at_index(0)
            check(
                "PPTX empty Tools state is truthful",
                "No tools" in hint.get_child().get_text(),
            )
            check(
                "empty hint is not an actionable option",
                not hint.get_selectable()
                and not hint.get_activatable()
                and window.listbox.get_selected_row() is None,
            )
        finally:
            window.win.destroy()
            pump_until(lambda: not app.get_windows())
    print(f"{sum(checks)}/{len(checks)} checks passed", flush=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

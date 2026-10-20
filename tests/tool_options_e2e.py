"""Real GTK4 options checks (no pytest/gi dependency in the virtualenv).

Run: PYTHONPATH=src /usr/bin/python3 tests/tool_options_e2e.py
Synthetic local fixture only; no user's files or desktop screenshots are read.
Component events, not physical pointer/keyboard automation.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RESULTS = []


def check(name, condition):
    RESULTS.append(bool(condition))
    print(f"{'PASS' if condition else 'FAIL'}: {name}", flush=True)


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def main():
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    from kumquat.gui import tool_options
    from kumquat.gui.css import build_css
    from kumquat.gui.theme import Palette

    check("factory is available", hasattr(tool_options, "create_tool_options"))
    if not RESULTS[-1]:
        return 1
    Gtk.init()
    if not Gtk.init_check():
        print("FAIL: no GTK display")
        return 2
    root = Path(tempfile.mkdtemp(prefix="kumquat-options-"))
    fixture = root / "Synthetic صورة.svg"
    fixture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60">'
        '<rect width="80" height="60" fill="orange"/></svg>'
    )
    original = fixture.read_bytes()
    window = Gtk.Window(title="Kumquat synthetic options test")
    window.set_default_size(520, 640)
    window.set_resizable(False)
    window.add_css_class("kumquat")
    provider = Gtk.CssProvider()
    parse_errors = []
    provider.connect("parsing-error", lambda *_args: parse_errors.append(True))
    palette = Palette("#111111", "#eeeeee", "#ffaa33", "#999999", "#222222", "#111111")
    provider.load_from_data(build_css(palette).encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    check("theme stylesheet parses", not parse_errors)
    applied, cancelled = [], []
    page = tool_options.create_tool_options(
        "cropImage", [fixture], applied.append, lambda: cancelled.append(True)
    )
    page.add_css_class("kumquat-panel")
    window.set_child(page)
    window.present()
    context = GLib.MainContext.default()

    def pump():
        loop = GLib.MainLoop()
        GLib.timeout_add(40, lambda: loop.quit() or False)
        loop.run()
        for _ in range(50):
            if not context.pending():
                break
            context.iteration(False)

    try:
        pump()
        check("root is Gtk.Box", isinstance(page, Gtk.Box))
        check(
            "allocated in 520x640 window",
            window.get_width() == 520 and window.get_height() == 640,
        )
        check("root glass class", page.has_css_class("kumquat-tool-options"))
        check(
            "Apply and Back",
            page.apply_button.get_label() == "Apply"
            and page.back_button.get_label() == "Back",
        )
        check(
            "scrolling form", any(isinstance(w, Gtk.ScrolledWindow) for w in walk(page))
        )
        check("visible 1:1 default", page.get_values() == {"aspect": "1:1"})
        check(
            "aspect controls shown, box controls hidden",
            page.rows["aspect"].get_visible() and not page.rows["width"].get_visible(),
        )
        page.set_value("crop_mode", "box")
        page.set_value("width", "not a number")
        page.set_value("height", "40")
        check("invalid submit blocked", page.submit() is False and applied == [])
        check(
            "validation error visible",
            page.error_label.get_visible() and bool(page.error_label.get_text()),
        )
        check("error CSS class", page.error_label.has_css_class("kumquat-option-error"))
        page.set_value("width", "30")
        page.set_value("x", "10")
        page.set_value("y", "20")
        check("editing clears error", not page.error_label.get_visible())
        check(
            "coordinate controls shown",
            page.rows["width"].get_visible() and not page.rows["aspect"].get_visible(),
        )
        check("valid submit returns true", page.submit() is True)
        check("only validated backend kwargs", applied == [{"box": (10, 20, 40, 60)}])
        page.back_button.emit("clicked")
        check("Back invokes callback", cancelled == [True])
        aspect_output = []
        aspect_page = tool_options.create_tool_options(
            "cropImage", [fixture], aspect_output.append, lambda: None
        )
        aspect_page.apply_button.emit("clicked")
        check("Apply button submits visible aspect", aspect_output == [{"aspect": "1:1"}])
        trim_outputs = []
        trim_page = tool_options.create_tool_options(
            "trimAudio", [fixture], trim_outputs.append, lambda: None
        )
        trim_page.apply_button.emit("clicked")
        check(
            "Apply cannot silently choose trim end",
            not trim_outputs and trim_page.error_label.get_visible(),
        )
        trim_page.set_value("end", "2.5")
        trim_page.controls["end"].emit("activate")
        check("Enter submits entry values", trim_outputs == [{"start": 0.0, "end": 2.5}])

        cases = [
            (
                "annotateImage",
                {
                    "text": "Synthetic note",
                    "x": "1",
                    "y": "2",
                    "font_size": "24",
                    "color": "#ff0000",
                },
                {
                    "text": "Synthetic note",
                    "xy": (1, 2),
                    "font_size": 24,
                    "color": "#ff0000",
                },
            ),
            (
                "redactImage",
                {"x": "2", "y": "4", "width": "10", "height": "12"},
                {"boxes": [(2, 4, 12, 16)]},
            ),
            (
                "redactVideo",
                {"x": "2", "y": "4", "width": "10", "height": "12"},
                {"boxes": [(2, 4, 12, 16)]},
            ),
            (
                "editImage",
                {"brightness": "1.2", "rotate": "-90"},
                {"brightness": 1.2, "contrast": 1.0, "saturation": 1.0, "rotate": -90.0},
            ),
            ("audioToVideo", {"size": "640x360"}, {"size": "640x360"}),
            ("audioChannels", {}, {}),
            (
                "cropVideo",
                {"x": "4", "y": "6", "width": "100", "height": "80"},
                {"box": (4, 6, 104, 86)},
            ),
            ("trimVideo", {"start": "1", "end": "2"}, {"start": 1.0, "end": 2.0}),
            ("trimAudio", {"start": "0.5", "end": "1.5"}, {"start": 0.5, "end": 1.5}),
            ("redactAudio", {"start": "0", "end": "1"}, {"start": 0.0, "end": 1.0}),
            ("changeVideoSpeed", {"factor": "0.5"}, {"factor": 0.5}),
            ("splitVideo", {"segment_time": "5"}, {"segment_time": 5.0}),
            ("videoSnapshots", {"at": "0.25"}, {"at": 0.25}),
            (
                "compress",
                {"quality": "80", "max_w": "640"},
                {"quality": 80, "max_w": 640},
            ),
            ("frameImage", {"mode": "blur"}, {"mode": "blur"}),
            ("createCollage", {"layout": "column"}, {"layout": "column"}),
            ("organizePDF", {"page_order": "3,1,2"}, {"spec": {"reorder": [2, 0, 1]}}),
            (
                "move",
                {"destination": str(root / "Destination")},
                {"destination": str(root / "Destination")},
            ),
        ]
        for tool_id, raw, expected in cases:
            outputs = []
            current = tool_options.create_tool_options(
                tool_id, [fixture], outputs.append, lambda: None
            )
            window.set_child(current)
            for name, value in raw.items():
                current.set_value(name, value)
            pump()
            check(
                f"{tool_id} valid submission", current.submit() and outputs == [expected]
            )
        check("move does not create destination", not (root / "Destination").exists())
        empty_edit_outputs = []
        edit_page = tool_options.create_tool_options(
            "editImage", [fixture], empty_edit_outputs.append, lambda: None
        )
        check(
            "unchanged edit cannot produce no-op output",
            not edit_page.submit()
            and not empty_edit_outputs
            and edit_page.error_label.get_visible(),
        )
        empty_annotation_outputs = []
        annotation_page = tool_options.create_tool_options(
            "annotateImage", [fixture], empty_annotation_outputs.append, lambda: None
        )
        check(
            "blank annotation cannot produce no-op output",
            not annotation_page.submit() and not empty_annotation_outputs,
        )
        target_outputs = []
        target_page = tool_options.create_tool_options(
            "compress", [fixture], target_outputs.append, lambda: None
        )
        target_page.set_value("max_bytes", "5000")
        check(
            "explicit compression target",
            target_page.submit()
            and target_outputs == [{"quality": 75, "max_w": 0, "max_bytes": 5000}],
        )
        invalid_move_outputs = []
        move_page = tool_options.create_tool_options(
            "move", [fixture], invalid_move_outputs.append, lambda: None
        )
        move_page.apply_button.emit("clicked")
        check(
            "move requires destination",
            not invalid_move_outputs and move_page.error_label.get_visible(),
        )
        for tool_id, schema in tool_options.SCHEMAS.items():
            if not schema.unavailable:
                continue
            outputs = []
            unavailable = tool_options.create_tool_options(
                tool_id, [fixture], outputs.append, lambda: None
            )
            check(
                f"{tool_id} truthfully unavailable",
                not unavailable.apply_button.get_sensitive()
                and not unavailable.submit()
                and not outputs
                and "unavailable" in unavailable.error_label.get_text(),
            )

        # The widget just submits kwargs. Processing belongs in the caller's worker.
        main_thread = threading.get_ident()
        done = threading.Event()
        release = threading.Event()
        thread_ids = []
        with ThreadPoolExecutor(max_workers=1) as executor:

            def worker(kwargs):
                thread_ids.append(threading.get_ident())
                release.wait(timeout=2)
                done.set()

            def queue_worker(kwargs):
                executor.submit(worker, kwargs)

            asynchronous = tool_options.create_tool_options(
                "changeVideoSpeed", [fixture], queue_worker, lambda: None
            )
            window.set_child(asynchronous)
            check(
                "submit schedules worker and returns",
                asynchronous.submit() and not done.is_set(),
            )
            heartbeat = []
            GLib.idle_add(lambda: heartbeat.append(True) and False)
            pump()
            check("GTK remains responsive while worker blocked", heartbeat == [True])
            release.set()
            check(
                "processing delegated off GTK thread",
                done.wait(timeout=2) and thread_ids and thread_ids[0] != main_thread,
            )
        check(
            "no processing backend imported",
            "kumquat.apply" not in sys.modules
            and "kumquat.tools_images" not in sys.modules,
        )
        check("fixture untouched", fixture.read_bytes() == original)
    finally:
        window.destroy()
        fixture.unlink()
        root.rmdir()
    passed = sum(RESULTS)
    print(f"{passed}/{len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)

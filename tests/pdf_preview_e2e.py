"""Real GTK proof of the Organize PDF page strip (synthetic PDF, no desktop access).

Opens Organize PDF in the real wheel window for a 3-page PDF whose pages are
numbered, then checks the thumbnails, the live reorder, the incomplete-order
message, and finally applies the order and reads the saved PDF back.

Run: PYTHONPATH=src /usr/bin/python3 tests/pdf_preview_e2e.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    import fitz
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk

    from kumquat.gui import wheel

    wheel._init_layer_shell = lambda _win: None
    checks: list[bool] = []

    def check(name, condition):
        checks.append(bool(condition))
        print(f"{'PASS' if condition else 'FAIL'}: {name}", flush=True)

    def pump_until(predicate, timeout=15.0):
        until = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def labels(page):
        """The page numbers under the thumbnails, left to right."""
        out = []
        cell = page.pdf_strip.get_first_child()
        while cell is not None:
            out.append(cell.get_last_child().get_label())
            cell = cell.get_next_sibling()
        return out

    app = Gtk.Application(
        application_id="dev.kumquat.pdfproof", flags=Gio.ApplicationFlags.NON_UNIQUE
    )
    app.register(None)
    with tempfile.TemporaryDirectory(prefix="kumquat-pdf-proof-") as directory:
        root = Path(directory)
        src = root / "Three pages.pdf"
        doc = fitz.open()
        for number in (1, 2, 3):
            page = doc.new_page(width=300, height=400)
            page.insert_text((40, 160), f"PAGE{number}", fontsize=60)
        doc.save(src)
        doc.close()
        before = hashlib.sha256(src.read_bytes()).hexdigest()

        window = wheel.WheelWindow(app, [str(src)])
        window.present()
        pump_until(lambda: window.win.get_mapped())
        try:
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            check("Organize PDF is offered for a PDF", "organizePDF" in ids)
            window.listbox.select_row(
                window.listbox.get_row_at_index(ids.index("organizePDF"))
            )
            window.apply_selected()
            page = window.options_page
            check(
                "the page opens in the same window",
                window.stack.get_visible_child_name() == "options",
            )
            check(
                "a thumbnail strip is shown", getattr(page, "pdf_strip", None) is not None
            )
            check("one thumbnail per page, in order", labels(page) == ["1", "2", "3"])
            check(
                "the order field is pre-filled with every page",
                page.controls["page_order"].get_text() == "1, 2, 3",
            )
            check(
                "thumbnails are real, different pictures",
                len({page.pdf_textures[i].get_width() for i in range(3)}) == 1
                and len(page.pdf_textures) == 3,
            )

            page.set_value("page_order", "3, 1, 2")
            check(
                "typing a new order reorders the thumbnails live",
                labels(page) == ["3", "1", "2"],
            )
            first = page.pdf_strip.get_first_child().get_first_child()
            check(
                "the first thumbnail is page 3's picture",
                first.get_paintable() is page.pdf_textures[2],
            )

            page.set_value("page_order", "3, 1")
            check(
                "an incomplete order keeps the current preview and says why",
                labels(page) == ["1", "2", "3"]
                and page.pdf_note.get_visible()
                and "every page once" in page.pdf_note.get_text(),
            )
            check(
                "Apply refuses an incomplete order",
                not page.submit()
                and "every page exactly once" in page.error_label.get_text(),
            )

            page.set_value("page_order", "3, 1, 2")
            check("a complete order hides the warning", not page.pdf_note.get_visible())
            check("Apply starts the job", page.submit() and window.busy)
            check("job finishes", pump_until(lambda: not window.busy))
            outputs = [p for p in root.glob("*.pdf") if p != src]
            check(
                "a new PDF was written beside the original",
                len(outputs) == 1 and window.status.get_text().startswith("Saved "),
            )
            if outputs:
                with fitz.open(outputs[0]) as out:
                    texts = [out[i].get_text().strip() for i in range(out.page_count)]
                check(
                    "saved pages are in the previewed order",
                    texts == ["PAGE3", "PAGE1", "PAGE2"],
                )
            check(
                "original PDF untouched",
                hashlib.sha256(src.read_bytes()).hexdigest() == before,
            )
            window.show_wheel()

            other = root / "Other.pdf"
            other.write_bytes(src.read_bytes())
            window.adopt([str(src), str(other)])
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            if "organizePDF" in ids:
                window.listbox.select_row(
                    window.listbox.get_row_at_index(ids.index("organizePDF"))
                )
                window.apply_selected()
                check(
                    "several PDFs: no strip, with an explanation",
                    "exactly one PDF" in window.options_page.pdf_note.get_text(),
                )
                window.show_wheel()

            broken = root / "broken.pdf"
            broken.write_bytes(b"%PDF-nonsense")
            window.adopt([str(broken)])
            window.set_mode(1)
            ids = [item[0] for item in window.current_items()]
            window.listbox.select_row(
                window.listbox.get_row_at_index(ids.index("organizePDF"))
            )
            window.apply_selected()
            check(
                "an unreadable PDF degrades to a message, not a crash",
                "unavailable" in window.options_page.pdf_note.get_text(),
            )
        finally:
            window.win.destroy()
            pump_until(lambda: not app.get_windows())
    print(f"{sum(checks)}/{len(checks)} checks passed", flush=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

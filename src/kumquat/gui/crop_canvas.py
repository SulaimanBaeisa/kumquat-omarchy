"""GTK4 widget: show a picture and let the user drag a crop rectangle on it.

All maths lives in `crop_geometry`; this module only draws and turns pointer and
key events into calls on it. Importing it imports no GTK; the widget class is
defined on first use (like `tool_options`). Selections are measured on the
image's *full* pixel grid, while the picture drawn may be a smaller preview.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from .crop_geometry import (
    MIN_SIDE,
    Rect,
    View,
    apply_ratio,
    centered_rect,
    fit_view,
    hit_test,
    move_rect,
    new_rect,
    resize_rect,
)

MIN_HEIGHT = 240  # px; the popup is small, so the canvas shares it with the form
PAD = 8.0  # px of breathing room around the picture
HANDLE_PX = 9.0  # drawn handle square
NUDGE_DIVISOR = 200  # arrow key moves 1/200th of the width; Shift moves 10x
DIM_ALPHA = 0.55
CURSORS = {
    "nw": "nwse-resize",
    "se": "nwse-resize",
    "ne": "nesw-resize",
    "sw": "nesw-resize",
    "n": "ns-resize",
    "s": "ns-resize",
    "e": "ew-resize",
    "w": "ew-resize",
    "move": "move",
    None: "crosshair",
}


@lru_cache(maxsize=1)
def _canvas_type() -> type:
    """Define the real `Gtk.DrawingArea` subtype once, when the GUI is opened."""
    import cairo
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

    def to_pixbuf(image: Any) -> tuple[Any, Any]:
        """A PIL RGB/RGBA image as a `GdkPixbuf` (plus the bytes it must outlive)."""
        has_alpha = image.mode == "RGBA"
        data = GLib.Bytes.new(image.tobytes())
        channels = 4 if has_alpha else 3
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            data,
            GdkPixbuf.Colorspace.RGB,
            has_alpha,
            8,
            image.width,
            image.height,
            image.width * channels,
        )
        return pixbuf, data

    class CropCanvas(Gtk.DrawingArea):
        """Drag to draw a box; drag its handles or inside it to resize or move."""

        def __init__(
            self,
            preview: Any,
            full_size: tuple[int, int],
            on_change: Callable[[Rect], None] | None = None,
        ) -> None:
            super().__init__()
            self.full_size = full_size
            self.on_change = on_change
            self.ratio: float | None = None
            self.selection = centered_rect(full_size, None)
            self._pixbuf, self._pixbuf_bytes = to_pixbuf(preview)
            self._preview_scale = preview.width / full_size[0]
            self._drag: (
                tuple[str, Rect, tuple[float, float], tuple[float, float]] | None
            ) = None
            self.set_hexpand(True)
            self.set_vexpand(True)
            self.set_size_request(-1, MIN_HEIGHT)
            self.set_focusable(True)
            self.set_draw_func(self._draw)
            self.add_css_class("kumquat-crop-canvas")
            self.update_property(
                [Gtk.AccessibleProperty.LABEL],
                ["Crop area: drag on the picture to choose the part to keep"],
            )
            drag = Gtk.GestureDrag()
            drag.connect("drag-begin", lambda _g, x, y: self.begin_drag(x, y))
            drag.connect("drag-update", lambda _g, dx, dy: self.update_drag(dx, dy))
            drag.connect("drag-end", lambda _g, _dx, _dy: self.end_drag())
            self.add_controller(drag)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda _c, x, y: self._update_cursor(x, y))
            self.add_controller(motion)
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self._on_key)
            self.add_controller(keys)

        # -- public API (also what the gestures call) --

        def box(self) -> tuple[int, int, int, int]:
            """The selection as an integer ``(left, top, right, bottom)`` box."""
            return self.selection.to_box()

        def set_ratio(self, ratio: float | None) -> None:
            """Lock the box to ``ratio`` (width/height) or free it with ``None``."""
            self.ratio = ratio
            self.selection = apply_ratio(self.selection, ratio, self.full_size)
            self._changed()

        def set_selection(self, rect: Rect) -> None:
            """Replace the selection, clamped inside the picture."""
            w = min(max(rect.w, MIN_SIDE), self.full_size[0])
            h = min(max(rect.h, MIN_SIDE), self.full_size[1])
            x = min(max(rect.x, 0), self.full_size[0] - w)
            y = min(max(rect.y, 0), self.full_size[1] - h)
            self.selection = Rect(x, y, w, h)
            self._changed()

        def view(self) -> View:
            """The current image -> widget mapping (needs an allocated size)."""
            inner = (
                max(self.get_width() - 2 * PAD, 1),
                max(self.get_height() - 2 * PAD, 1),
            )
            fitted = fit_view(self.full_size, inner)
            return View(fitted.scale, fitted.ox + PAD, fitted.oy + PAD)

        def begin_drag(self, x: float, y: float) -> None:
            self.grab_focus()
            view = self.view()
            mode = hit_test(self.selection, view, x, y) or "new"
            anchor = view.to_image(x, y)
            self._drag = (mode, self.selection, anchor, (x, y))

        def update_drag(self, dx: float, dy: float) -> None:
            if self._drag is None:
                return
            mode, start, anchor, origin = self._drag
            view = self.view()
            point = view.to_image(origin[0] + dx, origin[1] + dy)
            if mode == "new":
                self.selection = new_rect(anchor, point, self.full_size, self.ratio)
            elif mode == "move":
                self.selection = move_rect(
                    start, dx / view.scale, dy / view.scale, self.full_size
                )
            else:
                self.selection = resize_rect(
                    start, mode, point, self.full_size, self.ratio
                )
            self._changed()

        def end_drag(self) -> None:
            if self._drag is None:
                return
            start = self._drag[1]
            self._drag = None
            low = min(MIN_SIDE, *self.full_size)
            if self.selection.w < low or self.selection.h < low:
                self.selection = start  # a click, not a box: keep what was there
                self._changed()

        def nudge(self, dx: float, dy: float) -> None:
            """Move the box by image pixels (keyboard)."""
            self.selection = move_rect(self.selection, dx, dy, self.full_size)
            self._changed()

        # -- internals --

        def _changed(self) -> None:
            self.queue_draw()
            if self.on_change is not None:
                self.on_change(self.selection)

        def _update_cursor(self, x: float, y: float) -> None:
            if self._drag is not None:
                return
            self.set_cursor_from_name(
                CURSORS[hit_test(self.selection, self.view(), x, y)]
            )

        def _on_key(self, _ctl: Any, keyval: int, _code: int, state: Any) -> bool:
            step = max(1.0, self.full_size[0] / NUDGE_DIVISOR)
            if state & Gdk.ModifierType.SHIFT_MASK:
                step *= 10
            moves = {
                Gdk.KEY_Left: (-step, 0),
                Gdk.KEY_Right: (step, 0),
                Gdk.KEY_Up: (0, -step),
                Gdk.KEY_Down: (0, step),
            }
            if keyval not in moves:
                return False
            self.nudge(*moves[keyval])
            return True

        def _draw(self, _area: Any, cr: Any, _width: int, _height: int) -> None:
            view = self.view()
            fw, fh = self.full_size
            scale = view.scale
            cr.save()
            cr.translate(view.ox, view.oy)
            cr.scale(scale / self._preview_scale, scale / self._preview_scale)
            Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            cr.paint()
            cr.restore()
            sx, sy = view.to_view(self.selection.x, self.selection.y)
            sw, sh = self.selection.w * scale, self.selection.h * scale
            # Dim everything outside the box: image rectangle minus the box.
            cr.set_source_rgba(0, 0, 0, DIM_ALPHA)
            cr.rectangle(view.ox, view.oy, fw * scale, fh * scale)
            cr.rectangle(sx, sy, sw, sh)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            self._draw_guides(cr, sx, sy, sw, sh)

        def _draw_guides(
            self, cr: Any, sx: float, sy: float, sw: float, sh: float
        ) -> None:
            cr.set_line_width(1.0)
            cr.set_source_rgba(1, 1, 1, 0.35)  # rule-of-thirds guides
            for i in (1, 2):
                cr.move_to(sx + sw * i / 3, sy)
                cr.line_to(sx + sw * i / 3, sy + sh)
                cr.move_to(sx, sy + sh * i / 3)
                cr.line_to(sx + sw, sy + sh * i / 3)
            cr.stroke()
            cr.set_line_width(2.0)
            cr.set_source_rgba(1, 1, 1, 1)
            cr.rectangle(sx, sy, sw, sh)
            cr.stroke()
            half = HANDLE_PX / 2
            xs = (sx, sx + sw / 2, sx + sw)
            ys = (sy, sy + sh / 2, sy + sh)
            for ix, hx in enumerate(xs):
                for iy, hy in enumerate(ys):
                    if ix == 1 and iy == 1:
                        continue
                    cr.rectangle(hx - half, hy - half, HANDLE_PX, HANDLE_PX)
                    cr.set_source_rgba(1, 1, 1, 1)
                    cr.fill_preserve()
                    cr.set_source_rgba(0, 0, 0, 0.8)
                    cr.set_line_width(1.0)
                    cr.stroke()

    return CropCanvas


def create_crop_canvas(
    preview: Any,
    full_size: tuple[int, int],
    on_change: Callable[[Rect], None] | None = None,
) -> Any:
    """Return a `CropCanvas` showing ``preview``, a PIL image of the full picture."""
    return _canvas_type()(preview, full_size, on_change)

"""Pure drag/resize maths for the draw-on-image crop; imports no GTK.

Selections live in *image pixels* with a top-left origin, as floats while the
pointer is moving; `Rect.to_box` rounds them to the exclusive integer
``(left, top, right, bottom)`` box the crop backend expects. A `View` maps
between image pixels and widget pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_SIDE = 8.0  # smallest selection side, in image pixels
GRAB_PX = 12.0  # pointer slop around handles/edges, in widget pixels
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
RATIOS = ("free", "1:1", "4:3", "3:2", "16:9", "9:16")


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle: top-left ``x, y`` plus ``w, h``."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def to_box(self) -> tuple[int, int, int, int]:
        """Integer ``(left, top, right, bottom)``, right/bottom exclusive."""
        left, top = round(self.x), round(self.y)
        right, bottom = round(self.right), round(self.bottom)
        return left, top, max(right, left + 1), max(bottom, top + 1)


@dataclass(frozen=True)
class View:
    """Image pixels -> widget pixels: ``widget = origin + image * scale``."""

    scale: float
    ox: float
    oy: float

    def to_image(self, px: float, py: float) -> tuple[float, float]:
        return (px - self.ox) / self.scale, (py - self.oy) / self.scale

    def to_view(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale


def fit_view(image_size: tuple[int, int], view_size: tuple[float, float]) -> View:
    """Scale the image to fit entirely inside the widget, centred."""
    iw, ih = image_size
    vw, vh = max(view_size[0], 1.0), max(view_size[1], 1.0)
    scale = min(vw / iw, vh / ih)
    return View(scale, (vw - iw * scale) / 2, (vh - ih * scale) / 2)


def parse_ratio(name: str) -> float | None:
    """``"16:9"`` -> width/height; ``"free"`` -> no lock."""
    if name == "free":
        return None
    try:
        a, b = (float(part) for part in name.split(":"))
    except ValueError:
        raise ValueError(f"bad aspect ratio: {name!r}") from None
    if a <= 0 or b <= 0:
        raise ValueError(f"bad aspect ratio: {name!r}")
    return a / b


def _min_side(bounds: tuple[int, int]) -> float:
    return min(MIN_SIDE, bounds[0], bounds[1])


def _fit_ratio(w: float, h: float, ratio: float) -> tuple[float, float]:
    """Shrink ``w x h`` (never grow) to the exact ``ratio``."""
    if w / h > ratio:
        return h * ratio, h
    return w, w / ratio


def centered_rect(
    bounds: tuple[int, int], ratio: float | None, fraction: float = 0.8
) -> Rect:
    """The starting selection: ``fraction`` of the image, centred."""
    bw, bh = bounds
    w, h = bw * fraction, bh * fraction
    if ratio is not None:
        w, h = _fit_ratio(w, h, ratio)
    return Rect((bw - w) / 2, (bh - h) / 2, w, h)


def apply_ratio(rect: Rect, ratio: float | None, bounds: tuple[int, int]) -> Rect:
    """Re-shape ``rect`` to ``ratio`` around its centre, staying inside bounds."""
    if ratio is None:
        return rect
    cx, cy = rect.x + rect.w / 2, rect.y + rect.h / 2
    max_w = 2 * min(cx, bounds[0] - cx)
    max_h = 2 * min(cy, bounds[1] - cy)
    w, h = _fit_ratio(min(rect.w, max_w), min(rect.h, max_h), ratio)
    if w <= 0 or h <= 0:  # centre hugs an edge: fall back to a fresh selection
        return centered_rect(bounds, ratio)
    return Rect(cx - w / 2, cy - h / 2, w, h)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def new_rect(
    anchor: tuple[float, float],
    point: tuple[float, float],
    bounds: tuple[int, int],
    ratio: float | None,
) -> Rect:
    """The rectangle dragged out from ``anchor`` to ``point``."""
    bw, bh = bounds
    ax, ay = _clamp(anchor[0], 0, bw), _clamp(anchor[1], 0, bh)
    px, py = _clamp(point[0], 0, bw), _clamp(point[1], 0, bh)
    sx = 1 if px >= ax else -1
    sy = 1 if py >= ay else -1
    w, h = abs(px - ax), abs(py - ay)
    if ratio is not None and w > 0 and h > 0:
        w, h = _fit_ratio(w, h, ratio)
    x = ax if sx > 0 else ax - w
    y = ay if sy > 0 else ay - h
    return Rect(x, y, w, h)


def move_rect(rect: Rect, dx: float, dy: float, bounds: tuple[int, int]) -> Rect:
    """Shift ``rect`` by ``dx, dy`` without leaving the image."""
    x = _clamp(rect.x + dx, 0, bounds[0] - rect.w)
    y = _clamp(rect.y + dy, 0, bounds[1] - rect.h)
    return Rect(x, y, rect.w, rect.h)


def resize_rect(
    rect: Rect,
    handle: str,
    point: tuple[float, float],
    bounds: tuple[int, int],
    ratio: float | None,
) -> Rect:
    """Drag ``handle`` of ``rect`` to ``point``; the opposite side stays put."""
    if handle not in HANDLES:
        raise ValueError(f"unknown handle {handle!r}")
    low = _min_side(bounds)
    if ratio is None:
        return _resize_free(rect, handle, point, bounds, low)
    if len(handle) == 2:
        return _resize_corner_ratio(rect, handle, point, bounds, low, ratio)
    return _resize_edge_ratio(rect, handle, point, bounds, low, ratio)


def _resize_free(
    rect: Rect,
    handle: str,
    point: tuple[float, float],
    bounds: tuple[int, int],
    low: float,
) -> Rect:
    left, top, right, bottom = rect.x, rect.y, rect.right, rect.bottom
    px, py = point
    if "w" in handle:
        left = _clamp(px, 0, right - low)
    if "e" in handle:
        right = _clamp(px, left + low, bounds[0])
    if "n" in handle:
        top = _clamp(py, 0, bottom - low)
    if "s" in handle:
        bottom = _clamp(py, top + low, bounds[1])
    return Rect(left, top, right - left, bottom - top)


def _resize_corner_ratio(
    rect: Rect,
    handle: str,
    point: tuple[float, float],
    bounds: tuple[int, int],
    low: float,
    ratio: float,
) -> Rect:
    east, south = "e" in handle, "s" in handle
    ax = rect.x if east else rect.right  # the fixed, opposite corner
    ay = rect.y if south else rect.bottom
    max_w = bounds[0] - ax if east else ax
    max_h = bounds[1] - ay if south else ay
    min_w = max(low, low * ratio)
    min_h = min_w / ratio
    w = _clamp(((point[0] - ax) if east else (ax - point[0])), min_w, max_w)
    h = _clamp(((point[1] - ay) if south else (ay - point[1])), min_h, max_h)
    w, h = _fit_ratio(w, h, ratio)
    return Rect(ax if east else ax - w, ay if south else ay - h, w, h)


def _resize_edge_ratio(
    rect: Rect,
    handle: str,
    point: tuple[float, float],
    bounds: tuple[int, int],
    low: float,
    ratio: float,
) -> Rect:
    if handle in ("e", "w"):
        cy = rect.y + rect.h / 2
        fixed = rect.x if handle == "e" else rect.right
        room = bounds[0] - fixed if handle == "e" else fixed
        room = min(room, ratio * 2 * min(cy, bounds[1] - cy))
        raw = (point[0] - fixed) if handle == "e" else (fixed - point[0])
        w = _clamp(raw, max(low, low * ratio), max(room, low))
        h = w / ratio
        return Rect(fixed if handle == "e" else fixed - w, cy - h / 2, w, h)
    cx = rect.x + rect.w / 2
    fixed = rect.y if handle == "s" else rect.bottom
    room = bounds[1] - fixed if handle == "s" else fixed
    room = min(room, 2 * min(cx, bounds[0] - cx) / ratio)
    raw = (point[1] - fixed) if handle == "s" else (fixed - point[1])
    h = _clamp(raw, max(low, low / ratio), max(room, low))
    w = h * ratio
    return Rect(cx - w / 2, fixed if handle == "s" else fixed - h, w, h)


def hit_test(
    rect: Rect, view: View, px: float, py: float, grab: float = GRAB_PX
) -> str | None:
    """Which handle (or ``"move"``) is under widget point ``px, py``, if any."""
    left, top = view.to_view(rect.x, rect.y)
    right, bottom = view.to_view(rect.right, rect.bottom)
    near_left, near_right = abs(px - left) <= grab, abs(px - right) <= grab
    near_top, near_bottom = abs(py - top) <= grab, abs(py - bottom) <= grab
    within_x = left - grab <= px <= right + grab
    within_y = top - grab <= py <= bottom + grab
    horizontal = "w" if near_left else "e" if near_right else ""
    vertical = "n" if near_top else "s" if near_bottom else ""
    if horizontal and vertical:
        return vertical + horizontal
    # Edge handles sit on the edge's span, so check the span exactly.
    if vertical and left <= px <= right:
        return vertical
    if horizontal and top <= py <= bottom:
        return horizontal
    if left <= px <= right and top <= py <= bottom:
        return "move"
    if horizontal and within_y or vertical and within_x:
        return horizontal or vertical
    return None

"""Pure drag/resize maths behind the draw-on-image crop; no GTK involved."""

import pytest

from kumquat.gui.crop_geometry import (
    Rect,
    View,
    apply_ratio,
    centered_rect,
    fit_view,
    hit_test,
    move_rect,
    new_rect,
    parse_ratio,
    resize_rect,
)

BOUNDS = (1000, 600)


def test_fit_view_letterboxes_a_wide_image_inside_the_widget():
    view = fit_view((1000, 500), (400, 400))
    assert view.scale == pytest.approx(0.4)
    assert (view.ox, view.oy) == pytest.approx((0, 100))


def test_view_round_trip_between_widget_and_image_pixels():
    view = View(scale=0.5, ox=10, oy=20)
    assert view.to_image(60, 70) == (100, 100)
    assert view.to_view(100, 100) == (60, 70)


def test_fit_view_survives_zero_sized_widget():
    assert fit_view((100, 100), (0, 0)).scale > 0


def test_parse_ratio_names():
    assert parse_ratio("free") is None
    assert parse_ratio("16:9") == pytest.approx(16 / 9)
    assert parse_ratio("9:16") == pytest.approx(9 / 16)
    with pytest.raises(ValueError):
        parse_ratio("0:5")


def test_centered_rect_is_inside_and_centred():
    rect = centered_rect(BOUNDS, None, 0.8)
    assert (rect.w, rect.h) == pytest.approx((800, 480))
    assert (rect.x, rect.y) == pytest.approx((100, 60))


def test_centered_rect_honours_ratio_inside_bounds():
    rect = centered_rect(BOUNDS, 1.0, 0.8)
    assert rect.w == pytest.approx(rect.h)
    assert rect.right <= 1000 and rect.bottom <= 600


def test_rect_to_box_rounds_to_exclusive_integer_box():
    assert Rect(10.4, 20.6, 100.2, 50.0).to_box() == (10, 21, 111, 71)


def test_new_rect_follows_pointer_in_any_direction_and_clamps():
    rect = new_rect((300, 300), (100, 100), BOUNDS, None)
    assert (rect.x, rect.y, rect.right, rect.bottom) == (100, 100, 300, 300)
    rect = new_rect((300, 300), (5000, -50), BOUNDS, None)
    assert (rect.right, rect.y) == (1000, 0)


def test_new_rect_keeps_ratio():
    rect = new_rect((100, 100), (500, 150), BOUNDS, 1.0)
    assert rect.w == pytest.approx(rect.h)
    assert rect.x == 100 and rect.y == 100
    assert rect.w <= 50 + 1e-6  # shrinks inside the pointer rectangle


def test_new_rect_ratio_never_leaves_the_image():
    rect = new_rect((900, 500), (2000, 2000), BOUNDS, 16 / 9)
    assert rect.right <= 1000 + 1e-6 and rect.bottom <= 600 + 1e-6
    assert rect.w / rect.h == pytest.approx(16 / 9)


def test_move_rect_clamps_at_every_edge():
    rect = Rect(100, 100, 200, 100)
    assert move_rect(rect, 5000, 5000, BOUNDS) == Rect(800, 500, 200, 100)
    assert move_rect(rect, -5000, -5000, BOUNDS) == Rect(0, 0, 200, 100)
    assert move_rect(rect, 10, -20, BOUNDS) == Rect(110, 80, 200, 100)


@pytest.mark.parametrize(
    "handle,point,expected",
    [
        ("e", (700, 999), (100, 100, 700, 300)),
        ("w", (50, 999), (50, 100, 300, 300)),
        ("s", (999, 500), (100, 100, 300, 500)),
        ("n", (999, 20), (100, 20, 300, 300)),
        ("se", (400, 450), (100, 100, 400, 450)),
        ("nw", (10, 20), (10, 20, 300, 300)),
        ("ne", (350, 30), (100, 30, 350, 300)),
        ("sw", (40, 380), (40, 100, 300, 380)),
    ],
)
def test_resize_moves_only_the_dragged_edges(handle, point, expected):
    rect = Rect(100, 100, 200, 200)
    out = resize_rect(rect, handle, point, BOUNDS, None)
    assert (out.x, out.y, out.right, out.bottom) == expected


def test_resize_cannot_invert_or_vanish():
    rect = Rect(100, 100, 200, 200)
    out = resize_rect(rect, "e", (0, 0), BOUNDS, None)
    assert out.x == 100 and out.w >= 8
    out = resize_rect(rect, "n", (0, 5000), BOUNDS, None)
    assert out.bottom == 300 and out.h >= 8


def test_resize_clamps_to_image():
    rect = Rect(100, 100, 200, 200)
    out = resize_rect(rect, "se", (9999, 9999), BOUNDS, None)
    assert (out.right, out.bottom) == (1000, 600)


def test_corner_resize_with_ratio_keeps_opposite_corner_fixed():
    rect = Rect(100, 100, 200, 200)
    out = resize_rect(rect, "se", (500, 800), BOUNDS, 1.0)
    assert (out.x, out.y) == (100, 100)
    assert out.w == pytest.approx(out.h)
    assert out.bottom <= 600 + 1e-6


def test_edge_resize_with_ratio_stays_centred_and_inside():
    rect = Rect(400, 200, 200, 200)
    out = resize_rect(rect, "e", (900, 0), BOUNDS, 1.0)
    assert out.w == pytest.approx(out.h)
    assert out.y + out.h / 2 == pytest.approx(300)
    assert out.y >= -1e-6 and out.bottom <= 600 + 1e-6
    assert out.x == pytest.approx(400)


def test_apply_ratio_keeps_centre_and_fits():
    rect = Rect(100, 100, 400, 100)
    out = apply_ratio(rect, 1.0, BOUNDS)
    assert out.w == pytest.approx(out.h)
    cx, cy = rect.x + rect.w / 2, rect.y + rect.h / 2
    assert out.x + out.w / 2 == pytest.approx(cx)
    assert out.y + out.h / 2 == pytest.approx(cy)


def test_apply_ratio_none_returns_same_rect():
    rect = Rect(1, 2, 30, 40)
    assert apply_ratio(rect, None, BOUNDS) == rect


def test_hit_test_finds_handles_edges_inside_and_outside():
    view = View(scale=1.0, ox=0, oy=0)
    rect = Rect(100, 100, 200, 200)
    assert hit_test(rect, view, 100, 100) == "nw"
    assert hit_test(rect, view, 300, 300) == "se"
    assert hit_test(rect, view, 300, 100) == "ne"
    assert hit_test(rect, view, 100, 300) == "sw"
    assert hit_test(rect, view, 200, 100) == "n"
    assert hit_test(rect, view, 300, 200) == "e"
    assert hit_test(rect, view, 200, 300) == "s"
    assert hit_test(rect, view, 100, 200) == "w"
    assert hit_test(rect, view, 200, 200) == "move"
    assert hit_test(rect, view, 600, 600) is None


def test_hit_test_uses_widget_pixels_not_image_pixels():
    view = View(scale=0.1, ox=0, oy=0)  # a 200px image box is 20 widget px
    rect = Rect(100, 100, 2000, 2000)
    assert hit_test(rect, view, 10, 10) == "nw"
    assert hit_test(rect, view, 105, 105) == "move"


def test_tiny_selection_prefers_corner_over_move():
    view = View(scale=1.0, ox=0, oy=0)
    rect = Rect(100, 100, 10, 10)
    assert hit_test(rect, view, 102, 102) == "nw"

"""The crop preview and the crop backend must share one upright pixel grid."""

import pytest
from PIL import Image

from kumquat.apply import apply_tool
from kumquat.preview import load_preview


def _rotated_photo(path, size=(80, 48), orientation=6):
    """A JPEG whose pixels are landscape but whose EXIF says 'rotate 90'."""
    exif = Image.Exif()
    exif[274] = orientation
    image = Image.new("RGB", size, "white")
    image.paste("red", (0, 0, size[0] // 2, size[1] // 2))
    image.save(path, exif=exif)
    return path


def test_preview_reports_upright_full_size_for_rotated_photo(tmp_path):
    photo = _rotated_photo(tmp_path / "phone.jpg")
    preview, full = load_preview(photo, max_side=1024)
    assert full == (48, 80)  # EXIF 6 swaps the sides
    assert preview.size == (48, 80)


def test_preview_downscales_but_keeps_true_full_size(tmp_path):
    big = tmp_path / "big.png"
    Image.new("RGB", (4000, 3000), "teal").save(big)
    preview, full = load_preview(big, max_side=1000)
    assert full == (4000, 3000)
    assert preview.size == (1000, 750)
    assert preview.mode in ("RGB", "RGBA")


def test_preview_keeps_transparency(tmp_path):
    path = tmp_path / "clear.png"
    Image.new("RGBA", (20, 10), (255, 0, 0, 0)).save(path)
    preview, _ = load_preview(path, max_side=64)
    assert preview.mode == "RGBA"
    assert preview.getpixel((1, 1))[3] == 0


def test_preview_rejects_unreadable_files(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        load_preview(path)
    with pytest.raises(FileNotFoundError):
        load_preview(tmp_path / "missing.png")


def test_crop_uses_the_same_upright_grid_as_the_preview(tmp_path):
    photo = _rotated_photo(tmp_path / "phone.jpg")
    preview, (width, height) = load_preview(photo)
    lossless = _rotated_photo(tmp_path / "phone.png")  # same tag, exact pixels
    # Only valid on the upright 48x80 grid; the raw 80x48 grid would reject it.
    out = apply_tool("cropImage", [photo], tmp_path, box=(0, 0, width // 2, height))
    with Image.open(out) as cropped:
        assert cropped.size == (24, 80)
    exact, _ = load_preview(lossless)
    full = apply_tool("cropImage", [lossless], tmp_path, box=(0, 0, width, height))
    with Image.open(full) as everything:
        assert list(everything.convert("RGB").getdata()) == list(
            exact.convert("RGB").getdata()
        ), "backend pixels differ from what the user saw in the preview"
    assert preview.size == (width, height)


def test_aspect_crop_is_computed_on_the_upright_image(tmp_path):
    photo = _rotated_photo(tmp_path / "phone.jpg")
    out = apply_tool("cropImage", [photo], tmp_path, aspect="1:1")
    with Image.open(out) as cropped:
        assert cropped.size == (48, 48)  # raw grid would also give 48; use 2:1 below
    out2 = apply_tool("cropImage", [photo], tmp_path, aspect="1:2")
    with Image.open(out2) as cropped:
        assert cropped.size == (40, 80)  # upright 48x80 -> trim sides to 1:2

"""Image conversions: registry routing + real conversions, originals untouched.

Tests needing an absent optional backend (pillow-heif, cairosvg) SKIP;
they never fail.
"""
import hashlib

import pytest
from PIL import Image

import kumquat.registry_data  # noqa: F401 -- registers all image rows
from kumquat.converters_images import BackendMissing, convert_image, to_png
from kumquat.registry import REGISTRY, options_for

IMAGE_ROWS = [c for c in REGISTRY if c.category == "images"]


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))
    except (RuntimeError, ImportError) as e:
        # Legacy guard: an absent optional backend surfacing as a plain
        # RuntimeError("backend missing: …") or raw ImportError also skips.
        if isinstance(e, ImportError) or "backend missing" in str(e):
            pytest.skip(f"optional backend absent: {e}")
        raise


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_source(path, fmt):
    """Create a tiny source image; skips when the backend is absent."""
    fmt = fmt.lower()
    if fmt == "svg":
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
            '<rect width="8" height="8" fill="red"/></svg>'
        )
        return
    if fmt in ("heic", "heif", "avif"):
        _or_skip(__import__("pillow_heif").register_heif_opener)
    pil_fmt = {
        "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
        "tiff": "TIFF", "tif": "TIFF", "bmp": "BMP",
        "heic": "HEIF", "heif": "HEIF", "avif": "AVIF",
    }[fmt]
    Image.new("RGB", (16, 16), "red").save(path, pil_fmt)


def _src_fmt(row_id):
    return row_id[len("image-"):].partition("-to-")[0]


def test_registry_routes_jpg_to_png():
    opts = options_for("a.jpg", "image/jpeg")
    assert len(opts) >= 6
    assert any(c.id == "image-jpg-to-png" for c in opts)


def test_registry_routes_svg_input():
    opts = options_for("a.svg", "image/svg+xml")
    assert len(opts) == 8  # svg is input-only: all image outputs
    assert all(c.id.startswith("image-svg-to-") for c in opts)


def test_jpg_converts_to_png(tmp_path):
    import magic

    src = tmp_path / "in.jpg"
    _make_source(src, "jpg")
    before = _sha(src)
    out = to_png(src, tmp_path / "out")
    assert out.exists() and out.suffix == ".png"
    assert magic.from_file(str(out), mime=True) == "image/png"
    with Image.open(out) as im:
        assert im.size == (16, 16)
    assert _sha(src) == before  # original untouched


@pytest.mark.parametrize("row_id", [c.id for c in IMAGE_ROWS])
def test_image_row_converts(tmp_path, row_id):
    import magic

    row = next(c for c in IMAGE_ROWS if c.id == row_id)
    ext = "." + _src_fmt(row_id)
    src = tmp_path / ("in" + ext)
    _or_skip(_make_source, src, _src_fmt(row_id))
    before = _sha(src)
    out = _or_skip(convert_image, src, row.output_ext, tmp_path / "out")
    assert out.exists() and out.suffix == row.output_ext
    assert magic.from_file(str(out), mime=True)
    assert _sha(src) == before  # original untouched

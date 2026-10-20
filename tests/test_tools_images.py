"""Image file tools (TDD): compress/strip-metadata/crop/pdf/collage/frame.

TDD record: this file was written FIRST against a nonexistent
`kumquat.tools_images` (RED: ModuleNotFoundError on collection),
then the module was implemented to make it GREEN.

Originals are never modified (sha-pinned in every behaviour test).
Optional backends raise BackendMissing only when genuinely unavailable.
Annotation/redaction/editing use explicit real pixel operations; absent user
choices are validation errors, not optional-backend skips.
"""
import hashlib
import random

import pytest
from PIL import Image

from kumquat.tools_images import (
    annotate_image,
    collage_name,
    compress_image,
    create_collage,
    crop_image,
    edit_image,
    frame_image,
    images_to_pdf,
    redact_image,
    strip_metadata,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _noise_jpg(path, size=(400, 400), quality=95, seed=42):
    """High-entropy JPEG: q95 source compresses smaller at q30."""
    w, h = size
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h))
    im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                for _ in range(w * h)])
    im.save(path, "JPEG", quality=quality)
    return path


def _flat(path, size=(200, 200), color="red", fmt="JPEG"):
    Image.new("RGB", size, color).save(path, fmt)
    return path


def _exif_jpg(path, size=(64, 64)):
    from PIL.Image import Exif

    ex = Exif()
    ex[0x013B] = "Test Artist"  # Artist tag
    Image.new("RGB", size, "blue").save(path, "JPEG", quality=90, exif=ex)
    with Image.open(path) as im:
        assert im.getexif().get(0x013B) == "Test Artist"  # fixture really tagged
    return path


# --- compress_image -------------------------------------------------------

def test_compress_shrinks_bytes_and_keeps_dims(tmp_path):
    src = _noise_jpg(tmp_path / "photo.jpg")
    before = _sha(src)
    out = compress_image(src, tmp_path / "out", quality=30)
    assert out.name == "photo-Compressed.jpg"
    assert out.stat().st_size < src.stat().st_size
    with Image.open(out) as im:
        assert im.size == (400, 400)
    assert _sha(src) == before  # original untouched


def test_compress_max_w_scales_down_only(tmp_path):
    src = _flat(tmp_path / "wide.jpg", size=(400, 300))
    before = _sha(src)
    out = compress_image(src, tmp_path / "out", max_w=100)
    with Image.open(out) as im:
        assert im.size == (100, 75)
    assert _sha(src) == before


def test_compress_max_w_leaves_small_images_alone(tmp_path):
    src = _flat(tmp_path / "small.jpg", size=(80, 60))
    out = compress_image(src, tmp_path / "out", max_w=100)
    with Image.open(out) as im:
        assert im.size == (80, 60)


# --- strip_metadata -------------------------------------------------------

def test_strip_metadata_drops_exif_without_exiftool(tmp_path):
    src = _exif_jpg(tmp_path / "tagged.jpg")
    before = _sha(src)
    out = strip_metadata(src, tmp_path / "out")
    assert out.name == "tagged-No Metadata.jpg"
    with Image.open(out) as im:
        assert not dict(im.getexif())  # fallback Pillow rewrite drops EXIF
        assert im.size == (64, 64)  # pixels survive
    assert _sha(src) == before


# --- crop_image -----------------------------------------------------------

def test_crop_box_exact_dims(tmp_path):
    src = _flat(tmp_path / "pic.png", size=(200, 200), fmt="PNG")
    before = _sha(src)
    out = crop_image(src, tmp_path / "out", box=(10, 20, 110, 120))
    assert out.name == "pic-Cropped.png"
    with Image.open(out) as im:
        assert im.size == (100, 100)
    assert _sha(src) == before


def test_crop_aspect_center_crops(tmp_path):
    src = _flat(tmp_path / "wide.jpg", size=(400, 300))
    out = crop_image(src, tmp_path / "out", aspect="16:9")
    with Image.open(out) as im:
        assert im.size == (400, 225)


def test_crop_rejects_bad_args(tmp_path):
    src = _flat(tmp_path / "pic.jpg")
    with pytest.raises(ValueError):
        crop_image(src, tmp_path / "o1")  # neither box nor aspect
    with pytest.raises(ValueError):
        crop_image(src, tmp_path / "o2", box=(0, 0, 10, 10), aspect="1:1")
    with pytest.raises(ValueError):
        crop_image(src, tmp_path / "o3", box=(0, 0, 500, 500))  # outside image
    with pytest.raises(ValueError):
        crop_image(src, tmp_path / "o4", aspect="bogus")


# --- images_to_pdf --------------------------------------------------------

def test_images_to_pdf_page_count_matches_inputs(tmp_path):
    import fitz

    srcs = [_flat(tmp_path / f"p{i}.jpg", size=(64, 64)) for i in range(3)]
    before = [_sha(p) for p in srcs]
    out = images_to_pdf(srcs, tmp_path / "out" / "album.pdf")
    assert out.suffix == ".pdf"
    with fitz.open(out) as doc:
        assert doc.page_count == 3
    assert [_sha(p) for p in srcs] == before


def test_images_to_pdf_directory_dest_uses_first_stem(tmp_path):
    srcs = [_flat(tmp_path / f"p{i}.jpg", size=(32, 32)) for i in range(2)]
    out = images_to_pdf(srcs, tmp_path / "out")
    assert out.name == "p0.pdf"


def test_images_to_pdf_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        images_to_pdf([], tmp_path / "out" / "x.pdf")


# --- create_collage -------------------------------------------------------

def test_collage_grid_dims(tmp_path):
    srcs = [_flat(tmp_path / f"c{i}.jpg", size=(300, 200)) for i in range(4)]
    before = [_sha(p) for p in srcs]
    out = create_collage(srcs, tmp_path / "out", layout="grid")
    assert out.name == "c0-Collage.jpg"
    with Image.open(out) as im:
        assert im.size == (2 * 256, 2 * 256)  # 2x2 of default 256px thumbs
    assert [_sha(p) for p in srcs] == before


def test_collage_row_and_column_dims(tmp_path):
    srcs = [_flat(tmp_path / f"r{i}.jpg", size=(100, 100)) for i in range(3)]
    row = create_collage(srcs, tmp_path / "row", layout="row", thumb=(64, 64))
    with Image.open(row) as im:
        assert im.size == (3 * 64, 64)
    col = create_collage(srcs, tmp_path / "col", layout="column", thumb=(64, 64))
    with Image.open(col) as im:
        assert im.size == (64, 3 * 64)


def test_collage_rejects_bad_input(tmp_path):
    with pytest.raises(ValueError):
        create_collage([], tmp_path / "out")
    src = _flat(tmp_path / "c.jpg")
    with pytest.raises(ValueError):
        create_collage([src], tmp_path / "out", layout="diagonal")


def test_collage_name_helper():
    assert collage_name("vacation") == "vacation-Collage.jpg"


# --- frame_image ----------------------------------------------------------

def test_frame_solid_padding_and_color(tmp_path):
    src = _flat(tmp_path / "art.png", size=(100, 80), color="blue", fmt="PNG")
    before = _sha(src)
    out = frame_image(src, tmp_path / "out", mode="solid",
                      color=(255, 0, 0), pad=10)
    assert out.name == "art-Background.png"
    with Image.open(out) as im:
        assert im.size == (120, 100)
        assert im.convert("RGB").getpixel((0, 0)) == (255, 0, 0)
        assert im.convert("RGB").getpixel((60, 50)) == (0, 0, 255)
    assert _sha(src) == before


def test_frame_blur_and_rounded_corners(tmp_path):
    src = _flat(tmp_path / "photo.png", size=(100, 80), fmt="PNG")
    before = _sha(src)
    out = frame_image(src, tmp_path / "out", mode="blur", pad=10,
                      radius=12, blur=8)
    with Image.open(out) as im:
        assert im.size == (120, 100)
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 0)  # rounded
    assert _sha(src) == before


def test_frame_rejects_bad_mode(tmp_path):
    src = _flat(tmp_path / "art.jpg")
    with pytest.raises(ValueError):
        frame_image(src, tmp_path / "out", mode="gradient")


# --- editors need explicit choices; absence is not a missing backend -------


def test_annotate_and_redact_require_choices(tmp_path):
    src = _flat(tmp_path / "pic.jpg")
    with pytest.raises(ValueError, match="text.*xy"):
        annotate_image(src, tmp_path / "out")
    with pytest.raises(ValueError, match="boxes"):
        redact_image(src, tmp_path / "out")


def test_edit_image_requires_a_nonidentity_edit(tmp_path):
    src = _flat(tmp_path / "pic.jpg")
    with pytest.raises(ValueError, match="needs a change"):
        edit_image(src, tmp_path / "out")



def test_compress_rejects_quality_outside_1_to_100(tmp_path):
    src = _flat(tmp_path / "pic.jpg")
    with pytest.raises(ValueError):
        compress_image(src, tmp_path / "o1", quality=0)
    with pytest.raises(ValueError):
        compress_image(src, tmp_path / "o2", quality=101)


@pytest.mark.parametrize("ext", ["jpg", "jpeg", "png", "webp", "heic", "heif",
                                  "tiff", "tif", "avif", "bmp"])
@pytest.mark.parametrize("tool", ["compress", "removeMetadata", "editImage",
                                  "annotateImage", "frameImage", "cropImage",
                                  "redactImage"])
def test_offered_image_types_have_real_tool_effects(tmp_path, ext, tool):
    import pillow_heif

    from kumquat.apply import apply_tool

    pillow_heif.register_heif_opener()
    src = tmp_path / f"صورة synthetic.{ext}"
    original = Image.new("RGB", (96, 64), "red")
    original.paste("blue", (48, 0, 96, 64))
    original.save(src)
    before = _sha(src)
    opts = {"compress": {"max_w": 48}, "editImage": {"brightness": 0.5},
            "annotateImage": {"text": "TEST", "xy": (4, 4), "color": "white"},
            "frameImage": {"pad": 10}, "cropImage": {"box": (48, 0, 96, 64)},
            "redactImage": {"boxes": [(0, 0, 48, 64)]}}.get(tool, {})
    out = apply_tool(tool, [src], tmp_path, **opts)
    with Image.open(out) as result, Image.open(src) as source:
        expected = {"compress": (48, 32), "frameImage": (116, 84),
                    "cropImage": (48, 64)}.get(tool, (96, 64))
        assert result.size == expected
        if tool == "redactImage":
            assert max(result.convert("RGB").getpixel((20, 20))) < 10
            assert result.convert("RGB").getpixel((70, 20))[2] > 200
        elif tool == "editImage":
            assert 110 < result.convert("RGB").getpixel((20, 20))[0] < 145
        elif tool == "annotateImage":
            assert result.tobytes() != source.tobytes()
    assert _sha(src) == before


@pytest.mark.parametrize("tool", ["createPDF", "createCollage"])
def test_svg_multi_tools_produce_raster_collage_or_pdf(tmp_path, tool):
    from kumquat.apply import apply_tool

    src = tmp_path / "synthetic.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64">'
                   '<rect width="96" height="64" fill="red"/></svg>')
    before = _sha(src)
    out = apply_tool(tool, [src, src], tmp_path)
    if tool == "createCollage":
        with Image.open(out) as im:
            assert im.size == (512, 256)
            assert im.convert("RGB").getpixel((40, 40)) == (255, 0, 0)
    else:
        import fitz

        with fitz.open(out) as doc:
            assert doc.page_count == 2
    assert _sha(src) == before

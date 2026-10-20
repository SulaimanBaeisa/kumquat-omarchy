"""Image converters (Pillow backend). Originals are never modified.

- jpg/png/webp/tiff/bmp: Pillow directly.
- pdf export: Pillow save_all (img2pdf-free).
- HEIC/AVIF (in or out): needs pillow-heif; else BackendMissing
  so tests SKIP instead of failing.
- SVG input: needs cairosvg; else the same skip-friendly BackendMissing.
"""
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from .converters_pdf import output_path

_FORMATS = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
    "tiff": "TIFF", "tif": "TIFF", "bmp": "BMP", "pdf": "PDF",
    "heic": "HEIF", "heif": "HEIF", "avif": "AVIF",
}
_HEIF_FMTS = {"heic", "heif", "avif"}
_NO_ALPHA = {"jpg", "jpeg", "pdf"}


class BackendMissing(RuntimeError):
    """Optional backend absent (pillow-heif, cairosvg). Tests SKIP on this."""


def _need_heif() -> None:
    try:
        import pillow_heif
    except ImportError as err:
        raise BackendMissing(
            "backend missing: pillow-heif not installed (HEIC/AVIF support)"
        ) from err
    pillow_heif.register_heif_opener()


def _open(src: Path) -> tuple[Image.Image, Path | None]:
    """Open src for Pillow; SVG renders via cairosvg to a temp PNG first."""
    if src.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError as err:
            raise BackendMissing(
                "backend missing: cairosvg not installed (SVG input)"
            ) from err
        fd, tmps = tempfile.mkstemp(suffix=".png", prefix="kumquat-svg-")
        os.close(fd)
        tmp = Path(tmps)
        cairosvg.svg2png(url=str(src), write_to=str(tmp))
        return Image.open(tmp), tmp
    if src.suffix.lower().lstrip(".") in _HEIF_FMTS:
        _need_heif()
    return Image.open(src), None


def open_upright(src: Path) -> tuple[Image.Image, Path | None]:
    """Open ``src`` with its EXIF orientation applied.

    Phone photos store sideways pixels plus a rotate tag; every viewer shows
    them upright, so crop coordinates must be measured on that upright grid.
    Returns ``(image, temp_file_to_delete)`` like `_open`. Lives beside `_open`
    so the options page can preview an image without importing a processing tool.
    """
    raw, tmp = _open(Path(src))
    try:
        return ImageOps.exif_transpose(raw), tmp
    except BaseException:
        raw.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        raise
    finally:
        raw.close()


def to_png(src: Path, dest_dir: Path) -> Path:
    """Thin alias for convert_image(src, ".png", dest_dir)."""
    return convert_image(src, ".png", dest_dir)


def convert_image(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = dest_ext.lstrip(".").lower()
    if key not in _FORMATS:
        raise ValueError(f"unsupported image output: {dest_ext!r}")
    if key in _HEIF_FMTS:
        _need_heif()
    dest = output_path(dest_dir / (src.stem + "." + key))
    im, tmp = _open(src)
    try:
        if key in _NO_ALPHA and im.mode in ("RGBA", "LA", "PA", "P"):
            im = im.convert("RGB")
        if key == "pdf":
            im.save(dest, "PDF", save_all=True)
        else:
            im.save(dest, _FORMATS[key])
    finally:
        im.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return dest

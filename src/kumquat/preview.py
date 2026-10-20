"""Downscaled, upright image previews for the interactive crop; imports no GTK."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .converters_images import open_upright

DEFAULT_MAX_SIDE = 1024
_ALPHA_BANDS = "A"


def load_preview(
    path: Path | str, max_side: int = DEFAULT_MAX_SIDE
) -> tuple[Image.Image, tuple[int, int]]:
    """Return ``(preview, full_size)`` for ``path``, upright like the crop backend.

    ``full_size`` is the real pixel grid the crop box is measured on; the preview
    is only a smaller picture of it. Raises FileNotFoundError, ValueError for an
    unreadable image, or BackendMissing when a format plugin is absent.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        image, tmp = open_upright(path)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as err:
        raise ValueError(f"Cannot read {path.name} as an image: {err}") from err
    try:
        full_size = image.size
        has_alpha = _ALPHA_BANDS in image.getbands() or "transparency" in image.info
        preview = image.convert("RGBA" if has_alpha else "RGB")
        preview.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return preview, full_size
    finally:
        image.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)

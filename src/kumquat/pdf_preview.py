"""Small page thumbnails for the PDF popup; imports no GTK."""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

THUMB_PX = 120  # longest side of one page thumbnail
THUMB_LIMIT = 120  # thumbnails drawn at most; the true page total is still reported


def load_thumbnails(
    path: Path | str, thumb_px: int = THUMB_PX, limit: int = THUMB_LIMIT
) -> tuple[int, list[Image.Image]]:
    """Return ``(total_pages, thumbnails)`` for the first ``limit`` pages of a PDF.

    Raises FileNotFoundError, or ValueError for an unreadable or locked PDF.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 - fitz raises several error types
        raise ValueError(f"Cannot read {path.name} as a PDF: {exc}") from exc
    with doc:
        if doc.needs_pass:
            raise ValueError(f"{path.name} needs a password; it cannot be previewed.")
        total = doc.page_count
        thumbs = []
        for index in range(min(total, limit)):
            page = doc[index]
            zoom = thumb_px / max(page.rect.width, page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            thumbs.append(image)
    return total, thumbs


def default_order(pages: int) -> str:
    """The unchanged order as the text the page-order field expects."""
    return ", ".join(str(n) for n in range(1, pages + 1))


def order_from_text(text: str, pages: int) -> list[int] | None:
    """The 1-based order typed by the user, or None unless it uses every page once."""
    try:
        order = [int(part) for part in text.split(",")]
    except ValueError:
        return None
    return order if sorted(order) == list(range(1, pages + 1)) else None

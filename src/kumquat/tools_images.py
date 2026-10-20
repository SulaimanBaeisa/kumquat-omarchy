"""Image file tools.

Originals are never modified — every function writes into ``dest_dir``
(or an explicit ``dest`` file) and leaves ``src`` bytes untouched.

Output suffixes: ``Compressed / No Metadata / Background / Cropped``;
``createPDF`` and ``createCollage`` have no fixed suffix, so PDF
takes the first input's stem and collage takes ``<stem>-Collage``.

Backends: Pillow pixel rewrites remove metadata, including TIFF IFD0 tags
that exiftool can retain. SVG/HEIC/AVIF reuse the converter's input loader
(cairosvg / pillow-heif; genuine backend absence raises BackendMissing).
Unary edits preserve TIFF pages and supported animation frames. GIF timing
operations use composed frames rather than flattening or unsupported codecs.
Text annotation, rectangle redaction and explicit image enhancements require
meaningful caller options; they are not freehand-editor stubs.
"""
import math
import tempfile
from functools import wraps
from pathlib import Path

from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageSequence,
)

from .converters_images import (  # noqa: F401 -- re-exported
    BackendMissing,
    _open,
    open_upright,
)

__all__ = [
    "BackendMissing",
    "annotate_image",
    "collage_name",
    "compress_image",
    "create_collage",
    "crop_image",
    "edit_image",
    "frame_image",
    "images_to_pdf",
    "redact_image",
    "strip_metadata",
]

_JPEG_LIKE = {".jpg", ".jpeg"}


def _dest(dest_dir: Path, stem: str, tag: str, suffix: str) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return unique_path(dest_dir / f"{stem}-{tag}{suffix}")


def unique_path(path: Path) -> Path:
    """Choose a new sibling, including when a dangling symlink occupies a name."""
    candidate = path
    n = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def _for_save(im: Image.Image, suffix: str) -> Image.Image:
    """Drop alpha/palette when the target format cannot hold it."""
    if suffix.lower() in _JPEG_LIKE and im.mode in ("RGBA", "LA", "PA", "P"):
        return im.convert("RGB")
    return im


def _close(im: Image.Image, tmp: Path | None) -> None:
    try:
        im.close()
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _framewise(fn):
    """Run unary edits on every TIFF page/animation frame, never flatten silently."""
    @wraps(fn)
    def apply(src, dest_dir, *args, **kwargs):
        src = Path(src)
        if src.suffix.lower() not in {".tif", ".tiff", ".heic", ".heif",
                                      ".webp", ".png", ".avif", ".gif"}:
            return fn(src, dest_dir, *args, **kwargs)
        image, tmp = _open(src)
        pages = []
        try:
            if getattr(image, "n_frames", 1) == 1:
                _close(image, tmp)
                image, tmp = None, None
                return fn(src, dest_dir, *args, **kwargs)
            timing = []
            info = dict(image.info)
            with tempfile.TemporaryDirectory(prefix="kumquat-image-pages-") as work:
                root = Path(work)
                first = None
                for n, frame in enumerate(ImageSequence.Iterator(image)):
                    folder = root / str(n)
                    folder.mkdir()
                    source = folder / src.name
                    frame.save(source)
                    result = fn(source, folder, *args, **kwargs)
                    first = first or result.name
                    with Image.open(result) as page:
                        pages.append(page.copy())
                    timing.append(frame.info.get("duration", 100))
                dest_dir = Path(dest_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)
                assert first is not None
                dest = unique_path(dest_dir / first)
                settings = {}
                if src.suffix.lower() in {".gif", ".png", ".webp"}:
                    settings = {"duration": timing, "loop": info.get("loop", 0)}
                if fn.__name__ == "compress_image":
                    if src.suffix.lower() in {".tif", ".tiff"}:
                        settings["compression"] = "tiff_deflate"
                    else:
                        settings["quality"] = kwargs.get(
                            "quality", args[0] if args else 75)
                pages[0].save(dest, save_all=True, append_images=pages[1:], **settings)
                return dest
        finally:
            if image is not None:
                _close(image, tmp)
            for page in pages:
                page.close()
    return apply


@_framewise
def compress_image(src: Path, dest_dir: Path, quality: int = 75,
                   max_w: int = 0) -> Path:
    """Re-encode ``src`` at ``quality``; shrink to ``max_w`` wide if set.

    Output keeps the source format, named ``<stem>-Compressed<ext>``.
    ``quality`` must be 1–100 (``ValueError`` otherwise).
    """
    if not 1 <= quality <= 100:
        raise ValueError(f"quality {quality!r} outside 1-100")
    src = Path(src)
    dest = _dest(dest_dir, src.stem, "Compressed", src.suffix)
    im, tmp = _open(src)
    try:
        if not isinstance(max_w, int) or isinstance(max_w, bool) or max_w < 0:
            raise ValueError("max_w must be a nonnegative integer")
        if max_w and im.width > max_w:
            im = im.resize((max_w, max(1, round(im.height * max_w / im.width))),
                           Image.Resampling.LANCZOS)
        im = _for_save(im, src.suffix)
        kw: dict = {"optimize": True}
        if src.suffix.lower() in _JPEG_LIKE | {".webp", ".heic", ".heif", ".avif"}:
            kw["quality"] = quality
        if src.suffix.lower() in {".tif", ".tiff"}:
            kw["compression"] = "tiff_deflate"
        im.save(dest, **kw)
    finally:
        _close(im, tmp)
    return dest


def transform_gif(tool_id: str, srcs: list[Path], dest_dir: Path, **opts) -> Path:
    """Preserve composed GIF frames/timing instead of saving only frame zero.

    GIF has no audio stream; its advertised multi-select Mute is explicitly
    unavailable rather than reporting a saved, unchanged animation.
    """
    if tool_id == "muteVideo":
        raise NotImplementedError("GIF cannot contain audio; Mute is unavailable for GIF")
    tags = {"compress": "Compressed", "removeMetadata": "No Metadata",
            "trimVideo": "Trimmed", "cropVideo": "Cropped",
            "changeVideoSpeed": "Speed", "joinVideos": "joined"}
    if tool_id not in tags:
        raise NotImplementedError(f"{tool_id} is unavailable for GIF")
    frames, durations = [], []
    first_info = {}
    try:
        for path in srcs:
            if path.suffix.lower() != ".gif":
                raise NotImplementedError("Joining GIF and non-GIF inputs is unavailable")
            with Image.open(path) as image:
                if not first_info:
                    first_info = dict(image.info)
                elapsed = 0.0
                total = sum(frame.info.get("duration", 100) / 1000
                            for frame in ImageSequence.Iterator(image))
                start, end = 0.0, total
                factor = 1.0
                if tool_id == "trimVideo":
                    start, end = opts["start"], opts["end"]
                    if not (math.isfinite(start) and math.isfinite(end)
                            and 0 <= start < end <= total + 0.001):
                        raise ValueError(
                            f"trim range must be inside GIF duration {total}s")
                elif tool_id == "changeVideoSpeed":
                    factor = opts["factor"]
                    if not math.isfinite(factor) or factor <= 0:
                        raise ValueError("speed factor must be finite and positive")
                for frame in ImageSequence.Iterator(image):
                    length = frame.info.get("duration", 100) / 1000
                    overlap = min(elapsed + length, end) - max(elapsed, start)
                    elapsed += length
                    if overlap <= 0:
                        continue
                    out = frame.convert("RGBA")
                    out.info.clear()
                    if tool_id == "compress" and opts.get("max_w", 0):
                        width = opts["max_w"]
                        if not isinstance(width, int) or width < 1:
                            raise ValueError("max_w must be a nonnegative integer")
                        if out.width > width:
                            height = max(1, round(out.height * width / out.width))
                            out = out.resize((width, height))
                    if tool_id == "cropVideo":
                        region = validate_boxes([opts["box"]], out.size)[0]
                        out = out.crop(region)
                    delay = round(overlap / factor * 100) * 10
                    if delay < 10:
                        raise ValueError(
                            "requested GIF timing is below its 10 ms resolution")
                    frames.append(out)
                    durations.append(delay)
        if not frames:
            raise ValueError("operation selected no GIF frames")
        if any(frame.size != frames[0].size for frame in frames):
            raise ValueError("joined GIF inputs must have matching dimensions")
        tag = tags[tool_id]
        if tool_id == "changeVideoSpeed":
            tag += f" {opts['factor']:g}x"
        dest = _dest(dest_dir, srcs[0].stem, tag, ".gif")
        settings = {"loop": first_info["loop"]} if "loop" in first_info else {}
        frames[0].save(dest, save_all=True, append_images=frames[1:],
                       duration=durations, disposal=2, optimize=True, **settings)
        return dest
    finally:
        for frame in frames:
            frame.close()


@_framewise
def strip_metadata(src: Path, dest_dir: Path) -> Path:
    """Drop descriptive EXIF/metadata by rebuilding pixels and palettes.

    Output named ``<stem>-No Metadata<ext>``. Pixels are unchanged.
    """
    src = Path(src)
    dest = _dest(dest_dir, src.stem, "No Metadata", src.suffix)
    im, tmp = _open(src)
    try:
        # TIFF IFD0 can retain Artist even after exiftool -all= reports success.
        # Rebuild pixels rather than trusting an external metadata-only rewrite.
        clean = Image.frombytes(im.mode, im.size, im.tobytes())
        if im.mode == "P":
            clean.putpalette(im.getpalette())
        if "transparency" in im.info:
            clean.info["transparency"] = im.info["transparency"]
        clean = _for_save(clean, src.suffix)
        clean.save(dest)
    finally:
        _close(im, tmp)
    return dest


@_framewise
def crop_image(src: Path, dest_dir: Path, box: tuple | None = None,
               aspect: str | None = None) -> Path:
    """Crop to ``box`` (l, upper, r, lower) or centred ``aspect`` ("16:9").

    Output named ``<stem>-Cropped<ext>``.
    """
    if (box is None) == (aspect is None):
        raise ValueError("pass exactly one of box= or aspect=")
    src = Path(src)
    dest = _dest(dest_dir, src.stem, "Cropped", src.suffix)
    im, tmp = open_upright(src)
    try:
        if box is not None:
            region = validate_boxes([box], im.size)[0]
        else:
            assert aspect is not None  # exactly-one rule above
            try:
                aw, ah = (float(p) for p in aspect.split(":"))
            except (ValueError, AttributeError) as err:
                raise ValueError(f"bad aspect ratio: {aspect!r}") from err
            if not (math.isfinite(aw) and math.isfinite(ah)) or aw <= 0 or ah <= 0:
                raise ValueError(f"bad aspect ratio: {aspect!r}")
            target = aw / ah
            w, h = im.size
            if w / h > target:  # too wide: trim sides
                nw, nh = round(h * target), h
            else:  # too tall: trim top/bottom
                nw, nh = w, round(w / target)
            if nw < 1 or nh < 1:
                raise ValueError("aspect crop would contain less than one pixel")
            left, u = (w - nw) // 2, (h - nh) // 2
            region = (left, u, left + nw, u + nh)
        _for_save(im, src.suffix).crop(region).save(dest)
    finally:
        _close(im, tmp)
    return dest


def images_to_pdf(srcs: list[Path], dest: Path) -> Path:
    """Merge images into one PDF (one page per image, input order).

    ``dest`` is either the output file or a directory — a directory (or a
    path without a ``.pdf`` suffix) yields ``<first-stem>.pdf`` inside it.
    """
    srcs = [Path(p) for p in srcs]
    if not srcs:
        raise ValueError("images_to_pdf needs at least one input")
    dest = Path(dest)
    if dest.suffix.lower() != ".pdf":
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / (srcs[0].stem + ".pdf")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest)
    pages = []
    tmps = []
    try:
        for p in srcs:
            im, tmp = _open(p)
            tmps.append(tmp)
            pages.append(im.convert("RGB"))
        pages[0].save(dest, save_all=True, append_images=pages[1:])
    finally:
        for im in pages:
            im.close()
        for t in tmps:
            if t is not None:
                t.unlink(missing_ok=True)
    return dest


def collage_name(first_stem: str, suffix: str = ".jpg") -> str:
    """Collage filename rule (no fixed suffix — first-stem)."""
    return f"{first_stem}-Collage{suffix}"


def create_collage(srcs: list[Path], dest_dir: Path, layout: str = "grid",
                   thumb: tuple[int, int] = (256, 256),
                   bg: tuple[int, int, int] = (255, 255, 255)) -> Path:
    """Tile images: ``grid`` (sqrt), ``row`` or ``column`` of ``thumb`` cells.

    Output named ``<first-stem>-Collage<first-ext>``.
    """
    if layout not in ("grid", "row", "column"):
        raise ValueError(f"unknown collage layout: {layout!r}")
    srcs = [Path(p) for p in srcs]
    if not srcs:
        raise ValueError("create_collage needs at least one input")
    tw, th = thumb
    cells = []
    tmps = []
    try:
        for p in srcs:
            im, tmp = _open(p)
            tmps.append(tmp)
            # Explicit RGB: _for_save only drops alpha for JPEG targets;
            # the RGB sheet below would drop it implicitly via paste().
            cells.append(ImageOps.fit(
                _for_save(im, p.suffix).convert("RGB"), (tw, th)))
            im.close()
        n = len(cells)
        if layout == "grid":
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
        elif layout == "row":
            cols, rows = n, 1
        else:
            cols, rows = 1, n
        sheet = Image.new("RGB", (cols * tw, rows * th), bg)
        for i, cell in enumerate(cells):
            sheet.paste(cell, ((i % cols) * tw, (i // cols) * th))
            cell.close()
        suffix = ".png" if srcs[0].suffix.lower() == ".svg" else srcs[0].suffix
        dest = _dest(dest_dir, srcs[0].stem, "Collage", suffix)
        sheet.save(dest)
    finally:
        for t in tmps:
            if t is not None:
                t.unlink(missing_ok=True)
    return dest


@_framewise
def frame_image(src: Path, dest_dir: Path, mode: str = "solid",
                color: tuple[int, int, int] = (255, 255, 255),
                pad: int = 40, radius: int = 0, blur: int = 25) -> Path:
    """Pad ``src`` on a ``solid`` colour or ``blur``red-fill background.

    ``radius`` rounds the output corners. Named ``<stem>-Background<ext>``.
    """
    if mode not in ("solid", "blur"):
        raise ValueError(f"unknown frame mode: {mode!r}")
    src = Path(src)
    dest = _dest(dest_dir, src.stem, "Background", src.suffix)
    im, tmp = _open(src)
    try:
        base = _for_save(im, src.suffix).convert("RGB")
        w, h = base.size
        canvas = (w + 2 * pad, h + 2 * pad)
        if mode == "solid":
            bg = Image.new("RGB", canvas, color)
        else:
            bg = ImageOps.fit(base, canvas).filter(
                ImageFilter.GaussianBlur(blur))
        bg.paste(base, (pad, pad))
        if radius:
            mask = Image.new("L", canvas, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, canvas[0] - 1, canvas[1] - 1], radius=radius, fill=255)
            out = Image.new("RGB", canvas, (0, 0, 0))
            out.paste(bg, mask=mask)
            bg = out
        bg.save(dest)
    finally:
        _close(im, tmp)
    return dest


def validate_boxes(boxes: list | None, size: tuple[int, int]) -> list[tuple]:
    """Require nonempty, integer pixel rectangles entirely inside the image/video."""
    if not boxes:
        raise ValueError("provide boxes=[(left, upper, right, lower), ...]")
    w, h = size
    regions = []
    for box in boxes:
        if not isinstance(box, (tuple, list)) or len(box) != 4 or any(
                not isinstance(v, int) or isinstance(v, bool) for v in box):
            raise ValueError("each box needs four integer pixel coordinates")
        left, top, right, bottom = box
        if not (0 <= left < right <= w and 0 <= top < bottom <= h):
            raise ValueError(f"box {box} outside {size}")
        regions.append(tuple(box))
    return regions


@_framewise
def annotate_image(src: Path, dest_dir: Path, *, text: str | None = None,
                   xy: tuple | None = None, color="black", font_size: int = 20) -> Path:
    """Draw text at an explicit pixel position; no GUI editor is implied."""
    if not isinstance(text, str) or not text.strip() or xy is None:
        raise ValueError("annotateImage needs nonblank text and xy=(x, y)")
    if not isinstance(font_size, int) or not 1 <= font_size <= 1000:
        raise ValueError("font_size must be an integer from 1 to 1000")
    src = Path(src)
    im, tmp = _open(src)
    try:
        if len(xy) != 2 or any(not isinstance(v, int) for v in xy) or not (
                0 <= xy[0] < im.width and 0 <= xy[1] < im.height):
            raise ValueError("xy must be an integer pixel position inside the image")
        out = _for_save(im, src.suffix).copy()
        draw = ImageDraw.Draw(out)
        draw.text(tuple(xy), text, fill=color,
                  font=ImageFont.load_default(size=font_size))
        if out.tobytes() == _for_save(im, src.suffix).tobytes():
            raise ValueError("annotation changes no visible pixels; "
                             "choose another position/colour")
        dest = _dest(dest_dir, src.stem, "Annotated", src.suffix)
        out.save(dest)
    finally:
        _close(im, tmp)
    return dest


@_framewise
def redact_image(src: Path, dest_dir: Path, boxes: list | None = None) -> Path:
    """Permanently replace selected rectangles with black, dropping metadata."""
    if not boxes:
        raise ValueError("redactImage needs boxes=[(left, upper, right, lower), ...]")
    src = Path(src)
    im, tmp = _open(src)
    try:
        regions = validate_boxes(boxes, im.size)
        out = im.convert("RGB")
        out.info.clear()
        for region in regions:
            out.paste((0, 0, 0), region)
        dest = _dest(dest_dir, src.stem, "Redacted", src.suffix)
        out.save(dest)
    finally:
        _close(im, tmp)
    return dest


@_framewise
def edit_image(src: Path, dest_dir: Path, *, brightness: float = 1,
               contrast: float = 1, saturation: float = 1, rotate: float = 0) -> Path:
    """Apply explicit enhancement factors and/or rotation to a new image."""
    settings = (brightness, contrast, saturation, rotate)
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in settings):
        raise ValueError("edit settings must be finite numbers")
    if min(brightness, contrast, saturation) < 0:
        raise ValueError("brightness, contrast and saturation must be nonnegative")
    if (brightness, contrast, saturation, rotate % 360) == (1, 1, 1, 0):
        raise ValueError("editImage needs a change: "
                         "brightness, contrast, saturation or rotate")
    src = Path(src)
    im, tmp = _open(src)
    try:
        out = im.convert("RGB")
        for enhancer, factor in ((ImageEnhance.Brightness, brightness),
                                 (ImageEnhance.Contrast, contrast),
                                 (ImageEnhance.Color, saturation)):
            if factor != 1:
                out = enhancer(out).enhance(factor)
        if rotate % 360:
            out = out.rotate(rotate, expand=True)
        if out.size == im.size and out.tobytes() == im.convert("RGB").tobytes():
            raise ValueError("edit changes no visible pixels; choose different settings")
        dest = _dest(dest_dir, src.stem, "Edited", src.suffix)
        out.save(dest)
    finally:
        _close(im, tmp)
    return dest

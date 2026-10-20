"""Slides converters (LibreOffice Impress headless). Originals never modified.

Backend policy (mirrors converters_docs):
- ppt/pptx inputs: LibreOffice headless (soffice); else BackendMissing.
- Image outputs render every slide through PDF at 300 dpi. Impress's direct
  PNG/JPG export writes only the first slide, silently dropping the rest.
- ppt output: direct Impress export ("MS PowerPoint 97" filter; LO writes
  .ppt from pptx fine); else BackendMissing.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from ._loshell import profile_args
from .converters_pdf import BackendMissing, convert_pdf, output_path

_IMPRESS_FILTERS = {
    "pdf": "pdf:impress_pdf_Export",
    "png": "png:impress_png_Export",
    "jpg": "jpg:impress_jpg_Export",
    "ppt": "ppt:MS PowerPoint 97",
    "pptx": "pptx:Impress MS PowerPoint 2007 XML",
}

_SLIDE_INPUTS = ("ppt", "pptx")
_SLIDE_OUTPUTS = ("pdf", "jpg", "png")


def _need_soffice() -> str:
    for binary in ("soffice", "libreoffice"):
        if shutil.which(binary) is not None:
            return binary
    raise BackendMissing(
        "backend missing: LibreOffice (soffice) not installed (slides support)"
    )


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def convert_slide(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    """Convert a slide deck (ppt/pptx) to dest_ext; returns the output path."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = src.suffix.lstrip(".").lower()
    dst = dest_ext.lstrip(".").lower()
    if key not in _SLIDE_INPUTS:
        raise ValueError(f"unsupported slide input: {src.suffix!r}")
    if dst not in _SLIDE_OUTPUTS:
        raise ValueError(f"unsupported slide output: {dest_ext!r}")
    soffice = _need_soffice()
    with tempfile.TemporaryDirectory(prefix="kumquat-slides-") as tmp:
        # The PDF bridge preserves all slides and landscape dimensions. Keep
        # intermediate files private; convert_pdf returns the first image and
        # collision-protects each slide output, matching PDF image conversion.
        export = "pdf" if dst in ("png", "jpg") else dst
        _run([soffice, *profile_args(tmp), "--headless",
              "--convert-to", _IMPRESS_FILTERS[export],
              "--outdir", tmp, str(src)])
        built = Path(tmp) / (src.stem + "." + export)
        if not built.exists():
            raise RuntimeError(f"soffice produced no {export} for {src}")
        if dst in ("png", "jpg"):
            return convert_pdf(built, dst, dest_dir)
        dest = output_path(dest_dir / (src.stem + "." + dst))
        shutil.move(str(built), dest)
    return dest

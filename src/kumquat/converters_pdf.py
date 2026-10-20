"""PDF converters (PyMuPDF + LibreOffice backends). Originals are never modified.

- jpg/png: PyMuPDF page renders at 300 dpi (zoom 300/72). One file per page
  (`stem-1.png`, …); the first page's path is returned.
- txt/md: PyMuPDF text extraction (pdf has no structure to preserve).
- docx: LibreOffice two-stage (pdf -> Draw HTML -> docx); direct pdf->docx
  has no export filter, verified by probe.
- pptx: LibreOffice Impress PDF import (one slide per page); slide size
  stamped from the PDF's first page (see _to_pptx for the two pitfalls).
- xlsx: pdf text -> CSV -> LibreOffice Calc filter (direct pdf/html->xlsx
  fails with "Unspecified Application Error", verified by probe).
- epub: text via fitz, then pandoc md->epub; pandoc absent -> BackendMissing.
- pages: impossible headless -> BackendMissing ALWAYS (needs macOS Pages).
- merge_pdfs / split_pdf / organize_pdf (mergePDF/splitPDF/organizePDF
  tools): PyMuPDF, always available (pinned dependency).
"""

import csv
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz

from ._loshell import profile_args
from .progress import Progress, ProgressCallback

_ZOOM_300DPI = 300 / 72


class BackendMissing(RuntimeError):
    """Optional backend absent (soffice, pandoc) or impossible (pages).

    Tests SKIP on this.
    """


def output_path(requested: Path) -> Path:
    """Choose a new output name without replacing an existing file/directory.

    Keep compound tar.gz suffixes intact; converter outputs are new artifacts,
    including when two same-stem sources share their destination directory.
    """
    suffix = ".tar.gz" if requested.name.endswith(".tar.gz") else requested.suffix
    stem = requested.name[:-len(suffix)] if suffix else requested.name
    candidate = requested
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = requested.with_name(f"{stem} ({counter}){suffix}")
        counter += 1
    return candidate


def _need_soffice() -> str:
    for binary in ("soffice", "libreoffice"):
        if shutil.which(binary) is not None:
            return binary
    raise BackendMissing(
        "backend missing: LibreOffice (soffice) not installed (pdf->office support)"
    )


def _need_pandoc() -> str:
    if shutil.which("pandoc") is None:
        raise BackendMissing("backend missing: pandoc not installed (pdf->epub support)")
    return "pandoc"


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def _pdf_text(src: Path) -> str:
    with fitz.open(src) as doc:
        return "\n\n".join(page.get_text() for page in doc)


def _to_image(src: Path, key: str, dest_dir: Path,
              progress: ProgressCallback | None = None) -> Path:
    """Render every page; reports one Progress per saved page."""
    with fitz.open(src) as doc:
        if doc.page_count == 0:
            raise ValueError(f"no pages to render: {src}")
        first = None
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(_ZOOM_300DPI, _ZOOM_300DPI))
            dest = output_path(dest_dir / f"{src.stem}-{i + 1}.{key}")
            pix.save(dest, output="jpg" if key == "jpg" else "png")
            if progress is not None:
                progress(Progress((i + 1) / doc.page_count))
            if first is None:
                first = dest
    assert first is not None
    return first


def _to_text(src: Path, key: str, dest_dir: Path) -> Path:
    dest = output_path(dest_dir / (src.stem + "." + key))
    dest.write_text(_pdf_text(src), encoding="utf-8")
    return dest


def _to_docx(src: Path, dest_dir: Path) -> Path:
    soffice = _need_soffice()
    with tempfile.TemporaryDirectory(prefix="kumquat-pdf-") as tmp:
        _run([soffice, *profile_args(tmp), "--headless",
              "--convert-to", "html:XHTML Draw File",
              "--outdir", tmp, str(src)])
        html = Path(tmp) / (src.stem + ".html")
        if not html.exists():
            raise RuntimeError(f"soffice produced no HTML for {src}")
        _run([soffice, *profile_args(tmp), "--headless",
              "--convert-to", "docx:MS Word 2007 XML",
              "--outdir", tmp, str(html)])
        built = Path(tmp) / (src.stem + ".docx")
        if not built.exists():
            raise RuntimeError(f"soffice produced no docx for {src}")
        dest = output_path(dest_dir / (src.stem + ".docx"))
        shutil.move(str(built), dest)
    return dest


_PPTX_IMPORT_FILTER = "--infilter=impress_pdf_import"
_EMU_PER_PT = 12700
_SLIDE_SIZE_RE = re.compile(rb'<p:sldSz cx="\d+" cy="\d+"')


def _to_pptx(src: Path, dest_dir: Path) -> Path:
    """PDF -> PPTX, one slide per page, slide size = the PDF's page size.

    Two LibreOffice pitfalls, both silent:
    * Without the Impress import filter soffice opens the PDF in *Draw*, and
      Draw -> PowerPoint writes a package with zero slides (PowerPoint calls
      it corrupt).
    * The Impress importer keeps PDF coordinates but writes its default
      US-Letter portrait slide size, clipping landscape decks; we stamp the
      real page size into presentation.xml afterwards.
    """
    soffice = _need_soffice()
    with tempfile.TemporaryDirectory(prefix="kumquat-pdf-") as tmp:
        _run([soffice, *profile_args(tmp), "--headless", _PPTX_IMPORT_FILTER,
              "--convert-to", "pptx:Impress MS PowerPoint 2007 XML",
              "--outdir", tmp, str(src)])
        built = Path(tmp) / (src.stem + ".pptx")
        if not built.exists():
            raise RuntimeError(f"soffice produced no pptx for {src}")
        if _pptx_slide_count(built) == 0:
            raise RuntimeError(f"soffice produced an empty pptx for {src}")
        _set_pptx_slide_size(built, _first_page_size_pt(src))
        dest = output_path(dest_dir / (src.stem + ".pptx"))
        shutil.move(str(built), dest)
    return dest


def _first_page_size_pt(src: Path) -> tuple[float, float]:
    """PPTX has one slide size per deck, so the first page decides it."""
    with fitz.open(src) as doc:
        rect = doc[0].rect
    return rect.width, rect.height


def _pptx_slide_count(pptx: Path) -> int:
    with zipfile.ZipFile(pptx) as pkg:
        return sum(1 for name in pkg.namelist()
                   if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))


def _set_pptx_slide_size(pptx: Path, size_pt: tuple[float, float]) -> None:
    """Rewrite ppt/presentation.xml's <p:sldSz>, copying every other member."""
    width, height = (round(v * _EMU_PER_PT) for v in size_pt)
    patched = pptx.with_suffix(".sized.pptx")
    with zipfile.ZipFile(pptx) as old, zipfile.ZipFile(
            patched, "w", zipfile.ZIP_DEFLATED) as new:
        for item in old.infolist():
            data = old.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                data = _SLIDE_SIZE_RE.sub(
                    f'<p:sldSz cx="{width}" cy="{height}"'.encode(), data, count=1)
            new.writestr(item, data)
    patched.replace(pptx)


def _to_xlsx(src: Path, dest_dir: Path) -> Path:
    soffice = _need_soffice()
    with tempfile.TemporaryDirectory(prefix="kumquat-pdf-") as tmp:
        csv_path = Path(tmp) / (src.stem + ".csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for line in _pdf_text(src).splitlines():
                writer.writerow([line])
        _run([soffice, *profile_args(tmp), "--headless", "--convert-to",
              "xlsx:Calc MS Excel 2007 XML", "--outdir", tmp, str(csv_path)])
        built = Path(tmp) / (src.stem + ".xlsx")
        if not built.exists():
            raise RuntimeError(f"soffice produced no xlsx for {src}")
        dest = output_path(dest_dir / (src.stem + ".xlsx"))
        shutil.move(str(built), dest)
    return dest


def _to_epub(src: Path, dest_dir: Path) -> Path:
    pandoc = _need_pandoc()
    dest = output_path(dest_dir / (src.stem + ".epub"))
    with tempfile.TemporaryDirectory(prefix="kumquat-pdf-") as tmp:
        md_path = Path(tmp) / (src.stem + ".md")
        md_path.write_text(_pdf_text(src), encoding="utf-8")
        _run([pandoc, str(md_path), "-o", str(dest)])
    if not dest.exists():
        raise RuntimeError(f"pandoc produced no epub for {src}")
    return dest


def convert_pdf(src: Path, dest_ext: str, dest_dir: Path,
                progress: ProgressCallback | None = None) -> Path:
    """Convert src pdf to dest_ext; returns the output path.

    `progress` is reported per page for image outputs; other outputs ignore it.
    """
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = dest_ext.lstrip(".").lower()
    if key in ("jpg", "jpeg", "png"):
        return _to_image(src, "jpg" if key in ("jpg", "jpeg") else "png", dest_dir,
                         progress)
    if key in ("txt", "md"):
        return _to_text(src, key, dest_dir)
    if key == "docx":
        return _to_docx(src, dest_dir)
    if key == "pptx":
        return _to_pptx(src, dest_dir)
    if key == "xlsx":
        return _to_xlsx(src, dest_dir)
    if key == "epub":
        return _to_epub(src, dest_dir)
    if key == "pages":
        raise BackendMissing(
            "backend missing: Apple Pages export needs macOS "
            "(no headless Linux exporter exists)"
        )
    raise ValueError(f"unsupported pdf output: {dest_ext!r}")


def merge_pdfs(srcs: list[Path], dest_dir: Path) -> Path:
    """Merge pdfs in order; returns the merged path."""
    paths = [Path(s) for s in srcs]
    if not paths:
        raise ValueError("merge_pdfs needs at least one input")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = fitz.open()
    try:
        for s in paths:
            with fitz.open(s) as doc:
                out.insert_pdf(doc)
        dest = dest_dir / (paths[0].stem + "-merged.pdf")
        out.save(dest)
    finally:
        out.close()
    return dest


def split_pdf(src: Path, dest_dir: Path) -> list[Path]:
    """Split a pdf into one single-page pdf per page."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    with fitz.open(src) as doc:
        for i in range(doc.page_count):
            one = fitz.open()
            try:
                one.insert_pdf(doc, from_page=i, to_page=i)
                dest = dest_dir / f"{src.stem}-{i + 1}.pdf"
                one.save(dest)
            finally:
                one.close()
            parts.append(dest)
    return parts


def organize_pdf(src: Path, dest_dir: Path, order: list[int] | None = None) -> Path:
    """Reorder pdf pages; order holds 0-based indices."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(src) as doc:
        count = doc.page_count
        seq = list(range(count)) if order is None else list(order)
        if sorted(seq) != list(range(count)):
            raise ValueError(f"order must permute range({count}): {order!r}")
        out = fitz.open()
        try:
            for i in seq:
                out.insert_pdf(doc, from_page=i, to_page=i)
            dest = dest_dir / (src.stem + "-organized.pdf")
            out.save(dest)
        finally:
            out.close()
    return dest

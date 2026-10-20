"""PDF conversions: registry routing + real conversions, originals untouched.

pdf row: pdf->[docx,pages,pptx,xlsx,jpg,png,epub,txt,md] (9 outputs).
pdf tools: splitPDF / organizePDF (single) + mergePDF (multi).

Backend policy (mirrors converters_images / converters_av):
- pdf->jpg/png/txt/md/merge/split/organize: PyMuPDF (pinned, always present).
- pdf->docx/pptx/xlsx: LibreOffice headless (soffice); else BackendMissing.
- pdf->epub: text via fitz, then pandoc md->epub; else BackendMissing.
- pdf->pages: impossible headless -> BackendMissing ALWAYS (needs macOS).
Tests needing an absent backend SKIP; they never fail.
"""
import hashlib
import shutil

import pytest

import kumquat.registry_data  # noqa: F401 -- registers image rows (pulls AV rows too)
import kumquat.registry_pdf  # noqa: F401 -- registers the 9 pdf rows
from kumquat.converters_pdf import (
    BackendMissing,
    convert_pdf,
    merge_pdfs,
    organize_pdf,
    split_pdf,
)
from kumquat.registry import REGISTRY, options_for

PDF_ROWS = [c for c in REGISTRY if c.category == "pdf"]

PDF_OUTPUTS = ["docx", "pages", "pptx", "xlsx", "jpg", "png", "epub", "txt", "md"]


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_pdf(path, pages=1):
    """Build a fixture pdf with fitz (no network); page i holds 'page i'."""
    import fitz

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"hello page {i}")
    doc.save(path)
    doc.close()


def test_registry_pdf_count():
    assert len(PDF_ROWS) == 9  # pdf row verbatim


def test_registry_total_with_pdf():
    assert len(REGISTRY) >= 170  # 161 + 9 pdf rows (later slices add more)


def test_pdf_ids():
    ids = {c.id for c in PDF_ROWS}
    assert ids == {f"pdf-to-{o}" for o in PDF_OUTPUTS}
    assert len(ids) == 9


def test_pdf_labels_follow_E_rule():
    for c in PDF_ROWS:
        dst = c.output_ext.lstrip(".")
        assert c.label == "Convert to " + ("GZIP" if dst == "gz" else dst.upper())


def test_registry_routes_pdf():
    opts = options_for("a.pdf", "application/pdf")
    assert len(opts) == 9
    assert any(c.id == "pdf-to-png" for c in opts)
    assert any(c.id == "pdf-to-docx" for c in opts)


@pytest.mark.parametrize("row_id", [f"pdf-to-{o}" for o in PDF_OUTPUTS])
def test_pdf_row_routes(row_id):
    row = next(c for c in PDF_ROWS if c.id == row_id)
    opts = options_for("file" + row.inputs[0], "application/octet-stream")
    assert row in opts


def test_pdf_converts_to_png(tmp_path):
    import magic

    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".png", tmp_path / "out")
    assert out.exists() and out.suffix == ".png"
    assert magic.from_file(str(out), mime=True) == "image/png"
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_jpg(tmp_path):
    import magic

    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".jpg", tmp_path / "out")
    assert out.exists() and out.suffix == ".jpg"
    assert magic.from_file(str(out), mime=True) == "image/jpeg"
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_txt(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".txt", tmp_path / "out")
    assert out.exists() and out.suffix == ".txt"
    assert "hello page 0" in out.read_text()
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_md(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".md", tmp_path / "out")
    assert out.exists() and out.suffix == ".md"
    assert "hello page 0" in out.read_text()
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_docx(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".docx", tmp_path / "out")
    assert out.exists() and out.suffix == ".docx"
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_pptx(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".pptx", tmp_path / "out")
    assert out.exists() and out.suffix == ".pptx"
    assert _sha(src) == before  # original untouched


def _pptx_slides_and_size(path):
    """(slide count, (width_pt, height_pt)) read straight from the package."""
    import re
    import zipfile

    with zipfile.ZipFile(path) as pkg:
        slides = [n for n in pkg.namelist()
                  if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        pres = pkg.read("ppt/presentation.xml").decode()
    size = re.search(r'<p:sldSz cx="(\d+)" cy="(\d+)"', pres)
    assert size is not None, "presentation.xml has no <p:sldSz>"
    emu_per_pt = 12700
    return len(slides), (int(size[1]) / emu_per_pt, int(size[2]) / emu_per_pt)


def test_pdf_to_pptx_has_one_slide_per_page(tmp_path):
    """Regression: LibreOffice opened the PDF in Draw and wrote a deck with
    ZERO slides (a valid zip PowerPoint reports as corrupt)."""
    src = tmp_path / "in.pdf"
    _make_pdf(src, pages=3)
    out = _or_skip(convert_pdf, src, ".pptx", tmp_path / "out")
    count, _ = _pptx_slides_and_size(out)
    assert count == 3


def test_pdf_to_pptx_slide_size_matches_landscape_pdf(tmp_path):
    """Regression: slides came out US-Letter portrait (612x792) while shapes
    kept PDF coordinates, clipping a landscape deck's right side."""
    import fitz

    src = tmp_path / "wide.pdf"
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=792, height=594)
        page.insert_text((72, 72), f"slide {i}")
    doc.save(src)
    doc.close()
    out = _or_skip(convert_pdf, src, ".pptx", tmp_path / "out")
    count, (width, height) = _pptx_slides_and_size(out)
    assert count == 2
    assert abs(width - 792) <= 1 and abs(height - 594) <= 1


def test_pdf_converts_to_xlsx(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".xlsx", tmp_path / "out")
    assert out.exists() and out.suffix == ".xlsx"
    assert _sha(src) == before  # original untouched


def test_pdf_converts_to_epub(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    before = _sha(src)
    out = _or_skip(convert_pdf, src, ".epub", tmp_path / "out")
    assert out.exists() and out.suffix == ".epub"
    assert _sha(src) == before  # original untouched


def test_pdf_to_pages_always_missing(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    with pytest.raises(BackendMissing):
        convert_pdf(src, ".pages", tmp_path / "out")


def test_merge_pdfs(tmp_path):
    import fitz

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, pages=1)
    _make_pdf(b, pages=2)
    out = merge_pdfs([a, b], tmp_path / "out")
    assert out.exists() and out.suffix == ".pdf"
    with fitz.open(out) as doc:
        assert doc.page_count == 3


def test_split_organize_round_trip(tmp_path):
    import fitz

    src = tmp_path / "in.pdf"
    _make_pdf(src, pages=3)
    parts = split_pdf(src, tmp_path / "pages")
    assert len(parts) == 3
    assert all(p.suffix == ".pdf" for p in parts)
    for p in parts:
        with fitz.open(p) as doc:
            assert doc.page_count == 1
    # split -> merge round-trips back to 3 pages
    rejoined = merge_pdfs(parts, tmp_path / "rejoined")
    with fitz.open(rejoined) as doc:
        assert doc.page_count == 3
    # organize reverses page order
    rev = organize_pdf(src, tmp_path / "org", order=[2, 1, 0])
    with fitz.open(rev) as doc:
        assert doc.page_count == 3
        assert "hello page 2" in doc[0].get_text()
        assert "hello page 0" in doc[2].get_text()


def test_missing_soffice_raises_backend_missing(tmp_path, monkeypatch):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_pdf(src, ".docx", tmp_path / "out")


def test_missing_pandoc_raises_backend_missing(tmp_path, monkeypatch):
    src = tmp_path / "in.pdf"
    _make_pdf(src)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_pdf(src, ".epub", tmp_path / "out")


def test_pdf_to_png_reports_one_update_per_page(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src, pages=4)
    updates = []
    convert_pdf(src, ".png", tmp_path / "out", progress=updates.append)
    assert [round(u.fraction, 2) for u in updates] == [0.25, 0.5, 0.75, 1.0]

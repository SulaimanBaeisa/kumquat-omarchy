"""Docs/sheets/subs conversions: registry routing + real conversions, originals untouched.

rows:
- docs=[docx,pages,md,rtf,rtfd,textClipping]->[docx,pages,pdf,txt,md,html,epub,png,jpg]
  (rtf/rtfd/textClipping input-only: filtered from outputs; self filtered)
  => 8+8+8+9+9+9 = 51 rows, category "documents".
- epub->[pdf,docx,pages,txt,md,html] = 6 rows, category "documents".
- txt->[docx,pages,pdf,md,html,epub,jpg,png] = 8 rows, category "documents".
- sheets=[xlsx,xls,ods,csv,tsv]->[...sheets,pdf] (xls input-only; self filtered)
  => 4+5+4+4+4 = 21 rows, category "spreadsheets".
- subs=[srt,vtt]->[other,txt] = 4 rows, category "subtitles".
New total: 170 + 51+6+8+21+4 = 260.

Backend policy (mirrors converters_pdf):
- docx/md/rtf/txt/csv inputs: LibreOffice headless (soffice); else BackendMissing.
- csv/tsv<->xlsx + csv<->tsv: openpyxl/csv stdlib (native, no backend needed).
- srt<->vtt, srt/vtt->txt: pure python (no backend needed).
- png/jpg outputs: LO pdf bridge + PyMuPDF render (soffice needed).
- pages in/out: BackendMissing ALWAYS (needs macOS).
- epub in/out: BackendMissing (this LO build lacks EPUB filters; pandoc absent).
- rtfd/textClipping in: BackendMissing (no headless Linux reader).
Tests needing an absent backend SKIP; they never fail.
"""
import hashlib
import shutil

import pytest

import kumquat.registry_data  # noqa: F401 -- registers image rows (pulls AV rows too)
import kumquat.registry_docs  # noqa: F401 -- registers the 90 docs/sheets/subs rows
import kumquat.registry_pdf  # noqa: F401 -- registers the 9 pdf rows
from kumquat.converters_docs import (
    BackendMissing,
    convert_doc,
    convert_sheet,
    convert_sub,
)
from kumquat.registry import REGISTRY, options_for

DOC_ROWS = [c for c in REGISTRY if c.category == "documents"]
SHEET_ROWS = [c for c in REGISTRY if c.category == "spreadsheets"]
SUB_ROWS = [c for c in REGISTRY if c.category == "subtitles"]


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_docx(path):
    """Build a minimal fixture docx with stdlib zipfile (no network, no backend)."""
    import zipfile

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>hello docx</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)


def _make_csv(path):
    path.write_text("name,age\nalice,30\nbob,25\n", encoding="utf-8")


def _make_tsv(path):
    path.write_text("name\tage\nalice\t30\nbob\t25\n", encoding="utf-8")


def _make_xlsx(path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["name", "age"])
    ws.append(["alice", 30])
    ws.append(["bob", 25])
    wb.save(path)


def _make_srt(path):
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:00:03,500 --> 00:00:05,000\nSecond line\n",
        encoding="utf-8",
    )


def _make_vtt(path):
    path.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello world\n\n"
        "00:00:03.500 --> 00:00:05.000\nSecond line\n",
        encoding="utf-8",
    )


def test_registry_docs_counts():
    assert len(DOC_ROWS) == 65  # 51 re + 6 epub + 8 txt
    assert len(SHEET_ROWS) == 21  # 4+5+4+4+4
    assert len(SUB_ROWS) == 4  # 2+2


def test_registry_total_with_docs():
    assert len(REGISTRY) >= 260  # 260 + archives/slides rows (later slices add more)


def test_docs_no_self_or_input_only_outputs():
    for c in DOC_ROWS + SHEET_ROWS + SUB_ROWS:
        dst = c.output_ext.lstrip(".")
        assert dst not in ("rtf", "rtfd", "textclipping", "xls"), c.id  # input-only
    for c in DOC_ROWS + SHEET_ROWS + SUB_ROWS:
        src = c.id.split("-to-")[0].split("-", 1)[1]
        dst = c.output_ext.lstrip(".")
        assert src != dst, c.id  # self filtered


def test_docs_labels_follow_E_rule():
    for c in DOC_ROWS + SHEET_ROWS + SUB_ROWS:
        dst = c.output_ext.lstrip(".")
        assert c.label == "Convert to " + ("GZIP" if dst == "gz" else dst.upper())


def test_registry_routes_docx():
    opts = options_for("a.docx", "application/octet-stream")
    assert len(opts) == 8  # doc outputs minus self
    assert any(c.id == "doc-docx-to-pdf" for c in opts)


def test_registry_routes_csv():
    opts = options_for("a.csv", "text/csv")
    assert len(opts) == 4
    assert any(c.id == "sheet-csv-to-xlsx" for c in opts)


def test_registry_routes_xls_gets_five():
    opts = options_for("a.xls", "application/octet-stream")
    assert len(opts) == 5  # xls input-only: never an output
    assert any(c.id == "sheet-xls-to-xlsx" for c in opts)


def test_registry_routes_srt():
    opts = options_for("a.srt", "application/octet-stream")
    assert len(opts) == 2
    assert {c.id for c in opts} == {"sub-srt-to-vtt", "sub-srt-to-txt"}


@pytest.mark.parametrize("row_id", [
    "doc-docx-to-pdf", "doc-pages-to-pdf", "doc-md-to-html", "doc-rtf-to-docx",
    "doc-rtfd-to-pdf", "doc-textclipping-to-txt", "doc-epub-to-pdf", "doc-txt-to-md",
    "sheet-xlsx-to-pdf", "sheet-xls-to-csv", "sheet-ods-to-xlsx",
    "sheet-csv-to-tsv", "sheet-tsv-to-xlsx",
    "sub-srt-to-vtt", "sub-srt-to-txt", "sub-vtt-to-srt", "sub-vtt-to-txt",
])
def test_docs_row_routes(row_id):
    row = next(c for c in REGISTRY if c.id == row_id)
    opts = options_for("file" + row.inputs[0], "application/octet-stream")
    assert row in opts


def test_docx_converts_to_pdf(tmp_path):
    import magic

    src = tmp_path / "in.docx"
    _make_docx(src)
    before = _sha(src)
    out = _or_skip(convert_doc, src, ".pdf", tmp_path / "out")
    assert out.exists() and out.suffix == ".pdf"
    assert magic.from_file(str(out), mime=True) == "application/pdf"
    assert _sha(src) == before  # original untouched


def test_docx_converts_to_txt(tmp_path):
    src = tmp_path / "in.docx"
    _make_docx(src)
    before = _sha(src)
    out = _or_skip(convert_doc, src, ".txt", tmp_path / "out")
    assert out.exists() and out.suffix == ".txt"
    assert "hello docx" in out.read_text()
    assert _sha(src) == before  # original untouched


def test_docx_converts_to_png_via_pdf_bridge(tmp_path):
    import magic

    src = tmp_path / "in.docx"
    _make_docx(src)
    before = _sha(src)
    out = _or_skip(convert_doc, src, ".png", tmp_path / "out")
    assert out.exists() and out.suffix == ".png"
    assert magic.from_file(str(out), mime=True) == "image/png"
    assert _sha(src) == before  # original untouched


def test_csv_converts_to_xlsx_native(tmp_path):
    from openpyxl import load_workbook

    src = tmp_path / "in.csv"
    _make_csv(src)
    before = _sha(src)
    out = convert_sheet(src, ".xlsx", tmp_path / "out")  # native, no backend needed
    assert out.exists() and out.suffix == ".xlsx"
    ws = load_workbook(out).active
    assert [ws.cell(1, 1).value, ws.cell(1, 2).value] == ["name", "age"]
    assert ws.cell(2, 1).value == "alice"
    assert _sha(src) == before  # original untouched


def test_tsv_converts_to_xlsx_native(tmp_path):
    from openpyxl import load_workbook

    src = tmp_path / "in.tsv"
    _make_tsv(src)
    out = convert_sheet(src, ".xlsx", tmp_path / "out")
    ws = load_workbook(out).active
    assert [ws.cell(1, 1).value, ws.cell(1, 2).value] == ["name", "age"]
    assert ws.cell(3, 1).value == "bob"


def test_xlsx_converts_to_csv_native(tmp_path):
    src = tmp_path / "in.xlsx"
    _make_xlsx(src)
    before = _sha(src)
    out = convert_sheet(src, ".csv", tmp_path / "out")  # native, no backend needed
    assert out.exists() and out.suffix == ".csv"
    text = out.read_text()
    assert "alice" in text and "bob" in text
    assert _sha(src) == before  # original untouched


def test_csv_converts_to_tsv_native(tmp_path):
    src = tmp_path / "in.csv"
    _make_csv(src)
    out = convert_sheet(src, ".tsv", tmp_path / "out")
    assert out.exists() and out.suffix == ".tsv"
    assert "alice\t30" in out.read_text()


def test_xlsx_converts_to_pdf(tmp_path):
    import magic

    src = tmp_path / "in.xlsx"
    _make_xlsx(src)
    before = _sha(src)
    out = _or_skip(convert_sheet, src, ".pdf", tmp_path / "out")
    assert out.exists() and out.suffix == ".pdf"
    assert magic.from_file(str(out), mime=True) == "application/pdf"
    assert _sha(src) == before  # original untouched


def test_srt_converts_to_vtt(tmp_path):
    src = tmp_path / "s.srt"
    _make_srt(src)
    before = _sha(src)
    out = convert_sub(src, ".vtt", tmp_path / "out")  # pure python, no backend
    assert out.exists() and out.suffix == ".vtt"
    text = out.read_text()
    assert text.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in text  # comma -> dot
    assert "Hello world" in text
    assert _sha(src) == before  # original untouched


def test_srt_converts_to_txt(tmp_path):
    src = tmp_path / "s.srt"
    _make_srt(src)
    out = convert_sub(src, ".txt", tmp_path / "out")
    text = out.read_text()
    assert "Hello world" in text and "Second line" in text
    assert "-->" not in text  # cues stripped


def test_vtt_converts_to_srt(tmp_path):
    src = tmp_path / "s.vtt"
    _make_vtt(src)
    before = _sha(src)
    out = convert_sub(src, ".srt", tmp_path / "out")  # pure python, no backend
    assert out.exists() and out.suffix == ".srt"
    text = out.read_text()
    assert "00:00:01,000 --> 00:00:02,000" in text  # dot -> comma
    assert text.startswith("1\n")  # cues renumbered
    assert _sha(src) == before  # original untouched


def test_vtt_converts_to_txt(tmp_path):
    src = tmp_path / "s.vtt"
    _make_vtt(src)
    out = convert_sub(src, ".txt", tmp_path / "out")
    text = out.read_text()
    assert "Hello world" in text and "Second line" in text
    assert "WEBVTT" not in text


def test_sub_round_trip(tmp_path):
    src = tmp_path / "s.srt"
    _make_srt(src)
    vtt = convert_sub(src, ".vtt", tmp_path / "a")
    back = convert_sub(vtt, ".srt", tmp_path / "b")
    assert "Hello world" in back.read_text()
    assert "00:00:03,500 --> 00:00:05,000" in back.read_text()


def test_srt_numeric_only_body_preserved(tmp_path):
    # Regression: numeric-only cue bodies ("42", "911", years) must not be
    # dropped as cue indices — digit-lines are indices only before a
    # timestamp is seen (final-review must-fix #1).
    src = tmp_path / "s.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n42\n\n"
        "2\n00:00:03,500 --> 00:00:05,000\n911\n",
        encoding="utf-8",
    )
    out = convert_sub(src, ".txt", tmp_path / "out")
    text = out.read_text()
    assert "Hello" in text and "42" in text and "911" in text


def test_vtt_numeric_only_body_preserved(tmp_path):
    src = tmp_path / "s.vtt"
    src.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n2024\n",
        encoding="utf-8",
    )
    out = convert_sub(src, ".txt", tmp_path / "out")
    assert "2024" in out.read_text()


def test_doc_to_pages_always_missing(tmp_path):
    src = tmp_path / "in.docx"
    _make_docx(src)
    with pytest.raises(BackendMissing):
        convert_doc(src, ".pages", tmp_path / "out")


def test_doc_to_epub(tmp_path):
    """epub export works when pandoc is present (regression: it used to
    refuse unconditionally even with pandoc installed)."""
    if not shutil.which("pandoc"):
        pytest.skip("backend missing: pandoc")
    src = tmp_path / "in.docx"
    _make_docx(src)
    out = convert_doc(src, ".epub", tmp_path / "out")
    assert out.suffix == ".epub"
    assert out.read_bytes()[:2] == b"PK"


def test_pages_input_always_missing(tmp_path):
    src = tmp_path / "in.pages"
    src.write_bytes(b"not a real pages bundle")
    with pytest.raises(BackendMissing):
        convert_doc(src, ".pdf", tmp_path / "out")


def test_rtfd_and_textclipping_inputs_missing(tmp_path):
    rtfd = tmp_path / "in.rtfd"
    rtfd.write_text("rtfd stub", encoding="utf-8")
    with pytest.raises(BackendMissing):
        convert_doc(rtfd, ".pdf", tmp_path / "out")
    clip = tmp_path / "in.textclipping"
    clip.write_bytes(b"textclipping stub")
    with pytest.raises(BackendMissing):
        convert_doc(clip, ".txt", tmp_path / "out")


def test_epub_input_converts(tmp_path):
    """epub input works via pandoc (regression: it used to raise)."""
    if not shutil.which("pandoc"):
        pytest.skip("backend missing: pandoc")
    md = tmp_path / "seed.md"
    md.write_text("# Title\n\nHello epub.\n")
    epub = convert_doc(md, ".epub", tmp_path)
    out = convert_doc(epub, ".pdf", tmp_path / "out")
    assert out.suffix == ".pdf"
    assert out.stat().st_size > 0


def test_unsupported_doc_output(tmp_path):
    src = tmp_path / "in.docx"
    _make_docx(src)
    with pytest.raises(ValueError):
        convert_doc(src, ".zip", tmp_path / "out")


def test_unsupported_sub_output(tmp_path):
    src = tmp_path / "s.srt"
    _make_srt(src)
    with pytest.raises(ValueError):
        convert_sub(src, ".pdf", tmp_path / "out")


def test_missing_soffice_raises_backend_missing(tmp_path, monkeypatch):
    src = tmp_path / "in.docx"
    _make_docx(src)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_doc(src, ".pdf", tmp_path / "out")

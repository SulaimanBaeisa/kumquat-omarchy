"""Slides conversions: registry routing + real conversions, originals untouched.

rows (verbatim):
- ppt/pptx->[pdf,jpg,png] (ppt input-only per He, so it never appears
  as an output; self is never in the output list).
  ppt: 3 rows; pptx: 3 rows. Total: 6 rows, category "slides".
- Registry gate: 260 + 9 archives + 6 slides = 275 EXACTLY.

Backend policy (mirrors converters_docs):
- ppt/pptx->pdf/png/jpg: LibreOffice Impress headless (soffice);
  else BackendMissing. Tests needing it SKIP; they never fail.
"""
import hashlib
import shutil
import zipfile

import pytest

import kumquat.registry_data  # noqa: F401 -- registers all rows (archives+slides too)
import kumquat.registry_slides  # noqa: F401 -- registers the 6 slides rows
from kumquat.converters_slides import BackendMissing, convert_slide
from kumquat.registry import REGISTRY, options_for

SLIDE_ROWS = [c for c in REGISTRY if c.category == "slides"]

SLIDE_IDS = {
    "slide-ppt-to-pdf", "slide-ppt-to-jpg", "slide-ppt-to-png",
    "slide-pptx-to-pdf", "slide-pptx-to-jpg", "slide-pptx-to-png",
}


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_pptx(path):
    """Build a minimal 1-slide pptx with stdlib zipfile (no backend needed)."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slide+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="'
        'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="'
        'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.theme+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.'
        'openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.extended-properties+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.'
        'openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/></Relationships>'
    )
    pres = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:sldMasterIdLst><p:sldMasterId id="1" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:sldIdLst><p:sldId id="2" r:id="rId2"/></p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>'
    )
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/slideMaster" '
        'Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        'Target="slides/slide1.xml"/></Relationships>'
    )
    slide = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/>'
        '<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
        '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
        '</a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="2" name="t"/>'
        '<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/>'
        '<a:p><a:r><a:t>hello slides</a:t></a:r></a:p></p:txBody></p:sp>'
        '</p:spTree></p:cSld></p:sld>'
    )
    layout = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' preserve="1"><p:cSld name="blank"><p:spTree><p:nvGrpSpPr>'
        '<p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
        '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld></p:sldLayout>'
    )
    master = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        '<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
        '<a:xfrm xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
        '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld></p:sldMaster>'
    )
    theme = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        ' name="t"><a:themeElements><a:clrScheme name=""><a:lt1>'
        '<a:srgbClr val="FFFFFF"/></a:lt1><a:dk1><a:srgbClr val="000000"/>'
        '</a:dk1></a:clrScheme></a:themeElements></a:theme>'
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
        'metadata/core-properties"></cp:coreProperties>'
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        'extended-properties"><Application>kumquat-test</Application></Properties>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("ppt/presentation.xml", pres)
        z.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        z.writestr("ppt/slides/slide1.xml", slide)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        z.writestr("ppt/slideMasters/slideMaster1.xml", master)
        z.writestr("ppt/theme/theme1.xml", theme)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)


def test_registry_slides_count():
    assert len(SLIDE_ROWS) == 6  # ppt 3 + pptx 3, verbatim


def test_registry_total_is_275():
    assert len(REGISTRY) == 275  # 260 + 9 archives + 6 slides;


def test_slides_ids():
    assert {c.id for c in SLIDE_ROWS} == SLIDE_IDS


def test_slides_no_self_or_input_only_outputs():
    for c in SLIDE_ROWS:
        dst = c.output_ext.lstrip(".")
        assert dst in ("pdf", "jpg", "png"), c.id  # ppt input-only, never output


def test_slides_labels_follow_E_rule():
    for c in SLIDE_ROWS:
        dst = c.output_ext.lstrip(".")
        assert c.label == "Convert to " + ("GZIP" if dst == "gz" else dst.upper())


def test_registry_routes_ppt_gets_three():
    opts = options_for("a.ppt", "application/octet-stream")
    assert {c.id for c in opts} == {
        "slide-ppt-to-pdf", "slide-ppt-to-jpg", "slide-ppt-to-png",
    }


def test_registry_routes_pptx_gets_three():
    opts = options_for("a.pptx", "application/octet-stream")
    assert {c.id for c in opts} == {
        "slide-pptx-to-pdf", "slide-pptx-to-jpg", "slide-pptx-to-png",
    }


@pytest.mark.parametrize("row_id", sorted(SLIDE_IDS))
def test_slides_row_routes(row_id):
    row = next(c for c in SLIDE_ROWS if c.id == row_id)
    opts = options_for("file" + row.inputs[0], "application/octet-stream")
    assert row in opts


def test_pptx_converts_to_pdf(tmp_path):
    import magic

    src = tmp_path / "in.pptx"
    _make_pptx(src)
    before = _sha(src)
    out = _or_skip(convert_slide, src, ".pdf", tmp_path / "out")
    assert out.exists() and out.suffix == ".pdf"
    assert magic.from_file(str(out), mime=True) == "application/pdf"
    assert _sha(src) == before  # original untouched


def test_pptx_converts_to_png(tmp_path):
    import magic

    src = tmp_path / "in.pptx"
    _make_pptx(src)
    before = _sha(src)
    out = _or_skip(convert_slide, src, ".png", tmp_path / "out")
    assert out.exists() and out.suffix == ".png"
    assert magic.from_file(str(out), mime=True) == "image/png"
    assert _sha(src) == before  # original untouched


def test_pptx_converts_to_jpg(tmp_path):
    import magic

    src = tmp_path / "in.pptx"
    _make_pptx(src)
    out = _or_skip(convert_slide, src, ".jpg", tmp_path / "out")
    assert out.exists() and out.suffix == ".jpg"
    assert magic.from_file(str(out), mime=True) == "image/jpeg"


def test_ppt_converts_to_pdf(tmp_path):
    import subprocess

    import magic

    if shutil.which("soffice") is None:
        pytest.skip("backend missing: LibreOffice (soffice) not installed")
    src = tmp_path / "in.pptx"
    _make_pptx(src)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "ppt:MS PowerPoint 97",
         "--outdir", str(tmp_path), str(src)],
        check=True, capture_output=True, timeout=300,
    )
    ppt = tmp_path / "in.ppt"
    before = _sha(ppt)
    out = _or_skip(convert_slide, ppt, ".pdf", tmp_path / "out")
    assert out.exists() and out.suffix == ".pdf"
    assert magic.from_file(str(out), mime=True) == "application/pdf"
    assert _sha(ppt) == before  # original untouched


def test_unsupported_slide_output(tmp_path):
    src = tmp_path / "in.pptx"
    _make_pptx(src)
    with pytest.raises(ValueError):
        convert_slide(src, ".zip", tmp_path / "out")


def test_unsupported_slide_input(tmp_path):
    src = tmp_path / "in.docx"
    src.write_bytes(b"stub")
    with pytest.raises(ValueError):
        convert_slide(src, ".pdf", tmp_path / "out")


def test_missing_soffice_raises_backend_missing(tmp_path, monkeypatch):
    src = tmp_path / "in.pptx"
    _make_pptx(src)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_slide(src, ".pdf", tmp_path / "out")

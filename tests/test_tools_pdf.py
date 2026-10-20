"""PDF file tools (TDD): merge / split (Pages folder) / organize (JSON spec).

TDD record: this file was written FIRST against a nonexistent
`kumquat.tools_pdf` (RED: ModuleNotFoundError on collection),
then the module was implemented to make it GREEN.

`merge_pdfs` writes a collision-safe `<first-stem>-merged.pdf` in page order.
`split_pdf` delegates page extraction to the converter but places parts
in a `<stem>-Pages/` folder (`Pages->folder`).
`organize_pdf` takes a JSON spec (dict, JSON string, or `.json` path)
with `reorder` / `drop` / `dup` / `rotate` keys and writes
`<stem>-Organized.pdf` (`Organized`).

Originals are never modified (sha-pinned in every behaviour test).
PyMuPDF is a pinned dependency, so no backend SKIPs apply here.
"""
import hashlib
import json

import pytest

from kumquat.tools_pdf import merge_pdfs, organize_pdf, split_pdf


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_pdf(path, pages=3):
    """N-page pdf fixture; page i reads 'hello page i'."""
    import fitz

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"hello page {i}")
    doc.save(path)
    doc.close()
    return path


def _texts(path):
    import fitz

    with fitz.open(path) as doc:
        return [doc[i].get_text() for i in range(doc.page_count)]


def _count(path):
    import fitz

    with fitz.open(path) as doc:
        return doc.page_count


# --- merge_pdfs (re-export) --------------------------------------------------

def test_merge_pdfs_page_count_and_name(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    b = _make_pdf(tmp_path / "b.pdf", pages=2)
    before = (_sha(a), _sha(b))
    out = merge_pdfs([a, b], tmp_path / "out")
    assert out.name == "a-merged.pdf"  # no fixed suffix: first-stem fallback
    assert _count(out) == 3
    assert (_sha(a), _sha(b)) == before  # originals untouched


def test_merge_pdfs_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        merge_pdfs([], tmp_path / "out")


# --- split_pdf (Pages folder) ------------------------------------------------

def test_split_pdf_pages_folder_and_round_trip(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    before = _sha(src)
    parts = split_pdf(src, tmp_path / "out")
    assert len(parts) == 3
    assert all(p.parent.name == "in-Pages" for p in parts)  # Pages->folder
    assert [p.name for p in parts] == ["in-1.pdf", "in-2.pdf", "in-3.pdf"]
    for i, p in enumerate(parts):
        assert _count(p) == 1
        assert f"hello page {i}" in _texts(p)[0]
    rejoined = merge_pdfs(parts, tmp_path / "rejoined")
    assert _count(rejoined) == 3
    assert _sha(src) == before


# --- organize_pdf: reorder / drop / dup / rotate ------------------------------

def test_organize_reorder_and_name(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    before = _sha(src)
    out = organize_pdf(src, tmp_path / "out", spec={"reorder": [2, 1, 0]})
    assert out.name == "in-Organized.pdf"  # suffix: Organized
    got = _texts(out)
    assert "hello page 2" in got[0]
    assert "hello page 0" in got[2]
    assert _sha(src) == before


def test_organize_drop(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    out = organize_pdf(src, tmp_path / "out", spec={"drop": [1]})
    got = _texts(out)
    assert len(got) == 2
    assert "hello page 0" in got[0]
    assert "hello page 2" in got[1]


def test_organize_dup_appends_copy(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    out = organize_pdf(src, tmp_path / "out", spec={"dup": [0]})
    got = _texts(out)
    assert len(got) == 4
    assert "hello page 0" in got[0]
    assert "hello page 0" in got[3]


def test_organize_rotate_sets_page_rotation(tmp_path):
    import fitz

    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    out = organize_pdf(src, tmp_path / "out", spec={"rotate": {"1": 90}})
    with fitz.open(out) as doc:
        assert doc[0].rotation == 0
        assert doc[1].rotation == 90
        assert doc[2].rotation == 0


def test_organize_accepts_json_string_and_file(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    combined = {"reorder": [2, 0, 1], "drop": [0], "dup": [2],
                "rotate": {"2": 180}}
    from_str = organize_pdf(src, tmp_path / "s", spec=json.dumps(combined))
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(combined), encoding="utf-8")
    from_file = organize_pdf(src, tmp_path / "f", spec=spec_file)
    # drop [0] from order [2,0,1] -> [2,1], dup [2] appends -> [2,1,2]
    for out in (from_str, from_file):
        got = _texts(out)
        assert len(got) == 3
        assert "hello page 2" in got[0]
        assert "hello page 1" in got[1]
        assert "hello page 2" in got[2]


def test_organize_none_is_identity_copy(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=2)
    before = _sha(src)
    out = organize_pdf(src, tmp_path / "out")
    assert out.name == "in-Organized.pdf"
    assert _count(out) == 2
    assert "hello page 0" in _texts(out)[0]
    assert _sha(src) == before


def test_organize_rejects_bad_specs(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", pages=3)
    with pytest.raises(ValueError):  # index out of range
        organize_pdf(src, tmp_path / "o1", spec={"reorder": [0, 1, 9]})
    with pytest.raises(ValueError):  # dropping everything empties the doc
        organize_pdf(src, tmp_path / "o2", spec={"drop": [0, 1, 2]})
    with pytest.raises(ValueError):  # rotation must be a multiple of 90
        organize_pdf(src, tmp_path / "o3", spec={"rotate": {"0": 45}})
    with pytest.raises(ValueError):  # unknown key (likely a typo)
        organize_pdf(src, tmp_path / "o4", spec={"reodrer": [0, 1, 2]})
    with pytest.raises(ValueError):  # drop and dup contradict
        organize_pdf(src, tmp_path / "o5", spec={"drop": [1], "dup": [1]})

"""Dispatcher tests: a wheel option must actually convert.

Regression cover for the gap where the app could list all 275 options but
had no code path that applied one.
"""
from __future__ import annotations

import pytest
from PIL import Image

import kumquat.registry_data  # noqa: F401 -- populates REGISTRY
from kumquat.apply import apply_conversion, apply_tool, find_conversion
from kumquat.registry import REGISTRY


def test_find_conversion_known_id():
    conv = find_conversion("image-jpg-to-png")
    assert conv.output_ext == ".png"
    assert conv.category == "images"


def test_find_conversion_unknown_id_lists_help():
    with pytest.raises(KeyError) as ei:
        find_conversion("image-nope-to-nope")
    assert "--list" in str(ei.value)


def test_every_registry_row_has_a_converter():
    """No row may exist that the dispatcher cannot route."""
    from kumquat.apply import _CONVERTERS
    cats = {c.category for c in REGISTRY}
    assert cats <= set(_CONVERTERS), cats - set(_CONVERTERS)


def test_apply_conversion_writes_new_file_and_keeps_original(tmp_path):
    src = tmp_path / "in.jpg"
    Image.new("RGB", (16, 16), "red").save(src, "JPEG")
    before = src.read_bytes()

    out = apply_conversion("image-jpg-to-png", src, tmp_path / "out")

    assert out.exists() and out.suffix == ".png"
    assert out.read_bytes()[:4] == b"\x89PNG"
    assert src.read_bytes() == before  # original untouched


def test_apply_conversion_bad_id_is_loud(tmp_path):
    src = tmp_path / "in.jpg"
    Image.new("RGB", (8, 8), "blue").save(src, "JPEG")
    with pytest.raises(KeyError):
        apply_conversion("bogus-id", src, tmp_path)


def test_apply_tool_compresses(tmp_path):
    src = tmp_path / "big.jpg"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(src, "JPEG", quality=98)
    out = apply_tool("compress", [src], tmp_path / "out", quality=40)
    assert out.exists()
    assert out.stat().st_size < src.stat().st_size


def test_apply_tool_unknown_is_loud(tmp_path):
    src = tmp_path / "x.jpg"
    Image.new("RGB", (8, 8), "green").save(src, "JPEG")
    with pytest.raises(KeyError):
        apply_tool("not-a-tool", [src], tmp_path)


def test_apply_tool_needs_inputs(tmp_path):
    with pytest.raises(ValueError):
        apply_tool("compress", [], tmp_path)


def _make_pdf(path, pages):
    """Tiny multi-page PDF. Local copy: tests/ is not a package, so importing
    test_pdf's helper only works under `python -m pytest`, not bare `pytest`."""
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"page {i}")
    doc.save(path)
    doc.close()


def test_apply_conversion_forwards_progress_for_pdf(tmp_path):
    src = tmp_path / "in.pdf"
    _make_pdf(src, pages=2)
    updates = []
    apply_conversion("pdf-to-png", src, tmp_path, progress=updates.append)
    assert updates and updates[-1].fraction == 1.0


def test_apply_conversion_accepts_progress_for_unmeasured_category(tmp_path):
    """Docs have no measurable progress: the kwarg is accepted and ignored."""
    from kumquat.apply import PROGRESS_AWARE

    assert "documents" not in PROGRESS_AWARE
    assert {"audio", "video", "pdf"} <= PROGRESS_AWARE

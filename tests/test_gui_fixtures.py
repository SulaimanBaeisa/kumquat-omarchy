"""The GUI proof must generate its inputs, not depend on yesterday's temp files."""
import runpy
import zipfile
from pathlib import Path

from PIL import Image


def test_e2e_work_fixtures_are_self_contained(tmp_path, monkeypatch):
    helpers = runpy.run_path(str(Path(__file__).with_name("gui_e2e.py")))
    Image.new("RGB", (8, 8), "teal").save(tmp_path / "pic.jpg")
    monkeypatch.setattr(helpers["shutil"], "which", lambda _name: None)
    helpers["build_work_dir"].__globals__["QA_DIR"] = tmp_path / "missing-old-cache"
    work = helpers["build_work_dir"](tmp_path)
    assert (work / "pic.jpg").is_file()
    with zipfile.ZipFile(work / "note.docx") as doc:
        assert b"Synthetic progress" in doc.read("word/document.xml")
        assert "[Content_Types].xml" in doc.namelist()

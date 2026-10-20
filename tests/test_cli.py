"""Wheel CLI surface (TDD): `kumquat --files ... --list`.

TDD record: this file was written FIRST against a nonexistent
`kumquat.cli` (RED: ModuleNotFoundError on collection),
then `src/kumquat/cli.py` was implemented to make it GREEN.

What is asserted here (verbatim strings):
- per-file sections list conversion labels from `options_for`
  (label rule E: "Convert to PNG"; gz -> "Convert to GZIP");
- tool section lists wheel titles (verbatim `L` titles from the REA
  bundle: COMPRESS, TRIM, MERGE PDF, ...); tool applicability follows
  the `et()` table and the `Je` allowlist;
- action section lists wheel titles;
- empty states: "No conversions for this format. Tap Control for file
  actions."; center prompts: "Choose a conversion format / file tool /
  file action";
- unknown/extensionless files degrade to the empty state, never crash.

No display is needed: `--list` is pure text over `options_for` plus
extension-keyed tool/action tables. The GTK wheel (`--gui`) is covered
only by a headless-degradation test (BackendMissing-style message when
`gi` is unavailable) — eyeball verification is deferred to the user
per the progress.md ruling (050/060 <-> headless).
"""
import subprocess
import sys
import unittest.mock as mock

import pytest

from kumquat.cli import (
    ACTION_TITLES,
    ACTIONS,
    MODIFIER_MAP,
    TOOL_TITLES,
    TOOLS,
    files_listing,
    format_listing,
)


def files_listing_text(files, mimes):
    """Render helper (module level so tests read top-down)."""
    return format_listing(files_listing(files, mimes))


def _labels(section):
    return [label for _id, label in section]


# --- registry wiring: labels come from options_for --------------------------


def test_listing_photo_conversions_use_registry_labels():
    listing = files_listing(["photo.jpg"], ["image/jpeg"])
    conv = dict(listing)["photo.jpg"]["conversions"]
    assert ("image-jpg-to-png", "Convert to PNG") in conv
    assert ("image-jpg-to-pdf", "Convert to PDF") in conv
    assert len(conv) == 7  # qe minus self


def test_listing_gzip_label_rule():
    # Label rule E: gz->"GZIP" else UPPER; Ge() names gz output tar.gz.
    listing = files_listing(["backup.zip"], ["application/zip"])
    entry = dict(listing)["backup.zip"]
    labels = _labels(entry["conversions"])
    assert "Convert to GZIP" in labels
    assert "Convert to TAR" in labels
    listing = files_listing(["backup.tar.gz"], ["application/gzip"])
    labels = _labels(dict(listing)["backup.tar.gz"]["conversions"])
    assert "Convert to ZIP" in labels
    assert "Convert to GZIP" not in labels  # self filtered


def test_listing_empty_state_verbatim():
    listing = files_listing(["README"], ["text/plain"])
    conv = dict(listing)["README"]["conversions"]
    assert conv == []
    text = files_listing_text(["README"], ["text/plain"])
    assert "No conversions for this format. Tap Control for file actions." in text


def test_listing_prompts_verbatim():
    text = files_listing_text(["photo.jpg"], ["image/jpeg"])
    assert "Choose a conversion format" in text
    assert "Choose a file tool" in text
    assert "Choose a file action" in text


# --- tools: et() table + Je allowlist ------------------------------------


def test_tool_titles_verbatim():
    assert TOOL_TITLES["compress"] == "COMPRESS"
    assert TOOL_TITLES["trimVideo"] == "TRIM"
    assert TOOL_TITLES["mergePDF"] == "MERGE PDF"
    assert TOOL_TITLES["extractArchive"] == "EXTRACT"
    assert TOOL_TITLES["createPDF"] == "CREATE PDF"
    assert TOOL_TITLES["muteVideo"] == "MUTE"
    assert len(TOOLS) == 26  # 32 L-keys = 26 tools + 6 actions


def test_single_jpg_tools_single_select_set():
    listing = files_listing(["photo.jpg"], ["image/jpeg"])
    ids = [tid for tid, _ in dict(listing)["photo.jpg"]["tools"]]
    for tid in ("compress", "removeMetadata", "editImage", "annotateImage",
                "frameImage", "cropImage", "redactImage"):
        assert tid in ids
    assert "createPDF" not in ids  # multi-only for svg-class inputs
    assert "createCollage" not in ids


def test_multi_jpg_tools_allowlist():
    listing = files_listing(["a.jpg", "b.jpg"], ["image/jpeg", "image/jpeg"])
    ids = [tid for tid, _ in dict(listing)["a.jpg"]["tools"]]
    assert "compress" in ids
    assert "removeMetadata" in ids
    assert "cropImage" in ids
    assert "createPDF" in ids
    assert "createCollage" in ids
    assert "editImage" not in ids  # filtered by $e for t>1


def test_wma_has_conversions_only_no_tools():
    listing = files_listing(["song.wma"], ["audio/x-ms-wma"])
    entry = dict(listing)["song.wma"]
    assert len(entry["conversions"]) == 7  # q->q minus self
    assert entry["tools"] == []


def test_gif_tools_remove_metadata_only():
    listing = files_listing(["anim.gif"], ["image/gif"])
    ids = [tid for tid, _ in dict(listing)["anim.gif"]["tools"]]
    assert ids == ["removeMetadata"]


def test_archive_tools_extract_only():
    listing = files_listing(["a.zip"], ["application/zip"])
    ids = [tid for tid, _ in dict(listing)["a.zip"]["tools"]]
    assert ids == ["extractArchive"]


def test_single_pdf_tools_no_merge():
    listing = files_listing(["doc.pdf"], ["application/pdf"])
    ids = [tid for tid, _ in dict(listing)["doc.pdf"]["tools"]]
    for tid in ("compress", "removeMetadata", "splitPDF", "organizePDF"):
        assert tid in ids
    assert "mergePDF" not in ids  # multi-only (organize->merge swap)


def test_multi_pdf_tools_merge_replaces_organize():
    listing = files_listing(["a.pdf", "b.pdf"],
                            ["application/pdf", "application/pdf"])
    ids = [tid for tid, _ in dict(listing)["a.pdf"]["tools"]]
    assert "mergePDF" in ids
    assert "organizePDF" not in ids


def test_single_mp4_tools_full_set():
    listing = files_listing(["clip.mp4"], ["video/mp4"])
    ids = [tid for tid, _ in dict(listing)["clip.mp4"]["tools"]]
    for tid in ("compress", "removeMetadata", "muteVideo", "trimVideo",
                "cropVideo", "changeVideoSpeed", "videoSnapshots",
                "splitVideo", "redactVideo"):
        assert tid in ids


def test_multi_mp4_tools_drop_snapshot_split_redact():
    listing = files_listing(["a.mp4", "b.mp4"], ["video/mp4", "video/mp4"])
    ids = [tid for tid, _ in dict(listing)["a.mp4"]["tools"]]
    assert "trimVideo" in ids
    assert "videoSnapshots" not in ids
    assert "splitVideo" not in ids
    assert "redactVideo" not in ids


# --- actions -------------------------------------------------------------


def test_action_titles_verbatim():
    assert ACTION_TITLES == {
        "share": "LOCALSEND",
        "float": "FLOAT",
        "copy": "COPY",
        "move": "MOVE",
        "copy-path": "COPY PATH",
        "open-terminal": "TERMINAL",
    }
    assert ACTIONS == ["share", "float", "copy", "move", "copy-path",
                       "open-terminal"]


def test_actions_available_for_every_file():
    listing = files_listing(["README"], ["text/plain"])
    ids = [aid for aid, _ in dict(listing)["README"]["actions"]]
    assert ids == ACTIONS


# --- keyboard map --------------------------------------------------------


def test_modifier_map_q1():
    assert MODIFIER_MAP == {
        "Shift": "conversions",
        "Meta": "tools",
        "Control": "actions",
    }


def test_list_text_shows_key_hints():
    text = files_listing_text(["photo.jpg"], ["image/jpeg"])
    assert "Shift" in text
    assert "Super" in text or "Meta" in text
    assert "Control" in text


# --- entry point -------------------------------------------------------------


def test_wheel_list_subprocess_no_display(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"fake")
    proc = subprocess.run(
        [sys.executable, "-m", "kumquat.cli", "--files", str(img),
         "--list"],
        capture_output=True, text=True, env={"PYTHONPATH": "src"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "Convert to PNG" in proc.stdout
    assert "Choose a conversion format" in proc.stdout


def test_gui_without_gtk_degrades_to_message():
    with mock.patch.dict("sys.modules", {"gi": None}):
        from kumquat.cli import run_gui
        with pytest.raises(RuntimeError, match="[Gg][Tt][Kk]|gi |display"):
            run_gui(["photo.jpg"])

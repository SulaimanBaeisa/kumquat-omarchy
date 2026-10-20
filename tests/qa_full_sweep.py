"""Real-format, content-checked conversion matrix; never touches user documents.

Run: PYTHONPATH=src .venv/bin/python tests/qa_full_sweep.py --json RESULT.json
The default corpus lives in TMPDIR; --work-dir must be an empty directory.
Every registry input key (including aliases) gets a cell. Tools/actions are
inventoried from files_listing, explicitly UNTESTED here, not credited as passes.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import hashlib
import io
import json
import multiprocessing
import os
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz
from PIL import Image, ImageDraw, ImageStat
from rar_fixture import write_rar5_stored

from kumquat import registry_data as _registry_data  # noqa: F401
from kumquat._loshell import profile_args
from kumquat.apply import apply_conversion
from kumquat.converters_archives import extract_archive
from kumquat.converters_av import BackendMissing as AVMissing
from kumquat.converters_images import BackendMissing as ImageMissing
from kumquat.converters_pdf import BackendMissing
from kumquat.registry import ACTIONS, REGISTRY
from kumquat.selection import TOOLS, files_listing

TOKEN = "Kumquat"
PAYLOAD = b"Kumquat archive payload 42\n"
MISSING_FIXTURES = {
    ".pages": "No genuine native Apple Pages fixture available; no fixture fabricated",
    ".rtfd": "No genuine native RTFD bundle available; no fixture fabricated",
    ".textclipping": (
        "No genuine native macOS text clipping available; no fixture fabricated"
    ),
}
BACKEND_ERRORS = (BackendMissing, AVMissing, ImageMissing)
_IN_WORKER = False


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Capture diagnostics; timeout kills the fixture backend's whole group."""
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=not _IN_WORKER,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            if _IN_WORKER:
                # Retain the worker's group so its parent can always clear
                # backend descendants, including LibreOffice's launcher child.
                proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.communicate(timeout=5)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
            raise
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd, stdout, stderr)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def conversion_inventory() -> list[dict]:
    return [
        {
            "id": f"{c.id}:{key}",
            "route_id": c.id,
            "source_key": key,
            "output_ext": c.output_ext,
            "category": c.category,
            "kind": "conversion",
        }
        for c in REGISTRY
        for key in c.inputs
    ]


def declared_inventory() -> list[dict]:
    """Enumerate single and homogeneous-pair offered tools/actions, not execution."""
    cells = []
    for key in sorted({k for c in REGISTRY for k in c.inputs}):
        for count in (1, 2):
            names = [f"synthetic-{i}{key}" for i in range(count)]
            sections = files_listing(names)[0][1]
            for kind in ("tools", "actions"):
                for ident, _ in sections[kind]:
                    cells.append(
                        {
                            "id": f"{kind}:{ident}:{key}:{count}",
                            "kind": kind,
                            "operation_id": ident,
                            "source_key": key,
                            "selection_count": count,
                            "status": "UNTESTED",
                            "reason": (
                                "Inventory only; effect/GUI proof belongs to "
                                "separate tools/actions sweep"
                            ),
                        }
                    )
    return cells


def office(src: Path, spec: str, dest_dir: Path, extension: str) -> Path:
    """Make/round-trip genuine office fixtures with an isolated LO profile."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qa-lo-") as profile:
        run(
            [
                "soffice",
                *profile_args(profile),
                "--headless",
                "--convert-to",
                spec,
                "--outdir",
                str(dest_dir),
                str(src),
            ]
        )
    out = dest_dir / (src.stem + extension)
    assert out.is_file() and out.stat().st_size, f"LibreOffice produced no {extension}"
    return out


def make_rar_fixture(path: Path) -> Path:
    """A stored RAR5 archive, proven genuine by having 7-Zip test and extract it.

    RAR cannot be authored with the installed tools, so the bytes are written to
    the public format (see rar_fixture.py). If the official reader does not
    accept it, the fixture is reported as a failed fixture, never as a pass.
    """
    write_rar5_stored(path, {"folder/hello.txt": PAYLOAD})
    subprocess.run(["7z", "t", str(path)], capture_output=True, check=True)
    probe = path.parent / "rar-fixture-probe"
    subprocess.run(
        ["7z", "x", f"-o{probe}", "-y", str(path)], capture_output=True, check=True
    )
    assert (probe / "folder/hello.txt").read_bytes() == PAYLOAD
    shutil.rmtree(probe)
    return path


def build_fixtures(root: Path) -> tuple[dict[str, Path], dict[str, str]]:
    """Adapt the original sweep's generators, with missing real formats filled in."""
    root.mkdir(parents=True)
    fixtures, failures = {}, dict(MISSING_FIXTURES)

    def attempt(key, fn):
        try:
            p = fn()
            assert p.is_file() and p.stat().st_size, "fixture generator produced nothing"
            fixtures[key] = p
        except Exception as exc:
            failures[key] = f"Fixture generation failed: {error_text(exc)}"

    base = Image.new("RGB", (96, 64), (30, 120, 200))
    ImageDraw.Draw(base).rectangle((5, 5, 45, 55), fill=(230, 60, 20))
    for ext, fmt in [
        ("jpg", "JPEG"),
        ("png", "PNG"),
        ("webp", "WEBP"),
        ("tiff", "TIFF"),
        ("bmp", "BMP"),
        ("heic", "HEIF"),
        ("avif", "AVIF"),
    ]:

        def image_fixture(ext=ext, fmt=fmt):
            if ext == "heic":
                import pillow_heif

                pillow_heif.register_heif_opener()
            p = root / f"صورة spaced.{ext}"
            base.save(p, fmt)
            return p

        attempt("." + ext, image_fixture)
    svg = root / "صورة spaced.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64">'
        '<rect width="96" height="64" fill="teal"/>'
        '<rect x="5" y="5" width="40" height="50" fill="red"/></svg>'
    )
    fixtures[".svg"] = svg
    for ext, codec in [
        ("wav", "pcm_s16le"),
        ("mp3", "libmp3lame"),
        ("flac", "flac"),
        ("ogg", "libvorbis"),
        ("opus", "libopus"),
        ("m4a", "aac"),
        ("aiff", "pcm_s16be"),
        ("wma", "wmav2"),
    ]:

        def audio_fixture(ext=ext, codec=codec):
            p = root / f"صوت spaced.{ext}"
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1.2",
                    "-c:a",
                    codec,
                    str(p),
                ]
            )
            return p

        attempt("." + ext, audio_fixture)
    for ext in ("mp4", "mov", "mkv", "webm", "avi", "wmv", "gif"):

        def video_fixture(ext=ext):
            p = root / f"فيديو spaced.{ext}"
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1.2:size=160x120:rate=10",
            ]
            if ext != "gif":
                cmd += [
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1.2",
                    "-shortest",
                ]
            if ext in ("mp4", "mov", "mkv", "webm"):
                cmd += ["-pix_fmt", "yuv420p"]
            run(cmd + [str(p)])
            return p

        attempt("." + ext, video_fixture)
    pdf = root / "مستند landscape.pdf"
    with fitz.open() as doc:
        for n in range(2):
            page = doc.new_page(width=720, height=405)
            page.insert_text((40, 70), f"Kumquat page {n + 1} - 42", fontsize=22)
            page.insert_text((590, 350), "Edge 911", fontsize=14)
        doc.save(pdf)
    fixtures[".pdf"] = pdf
    for ext, content in [
        ("md", "# Kumquat\n\nKumquat body 42.\n"),
        ("txt", "Kumquat body 42.\nSecond line 911.\n"),
        ("rtf", r"{\rtf1\ansi Kumquat body 42.\par Second line 911.}"),
    ]:
        p = root / f"ملاحظة spaced.{ext}"
        p.write_text(content, encoding="utf-8")
        fixtures["." + ext] = p
    attempt(
        ".docx", lambda: office(fixtures[".txt"], "docx:MS Word 2007 XML", root, ".docx")
    )
    epub = root / "كتاب spaced.epub"

    def epub_fixture():
        run(
            [
                "pandoc",
                str(fixtures[".md"]),
                "-o",
                str(epub),
                "--metadata=title:Kumquat",
            ]
        )
        return epub

    attempt(".epub", epub_fixture)
    for ext, delimiter in [("csv", ","), ("tsv", "\t")]:
        p = root / f"جدول spaced.{ext}"
        with p.open("w", newline="") as stream:
            csv.writer(stream, delimiter=delimiter).writerows(
                [["Kumquat", "Value"], ["row", 42]]
            )
        fixtures["." + ext] = p

    def xlsx_fixture():
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.append(["Kumquat", "Value"])
        wb.active.append(["row", 42])
        p = root / "جدول spaced.xlsx"
        wb.save(p)
        return p

    attempt(".xlsx", xlsx_fixture)
    for ext, spec in [("xls", "xls:MS Excel 97"), ("ods", "ods")]:
        attempt(
            "." + ext,
            lambda ext=ext, spec=spec: office(fixtures[".xlsx"], spec, root, "." + ext),
        )

    def pptx_fixture():
        from pptx import Presentation
        from pptx.util import Inches

        prs = Presentation()
        prs.slide_width, prs.slide_height = Inches(10), Inches(5.625)
        for n in range(2):
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
            box.text_frame.text = f"Kumquat slide {n + 1} 42"
        p = root / "شرائح spaced.pptx"
        prs.save(p)
        return p

    attempt(".pptx", pptx_fixture)
    attempt(
        ".ppt", lambda: office(fixtures[".pptx"], "ppt:MS PowerPoint 97", root, ".ppt")
    )
    for ext, content in [
        (
            "srt",
            "1\n00:00:01,000 --> 00:00:02,000\nKumquat\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\n42\n",
        ),
        (
            "vtt",
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nKumquat\n\n"
            "00:00:03.000 --> 00:00:04.000\n42\n",
        ),
    ]:
        p = root / f"ترجمة spaced.{ext}"
        p.write_text(content)
        fixtures["." + ext] = p
    z = root / "أرشيف spaced.zip"
    with zipfile.ZipFile(z, "w") as archive:
        archive.writestr("folder/hello.txt", PAYLOAD)
    fixtures[".zip"] = z
    for ext, mode in [("tar", "w"), ("tar.gz", "w:gz"), ("tgz", "w:gz")]:
        p = root / f"أرشيف spaced.{ext}"
        with tarfile.open(p, mode) as archive:
            member = tarfile.TarInfo("folder/hello.txt")
            member.size = len(PAYLOAD)
            archive.addfile(member, io.BytesIO(PAYLOAD))
        fixtures["." + ext] = p
    g = root / "hello.txt.gz"
    g.write_bytes(gzip.compress(PAYLOAD))
    fixtures[".gz"] = g
    attempt(".rar", lambda: make_rar_fixture(root / "أرشيف spaced.rar"))
    for alias, canonical in {
        ".jpeg": ".jpg",
        ".tif": ".tiff",
        ".heif": ".heic",
        ".aif": ".aiff",
        ".markdown": ".md",
    }.items():

        def alias_fixture(alias=alias, canonical=canonical):
            p = root / ("alias Unicode Ω" + alias)
            shutil.copyfile(fixtures[canonical], p)
            return p

        attempt(alias, alias_fixture)
    return fixtures, failures


def image_evidence(path: Path, expected=None) -> dict:
    with Image.open(path) as image:
        image.load()
        assert image.width > 0 and image.height > 0
        if expected is not None:
            assert image.size == expected, f"dimensions {image.size} != {expected}"
        assert max(ImageStat.Stat(image.convert("RGB")).var) > 0.1, "blank image"
        return {"dimensions": list(image.size), "format": image.format}


def validate_output(out: Path, *, category: str, source_key: str) -> dict:
    """Substantive gates, deliberately stronger than file-exists/magic checks."""
    assert out.is_file() and out.stat().st_size, "missing or empty output"
    ext = out.suffix.lower()
    evidence = {"bytes": out.stat().st_size, "sha256": digest(out)}
    if category in ("audio", "video"):
        data = json.loads(
            run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(out),
                ]
            ).stdout
        )
        streams = data["streams"]
        duration = float(data["format"].get("duration", 0))
        assert 0.8 <= duration <= 1.8, f"wrong duration {duration}"
        kinds = {s["codec_type"] for s in streams}
        if category == "audio" or ext in (
            ".mp3",
            ".m4a",
            ".wav",
            ".flac",
            ".ogg",
            ".opus",
            ".aiff",
            ".wma",
        ):
            assert kinds == {"audio"}, f"wrong streams {kinds}"
        else:
            assert "video" in kinds
            for stream in streams:
                if stream["codec_type"] == "video":
                    assert (stream["width"], stream["height"]) == (160, 120)
            if ext != ".gif" and source_key != ".gif":
                assert "audio" in kinds, "audio stream lost"
        run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "null", "-"])
        evidence.update(duration=duration, streams=sorted(kinds))
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".heic", ".avif"):
        evidence.update(image_evidence(out, (96, 64) if category == "images" else None))
        if category in ("pdf", "slides"):
            pages = sorted(out.parent.glob("*." + ext[1:]))
            assert len(pages) == 2, f"{category} image conversion lost pages/slides"
            evidence["rendered_pages"] = len(pages)
            evidence["page_images"] = []
            for p in pages:
                info = image_evidence(p, (3000, 1688))
                evidence["page_images"].append(
                    {"name": p.name, "sha256": digest(p), **info}
                )
            assert len({p["sha256"] for p in evidence["page_images"]}) == 2, (
                "distinct pages/slides became duplicate images"
            )
    elif ext == ".pdf":
        with fitz.open(out) as doc:
            assert doc.page_count == (2 if category == "slides" else 1)
            text = "\n".join(p.get_text() for p in doc)
            if category != "images":
                assert TOKEN in text, "PDF lost fixture text"
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                assert len(set(pix.samples)) > 1, "blank PDF render"
            evidence.update(pages=doc.page_count, text_token_present=TOKEN in text)
    elif ext in (".docx", ".pptx", ".xlsx", ".ods", ".epub"):
        with zipfile.ZipFile(out) as package:
            assert package.testzip() is None
            names = package.namelist()
            if ext == ".docx":
                body = ET.fromstring(package.read("word/document.xml"))
                assert TOKEN in "".join(body.itertext()), "DOCX body text lost"
            elif ext == ".pptx":
                slides = [
                    n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
                ]
                assert len(slides) == 2, f"expected two slides, got {len(slides)}"
                assert all(
                    TOKEN in "".join(ET.fromstring(package.read(n)).itertext())
                    for n in slides
                )
                presentation = ET.fromstring(package.read("ppt/presentation.xml"))
                size = presentation.find(
                    "{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz"
                )
                assert size is not None
                assert (int(size.attrib["cx"]), int(size.attrib["cy"])) == (
                    9144000,
                    5143500,
                )
                rendered = office(
                    out, "pdf:impress_pdf_Export", out.parent / "roundtrip", ".pdf"
                )
                with fitz.open(rendered) as pdf:
                    assert len(pdf) == 2
                    assert all("Edge 911" in p.get_text() for p in pdf), (
                        "landscape edge text clipped"
                    )
                    for n in (0, 1):
                        path = out.parent / f"representative-slide-{n + 1}.png"
                        pdf[n].get_pixmap().save(path)
                        image_evidence(path)
                evidence.update(
                    slides=len(slides),
                    dimensions_emu=dict(size.attrib),
                    rendered_slides=2,
                )
            elif ext == ".xlsx":
                from openpyxl import load_workbook

                wb = load_workbook(out, read_only=True, data_only=True)
                values = [
                    str(v)
                    for sheet in wb
                    for row in sheet.values
                    for v in row
                    if v is not None
                ]
                wb.close()
                assert TOKEN in " ".join(values), "XLSX cells lost"
                assert any("42" in v for v in values), "numeric cell/text lost"
                evidence["nonempty_cells"] = len(values)
            elif ext == ".ods":
                assert TOKEN in package.read("content.xml").decode(), "ODS cells lost"
                assert "42" in package.read("content.xml").decode()
            else:
                assert package.read("mimetype") == b"application/epub+zip"
                assert any(
                    TOKEN in package.read(n).decode(errors="replace")
                    for n in names
                    if n.endswith((".html", ".xhtml"))
                ), "EPUB body lost"
            evidence["zip_members"] = len(names)
    elif ext in (".txt", ".md", ".html", ".csv", ".tsv", ".srt", ".vtt"):
        text = out.read_text(encoding="utf-8-sig")
        assert TOKEN in text and "42" in text, "substantive text/numeric content lost"
        if ext in (".csv", ".tsv"):
            rows = list(
                csv.reader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ",")
            )
            assert len(rows) == 2 and all(len(r) == 2 for r in rows), (
                f"wrong cells: {rows}"
            )
            assert rows[1][1] == "42"
            evidence["rows"] = rows
        if ext in (".srt", ".vtt"):
            assert text.count("-->") == 2 and "\n42" in text
            assert (text.startswith("WEBVTT")) == (ext == ".vtt")
            evidence["cues"] = 2
        evidence["text_token_present"] = True
    elif ext in (".zip", ".tar", ".gz"):
        unpacked = out.parent / "validated-unpacked"
        extract_archive(out, unpacked)
        members = [p for p in unpacked.rglob("*") if p.is_file()]
        assert len(members) == 1 and members[0].read_bytes() == PAYLOAD, (
            "archive member content lost"
        )
        assert all(unpacked.resolve() in p.resolve().parents for p in members)
        evidence["members"] = [p.relative_to(unpacked).as_posix() for p in members]
    else:
        raise AssertionError(f"No content validator for output {ext}")
    return evidence


def error_text(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, subprocess.CalledProcessError):
        text += " | " + str(exc.stderr or exc.stdout or "")[-1800:]
    return text


def edge_cases(fixtures: dict[str, Path], root: Path) -> list[dict]:
    results = []
    for ext in ("zip", "tar"):

        def traversal(ext=ext):
            bad = root / ("traversal." + ext)
            if ext == "zip":
                with zipfile.ZipFile(bad, "w") as archive:
                    archive.writestr("../escaped.txt", PAYLOAD)
            else:
                with tarfile.open(bad, "w") as archive:
                    info = tarfile.TarInfo("../escaped.txt")
                    info.size = len(PAYLOAD)
                    archive.addfile(info, io.BytesIO(PAYLOAD))
            before = digest(bad)
            try:
                extract_archive(bad, root / ("unpack-" + ext))
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe member accepted")
            assert not (root / "escaped.txt").exists() and digest(bad) == before
            return {"source_preserved": True, "traversal_rejected": True}

        results.append(exercise(f"edge:traversal:{ext}", traversal))
    for category in (
        "images",
        "audio",
        "video",
        "pdf",
        "documents",
        "spreadsheets",
        "subtitles",
        "archives",
        "slides",
    ):
        conv = next(
            c
            for c in REGISTRY
            if c.category == category
            and c.output_ext != ".pages"
            and c.inputs[0] in fixtures
        )

        def collision(conv=conv):
            src = fixtures[conv.inputs[0]]
            dest_dir = root / "collisions" / conv.category
            first = apply_conversion(conv.id, src, dest_dir)
            before = digest(first)
            second = apply_conversion(conv.id, src, dest_dir)
            assert first != second, (
                "existing output overwritten instead of new collision-safe name"
            )
            assert digest(first) == before
            return {"source_preserved": True, "first_output_preserved": True}

        results.append(exercise(f"edge:collision:{category}", collision))
    for category in (
        "images",
        "audio",
        "video",
        "pdf",
        "documents",
        "spreadsheets",
        "slides",
        "archives",
        "subtitles",
    ):
        conv = next(
            c
            for c in REGISTRY
            if c.category == category
            and c.output_ext != ".pages"
            and c.inputs[0] in fixtures
        )

        def corrupt(conv=conv):
            src = root / ("corrupt" + conv.inputs[0])
            src.write_bytes(b"not a valid format\x00\xff")
            before = digest(src)
            try:
                apply_conversion(conv.id, src, root / "corrupt-out" / conv.category)
            except BACKEND_ERRORS:
                raise
            except Exception:
                assert digest(src) == before
                return {"source_preserved": True, "invalid_input_rejected": True}
            raise AssertionError("invalid binary input was silently accepted")

        # Plain CSV/TXT aren't a corruptible binary format; use the binary first route.
        results.append(exercise(f"edge:corrupt:{category}", corrupt))
    return results + regression_edges(fixtures, root)


def regression_edges(fixtures: dict[str, Path], root: Path) -> list[dict]:
    """Small real-content regressions plus explicitly simulated backend absence."""
    from unittest.mock import patch

    results = []
    routes = [
        ("ffmpeg", "audio-wav-to-mp3", ".wav"),
        ("soffice-doc", "doc-txt-to-docx", ".txt"),
        ("soffice-sheet", "sheet-csv-to-pdf", ".csv"),
        ("soffice-slide", "slide-pptx-to-pdf", ".pptx"),
        ("soffice-pdf", "pdf-to-pptx", ".pdf"),
        ("pandoc", "doc-md-to-epub", ".md"),
    ]
    for backend, route, key in routes:

        def missing_backend(route=route, key=key):
            # This is a fault-injection test, not a claim a backend is absent.
            with patch("shutil.which", return_value=None):
                try:
                    apply_conversion(route, fixtures[key], root / "absent" / route)
                except BACKEND_ERRORS as exc:
                    assert str(exc)
                    return {"simulated_absence": True, "actionable_error": str(exc)}
                raise AssertionError("missing backend was silently accepted")

        results.append(exercise(f"edge:missing-backend:{backend}", missing_backend))

    def palette():
        src = root / "palette.png"
        image = Image.new("P", (96, 64))
        image.putpalette([200, 80, 20] + [0, 0, 0] * 255)
        image.save(src)
        before = digest(src)
        out = apply_conversion("image-png-to-jpg", src, root / "palette-out")
        with Image.open(out) as decoded:
            assert decoded.size == (96, 64)
            pixel = decoded.getpixel((0, 0))
            assert isinstance(pixel, tuple) and pixel[0] > 190
        assert digest(src) == before
        return {"source_preserved": True, "palette_pixels_decoded": True}

    results.append(exercise("edge:palette-png-to-jpg", palette))

    def tsv_sidecar():
        dest = root / "tsv-sidecar"
        dest.mkdir()
        sentinel = dest / (fixtures[".ods"].stem + ".csv")
        sentinel.write_text("Keep existing CSV")
        out = apply_conversion("sheet-ods-to-tsv", fixtures[".ods"], dest)
        assert sentinel.read_text() == "Keep existing CSV"
        assert len(list(dest.iterdir())) == 2
        return validate_output(out, category="spreadsheets", source_key=".ods")

    results.append(exercise("edge:tsv-private-bridge", tsv_sidecar))

    def no_cues():
        src = root / "no-cues.srt"
        src.write_text("No valid timing cues here")
        before = digest(src)
        try:
            apply_conversion("sub-srt-to-vtt", src, root / "no-cues-out")
        except ValueError as exc:
            assert "no subtitle cues" in str(exc) and digest(src) == before
            return {"source_preserved": True, "no_cues_rejected": True}
        raise AssertionError("subtitle with no cues silently accepted")

    results.append(exercise("edge:subtitle-without-cues", no_cues))
    return results


def exercise(ident: str, fn, *, timeout: float = 240) -> dict:
    """Bound conversion plus content checks; reap backend descendants on timeout.

    Linux fork preserves local callables without pickling fixture generator state.
    The worker owns a fresh process group; no unrelated desktop job is targeted.
    """
    cell = {"id": ident, "kind": "edge"}
    ctx = multiprocessing.get_context("fork")
    receiving, sending = ctx.Pipe(duplex=False)

    def worker():
        global _IN_WORKER
        _IN_WORKER = True
        os.setsid()
        try:
            result = {"evidence": fn(), "status": "PASS",
                      "reason": "Content/effect assertions passed"}
        except BACKEND_ERRORS as exc:
            result = {"status": "UNSUPPORTED", "reason": error_text(exc)}
        except Exception as exc:
            result = {"status": "FAIL", "reason": error_text(exc)}
        sending.send(result)
        sending.close()

    proc = ctx.Process(target=worker)
    proc.start()
    assert proc.pid is not None
    sending.close()
    try:
        if receiving.poll(timeout):
            try:
                cell.update(receiving.recv())
            except EOFError:
                cell.update(status="FAIL", reason="Worker exited without a result")
        else:
            cell.update(status="FAIL",
                        reason=f"Conversion/validation timeout after {timeout}s")
    finally:
        # Also clear any surviving subprocess after a worker-reported failure.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join()
        receiving.close()
    return cell


def checkpoint(path: Path, cells: list[dict], *, phase: str, **extra) -> None:
    """Atomically persist every pending/completed inventory cell after each route."""
    report = {
        "schema_version": 2, "complete": False, "phase": phase,
        "conversion_cell_count": len(cells), "conversion_totals": totals(cells),
        "conversions": cells, **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".pending")
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    pending.replace(path)


def totals(cells: list[dict]) -> dict:
    return {
        s: sum(c["status"] == s for c in cells)
        for s in ("PASS", "FAIL", "UNSUPPORTED", "UNTESTED")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=Path("tests/qa_matrix.json"))
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    root = args.work_dir or Path(tempfile.mkdtemp(prefix="kumquat-full-sweep-"))
    if args.work_dir:
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            parser.error("--work-dir must be empty (no existing data will be touched)")
    cells = [dict(c, status="UNTESTED", reason="Not yet executed")
             for c in conversion_inventory()]
    assert len({c["id"] for c in cells}) == len(cells), "Duplicate registry input cell"
    declared = declared_inventory()
    started = time.monotonic()
    source_dir = Path(_registry_data.__file__).parent
    code_hashes = {
        p.name: digest(p)
        for p in sorted(source_dir.glob("converters_*.py"))
    }
    code_hashes["qa_full_sweep.py"] = digest(Path(__file__))
    checkpoint(args.json, cells, phase="fixtures", declared_gui_inventory=declared)
    fixtures, fixture_errors = build_fixtures(root / "fixtures")
    original_hashes = {key: digest(p) for key, p in fixtures.items()}
    for cell in cells:
        key = cell["source_key"]
        if key not in fixtures:
            cell.update(
                status="UNTESTED",
                reason=fixture_errors.get(key, "No real fixture generator"),
            )
        else:
            src = fixtures[key]

            def convert_and_validate(cell=cell, src=src, key=key):
                dest = root / "outputs" / cell["route_id"] / key.lstrip(".")
                out = apply_conversion(cell["route_id"], src, dest)
                assert digest(src) == original_hashes[key], "SOURCE MODIFIED"
                evidence = validate_output(out, category=cell["category"], source_key=key)
                evidence.update(
                    source_preserved=True, source_sha256=original_hashes[key],
                    output=out.relative_to(root).as_posix(),
                )
                return evidence

            result = exercise(cell["id"], convert_and_validate)
            cell.update({k: v for k, v in result.items() if k not in ("id", "kind")})
            cell["source_sha256_before"] = original_hashes[key]
            cell["source_sha256_after"] = digest(src)
            if cell["source_sha256_after"] != original_hashes[key]:
                cell.update(status="FAIL", reason="SOURCE MODIFIED")
        checkpoint(args.json, cells, phase="conversions", fixture_hashes=original_hashes,
                   fixture_errors=fixture_errors, declared_gui_inventory=declared)
        print(cell["status"], cell["id"], cell["reason"], flush=True)
    checkpoint(args.json, cells, phase="edges", fixture_hashes=original_hashes,
               fixture_errors=fixture_errors, declared_gui_inventory=declared)
    edges = edge_cases(fixtures, root)
    preserved = all(digest(p) == original_hashes[k] for k, p in fixtures.items())
    by_category = {
        k: totals([c for c in cells if c["category"] == k])
        for k in sorted({c["category"] for c in cells})
    }
    route_results = []
    priority = {"PASS": 0, "UNSUPPORTED": 1, "UNTESTED": 2, "FAIL": 3}
    for route in REGISTRY:
        aliases = [c for c in cells if c["route_id"] == route.id]
        worst = max(aliases, key=lambda c: priority[c["status"]])
        route_results.append(
            {
                "route_id": route.id,
                "category": route.category,
                "status": worst["status"],
                "reason": worst["reason"],
                "source_keys": [c["source_key"] for c in aliases],
                "source_keys_exercised": [
                    c["source_key"] for c in aliases if c["status"] != "UNTESTED"
                ],
            }
        )
    expected = Counter((c["route_id"], c["source_key"])
                       for c in conversion_inventory())
    actual = Counter((c["route_id"], c["source_key"]) for c in cells)
    assert actual == expected and all(n == 1 for n in actual.values())
    assert Counter(c["route_id"] for c in route_results) == Counter(
        c.id for c in REGISTRY
    )
    assert all(c["status"] in totals(cells) and c["reason"] for c in cells)
    declared = declared_inventory()
    reasons = defaultdict(list)
    for c in cells + edges:
        if c["status"] != "PASS":
            reasons[c["status"] + ": " + c["reason"]].append(c["id"])
    report = {
        "schema_version": 2,
        "complete": True,
        "phase": "complete",
        "scope": "All registry routes and input aliases; synthetic local corpus only",
        "registry_route_count": len(REGISTRY),
        "coverage_checks": {
            "every_route_exactly_once": True,
            "every_route_input_pair_exactly_once": True,
            "missing_route_ids": [], "duplicate_route_ids": [],
            "fixture_set": (
                "synthetic Unicode/spaces; one genuine fixture per available key"
            ),
        },
        "conversion_cell_count": len(cells),
        "conversion_totals": totals(cells),
        "route_totals": totals(route_results),
        "by_category": by_category,
        "edge_totals": totals(edges),
        "declared_tool_ids": TOOLS,
        "declared_action_ids": ACTIONS,
        "declared_inventory_totals": totals(declared),
        "source_preservation": preserved,
        "code_sha256": code_hashes,
        "fixture_hashes": original_hashes,
        "fixture_errors": fixture_errors,
        "routes": route_results,
        "conversions": cells,
        "edges": edges,
        "declared_gui_inventory": declared,
        "nonpass_by_reason": dict(reasons),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "corpus_location": "runtime scratch only (not shipped)",
        "backend_paths": {
            x: bool(shutil.which(x)) for x in ("ffmpeg", "ffprobe", "soffice", "pandoc")
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "routes": report["route_totals"],
                "conversion_cells": report["conversion_totals"],
                "edges": report["edge_totals"],
                "declared_gui": report["declared_inventory_totals"],
                "sources_preserved": preserved,
            },
            indent=2,
        )
    )
    for edge in edges:
        print(edge["status"], edge["id"], edge["reason"])
    return int(not preserved or any(c["status"] == "FAIL" for c in cells + edges))


if __name__ == "__main__":
    raise SystemExit(main())

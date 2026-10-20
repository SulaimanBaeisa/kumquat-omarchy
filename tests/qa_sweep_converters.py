"""Exhaustive QA sweep: build a real fixture per input format, then run
EVERY registry conversion row end-to-end through apply_conversion.

Prints a per-category table and a final PASS/FAIL/SKIP count.
Exit code 0 only when there are zero FAILs.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402

from kumquat import registry_data  # noqa: F401,E402
from kumquat.apply import apply_conversion  # noqa: E402
from kumquat.registry import REGISTRY  # noqa: E402

FIX = Path("/tmp/qa-fixtures")
OUT = Path("/tmp/qa-out")


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def build_fixtures() -> dict[str, Path]:
    """One real file per registry input extension. Best-effort for exotic types."""
    FIX.mkdir(parents=True, exist_ok=True)
    f: dict[str, Path] = {}

    base = Image.new("RGB", (64, 48), (30, 120, 200))
    for ext, fmt in [("jpg", "JPEG"), ("png", "PNG"), ("webp", "WEBP"),
                     ("tiff", "TIFF"), ("bmp", "BMP")]:
        p = FIX / f"pic.{ext}"
        base.save(p, fmt)
        f[ext] = p

    # heic/avif need pillow-heif
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        for ext in ("heic", "avif"):
            p = FIX / f"pic.{ext}"
            base.save(p, "HEIF" if ext == "heic" else "AVIF")
            f[ext] = p
    except Exception as e:  # pragma: no cover - backend absent
        print(f"  [fixture] heic/avif unavailable: {e}")

    svg = FIX / "pic.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" '
                   'height="48"><rect width="64" height="48" fill="teal"/>'
                   '</svg>')
    f["svg"] = svg

    # audio
    for ext, codec in [("wav", "pcm_s16le"), ("mp3", "libmp3lame"),
                       ("flac", "flac"), ("ogg", "libvorbis"),
                       ("opus", "libopus"), ("m4a", "aac"),
                       ("aiff", "pcm_s16be"), ("wma", "wmav2")]:
        p = FIX / f"snd.{ext}"
        try:
            sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1", "-c:a", codec, str(p)])
            f[ext] = p
        except Exception as e:
            print(f"  [fixture] audio {ext} failed: {e}")

    # video
    for ext in ("mp4", "mov", "mkv", "webm", "avi", "wmv"):
        p = FIX / f"vid.{ext}"
        try:
            sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-shortest", str(p)])
            f[ext] = p
        except Exception as e:
            print(f"  [fixture] video {ext} failed: {e}")

    gif = FIX / "vid.gif"
    sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "testsrc=duration=1:size=80x60:rate=5", str(gif)])
    f["gif"] = gif

    # pdf — a real TEXT pdf so pdf->txt/md extract actual content
    txtseed = FIX / "seed.txt"
    txtseed.write_text("Hello PDF text.\nSecond line.\n")
    try:
        sh(["soffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(FIX), str(txtseed)])
        pdf = FIX / "seed.pdf"
        if pdf.exists():
            pdf.rename(FIX / "doc.pdf")
            f["pdf"] = FIX / "doc.pdf"
        else:
            raise RuntimeError("soffice produced no pdf")
    except Exception:
        pdf = FIX / "doc.pdf"
        base.save(pdf, "PDF")
        f["pdf"] = pdf

    # documents
    md = FIX / "note.md"
    md.write_text("# Title\n\nHello world.\n")
    f["md"] = md
    txt = FIX / "note.txt"
    txt.write_text("Hello world.\nSecond line.\n")
    f["txt"] = txt
    rtf = FIX / "note.rtf"
    rtf.write_text(r"{\rtf1\ansi Hello world.}")
    f["rtf"] = rtf

    for ext in ("docx", "odt"):
        p = FIX / f"note.{ext}"
        try:
            sh(["soffice", "--headless", "--convert-to", ext,
                "--outdir", str(FIX), str(txt)])
            if p.exists():
                f[ext] = p
        except Exception as e:
            print(f"  [fixture] {ext} failed: {e}")

    # spreadsheets
    csv = FIX / "sheet.csv"
    csv.write_text("a,b\n1,2\n")
    f["csv"] = csv
    tsv = FIX / "sheet.tsv"
    tsv.write_text("a\tb\n1\t2\n")
    f["tsv"] = tsv
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["a", "b"])
        ws.append([1, 2])
        xlsx = FIX / "sheet.xlsx"
        wb.save(xlsx)
        f["xlsx"] = xlsx
    except Exception as e:
        print(f"  [fixture] xlsx failed: {e}")
    for ext in ("ods",):
        p = FIX / f"sheet.{ext}"
        try:
            sh(["soffice", "--headless", "--convert-to", ext,
                "--outdir", str(FIX), str(csv)])
            if p.exists():
                f[ext] = p
        except Exception as e:
            print(f"  [fixture] {ext} failed: {e}")

    # slides — pptx from python-pptx (a real deck), ppt via LibreOffice
    try:
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(0, 0, 1000, 500)
        box.text_frame.text = "Hello slide"
        deck = FIX / "deck.pptx"
        prs.save(deck)
        f["pptx"] = deck
        try:
            sh(["soffice", "--headless", "--convert-to", "ppt",
                "--outdir", str(FIX), str(deck)])
            if (FIX / "deck.ppt").exists():
                f["ppt"] = FIX / "deck.ppt"
        except Exception:
            pass
    except ImportError:
        print("  [fixture] pptx skipped: python-pptx not installed")

    # xls via LibreOffice from the xlsx fixture
    if "xlsx" in f:
        try:
            sh(["soffice", "--headless", "--convert-to", "xls",
                "--outdir", str(FIX), str(f["xlsx"])])
            if (FIX / "sheet.xls").exists():
                f["xls"] = FIX / "sheet.xls"
        except Exception:
            pass

    # epub via pandoc
    if shutil.which("pandoc"):
        try:
            sh(["pandoc", str(md), "-o", str(FIX / "book.epub")])
            f["epub"] = FIX / "book.epub"
        except Exception:
            pass

    # subtitles
    srt = FIX / "subs.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
                   "2\n00:00:03,000 --> 00:00:04,000\n42\n")
    f["srt"] = srt
    vtt = FIX / "subs.vtt"
    vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n")
    f["vtt"] = vtt

    # archives
    z = FIX / "arc.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("hello.txt", "hi")
    f["zip"] = z
    t = FIX / "arc.tar"
    with __import__("tarfile").open(t, "w") as tf:
        tf.add(txt, arcname="hello.txt")
    f["tar"] = t
    g = FIX / "arc.gz"
    import gzip
    g.write_bytes(gzip.compress(b"hello\n"))
    f["gz"] = g

    # 7z / rar / pages / rtfd / textClipping: genuinely hard or impossible
    # to author locally -> documented SKIPs, not silent passes.
    return f


# registry category -> input extension(s) it accepts
def main() -> int:
    print("== fixtures ==")
    fx = build_fixtures()
    print(f"  built {len(fx)}: {' '.join(sorted(fx))}\n")

    # Every row: pick the fixture whose extension matches one of its inputs.
    results = {"PASS": [], "FAIL": [], "SKIP": []}
    OUT.mkdir(parents=True, exist_ok=True)

    for conv in REGISTRY:
        exts = [i.lstrip(".") for i in conv.inputs if i.startswith(".")]
        src = next((fx[e] for e in exts if e in fx), None)
        if src is None:
            results["SKIP"].append((conv.id, f"no fixture for {exts}"))
            continue
        dest = OUT / conv.id
        try:
            out = apply_conversion(conv.id, src, dest)
            ok = Path(out).exists() and Path(out).stat().st_size > 0
            results["PASS" if ok else "FAIL"].append(
                (conv.id, "empty output" if not ok else ""))
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            # backend-missing is an honest skip; everything else is a failure
            if "backend" in msg.lower() or "not installed" in msg.lower():
                results["SKIP"].append((conv.id, msg[:90]))
            else:
                results["FAIL"].append((conv.id, msg[:120]))

    total = sum(len(v) for v in results.values())
    print(f"== conversions: {total} registry rows ==")
    print(f"  PASS {len(results['PASS'])}  FAIL {len(results['FAIL'])}"
          f"  SKIP {len(results['SKIP'])}\n")

    if results["FAIL"]:
        print("-- FAILURES --")
        for cid, why in results["FAIL"]:
            print(f"  {cid}: {why}")
        print()
    if results["SKIP"]:
        print("-- SKIPPED (no fixture / backend absent) --")
        seen = {}
        for cid, why in results["SKIP"]:
            seen.setdefault(why.split(":")[0], []).append(cid)
        for why, ids in seen.items():
            print(f"  {len(ids):3d}  {why}  e.g. {ids[:3]}")
        print()

    return 1 if results["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

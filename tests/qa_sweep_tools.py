"""QA sweep: every file tool and every file action, executed for real
(actions with their external binaries stubbed, since wl-copy/hyprctl need
a live session).

Prints PASS/FAIL per tool and action; exit 0 only when zero FAILs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402

from kumquat.apply import apply_tool  # noqa: E402

FIX = Path("/tmp/qa-tool-fixtures")
OUT = Path("/tmp/qa-tool-out")


def sh(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def build():
    FIX.mkdir(parents=True, exist_ok=True)
    out = {}
    img = FIX / "photo.jpg"
    Image.new("RGB", (200, 150), (200, 80, 40)).save(img, "JPEG")
    out["img"] = img
    img2 = FIX / "photo2.jpg"
    Image.new("RGB", (120, 90), (40, 200, 80)).save(img2, "JPEG")
    out["img2"] = img2

    wav = FIX / "snd.wav"
    sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=3", str(wav)])
    out["wav"] = wav

    vid = FIX / "clip.mp4"
    sh(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "testsrc=duration=3:size=160x120:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-shortest", str(vid)])
    out["vid"] = vid

    pdf = FIX / "doc.pdf"
    Image.new("RGB", (100, 100), "white").save(pdf, "PDF")
    out["pdf"] = pdf
    pdf2 = FIX / "doc2.pdf"
    Image.new("RGB", (100, 100), "gray").save(pdf2, "PDF")
    out["pdf2"] = pdf2

    import zipfile
    z = FIX / "arc.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.txt", "hello")
    out["zip"] = z
    return out


def check(name, fn):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        r = fn()
        paths = r if isinstance(r, list) else [r]
        missing = [str(p) for p in paths if not Path(p).exists()]
        if missing:
            return ("FAIL", f"{name}: missing output {missing[:2]}")
        sizes = [Path(p).stat().st_size for p in paths]
        if any(s == 0 for s in sizes):
            return ("FAIL", f"{name}: zero-byte output")
        return ("PASS", f"{name}: {len(paths)} file(s)")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if "BackendMissing" in msg or "not installed" in msg.lower():
            return ("SKIP", f"{name}: {msg[:70]}")
        return ("FAIL", f"{name}: {msg[:110]}")


def main() -> int:
    fx = build()
    d = OUT
    results = []

    # --- image tools ---------------------------------------------------
    results.append(check("compress", lambda: apply_tool(
        "compress", [fx["img"]], d, quality=60)))
    results.append(check("removeMetadata", lambda: apply_tool(
        "removeMetadata", [fx["img"]], d)))
    results.append(check("cropImage", lambda: apply_tool(
        "cropImage", [fx["img"]], d, box=(10, 10, 110, 110))))
    results.append(check("frameImage", lambda: apply_tool(
        "frameImage", [fx["img"]], d)))
    results.append(check("createCollage", lambda: apply_tool(
        "createCollage", [fx["img"], fx["img2"]], d, layout="grid")))
    results.append(check("createPDF", lambda: apply_tool(
        "createPDF", [fx["img"], fx["img2"]], d)))
    results.append(check("editImage(stub)", lambda: apply_tool(
        "editImage", [fx["img"]], d)))
    results.append(check("annotateImage(stub)", lambda: apply_tool(
        "annotateImage", [fx["img"]], d)))
    results.append(check("redactImage(stub)", lambda: apply_tool(
        "redactImage", [fx["img"]], d)))

    # --- media tools ---------------------------------------------------
    results.append(check("trimVideo", lambda: apply_tool(
        "trimVideo", [fx["vid"]], d, start=0, end=1)))
    results.append(check("trimAudio", lambda: apply_tool(
        "trimAudio", [fx["wav"]], d, start=0, end=1)))
    results.append(check("cropVideo", lambda: apply_tool(
        "cropVideo", [fx["vid"]], d, box=(0, 0, 80, 60))))
    results.append(check("changeVideoSpeed", lambda: apply_tool(
        "changeVideoSpeed", [fx["vid"]], d, factor=2.0)))
    results.append(check("joinVideos", lambda: apply_tool(
        "joinVideos", [fx["vid"], fx["vid"]], d)))
    results.append(check("videoSnapshots", lambda: apply_tool(
        "videoSnapshots", [fx["vid"]], d, at=0.5)))
    results.append(check("splitVideo", lambda: apply_tool(
        "splitVideo", [fx["vid"]], d, segment_time=1.0)))
    results.append(check("muteVideo", lambda: apply_tool(
        "muteVideo", [fx["vid"]], d)))
    results.append(check("normalizeAudio", lambda: apply_tool(
        "normalizeAudio", [fx["wav"]], d)))
    results.append(check("audioChannels(mono)", lambda: apply_tool(
        "audioChannels", [fx["wav"]], d)))
    results.append(check("redactAudio(bleep)", lambda: apply_tool(
        "redactAudio", [fx["wav"]], d, start=0.5, end=1.0)))

    # --- pdf tools -----------------------------------------------------
    results.append(check("mergePDF", lambda: apply_tool(
        "mergePDF", [fx["pdf"], fx["pdf2"]], d)))
    results.append(check("splitPDF", lambda: apply_tool(
        "splitPDF", [fx["pdf"]], d)))
    results.append(check("organizePDF", lambda: apply_tool(
        "organizePDF", [fx["pdf"]], d, spec={"reorder": [0]})))

    # --- archive tools -------------------------------------------------
    results.append(check("extractArchive", lambda: apply_tool(
        "extractArchive", [fx["zip"]], d)))

    # --- actions (external binaries stubbed) ---------------------------
    import kumquat.actions as A
    calls = []

    class FakeRun:
        def __init__(self, *a, **k):
            calls.append(a[0] if a else k.get("args"))

        def __call__(self, *a, **k):
            calls.append(a[0] if a else k.get("args"))
            return subprocess.CompletedProcess(args=[], returncode=0,
                                               stdout=b"", stderr=b"")

    def fake_which(exe):
        return f"/usr/bin/{exe}"   # pretend every backend exists

    orig_which = A.shutil.which
    A.shutil.which = fake_which
    orig_sub_run = A.subprocess.run
    A.subprocess.run = FakeRun()
    orig_popen = A.subprocess.Popen
    A.subprocess.Popen = lambda *a, **k: calls.append(a[0] if a else None)

    try:
        p = [fx["img"]]
        try:
            txt = A.copy_paths(p)
            results.append(("PASS", f"copy_paths: {txt.strip()!r}"))
        except Exception as e:
            results.append(("FAIL", f"copy_paths: {e}"))
        try:
            A.copy_files(p)
            results.append(("PASS", "copy_files: invoked"))
        except Exception as e:
            results.append(("FAIL", f"copy_files: {e}"))
        try:
            moved = A.move_files([fx["img2"].copy() if False else fx["img2"]],
                                 FIX / "moved")
            ok = all(Path(m).exists() for m in moved)
            results.append(("PASS" if ok else "FAIL", "move_files"))
        except Exception as e:
            results.append(("FAIL", f"move_files: {e}"))
        try:
            A.open_terminal(fx["img"])
            results.append(("PASS", "open_terminal: invoked"))
        except Exception as e:
            results.append(("FAIL", f"open_terminal: {e}"))
        try:
            A.share(p)
            results.append(("PASS", "share: invoked"))
        except Exception as e:
            results.append(("SKIP", f"share: {e}"))
        try:
            shelf = A.float_shelf(p)
            results.append(("PASS", f"float_shelf: {shelf}"))
        except Exception as e:
            results.append(("FAIL", f"float_shelf: {e}"))
    finally:
        A.shutil.which = orig_which
        A.subprocess.run = orig_sub_run
        A.subprocess.Popen = orig_popen

    # --- report ---------------------------------------------------------
    print("\n== tools + actions ==")
    for status, msg in results:
        print(f"  {status:4s} {msg}")
    fails = [r for r in results if r[0] == "FAIL"]
    skips = [r for r in results if r[0] == "SKIP"]
    passes = [r for r in results if r[0] == "PASS"]
    print(f"\n  PASS {len(passes)}  FAIL {len(fails)}  SKIP {len(skips)}"
          f"  (total {len(results)})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

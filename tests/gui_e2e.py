"""Real-GTK end-to-end check of the user's flow (not collected by pytest).

Reproduces: SUPER+E opens ONE "Kumquat" window with an embedded file
browser -> one click on a file -> that file's conversions are listed. Then the
bottom Convert/Tools/Actions tab bar, Left/Right and A/D, double-click to
apply, and real background conversions with a live progress bar.

Run on a live Wayland session with the system Python (it has ``gi``):

    cd omarchy-plugin-kumquat      # your checkout
    WAYLAND_DISPLAY=wayland-1 PYTHONPATH=src /usr/bin/python3 tests/gui_e2e.py

Drives the real ``WheelWindow`` in-process through its public contract API
(``.stack``, ``.picker``, ``.listbox``, ``.files``, ``.mode``) and prints
PASS/FAIL per check. Exit 0 = all passed, 1 = any failure, 2 = could not even
start (no gi / no display / app code missing). A watchdog always quits.

Real conversions run on copies inside the e2e tempdir, never on
``/tmp/qa-fixtures`` itself.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

QA_DIR = Path("/tmp/qa-fixtures")
WATCHDOG_MS = 180_000  # real ffmpeg / LibreOffice jobs run below
STEP_MS = 60          # gap between steps so the main loop really iterates
JOB_TIMEOUT_S = 90    # one background conversion, start to finish
SAMPLE_S = 0.02       # gap between progress samples while a job runs
PROBE_AFTER_SAMPLES = 5  # poke the window this many samples into a job
RESPONSIVE_S = 0.5    # a key press during a job must return within this
# testsrc2 at 720p keeps libvpx busy for several seconds, so ffmpeg's 0.5 s
# progress ticks yield many measured fractions before the job ends.
TEST_VIDEO = "testsrc2=duration=6:size=1280x720:rate=30"
WORKING_RE = re.compile(r"^Working… (\d+) s$")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" -- {detail}" if detail else ""),
          flush=True)
    return bool(ok)


# --- fixtures ---------------------------------------------------------------

def build_fixtures() -> Path:
    """tmp/{pic.jpg, sub/inner.jpg, .hidden.txt}. JPEG via Pillow or a copy."""
    root = Path(tempfile.mkdtemp(prefix="kumquat-e2e-"))
    (root / "sub").mkdir()
    for target in (root / "pic.jpg", root / "sub" / "inner.jpg"):
        try:
            from PIL import Image
            Image.new("RGB", (8, 8), (255, 136, 0)).save(target, "JPEG")
        except Exception as exc:
            src = QA_DIR / "pic.jpg"
            if not src.exists():
                raise RuntimeError(
                    "no Pillow and no /tmp/qa-fixtures/pic.jpg") from exc
            shutil.copyfile(src, target)
    (root / ".hidden.txt").write_text("hidden\n")
    return root


def build_work_dir(root: Path) -> Path:
    """root/work/{pic.jpg, note.docx, big.mp4}: copies and a generated video."""
    work = root / "work"
    work.mkdir()
    shutil.copyfile(root / "pic.jpg", work / "pic.jpg")
    # A real, self-contained DOCX, not an optional leftover /tmp fixture.
    # Enough paragraphs to exercise an observable LibreOffice background job.
    import zipfile

    document = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body>'
                + '<w:p><w:r><w:t>Synthetic progress test document.</w:t></w:r></w:p>'
                * 3000 + '</w:body></w:document>')
    with zipfile.ZipFile(work / "note.docx", "w", zipfile.ZIP_DEFLATED) as doc:
        doc.writestr("word/document.xml", document)
        doc.writestr("[Content_Types].xml",
                     '<Types xmlns="http://schemas.openxmlformats.org/package/'
                     '2006/content-types"><Default Extension="rels" ContentType="'
                     'application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="'
                     'application/vnd.openxmlformats-officedocument.'
                     'wordprocessingml.document.main+xml"/></Types>')
        doc.writestr("_rels/.rels",
                     '<Relationships xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/relationships"><Relationship Id="rId1" Type="'
                     'http://schemas.openxmlformats.org/officeDocument/2006/'
                     'relationships/officeDocument" Target="word/document.xml"/>'
                     '</Relationships>')
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             TEST_VIDEO,
             "-pix_fmt", "yuv420p", str(work / "big.mp4")],
            check=True, timeout=JOB_TIMEOUT_S)
    return work


# --- widget helpers ---------------------------------------------------------

def walk(widget):
    """Depth-first over a widget and all its descendants."""
    if widget is None:
        return
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def labels_of(widget) -> list[str]:
    from gi.repository import Gtk
    return [w.get_text() for w in walk(widget) if isinstance(w, Gtk.Label)]


def row_texts(listbox) -> list[str]:
    out, i = [], 0
    while (row := listbox.get_row_at_index(i)) is not None:
        out.append(" ".join(labels_of(row)))
        i += 1
    return out


def find_by_class(root, css_class: str):
    for w in walk(root):
        if w.has_css_class(css_class):
            return w
    return None


def key_controllers(widget):
    from gi.repository import Gtk
    model = widget.observe_controllers()
    return [model.get_item(i) for i in range(model.get_n_items())
            if isinstance(model.get_item(i), Gtk.EventControllerKey)]


def send_key(widgets, keyval: int, release: bool = False) -> bool:
    """Emit key-pressed (and optionally key-released) on the first controller
    found on ``widgets`` (searched in order, descendants included)."""
    from gi.repository import Gdk
    for root in widgets:
        for w in walk(root):
            for ctl in key_controllers(w):
                handled = ctl.emit("key-pressed", keyval, 0, Gdk.ModifierType(0))
                if release:
                    ctl.emit("key-released", keyval, 0, Gdk.ModifierType(0))
                if handled:
                    return True
    return False


def page(w) -> str | None:
    return w.stack.get_visible_child_name()


def is_closed(app, w) -> bool:
    return w.win not in app.get_windows() or not w.win.get_visible()


def entry_index(picker, name: str) -> int:
    for i, entry in enumerate(picker.entries):
        if entry.name == name:
            return i
    return -1


def select_label(w, label: str):
    """Select the option row whose label is ``label``; return it (or None)."""
    labels = [lab for _id, lab in w.current_items()]
    if label not in labels:
        return None
    row = w.listbox.get_row_at_index(labels.index(label))
    w.listbox.select_row(row)
    return row


def drain() -> None:
    """Dispatch everything pending on the default main context."""
    from gi.repository import GLib
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


def run_job(w, probe=None) -> list[dict]:
    """Iterate the main loop while ``w`` is busy, sampling the progress bar.

    ``probe`` (if given) is called once, mid-job, with the live ``Job``.
    """
    job, samples = w._job, []
    deadline = time.monotonic() + JOB_TIMEOUT_S
    while w.busy and time.monotonic() < deadline:
        drain()
        bar = w.progress_bar
        samples.append({"visible": bar.get_visible(), "fraction": bar.get_fraction(),
                        "text": bar.get_text() or "", "running": job.running})
        if probe is not None and len(samples) == PROBE_AFTER_SAMPLES:
            probe(job)
        time.sleep(SAMPLE_S)
    drain()
    return samples


def outputs(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()}


# --- the scenario (a generator: every ``yield`` lets GTK iterate) ------------

def scenario(app, fixtures: Path):
    from gi.repository import Gdk

    from kumquat.gui.wheel import WheelWindow

    start = QA_DIR if (QA_DIR / "pic.jpg").exists() else fixtures
    pic = str(start / "pic.jpg")

    # 1. SUPER+E with nothing selected -> one window, picker page.
    w = WheelWindow(app, files=[], start_dir=str(start))
    w.win.present()
    yield
    check("window title is 'Kumquat'", w.win.get_title() == "Kumquat",
          repr(w.win.get_title()))
    check("starts on the 'picker' page", page(w) == "picker", repr(page(w)))
    check("picker page is framed as an opaque panel (no desktop bleed-through)",
          w.picker.has_css_class("kumquat-panel"))
    check("exactly one app window", len(app.get_windows()) == 1,
          f"{len(app.get_windows())} windows")
    chooser = [x for x in walk(w.win) if type(x).__name__ == "FileChooserWidget"]
    check("no GTK FileChooserWidget inside the window", not chooser)
    check("picker shows start_dir", Path(w.picker.current_dir) == start,
          w.picker.current_dir)

    # 2. One click on pic.jpg -> its conversions.
    i = entry_index(w.picker, "pic.jpg")
    if not check("pic.jpg listed in picker.entries", i >= 0,
                 f"{[e.name for e in w.picker.entries][:12]}"):
        return
    w.picker.activate_index(i)
    yield
    yield
    check("after one click: page is 'wheel'", page(w) == "wheel", repr(page(w)))
    check("after one click: files == [pic.jpg]", w.files == [pic], repr(w.files))
    check("mode is 0 (conversions)", w.mode == 0, repr(w.mode))
    rows = row_texts(w.listbox)
    check("listbox shows 'Convert to PNG'", any("Convert to PNG" in r for r in rows),
          f"{len(rows)} rows, first={rows[:3]}")
    check("first conversion row selected", w.listbox.get_selected_row() is not None
          and w.listbox.get_selected_row().get_index() == 0)

    # 3. Super held -> tools wheel.
    if hasattr(w, "set_mode"):
        w.set_mode(1)
        how = "set_mode(1)"
    elif send_key([w.win], Gdk.KEY_Super_L):
        how = "Super_L key-pressed"
    else:
        w.mode = 1
        getattr(w, "render", lambda: None)()
        how = "mode=1 + render()"
    yield
    rows = row_texts(w.listbox)
    check(f"tools mode via {how}: mode == 1", w.mode == 1, repr(w.mode))
    check("tools wheel shows 'COMPRESS'", any("COMPRESS" in r for r in rows),
          f"first={rows[:3]}")
    check("rows show labels only, no internal [ids]",
          not any("[" in r for r in rows), f"first={rows[:3]}")
    if how.startswith("Super"):
        send_key([w.win], Gdk.KEY_Super_L, release=True)
    yield

    # 4. 'Change files…' -> picker; picker Cancel with files -> back to wheel.
    change = find_by_class(w.win, "kumquat-change")
    if check("'Change files…' button present", change is not None):
        change.emit("clicked")
        yield
        check("'Change files…' shows the picker", page(w) == "picker", repr(page(w)))
        cancel = find_by_class(w.picker, "kumquat-picker-cancel")
        if check("picker Cancel button present", cancel is not None):
            cancel.emit("clicked")
            yield
            check("cancel with files returns to wheel (files kept)",
                  page(w) == "wheel" and w.files == [pic],
                  f"page={page(w)!r} files={w.files!r}")
        change.emit("clicked")
        yield

    # 5. Folder navigation: one click on a folder enters it; go_up returns.
    w.picker.navigate(str(fixtures))
    yield
    names = [e.name for e in w.picker.entries]
    check("navigate(): dirs first, dot-files hidden",
          names[:1] == ["sub"] and ".hidden.txt" not in names, repr(names))
    j = entry_index(w.picker, "sub")
    if check("'sub' folder listed", j >= 0 and w.picker.entries[j].is_dir):
        w.picker.activate_index(j)
        yield
        check("one click on folder enters it",
              Path(w.picker.current_dir) == fixtures / "sub"
              and page(w) == "picker", f"{w.picker.current_dir} page={page(w)!r}")
        check("subfolder lists inner.jpg",
              [e.name for e in w.picker.entries] == ["inner.jpg"],
              repr([e.name for e in w.picker.entries]))
        w.picker.go_up()
        yield
        check("go_up() returns to parent", Path(w.picker.current_dir) == fixtures,
              w.picker.current_dir)
        w.picker.navigate(str(fixtures / "sub"))
        yield
        w.picker.activate_index(0)
        yield
        check("file in subfolder adopted", page(w) == "wheel"
              and w.files == [str(fixtures / "sub" / "inner.jpg")], repr(w.files))
    w.win.close()
    yield

    # 6. Escape on the picker with no files closes the window.
    w2 = WheelWindow(app, files=[], start_dir=str(fixtures))
    w2.win.present()
    yield
    sent = send_key([w2.picker, w2.win], Gdk.KEY_Escape)
    yield
    yield
    check("Escape (no files) closes the window", sent and is_closed(app, w2),
          f"handled={sent} windows={len(app.get_windows())}")

    # 7. Cancel button with no files closes the window.
    w3 = WheelWindow(app, files=[], start_dir=str(fixtures))
    w3.win.present()
    yield
    cancel = find_by_class(w3.picker, "kumquat-picker-cancel")
    if cancel is not None:
        cancel.emit("clicked")
        yield
        yield
    check("Cancel (no files) closes the window", cancel is not None
          and is_closed(app, w3))

    # 8. Files given up front -> straight to the wheel.
    w4 = WheelWindow(app, files=[pic], start_dir=str(start))
    w4.win.present()
    yield
    check("files given -> starts on 'wheel'", page(w4) == "wheel", repr(page(w4)))
    w4.win.close()
    yield

    work = build_work_dir(fixtures)
    yield from tab_bar_checks(app, work)
    yield from double_click_checks(app, work)
    yield from progress_checks(app, work)


# --- tabs, A/D, double-click, progress ------------------------------------------

def tab_bar_checks(app, work: Path):
    """Bottom tab bar (TASK-402) and Left/Right, A/D (TASK-403)."""
    from gi.repository import Gdk, Gtk

    from kumquat.gui.wheel import TAB_LABELS, WheelWindow

    w = WheelWindow(app, files=[str(work / "pic.jpg")], start_dir=str(work))
    w.win.present()
    yield
    tabs = getattr(w, "tabs", [])
    check("three tab toggle buttons Convert/Tools/Actions",
          [t.get_label() for t in tabs] == list(TAB_LABELS)
          and all(isinstance(t, Gtk.ToggleButton) for t in tabs),
          repr([t.get_label() for t in tabs]))
    if len(tabs) != len(TAB_LABELS):
        w.win.destroy()
        return
    check("Convert tab active on open", tabs[0].get_active() and w.mode == 0)
    renders = []
    original_render = w.render
    w.render = lambda: (renders.append(w.mode), original_render())[0]
    tabs[1].set_active(True)
    yield
    rows = row_texts(w.listbox)
    check("clicking Tools tab -> mode 1, list shows COMPRESS",
          w.mode == 1 and bool(rows) and "COMPRESS" in rows[0], f"first={rows[:1]}")
    check("one tab click renders exactly once", renders == [1], repr(renders))
    renders.clear()
    w.handle_key("Shift_L", True)
    w.handle_key("Shift_L", False)
    yield
    check("Shift -> mode 0 and Convert tab active (keys and tabs in sync)",
          w.mode == 0 and tabs[0].get_active() and not tabs[1].get_active())
    check("one key mode change renders exactly once", renders == [0], repr(renders))
    w.render = original_render
    page_box = w.stack.get_child_by_name("wheel")
    check("tab bar is the last child of the wheel page",
          page_box.get_last_child() is w.tab_bar)
    change = find_by_class(page_box, "kumquat-change")
    header = w.prompt.get_parent()
    check("'Change files…' sits in the header row beside the prompt",
          change is not None and change.get_parent() is header
          and page_box.get_first_child() is header
          and page_box.get_last_child() is not change)

    expected = (("Right", 1), ("d", 2), ("D", 0), ("Left", 2), ("a", 1))
    seen = []
    for key, _mode in expected:
        consumed = w.handle_key(key, True)
        seen.append((key, w.mode, consumed, tabs[w.mode].get_active()))
    yield
    check("Right/d/D/Left/a cycle and wrap the tabs (tab buttons follow)",
          seen == [(k, m, True, True) for k, m in expected], repr(seen))
    released = w.handle_key("d", False)
    check("tab key release is consumed and does not move", released and w.mode == 1,
          f"consumed={released} mode={w.mode}")
    w.show_picker()
    yield
    ignored = w._on_key(None, Gdk.KEY_a, 0, Gdk.ModifierType(0), True)
    check("picker page ignores A (no tab switch)", ignored is False and w.mode == 1,
          f"returned={ignored!r} mode={w.mode}")
    w.win.destroy()
    yield


def double_click_checks(app, work: Path):
    """Double-click applies, single click selects, Enter fires once (TASK-401)."""
    from kumquat.gui.wheel import WheelWindow

    w = WheelWindow(app, files=[str(work / "pic.jpg")], start_dir=str(work))
    w.win.present()
    yield
    check("list activates on double-click only",
          w.listbox.get_activate_on_single_click() is False)
    w.listbox.select_row(w.listbox.get_row_at_index(2))
    yield
    check("single click (select) does not apply",
          not w.status.get_text().startswith("Saved") and not w.busy,
          repr(w.status.get_text()))
    labels = [lab for _id, lab in w.current_items()]
    webp = w.listbox.get_row_at_index(labels.index("Convert to WEBP"))
    w.listbox.emit("row-activated", webp)
    run_job(w)
    check("double-click (row-activated) applies that row",
          w.status.get_text() == "Saved pic.webp" and (work / "pic.webp").exists(),
          repr(w.status.get_text()))
    select_label(w, "Convert to PNG")
    before = outputs(work)
    consumed = w.handle_key("Return", True)
    run_job(w)
    new = outputs(work) - before
    check("Enter applies exactly once (one new file)",
          consumed and new == {"pic.png"}, f"new={sorted(new)}")
    w.win.destroy()
    yield


def progress_checks(app, work: Path):
    """Live % for ffmpeg (TASK-302) and a ticking timer for LibreOffice (303)."""
    from kumquat.gui.wheel import BUSY_HINT, WheelWindow

    if not (work / "big.mp4").exists():
        check("ffmpeg available for the progress check", False)
        return
    w = WheelWindow(app, files=[str(work / "big.mp4")], start_dir=str(work))
    w.win.present()
    yield
    probe: dict = {}

    def poke(job) -> None:
        began = time.monotonic()
        probe["down"] = w.handle_key("Down", True)
        probe["seconds"] = time.monotonic() - began
        probe["running"] = job.running
        w.handle_key("Right", True)
        probe["tab"] = w.mode
        w.handle_key("Left", True)
        w.handle_key("Return", True)
        probe["enter"] = w.status.get_text()
        w.listbox.emit("row-activated", w.listbox.get_row_at_index(0))
        probe["double"] = w.status.get_text()
        probe["escape"] = w.handle_key("Escape", True)
        drain()
        probe["open"] = w.win in app.get_windows() and w.win.get_visible()
        probe["status"] = w.status.get_text()
        w.handle_key("Right", True)  # re-renders the list mid-job
        probe["status_after_tab"] = w.status.get_text()
        w.handle_key("Left", True)

    if not check("video lists 'Convert to WEBM'", select_label(w, "Convert to WEBM")):
        w.win.destroy()
        return
    w.apply_selected()
    samples = run_job(w, poke)
    running = [s for s in samples if s["running"]]
    check("progress bar visible while the job runs",
          bool(running) and all(s["visible"] for s in running), f"{len(running)} samples")
    fractions = [s["fraction"] for s in running if s["text"].endswith("%")]
    distinct = sorted(set(fractions))
    check("at least 2 distinct measured fractions, non-decreasing",
          len(distinct) >= 2 and fractions == sorted(fractions),
          f"distinct={[round(f, 2) for f in distinct][:8]}")
    check("window stayed responsive during the job (Down handled mid-job)",
          probe.get("down") is True and probe.get("running") is True
          and probe.get("seconds", 1.0) < RESPONSIVE_S, repr(probe))
    check("tabs still switch while busy", probe.get("tab") == 1, repr(probe.get("tab")))
    check("Enter and double-click while busy are refused with the busy hint",
          probe.get("enter") == BUSY_HINT and probe.get("double") == BUSY_HINT)
    check("Escape while busy is consumed, window stays, status is the busy hint",
          probe.get("escape") is True and probe.get("open") is True
          and probe.get("status") == BUSY_HINT, repr(probe))
    check("switching tabs mid-job keeps the busy message",
          probe.get("status_after_tab") == BUSY_HINT, repr(probe.get("status_after_tab")))
    check("after the job: bar hidden, status 'Saved…', .webm exists",
          not w.progress_bar.get_visible() and w.status.get_text() == "Saved big.webm"
          and (work / "big.webm").exists(), repr(w.status.get_text()))
    w.win.destroy()
    yield

    w = WheelWindow(app, files=[str(work / "note.docx")], start_dir=str(work))
    w.win.present()
    yield
    if not check("docx lists 'Convert to PDF'", select_label(w, "Convert to PDF")):
        w.win.destroy()
        return
    w.apply_selected()
    texts = [s["text"] for s in run_job(w) if s["running"]]
    ticks = {int(m.group(1)) for t in texts if (m := WORKING_RE.match(t))}
    check("unmeasured job shows a ticking 'Working… N s' timer",
          bool(ticks) and max(ticks) >= 1, f"seconds seen={sorted(ticks)}")
    check("docx job finishes with 'Saved note.pdf'",
          w.status.get_text() == "Saved note.pdf" and (work / "note.pdf").exists(),
          repr(w.status.get_text()))
    w.win.destroy()


def main() -> int:
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        print("FAIL: no display (set WAYLAND_DISPLAY=wayland-1)")
        return 2
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gio, GLib, Gtk
    except Exception as exc:
        print(f"FAIL: gi/GTK4 unavailable ({exc}); run with /usr/bin/python3")
        return 2
    try:
        import kumquat.gui.wheel  # noqa: F401
    except Exception as exc:
        print(f"FAIL: cannot import kumquat.gui.wheel ({type(exc).__name__}: {exc})")
        return 2

    fixtures = build_fixtures()
    app = Gtk.Application(application_id="dev.kumquat.e2e",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    state = {"done": False, "completed": False}

    def finish():
        if not state["done"]:
            state["done"] = True
            for win in list(app.get_windows()):
                win.destroy()
            app.release()
            app.quit()

    def watchdog():
        if not state["done"]:
            check(f"scenario finished before {WATCHDOG_MS // 1000} s watchdog", False)
            finish()
        return False

    def on_activate(_app):
        app.hold()
        GLib.timeout_add(WATCHDOG_MS, watchdog)
        steps = scenario(app, fixtures)

        def tick():
            if state["done"]:
                return False
            try:
                next(steps)
                return True
            except StopIteration:
                state["completed"] = True
                finish()
            except Exception as exc:
                traceback.print_exc()
                check("scenario ran without exceptions", False,
                      f"{type(exc).__name__}: {exc}")
                finish()
            return False

        GLib.timeout_add(STEP_MS, tick)

    app.connect("activate", on_activate)
    try:
        app.run([])
    finally:
        shutil.rmtree(fixtures, ignore_errors=True)

    if not state["completed"] and not any(not ok for _, ok, _ in RESULTS):
        check("scenario ran to completion (app quit early?)", False)
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if not RESULTS:
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

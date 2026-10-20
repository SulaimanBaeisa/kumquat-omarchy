# Picker diagnosis

**User report:** pressing `SUPER+E` opened a separate file chooser; clicking a
file "only goes to the file location" instead of showing its conversions.

## Hypotheses

| # | Hypothesis | Result |
|---|---|---|
| H1 | The chooser dialog loses keyboard focus to the wheel, so clicks/Enter never reach it | **Not reproduced** |
| H4 | GTK's chooser semantics: a single click only *selects*; activating a row (double-click, or a click on a *Recent* entry) navigates to the file's location instead of accepting it | **Concluded — root cause** |

## Evidence

- H1: the old build's chooser was a separate floating top-level surface (class
  `python3`, title `Choose files for Kumquat`, same pid as the wheel). It
  **held focus**: `activewindow=python3`, `focusHistoryID=0` from 0.5 s to 8 s
  after launch. Focus loss does not explain the report.
- `tests/check_picker_live.py` against the old code (baseline `c13f811`):
  `FAIL: the old 'Choose files for Kumquat' dialog is open: 'Choose files for
  Kumquat' (class='python3', pid=…, floating=True)`.
- H4: `Gtk.FileChooserDialog` / `Gtk.FileChooserWidget` (GTK 4.24) accept only
  through the Open button. A single click selects; activating a row in the
  *Recent* view jumps to the containing folder — "goes to the file location".
  The widget also has no `selection-changed` / `file-activated` signals in GTK
  4.24 (connecting raises `TypeError`), so "one click = accept" cannot be added
  on top of it.
- The `response` value / item count from a human click in the old dialog was
  never recorded; H4 rests on GTK's behaviour plus the symptom matching it
  exactly.

## Conclusion and fix

Root cause is **H4**. Fix: remove every GTK chooser (`FileChooserDialog`,
`FileDialog`, `FileChooserWidget` are banned in `src/`, enforced by tests) and
embed a small custom browser (`gui/picker.py`) in the single `Kumquat`
window (`gui/wheel.py`: a `Gtk.Stack` with `picker` and `wheel` pages):

- one click on a folder enters it;
- one click on a file immediately switches to the wheel showing that file's
  conversions.

## Verification

- `WAYLAND_DISPLAY=wayland-1 PYTHONPATH=src /usr/bin/python3 tests/gui_e2e.py`
  drives the real window in-process: picker → one click on `pic.jpg` → wheel
  page listing `Convert to PNG`; tools wheel shows `COMPRESS`; folder
  navigation; Esc/Cancel closes when no files are picked. 26/26 checks passed.
- `PYTHONPATH=src /usr/bin/python3 tests/check_picker_live.py`:
  `PASS: exactly one 'Kumquat' window, no chooser dialog` (window
  floating at 520×640 from the persistent Hyprland rule).

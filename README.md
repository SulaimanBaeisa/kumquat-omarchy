<div align="center">

# 🍊 Kumquat

**A small, offline file converter and toolbox for [Omarchy](https://omarchy.org) — press a key, pick a file, done.**

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Omarchy / Arch + Hyprland](https://img.shields.io/badge/platform-Omarchy%20%7C%20Arch%20%2B%20Hyprland-blue)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)
![GTK 4](https://img.shields.io/badge/GTK-4.12%2B-7fe719)
![Offline](https://img.shields.io/badge/runs-100%25%20offline-lightgrey)

<img src="docs/images/themes.png" alt="Kumquat drawn in eight stock Omarchy themes: Tokyo Night, Catppuccin, Gruvbox, Nord, Rose Pine, Everforest, Kanagawa and Catppuccin Latte" width="100%">

<sub>The same window in eight stock Omarchy themes. Kumquat picks its colours from whichever theme you have active.</sub>

</div>

---

## Contents

[Highlights](#highlights) · [Quick start](#quick-start) · [Works with Omarchy themes](#works-with-omarchy-themes) ·
[Using it](#using-it) · [Tools](#tools-and-their-settings) · [Install in detail](#install-in-detail) ·
[Command line](#command-line) · [Configuration](#configuration-reference) · [Troubleshooting](#troubleshooting) ·
[Development](#development) · [What is tested](#what-is-tested-and-what-is-not) · [Privacy](#privacy) · [License](#license-and-credits)

## Highlights

- **Two key presses to convert.** `Super+E` opens a small popup with its own file browser.
  `Shift+E` inside Files (Nautilus) opens it on the files you selected.
- **275 conversion routes, 26 tools, 6 actions** across images, audio, video, PDF, documents,
  slides and archives (see [what is tested](#what-is-tested-and-what-is-not) for what that means).
- **Draw-on-image crop.** Drag a box on the picture like a photo editor, with 8 handles,
  ratio lock and arrow-key nudging.
- **PDF page thumbnails.** Reorder pages and watch the thumbnails move as you type.
- **Follows your Omarchy theme.** Switch themes and the next window matches.
- **Private by design.** Everything runs locally. No uploads, no telemetry, no accounts.
- **Safe by default.** Your original files are never modified and existing outputs are never
  overwritten. (*Move* is the one action that moves originals, and only when you ask.)
- **Share with LocalSend.** Hands your files to the LocalSend app you already have.

> **Unofficial.** Kumquat is an independent Linux implementation inspired by the Mac app
> *Tangerine*. It is not affiliated with, endorsed by, or distributed by its developer.

## Screenshots

| Pick a file | Convert | Tools | Actions |
|:--:|:--:|:--:|:--:|
| <img src="docs/images/wheel-picker.png" width="190" alt="Built-in file browser"> | <img src="docs/images/wheel-conversions.png" width="190" alt="Conversion formats for a JPEG"> | <img src="docs/images/wheel-tools.png" width="190" alt="Tools for an image"> | <img src="docs/images/wheel-actions.png" width="190" alt="Actions including LocalSend"> |

| Progress | Crop | Organize PDF |
|:--:|:--:|:--:|
| <img src="docs/images/wheel-progress.png" width="190" alt="A real video conversion at 38 percent"> | <img src="docs/images/wheel-crop.png" width="190" alt="Draw-on-image crop with handles"> | <img src="docs/images/wheel-pdf.png" width="190" alt="PDF page thumbnail strip"> |

<sub>All screenshots are rendered from the real widgets with synthetic files
(`tests/make_screenshots.py`). No desktop capture or personal file is used.</sub>

## Quick start

On Omarchy (Arch):

```bash
# 1. Get the code
git clone https://github.com/SulaimanBaeisa/kumquat-omarchy.git
cd kumquat-omarchy

# 2. Install the dependencies (see "Install in detail" for what each one is for)
sudo pacman -S --needed python gtk4 python-gobject python-pillow python-pymupdf \
  ffmpeg imagemagick libheif libavif poppler qpdf

# 3. Install the launcher and both shortcuts (no sudo needed for this step)
/usr/bin/python3 scripts/install-shortcuts.py
hyprctl reload && hyprctl configerrors     # the second command must print nothing
```

Then **restart Files once**, press **`Super+E`**, and pick a file. That is all.

> Keep the cloned folder where it is: the launcher runs the code from there. If you move it,
> run the installer again.

## Works with Omarchy themes

Kumquat reads the colours of your **active Omarchy theme**, so it looks native on any of them
without configuration.

**How it works**

1. Omarchy publishes the live palette at
   `~/.local/state/omarchy/current/theme/colors.toml`.
2. Every time Kumquat opens, it reads that file and derives six colours from it:
   background, foreground, accent, a slightly lighter panel surface, muted text and the text
   colour used on the selected row.
3. Themes name their colours differently, so each role tries several keys
   (for example `lighter_bg`, `lighter_background`, then `color0`) before it derives a value
   from the colours the theme *does* provide.
4. If the file is missing or broken, Kumquat falls back to a built-in palette instead of
   failing — a dark one, or a light one when the theme says `mode = "light"`.

**Readability is enforced, not hoped for.** The selected row's text must reach a 4.5 : 1
contrast ratio against the accent colour, and body text against the panel surface; if a theme's
own values would be too faint, black or white is used instead. Colours from the theme file are
validated as strict `#hex` values, so a bad theme cannot inject anything into the stylesheet.

**Changing theme**

```bash
omarchy-theme-list             # see what is installed
omarchy-theme-set "Tokyo Night"   # switch (or use Omarchy's own theme menu)
```

A window that is already open keeps the colours it started with; **the next one you open uses
the new theme.** Nothing needs restarting and there is no Kumquat setting to change.

The picture at the top shows eight themes that ship with Omarchy. Your own and
wallpaper-generated themes work the same way, as long as they provide a `colors.toml`.
This is covered by 122 automated cases in `tests/test_theme.py` (plus the GTK stylesheet checks in
`tests/test_css_gtk.py`); see [Development](#development) to render the gallery yourself.

**Optional: glass.** By default the panel is opaque. A tinted, slightly see-through panel is
available — see [Appearance](#appearance-glass-or-opaque).

## Using it

### Two ways to open it

**1. Open Kumquat, then choose a file — `Super+E`.**
The popup has its **own file browser**, starting in your home folder. Click a folder to enter
it, click a file to see what you can do with it. Up button, `Backspace` or `Alt+Up` goes to the
parent; the home button returns home. **Change files…** returns to the browser.

**2. Select files in Files, then press `Shift+E`.**
With the Nautilus integration installed, select one or more files in **Files** and press
**`Shift+E`**. Kumquat opens on those files' **Actions** tab. No copy, no right-click.
A context-menu entry, **Open in Kumquat**, does the same.

`Shift+E` is **not** a global shortcut: it only fires inside Files, so capital *E* keeps working
everywhere else, including in Files' rename, search and location fields.
**`Super+Shift+E` stays Omarchy's Email shortcut.**

### Keys and mouse

| Input | Result |
|---|---|
| Bottom **Convert · Tools · Actions** tabs | Choose the kind of operation |
| `←` `→` or `A` `D` | Switch tabs (wraps around) |
| Hold `Shift` / `Super` / `Ctrl` | Jump to Convert / Tools / Actions |
| `↑` `↓` | Select an option |
| Single-click an option | Select it without running it |
| **Double-click** an option, or `Enter` | Run it (or open its settings first) |
| `Esc` on a settings page | Go back without applying |
| `Esc` on the main list | Close (not while a job is running) |

An empty **Tools** tab means *no tools are offered for that file type*, not that something is
broken. For example, a PPTX offers PDF/JPG/PNG conversions but no tools.

### Big files: is it working?

Work runs in a background thread, so the window stays responsive.
Audio/video conversions and PDF→image show a **measured percentage**; other jobs show a moving
bar and elapsed time (`Working… 1 min 15 s`). Errors appear as `Failed: …`, never silently.
Tabs and selection still respond, but a second *Apply* and closing the window are refused
until the job ends. There is no general *Cancel* yet.

### Share with LocalSend

The **LOCALSEND** action uses the LocalSend app you already have. It opens (or raises) the app
and puts your selected files on the Wayland clipboard: press **`Ctrl+V`** in LocalSend or drag
the files in, then pick the device.

Why not send directly? LocalSend's tray app already owns its network port, so a second
`localsend-cli` fails with *Address already in use*. If only `localsend-cli` is installed,
Kumquat opens its device list in a terminal with the files preselected instead.
**Honest limit:** Kumquat does not transfer the files itself, and whether `Ctrl+V` accepts
files depends on your LocalSend version.

## Tools and their settings

Tools that need choices open a settings page **inside the same window**. Press **Apply** to
start; **Back** changes nothing. Invalid values stay on the page with an explanation.

| Tool | What you set |
|---|---|
| **Crop image** | **Draw on image**, a centred ratio, or left/top/width/height in pixels |
| Crop / redact video, redact image | Pixel coordinates (no drawing yet) |
| Trim / bleep | Start and end in seconds — no silently chosen end |
| Speed / split / snapshot | Speed factor, clip length, or snapshot time |
| Edit / annotate image | Enhancement values, or text + position + colour |
| **Organize PDF** | New page order, with a live thumbnail strip |
| Move | An absolute destination folder, with overwrite protection |

**Draw-on-image crop.** Drag on empty space to draw a box, drag inside it to move it, drag any
of its 8 handles to resize, or nudge with the arrow keys (`Shift` = bigger steps).
**Keep ratio** locks 1:1, 4:3, 3:2, 16:9 or 9:16. A line under the picture shows exactly how many
pixels you are keeping, and the pixel fields stay in sync. Phone photos are shown upright and
cropped exactly where you see the box. Drawing needs **one** readable image; with several, pick a
ratio or pixels instead.

**Organize PDF.** A strip of small page thumbnails shows every page. Type the new order using
page numbers from 1, each page once (`3, 1, 4, 2`) and the strip reorders as you type. An
incomplete order keeps the current strip and says why. Needs one readable, unlocked PDF; the
first 120 pages are drawn.

This is not a full freehand editor or an automatic face detector.

## Appearance: glass or opaque

Colours always come from your Omarchy theme ([above](#works-with-omarchy-themes)). The *panel
style* is a separate, optional preference. Create `~/.config/kumquat/appearance.toml`:

```toml
[appearance]
style = "glass"     # or "opaque" (the default)
opacity = 0.90      # accepted range 0.75 – 1.0
```

Only the panel **background** becomes translucent; text and controls are never faded. A missing
or malformed file safely falls back to opaque. *Glass* here means tinted transparency — Kumquat
does not turn on compositor blur or change your desktop theme. If a busy wallpaper makes text
hard to read, use `opaque`.

## Install in detail

**Requirements:** Python **3.11+**, GTK **4.12+** and GTK's Python bindings for the **system**
Python (`/usr/bin/python3`). A virtualenv alone does not provide the GUI.

### Dependencies

Required for the core app:

```bash
sudo pacman -S --needed python gtk4 python-gobject python-pillow python-pymupdf \
  ffmpeg imagemagick libheif libavif poppler qpdf
```

Optional, per feature — a missing optional backend only disables the routes that need it:

| Package | Needed for |
|---|---|
| `libreoffice-still` | Word / Excel / PowerPoint / OpenDocument conversions |
| `pandoc` | Markdown, EPUB, text-document conversions |
| `7zip` | Extracting RAR / 7z and other archives |
| `exiftool` | Removing metadata from most image/media formats |
| `wl-clipboard` | Clipboard actions (*Copy*, *Share*) |
| `nautilus-python` | The `Shift+E` shortcut and the context-menu entry in Files |
| `localsend` | The *Share* action |

Some image formats also need the Python plugins `pillow-heif` / `cairosvg`.

### Install the launcher and shortcuts

```bash
cd kumquat-omarchy
/usr/bin/python3 scripts/install-shortcuts.py
hyprctl reload
hyprctl configerrors        # must be empty
```

The installer is safe to run repeatedly. It backs up any config it changes, keeps your other
shortcuts (including Email), and prints what it did. It installs:

- a launcher at `~/.local/bin/kumquat` that runs the code in your checkout;
- the `Super+E` binding in `~/.config/hypr/bindings.lua`;
- the Files integration (extension + script + `Shift+E` accelerator).

**Restart Files once** afterwards so it loads the integration.

### Popup size and placement (Omarchy)

By default Hyprland would tile the popup like a normal window. A small **window rule** makes it a
centred, floating 520 × 640 popup instead.

> ⚠️ **This is a line of Hyprland configuration (Lua), not a terminal command.** Pasting it into a
> terminal prints errors like `syntax error near ...` — that is expected. It belongs *inside a
> file*, as described below.

**You normally need to do nothing.** The installer (`scripts/install-shortcuts.py`) adds the rule
for you, in a clearly marked block at the end of `~/.config/hypr/hyprland.lua`, after making a
backup. Running it again never adds a second copy, and a rule you wrote yourself is left alone.
Check that it is there:

```bash
grep -n -A3 "Kumquat window rule" ~/.config/hypr/hyprland.lua
```

You should see a `-- BEGIN Kumquat window rule (managed)` block containing one `o.window(...)` line.
Then apply it and confirm there are no errors:

```bash
hyprctl reload
hyprctl configerrors      # must print nothing
```

Press `Super+E`: the popup should now appear small, floating and centred.

**Adding it by hand** (only if you skipped the installer or want to do it yourself). Pick one:

1. *With an editor.* Omarchy's default editor is **nvim**:

   ```bash
   nvim ~/.config/hypr/hyprland.lua
   ```

   (`omarchy-launch-editor ~/.config/hypr/hyprland.lua` opens it in whichever editor Omarchy is set
   to use, and `nano ~/.config/hypr/hyprland.lua` works if you have nano installed.)

   In **nvim**: press `G` to jump to the end, press `i` to start typing, paste the line below on a
   new line, press `Esc`, then type `:wq` and `Enter` to save and quit (`:q!` quits without saving).
   Finally run `hyprctl reload`.

   ```lua
   o.window("^(dev\\.kumquat\\.app)$", { float = true, center = true, size = { 520, 640 } })
   ```

2. *From a terminal in one step* — this **appends** to the file (it never overwrites it), and is
   safe to paste exactly as shown, including the two backslashes:

   ```bash
   cat >> ~/.config/hypr/hyprland.lua <<'EOF'

   -- Kumquat: small centred floating popup
   o.window("^(dev\\.kumquat\\.app)$", { float = true, center = true, size = { 520, 640 } })
   EOF
   hyprctl reload && hyprctl configerrors
   ```

   Run it only once, or the line is added twice (harmless, but untidy).

**Change the size:** edit the two numbers in `size = { 520, 640 }` (width, height in pixels) and
run `hyprctl reload`. **Remove it:** delete the block (or that one line) and reload.

**If it doesn't work:** make sure the file is `~/.config/hypr/hyprland.lua` (Omarchy 4+; older
Omarchy used `hyprland.conf` with a different syntax, which this rule does not fit);
`hyprctl configerrors` shows the exact line Hyprland dislikes; and the class must be spelled
`dev.kumquat.app` with the doubled backslashes (`\\.`) inside the Lua string. This rule is
Hyprland/Omarchy-specific and optional — Kumquat works without it, only larger and tiled.

### Optional: system package

```bash
cd kumquat-omarchy/packaging
makepkg --force --cleanbuild -si
```

Installs `/usr/bin/kumquat`, the code under `/usr/lib/kumquat` and a desktop entry. Rebuild after
source changes — installing an old cached package does not update the code. If you also use the
user launcher, `command -v kumquat` tells you which one your shell runs.

### Upgrading from the old "Tangerine" name

The project was renamed from Tangerine to **Kumquat**. Running the installer migrates an
existing install and keeps copies of what it replaces:

- the old `tangerine-wheel` launcher, Files script and extension are retired
  (copies in `~/.local/share/kumquat/legacy-backup/`);
- the old Hyprland binding block is replaced and the old window rule is pointed at the new
  class, with backups;
- `~/.config/tangerine-wheel/appearance.toml` is copied to `~/.config/kumquat/`
  (the old folder is also still read as a fallback);
- the system package `replaces`/`conflicts` with `tangerine-wheel`; if pacman asks, run
  `sudo pacman -Rns tangerine-wheel` first.

Restart Files once afterwards.

### Uninstall

- System package: `sudo pacman -Rns kumquat`.
- User install: delete `~/.local/bin/kumquat`, the Kumquat block in
  `~/.config/hypr/bindings.lua` (keep your other bindings), and the Kumquat extension/script and
  `scripts-accels` line for Files. Restart Files and run `hyprctl reload`.

Converted outputs and your source files are never deleted by uninstalling.

## Command line

```bash
kumquat --files photo.jpg song.wav --list                    # what is possible (no display needed)
kumquat --files photo.jpg --convert image-jpg-to-png         # convert
kumquat --files photo.jpg --convert image-jpg-to-png --out ./converted
kumquat --gui --tab actions --files photo.jpg                # open on a tab
kumquat --from-clipboard --list                              # explicit clipboard pickup
```

`--from-nautilus` is used by the Files integration: it accepts only the selection Files
supplies, and rejects missing or invalid selections rather than guessing from a stale clipboard.
It cannot be combined with `--files` or `--from-clipboard`.

## Configuration reference

| What | Where | Notes |
|---|---|---|
| Theme colours | `~/.local/state/omarchy/current/theme/colors.toml` | Owned by Omarchy; Kumquat only reads it |
| Panel style | `~/.config/kumquat/appearance.toml` | Optional; `style`, `opacity` |
| Shortcuts | `~/.config/hypr/bindings.lua` | A clearly marked managed block |
| Popup rule | `~/.config/hypr/hyprland.lua` | `dev.kumquat.app` window class |
| Files integration | `~/.local/share/nautilus-python/extensions/` and `~/.local/share/nautilus/scripts/` | Restart Files after changes |
| Launcher | `~/.local/bin/kumquat` | Written by the installer |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Pasting the `o.window(...)` line into a terminal gives errors | It is a config line, not a command. The installer adds it for you; to do it by hand see [Popup size and placement](#popup-size-and-placement-omarchy) |
| `Super+E` does nothing | `hyprctl configerrors` must be empty; run `hyprctl binds \| grep -i kumquat`; rerun the installer |
| `Shift+E` does nothing in Files | Restart Files once. It works only when a **file** is selected, not a text field |
| Wrong file is opened | Selection comes from Files itself; Kumquat never guesses from the clipboard. Re-select the file |
| Colours don't match my theme | Open a **new** window (open ones keep their colours). Check the file exists: `ls ~/.local/state/omarchy/current/theme/colors.toml` |
| Text hard to read on a wallpaper | Set `style = "opaque"` in `appearance.toml` |
| Tools tab is empty | That file type has conversions but no tools — read the tab's message |
| A conversion says a backend is missing | Install the matching optional package from the table above |
| The window won't open / `gi` import error | `/usr/bin/python3 -c "import gi; gi.require_version('Gtk','4.0')"` must succeed |
| Installed behaviour differs from the repo | `command -v kumquat` shows which launcher runs; reinstall or rebuild the package |
| LocalSend says *Address already in use* | Expected with the CLI while the tray app runs — use the app; the *Share* action already does |

**Other distributions:** not validated. See [docs/portability.md](docs/portability.md).

## Development

```bash
git clone https://github.com/SulaimanBaeisa/kumquat-omarchy.git && cd kumquat-omarchy
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                       # unit and integration tests
.venv/bin/python -m ruff check src tests scripts    # lint
```

GUI checks need a Wayland session and the **system** interpreter that has `gi`:

```bash
export PYTHONPATH=src
/usr/bin/python3 tests/gui_e2e.py
/usr/bin/python3 tests/tool_options_e2e.py
/usr/bin/python3 tests/gui_options_flow.py
/usr/bin/python3 tests/crop_canvas_e2e.py      # draw-on-image crop
/usr/bin/python3 tests/pdf_preview_e2e.py      # PDF page strip
/usr/bin/python3 tests/check_picker_live.py
```

Regenerate the images (real widgets, synthetic files, no screen capture):

```bash
PYTHONPATH=src /usr/bin/python3 tests/make_screenshots.py docs/images --theme tokyo-night
PYTHONPATH=src /usr/bin/python3 tests/make_theme_gallery.py docs/images/themes.png
```

**Layout**

| Path | Contents |
|---|---|
| `src/kumquat/` | Converters, tools, registry, jobs, CLI |
| `src/kumquat/gui/` | GTK 4 window, theme/CSS, crop canvas, tool settings |
| `extensions/` | Files (Nautilus) and Dolphin integration |
| `scripts/install-shortcuts.py` | Idempotent installer with migration |
| `packaging/` | `PKGBUILD` and desktop entry |
| `tests/` | Unit tests, real-GTK scripts, QA sweeps |
| `docs/` | Portability notes, QA summaries |

## What is tested, and what is not

Catalog size is **not** a claim that every route works on every machine. Real files were pushed
through the real backends, and results are reported as **PASS / FAIL / UNSUPPORTED / UNTESTED**
separately:

| Suite | PASS | FAIL | UNSUPPORTED | UNTESTED |
|---|---:|---:|---:|---:|
| Conversions (315 input cases, 275 routes) | 279 | 0 | 7 | 29 |
| Tools (286 cases) | 285 | 0 | 1 | 0 |
| Desktop actions (Copy, Share, Float, …) | 98 | 0 | 0 | 526 |
| Automated unit/integration tests | 1304 | 0 | – | – |

- **Unsupported:** Apple Pages export needs macOS; GIF cannot carry audio.
- **Untested:** no genuine Pages / RTFD / text-clipping files were available and none were faked;
  the desktop actions that touch your clipboard, windows or a terminal were deliberately not
  driven on a live desktop.
- The **crop** tests call the drag handlers directly: they prove the box maths and the pixels
  written, **not** a physical mouse. LocalSend receiving a paste is **not** verified end to end.
- Tested on **Omarchy / Arch + Hyprland + Nautilus**. Other systems are untested.

Details: [conversion QA](docs/conversion-qa-summary.md) · [tool QA](docs/tool-qa-summary.md) ·
[portability](docs/portability.md).

## Privacy

Files are processed on your machine. Kumquat makes no network requests of its own, collects no
telemetry, and uploads nothing. The only networking is whatever the LocalSend app you choose to
share with does.

## Suggestions and contributions

Ideas and bug reports are welcome through [issues](https://github.com/SulaimanBaeisa/kumquat-omarchy/issues/new/choose);
small fixes can come as pull requests. The maintainer reviews and merges everything — see
[CONTRIBUTING.md](CONTRIBUTING.md). Please never attach private files or paths with your username.

## License and credits

[MIT](LICENSE) © Sulaiman Baeisa.

Kumquat stands on excellent open-source tools: FFmpeg, ImageMagick, Pillow, PyMuPDF, poppler,
qpdf, LibreOffice, pandoc, 7-Zip, ExifTool, GTK and LocalSend. Note that
[PyMuPDF is AGPL-3.0 / commercial](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
licensed; Kumquat only uses it as an installed dependency — check that licence if you
redistribute a bundle that includes it.

*Tangerine* is the name of a Mac application by its own developer. Kumquat is an independent
project with its own code and no affiliation.

# Appearance and Linux portability

Assessment: October 19, 2026. This is a source-checkout and local-runtime
assessment, not certification for every Linux distribution or desktop.

## App-local appearance

The default is **opaque**. Preferences live at
`$XDG_CONFIG_HOME/kumquat/appearance.toml`, or
`~/.config/kumquat/appearance.toml` when `XDG_CONFIG_HOME` is unset/empty:

```toml
[appearance]
style = "glass"
opacity = 0.90
```

Use `style = "opaque"` for the readable fallback. The only accepted styles are
`opaque` and `glass`; opacity must be a finite number from **0.75 through 1.0**.
It affects glass only. Missing, unreadable, malformed or invalid preference
files fall back to opaque with the default opacity of 0.90. Restart the app to
reload preferences; this is not a live desktop-theme editor.

Both styles use the active Omarchy palette from
`~/.local/state/omarchy/current/theme/colors.toml`. Without that file, a built-in
dark palette is used. A theme declaring light mode gets a light fallback for
missing colours. The stylesheet discards theme-supplied colour alpha, validates
hex colours and checks appearance values before interpolation. A palette's
unreadable body/selected text is replaced with contrasting black or white;
its accent is preserved. The loader enforces a nominal 4.5:1 contrast ratio for
body text on the opaque surface and selected text on the solid accent.

**Glass is translucency, not guaranteed frosted glass.** Only the shared panel
background receives appearance alpha. Text, controls and the window do not
receive a whole-widget opacity setting. The window's transparent outer area
allows rounded corners in both styles. Glass adds a subtle panel border and
inset highlight; input surfaces and selected accents remain solid. Headers,
status/progress text, tabs, empty states and tool choices inherit readable
foreground colours rather than multiplying the panel's alpha.

An arbitrary bright or patterned backdrop can reduce glass contrast, especially
at 0.75. No readability guarantee is made for arbitrary translucent composites:
choose opaque or increase opacity if the desktop shows through too strongly.
Existing compositor-wide window-opacity rules can still dim the entire app;
Kumquat does not override those user rules.

The appearance implementation does **not** download wallpapers or fonts, edit
Hyprland configuration, enable global blur, or supply a cross-compositor
backdrop-blur API. Blur was disabled on the assessed host and was left disabled.
Any future blur integration must be explicitly approved and scoped to this app
using the compositor's supported window/layer mechanism, not a global toggle.

## Runtime requirements and actual minimums

| Component | Source requirement | What was exercised here |
| --- | --- | --- |
| Python | **3.11+**, matching `pyproject.toml`; the theme/preferences modules use standard-library `tomllib`, introduced in 3.11.[2] | System Python 3.14.8 and project virtualenv Python 3.14.7. Python 3.11 itself was not run. |
| GTK | **4.12+** with GTK 4 introspection data: the GUI calls `Gtk.CssProvider.load_from_string`, introduced in 4.12. Requiring the `Gtk` namespace version `4.0` alone does not enforce this minor-version floor.[1] | GTK 4.24.1. GTK 4.12 itself was not run. |
| Python GTK bindings | PyGObject (`gi`) installed for the interpreter that launches the GUI, plus GTK 4 typelibs. A separate numeric PyGObject minimum has not been validated. Upstream setup instructions distinguish these bindings from the GTK library.[7] | System PyGObject 3.58.1. The project's virtualenv has no `gi`; real-GTK tests therefore use `/usr/bin/python3`. |
| Display session | An available GTK display backend and server/compositor. GTK documents separate Wayland and X11 backends, selected with `GDK_BACKEND`.[6] | Local `GdkWaylandDisplay` under Hyprland 0.56.2. |
| Conversion backends | Separate per-feature external programs and Python libraries; appearance support does not establish conversion support. | Not audited by the appearance checks; see the conversion/tool QA results. |

The CSS uses GTK colour definitions/functions, not browser CSS custom
properties or browser `backdrop-filter`. GTK 3 is not supported. A headless CSS
parse proves stylesheet syntax only, not window placement, rendering, focus,
keyboard shortcuts or compositor effects.

## Desktop integration is not distribution support

| Environment | Evidence / support boundary |
| --- | --- |
| Omarchy / Arch, Hyprland, Wayland | Local runtime available. Both appearance styles parse cleanly with real GTK for all 22 installed stock and 9 user palettes, the active palette, and dark/light fallbacks. Opaque body and selected-colour contrast checks pass. This does not substitute for visual/input testing of the integrated popup. |
| Arch with another desktop | **Untested.** GTK libraries are not enough to establish layer-shell, shortcuts, file-manager integration or blur. |
| Fedora, Debian, Ubuntu, other distributions | **Untested.** Match the Python/GTK floor, distro bindings/typelibs and conversion dependencies; no DEB/RPM packaging or desktop execution was validated. |
| GNOME Wayland | **Untested as an app.** Upstream GTK4 layer-shell explicitly does not support GNOME Wayland. An ordinary GTK toplevel and desktop-specific shortcuts need separate verification.[5] |
| X11 desktops | **Untested as an app.** GTK has an X11 backend, but GTK4 layer-shell does not support X11; Wayland clipboard helpers and Hyprland actions are not native X11 implementations.[5][6] |
| Headless containers | No distribution image was available locally. A preexisting Podman executable was found, but its image list was empty. No image was pulled, package installed or VM created for this assessment. A container without a display would not prove desktop behaviour anyway. |

Layer-shell requires both its optional library and a compositor exposing the
necessary Wayland protocol.[5] The GTK4 typelib on the tested Arch system is
`Gtk4LayerShell` version `1.0`, **not** the GTK3-style `GtkLayerShell` `0.1`.
An adapter must select the correct namespace and check runtime support after
GTK has opened a display before requesting overlay/exclusive-keyboard behaviour.
Do not infer a working overlay merely from the package being installed.

The current clipboard paths use `wl-copy`/`wl-paste` from `wl-clipboard`.
Hyprland floating actions use `hyprctl`; other compositors do not acquire that
integration by running GTK. Nautilus selection actions require the Nautilus
extension and its Python bindings. Installing GTK does not install or enable a
file-manager selection shortcut.

## Arch packaging caveats

The repository's local `packaging/PKGBUILD` is not a portable installer. In the
assessed recipe:

- `gtk4` is listed without the source's 4.12 minimum.
- `python-gobject` is missing from `depends`, although importing `gi` requires
  it on Arch. Upstream's Arch instructions name both `python-gobject` and
  `gtk4`; GTK's package metadata does not make the Python bindings a runtime
  requirement.[3][4][7] A workstation where the bindings were already installed
  can mask this packaging gap.
- `gtk4-layer-shell` is listed as mandatory, even though the GUI has an import
  fallback to an ordinary window. That fallback's actual display behaviour
  still needs testing.
- Clipboard integration also needs `wl-clipboard`, which is not declared there.

These are packaging/integration findings, not changes made by the appearance
feature. System GTK packages must be visible to the launching interpreter;
`pip install` of this project's metadata alone does not install GTK or `gi`.

## Reproducing the appearance checks

From the checkout, with the project test environment available:

```sh
.venv/bin/python -m pytest tests/test_theme.py tests/test_css_gtk.py tests/test_appearance.py -q
.venv/bin/python -m ruff check src/kumquat/gui/css.py src/kumquat/gui/theme.py src/kumquat/gui/appearance.py tests/test_theme.py tests/test_css_gtk.py tests/test_appearance.py
```

The GTK harness records `parsing-error` signals, including a deliberately broken
control sheet. It covers opaque plus glass at 0.75, 0.90 and 1.0 against every
installed palette discovered in stock/user theme directories. It skips those
real-GTK checks explicitly when system Python lacks GTK bindings; a skipped
check is not a portability pass. Pure tests cover loading, invalid preferences,
CSS injection attempts, opacity isolation, tool-option selectors, import without
GTK, and page classes not overriding the shared panel background.

Before claiming another desktop is supported, run the app there: verify opaque
and glass against light/dark backdrops, readable headers/tabs/status/empty and
tool-option states, focus and keyboard access, file selection, clipboard actions,
and successful conversion with that platform's installed backends. Keep blur
separate from translucency in the result.

## Sources

[1] https://docs.gtk.org/gtk4/method.CssProvider.load_from_string.html
[2] https://docs.python.org/3/library/tomllib.html
[3] https://packages.archlinux.org/extra/x86_64/gtk4
[4] https://packages.archlinux.org/extra/x86_64/python-gobject
[5] https://github.com/wmww/gtk4-layer-shell
[6] https://docs.gtk.org/gtk4/running.html
[7] https://pygobject.gnome.org/getting_started.html

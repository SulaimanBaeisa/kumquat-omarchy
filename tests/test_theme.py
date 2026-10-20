"""Omarchy palette loading and GTK CSS generation (no GTK needed)."""
from pathlib import Path

import pytest

from kumquat.gui.css import CONTRACT_SELECTORS, build_css
from kumquat.gui.theme import (
    BLACK,
    FALLBACK,
    FALLBACK_LIGHT,
    MIN_SELECTION_CONTRAST,
    WHITE,
    Palette,
    contrast_ratio,
    is_colour,
    load_palette,
    mix,
    readable_on,
    relative_luminance,
)

THEMES_DIR = Path.home() / ".config/omarchy/themes"
THEME_FILES = sorted(path for root in (THEMES_DIR, Path("/usr/share/omarchy/themes"))
                     for path in root.glob("*/colors.toml"))
PALETTE_FIELDS = ("background", "foreground", "accent", "muted", "surface",
                  "selection_fg")
NO_THEME = Path("/nonexistent/colors.toml")


def _write(tmp_path: Path, text: str) -> Path:
    colors = tmp_path / "colors.toml"
    colors.write_text(text)
    return colors


def _fields(palette: Palette) -> list[str]:
    return [getattr(palette, name) for name in PALETTE_FIELDS]


# --- loading the canonical Omarchy file ---------------------------------------

def test_loads_real_omarchy_theme(tmp_path):
    colors = _write(tmp_path,
        'mode = "dark"\n'
        'accent = "#f31895"\n'
        'foreground = "#9cacae"\n'
        'background = "#02000d"\n'
        'lighter_bg = "#18181f"\n'
        'muted = "#383a3d"\n'
        'selection_foreground = "#02000d"\n'
    )
    palette = load_palette(colors)
    assert palette.accent == "#f31895"
    assert palette.background == "#02000d"
    assert palette.foreground == "#9cacae"
    assert palette.surface == "#18181f"
    assert palette.muted == "#383a3d"
    assert palette.selection_fg == "#02000d"


def test_missing_file_falls_back(tmp_path):
    palette = load_palette(tmp_path / "nope.toml")
    assert palette.accent == FALLBACK["accent"]
    assert palette.background == FALLBACK["background"]


def test_broken_toml_falls_back(tmp_path):
    broken = _write(tmp_path, "this is not toml {{{")
    assert load_palette(broken).background == FALLBACK["background"]


def test_bad_colour_value_falls_back(tmp_path):
    colors = _write(tmp_path, 'accent = "not-a-colour"\n')
    assert load_palette(colors).accent == FALLBACK["accent"]


def test_non_utf8_file_falls_back(tmp_path):
    """A colours file with invalid UTF-8 must not escape as a crash."""
    colors = tmp_path / "colors.toml"
    colors.write_bytes(b"accent = \"\xff\xfe\"\n")
    assert load_palette(colors).accent == FALLBACK["accent"]


# --- strict colour validation -------------------------------------------------

@pytest.mark.parametrize("value", ["#abc", "#AABBCC", "#a1b2c3", "#a1b2c3d4"])
def test_is_colour_accepts_hex(value):
    assert is_colour(value)


@pytest.mark.parametrize("value", [
    "#", "#ab", "#abcd", "#abcde", "#ggg", "#12345g", "#a1b2c3d", "abc",
    "#abc;}", "#abc ", " #abc", "rgb(1,2,3)", "#aabbcc\n", "red", 123, None,
    ["#abc"],
])
def test_is_colour_rejects_everything_else(value):
    assert not is_colour(value)


def test_css_injection_attempt_is_rejected(tmp_path):
    """A crafted value must never reach the stylesheet."""
    colors = _write(tmp_path, 'accent = "#fff; } * { color: red"\n')
    palette = load_palette(colors)
    assert palette.accent == FALLBACK["accent"]
    css = build_css(palette)
    assert "color: red" not in css
    assert "* {" not in css


def test_non_string_colour_falls_back(tmp_path):
    colors = _write(tmp_path, "accent = 16711680\nbackground = [1, 2]\n")
    palette = load_palette(colors)
    assert palette.accent == FALLBACK["accent"]
    assert palette.background == FALLBACK["background"]


# --- colour maths --------------------------------------------------------------

def test_relative_luminance_extremes():
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert relative_luminance("#fff") == pytest.approx(1.0)


def test_relative_luminance_ignores_alpha_and_orders_greys():
    assert relative_luminance("#80808000") == pytest.approx(
        relative_luminance("#808080"))
    assert relative_luminance("#333333") < relative_luminance("#999999")


def test_relative_luminance_matches_wcag_reference():
    # sRGB pure red: 0.2126 per the WCAG 2.x definition.
    assert relative_luminance("#ff0000") == pytest.approx(0.2126, abs=1e-4)


def test_contrast_ratio_black_white_is_21():
    assert contrast_ratio("#000", "#fff") == pytest.approx(21.0)
    assert contrast_ratio("#fff", "#000") == pytest.approx(21.0)
    assert contrast_ratio("#123456", "#123456") == pytest.approx(1.0)


@pytest.mark.parametrize(("accent", "expected"), [
    ("#ffff00", BLACK),   # bright yellow -> black text
    ("#7dcfff", BLACK),   # light cyan -> black text
    ("#000080", WHITE),   # navy -> white text
    ("#d83b4d", BLACK),   # mid red: black still contrasts slightly more
    ("#5a2d82", WHITE),   # dark purple -> white text
])
def test_readable_on_picks_higher_contrast(accent, expected):
    assert readable_on(accent) == expected


def test_mix_endpoints_and_midpoint():
    assert mix("#000000", "#ffffff", 0.0) == "#000000"
    assert mix("#000000", "#ffffff", 1.0) == "#ffffff"
    assert mix("#000000", "#ffffff", 0.5) == "#808080"
    assert mix("#000", "#fff", 0.5) == "#808080"


# --- derivation fallbacks ------------------------------------------------------

def test_surface_and_muted_fall_back_to_theme_aliases(tmp_path):
    colors = _write(tmp_path,
        'background = "#0d1117"\nforeground = "#c9d1d9"\n'
        'lighter_background = "#161b22"\ndark_foreground = "#484f58"\n'
    )
    palette = load_palette(colors)
    assert palette.surface == "#161b22"
    assert palette.muted == "#484f58"


def test_surface_and_muted_fall_back_to_ansi_slots(tmp_path):
    colors = _write(tmp_path,
        'background = "#1a1b26"\nforeground = "#a9b1d6"\n'
        'color0 = "#32344a"\ncolor8 = "#444b6a"\n'
    )
    palette = load_palette(colors)
    assert palette.surface == "#32344a"
    assert palette.muted == "#444b6a"


def test_surface_and_muted_derived_from_background_when_no_hints(tmp_path):
    colors = _write(tmp_path, 'background = "#000000"\nforeground = "#ffffff"\n')
    palette = load_palette(colors)
    # Derived from the theme's own colours, not the hard-coded fallback.
    assert palette.surface not in (FALLBACK["lighter_bg"], "#000000")
    assert palette.muted not in (FALLBACK["muted"], "#000000")
    assert relative_luminance(palette.surface) < relative_luminance(palette.muted)


def test_background_and_foreground_aliases(tmp_path):
    colors = _write(tmp_path, 'bg = "#111111"\nfg = "#eeeeee"\n')
    palette = load_palette(colors)
    assert palette.background == "#111111"
    assert palette.foreground == "#eeeeee"


def test_accent_falls_back_to_selection_background(tmp_path):
    colors = _write(tmp_path, 'selection_background = "#3bcddf"\n')
    assert load_palette(colors).accent == "#3bcddf"


def test_invalid_primary_key_uses_alias(tmp_path):
    colors = _write(tmp_path, 'lighter_bg = "nope"\ncolor0 = "#222222"\n')
    assert load_palette(colors).surface == "#222222"


# --- selection foreground -------------------------------------------------------

def test_selection_fg_derived_from_accent_when_missing(tmp_path):
    colors = _write(tmp_path, 'accent = "#7dcfff"\n')
    assert load_palette(colors).selection_fg == BLACK
    colors = _write(tmp_path, 'accent = "#000080"\n')
    assert load_palette(colors).selection_fg == WHITE


def test_unreadable_selection_fg_is_replaced(tmp_path):
    """Theme-supplied text on the accent must stay legible."""
    colors = _write(tmp_path,
        'accent = "#7aa2f7"\nselection_foreground = "#c0caf5"\n')
    palette = load_palette(colors)
    ratio = contrast_ratio(palette.selection_fg, palette.accent)
    assert ratio >= MIN_SELECTION_CONTRAST


def test_readable_selection_fg_is_kept(tmp_path):
    colors = _write(tmp_path,
        'accent = "#f31895"\nselection_foreground = "#02000d"\n')
    assert load_palette(colors).selection_fg == "#02000d"


# --- light mode ------------------------------------------------------------------

def test_light_mode_without_colours_uses_light_fallback(tmp_path):
    palette = load_palette(_write(tmp_path, 'mode = "light"\n'))
    assert palette.background == FALLBACK_LIGHT["background"]
    assert palette.foreground == FALLBACK_LIGHT["foreground"]
    assert relative_luminance(palette.background) > relative_luminance(
        palette.foreground)


def test_light_mode_derived_surface_and_muted_stay_light(tmp_path):
    colors = _write(tmp_path,
        'mode = "light"\nbackground = "#fafafa"\nforeground = "#202020"\n'
        'accent = "#ffd400"\n')
    palette = load_palette(colors)
    assert relative_luminance(palette.surface) > 0.5
    assert palette.selection_fg == BLACK
    assert contrast_ratio(palette.foreground, palette.surface) >= 4.5


def test_mode_is_case_insensitive_and_unknown_means_dark(tmp_path):
    light = load_palette(_write(tmp_path, 'mode = "LIGHT"\n'))
    assert light.background == FALLBACK_LIGHT["background"]
    weird = load_palette(_write(tmp_path, "mode = 7\n"))
    assert weird.background == FALLBACK["background"]


def test_fallback_palettes_are_valid():
    for table in (FALLBACK, FALLBACK_LIGHT):
        assert all(is_colour(value) for value in table.values())
        ratio = contrast_ratio(table["selection_foreground"], table["accent"])
        assert ratio >= MIN_SELECTION_CONTRAST


# --- every installed Omarchy theme -------------------------------------------------

@pytest.mark.skipif(not THEME_FILES, reason="no Omarchy themes installed")
@pytest.mark.parametrize("colors", THEME_FILES, ids=lambda p: p.parent.name)
def test_installed_theme_loads_to_valid_palette(colors):
    palette = load_palette(colors)
    assert all(is_colour(value) for value in _fields(palette))
    assert contrast_ratio(palette.foreground, palette.surface) >= 4.5
    ratio = contrast_ratio(palette.selection_fg, palette.accent)
    assert ratio >= MIN_SELECTION_CONTRAST
    assert "$" not in build_css(palette)


# --- CSS generation (string level; real GTK parsing is in test_css_gtk.py) -------

def test_css_contains_palette_values():
    palette = Palette(background="#010101", foreground="#eeeeee",
                      accent="#ff0066", muted="#333333",
                      surface="#111111", selection_fg="#000000")
    css = build_css(palette)
    for value in _fields(palette):
        assert value in css
    assert ".kumquat-list row:selected" in css


def test_css_has_no_unfilled_placeholders():
    assert "$" not in build_css(load_palette(NO_THEME))


def test_css_styles_every_contract_selector():
    css = build_css(load_palette(NO_THEME))
    for selector in CONTRACT_SELECTORS:
        assert f"{selector} {{" in css or f"{selector}," in css, selector


def test_accent_only_used_for_state_and_progress():
    """Design rule: the accent marks only the selected row, hover, the active
    tab, the primary action and the progress fill; never chrome like panels."""
    css = build_css(load_palette(NO_THEME))
    rules_text = "\n".join(line for line in css.splitlines()
                           if not line.startswith("@define-color"))
    allowed = (":selected", ":hover", ":checked", ".suggested-action",
               ".kumquat-progress progress", ".kumquat-apply")
    for block in rules_text.split("}"):
        if "{" not in block:
            continue
        selectors, body = block.split("{", 1)
        if "@tng_accent" in body:
            assert all(any(mark in sel for mark in allowed)
                       for sel in selectors.split(",")), selectors


def test_idle_tabs_and_trough_stay_off_the_accent():
    """Only the checked tab is accent-filled; idle tabs and the trough are not."""
    import re

    css = build_css(load_palette(NO_THEME))
    for selector in (".kumquat-tab", ".kumquat-progress trough"):
        block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert block is not None, f"{selector} rule missing"
        assert "@tng_accent" not in block.group(1), selector
    checked = re.search(r"\.kumquat-tab:checked[^{]*\{([^}]*)\}", css)
    assert checked is not None and "@tng_accent" in checked.group(1)


@pytest.mark.parametrize("appearance", ["opaque", "glass"])
def test_page_classes_do_not_override_panel_background(appearance):
    """Pages are framed by .kumquat-panel; a later equal-specificity rule
    that sets `background` on a page class would make the page see-through."""
    import re

    css = build_css(load_palette(NO_THEME), appearance=appearance)
    for page_class in (".kumquat-picker", ".kumquat-tool-options"):
        block = re.search(re.escape(page_class) + r"\s*\{([^}]*)\}", css)
        assert block is not None, f"{page_class} rule missing"
        body = re.sub(r"/\*.*?\*/", "", block.group(1), flags=re.S)
        assert not re.search(r"\bbackground(-color)?\s*:", body), (
            f"{page_class} sets a background and overrides .kumquat-panel")


def _css_rule(css, selector):
    import re

    block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert block is not None, f"{selector} missing"
    return re.sub(r"/\*.*?\*/", "", block.group(1), flags=re.S)


def test_opaque_is_default_and_does_not_apply_panel_alpha():
    palette = load_palette(NO_THEME)
    default = build_css(palette)
    assert default == build_css(palette, appearance="opaque")
    assert "background: @tng_surface;" in _css_rule(default, ".kumquat-panel")
    assert default == build_css(palette, appearance="opaque", opacity=0.75)


def test_glass_changes_only_panel_not_text_or_window_opacity():
    import re

    palette = load_palette(NO_THEME)
    css = build_css(palette, appearance="glass", opacity=0.82)
    panel = _css_rule(css, ".kumquat-panel")
    assert "background: alpha(@tng_surface, 0.820);" in panel
    assert "inset" in panel
    assert "border:" in panel
    assert not re.search(r"\bopacity\s*:", css)
    assert "backdrop-filter" not in css
    assert "background: transparent;" in _css_rule(css, "window.kumquat")
    assert f"@define-color tng_accent {palette.accent};" in css
    for selector in (".kumquat-status", ".kumquat-prompt",
                     ".kumquat-picker-path", ".kumquat-progress text"):
        assert "color: @tng_fg;" in _css_rule(css, selector)


@pytest.mark.parametrize("style, opacity", [
    ("glass; } * {", 0.9), ("glass", "0.9); } * {"),
    ("glass", float("nan")), ("glass", 0.74), ("glass", True),
])
def test_css_rejects_invalid_appearance_instead_of_interpolating(style, opacity):
    with pytest.raises(ValueError):
        build_css(load_palette(NO_THEME), appearance=style, opacity=opacity)


@pytest.mark.parametrize("field", PALETTE_FIELDS)
@pytest.mark.parametrize("bad", ["#fff; } * { color: red", "#123456\n"])
def test_css_rejects_injected_programmatic_palette(field, bad):
    from dataclasses import replace

    palette = replace(load_palette(NO_THEME), **{field: bad})
    with pytest.raises(ValueError):
        build_css(palette)


@pytest.mark.parametrize("appearance", ["opaque", "glass"])
def test_theme_alpha_cannot_make_text_or_opaque_panel_translucent(appearance):
    palette = Palette(background="#11111100", foreground="#eeeeee22",
                      accent="#ff006600", muted="#33333344",
                      surface="#11223300", selection_fg="#00000000")
    css = build_css(palette, appearance=appearance)
    assert "@define-color tng_surface #112233;" in css
    assert "@define-color tng_fg #eeeeee;" in css
    assert "#00000000" not in css


def test_small_selected_text_requires_normal_text_contrast(tmp_path):
    palette = load_palette(_write(tmp_path,
        'accent = "#777777"\nselection_foreground = "#eeeeee"\n'))
    assert contrast_ratio(palette.selection_fg, palette.accent) >= 4.5


def test_unreadable_body_text_recovers_without_replacing_accent(tmp_path):
    palette = load_palette(_write(tmp_path,
        'background = "#eeeeee"\nforeground = "#eeeeee"\n'
        'lighter_bg = "#eeeeee"\naccent = "#34abcd"\n'))
    assert contrast_ratio(palette.foreground, palette.surface) >= 4.5
    assert palette.accent == "#34abcd"


def test_appearance_helpers_do_not_import_gtk():
    import os
    import subprocess
    import sys

    source = Path(__file__).resolve().parents[1] / "src"
    completed = subprocess.run(
        [sys.executable, "-c", "import sys; import kumquat.gui.appearance; "
         "import kumquat.gui.theme; import kumquat.gui.css; "
         "assert 'gi' not in sys.modules"],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("appearance", ["opaque", "glass"])
def test_tool_options_have_readable_controls_without_page_background(appearance):
    css = build_css(load_palette(NO_THEME), appearance=appearance)
    for selector in (".kumquat-tool-options", ".kumquat-option-row",
                     ".kumquat-option-error", ".kumquat-apply"):
        assert selector in css
    assert "background:" not in _css_rule(css, ".kumquat-tool-options")
    assert "color: @tng_fg;" in _css_rule(css, ".kumquat-option-error")
    assert ".kumquat-option-row entry" in css
    assert ".kumquat-apply:focus-visible" in css

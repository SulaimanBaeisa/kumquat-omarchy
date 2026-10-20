"""GTK stylesheet generated from an Omarchy palette.

Design rule: one accent colour, used only for selected/hovered rows, the
checked tab, the progress fill and the primary action
(``button.suggested-action``); everything else is drawn from
background, surface, foreground and muted. The sheet is built with
:class:`string.Template` so CSS braces stay literal and the source reads like
ordinary CSS. Palette values are strict ``#hex`` strings, revalidated at the
CSS boundary even for programmatically constructed palettes. Theme alpha is
removed; appearance alpha belongs only to the panel background.
"""
from __future__ import annotations

from dataclasses import fields
from string import Template

from .appearance import Appearance
from .theme import Palette, is_colour

CONTRACT_SELECTORS: tuple[str, ...] = (
    "window.kumquat",
    ".kumquat-panel",
    ".kumquat-prompt",
    ".kumquat-status",
    ".kumquat-list row",
    ".kumquat-list row:selected",
    ".kumquat-change",
    ".kumquat-progress",
    ".kumquat-tabs",
    ".kumquat-tab",
    ".kumquat-tab:checked",
    ".kumquat-picker",
    ".kumquat-picker-header",
    ".kumquat-picker-path",
    ".kumquat-picker-up",
    ".kumquat-picker-home",
    ".kumquat-picker-cancel",
    ".kumquat-picker-list row",
    ".kumquat-picker-list row:hover",
    ".kumquat-picker-list row:selected",
    ".kumquat-picker-row.is-dir",
    ".kumquat-picker-icon",
    ".kumquat-picker-name",
    ".kumquat-tool-options",
    ".kumquat-option-row",
    ".kumquat-option-error",
    ".kumquat-apply",
)
"""Selectors the shared UI contract requires this stylesheet to style."""

_TEMPLATE = Template("""
@define-color tng_bg $background;
@define-color tng_surface $surface;
@define-color tng_fg $foreground;
@define-color tng_muted $muted;
@define-color tng_accent $accent;
@define-color tng_on_accent $selection_fg;

/* ---- window and panel ------------------------------------------------ */

window.kumquat {
    background: transparent;
    color: @tng_fg;
    font-size: 13px;
}

.kumquat-panel {
    /* Only this fill is translucent in glass mode, never the text/window. */
    background: $panel_background;
    border: 1px solid alpha(@tng_fg, 0.20);
    box-shadow: $panel_highlight;
    border-radius: 16px;
    padding: 14px;
}

.kumquat-prompt {
    font-size: 11px;
    font-weight: 600;
    color: @tng_fg;
    margin-bottom: 6px;
}

.kumquat-status {
    font-size: 11px;
    color: @tng_fg;
    margin-top: 8px;
}

/* ---- buttons: flat on the surface; accent only for the primary action - */

.kumquat-change,
.kumquat-picker-up,
.kumquat-picker-home,
.kumquat-picker-cancel {
    background: @tng_surface;
    background-image: none;
    color: @tng_fg;
    border: 1px solid alpha(@tng_muted, 0.70);
    border-radius: 9px;
    box-shadow: none;
    min-height: 26px;
    min-width: 26px;
    padding: 2px 10px;
}

.kumquat-change:hover,
.kumquat-picker-up:hover,
.kumquat-picker-home:hover,
.kumquat-picker-cancel:hover {
    background: mix(@tng_surface, @tng_fg, 0.08);
}

.kumquat-change:active,
.kumquat-picker-up:active,
.kumquat-picker-home:active,
.kumquat-picker-cancel:active {
    background: mix(@tng_surface, @tng_fg, 0.16);
}

.kumquat-change:focus-visible,
.kumquat-picker-up:focus-visible,
.kumquat-picker-home:focus-visible,
.kumquat-picker-cancel:focus-visible {
    outline: 2px solid alpha(@tng_fg, 0.45);
    outline-offset: 1px;
}

.kumquat-change:disabled,
.kumquat-picker-up:disabled,
.kumquat-picker-home:disabled,
.kumquat-picker-cancel:disabled {
    color: alpha(@tng_fg, 0.35);
}

.kumquat-picker-cancel {
    color: alpha(@tng_fg, 0.75);
}

window.kumquat button.suggested-action,
.kumquat-apply {
    background: @tng_accent;
    background-image: none;
    color: @tng_on_accent;
    border: none;
    border-radius: 9px;
    box-shadow: none;
    font-weight: 600;
    padding: 4px 14px;
}

window.kumquat button.suggested-action:hover,
.kumquat-apply:hover {
    background: mix(@tng_accent, @tng_on_accent, 0.12);
}

.kumquat-apply:focus-visible {
    outline: 2px solid @tng_fg;
    outline-offset: 2px;
}

.kumquat-apply:disabled {
    background: @tng_muted;
    color: @tng_fg;
}

/* ---- wheel option list ----------------------------------------------- */

.kumquat-list,
.kumquat-picker-list {
    background: transparent;
    color: @tng_fg;
}

.kumquat-list row {
    border-radius: 10px;
    padding: 7px 10px;
    color: @tng_fg;
    background: transparent;
}

.kumquat-list row:hover {
    background: alpha(@tng_accent, 0.14);
}

.kumquat-list row:selected,
.kumquat-list row:selected:hover {
    background: @tng_accent;
    color: @tng_on_accent;
}

.kumquat-list row:focus-visible {
    outline: 1px solid alpha(@tng_fg, 0.35);
    outline-offset: -2px;
}

/* ---- job progress: muted trough, accent fill --------------------------- */

.kumquat-progress {
    margin-top: 4px;
}

.kumquat-progress trough {
    min-height: 6px;
    border-radius: 3px;
    background: alpha(@tng_muted, 0.55);
}

.kumquat-progress progress {
    min-height: 6px;
    border-radius: 3px;
    background: @tng_accent;
}

.kumquat-progress text {
    font-size: 11px;
    color: @tng_fg;
}

/* ---- bottom tab bar: only the checked tab carries the accent ---------- */

.kumquat-tabs {
    margin-top: 6px;
}

.kumquat-tab {
    background: alpha(@tng_muted, 0.35);
    background-image: none;
    color: @tng_fg;
    border: none;
    border-radius: 0;
    box-shadow: none;
    padding: 6px 0;
    font-weight: 600;
}

.kumquat-tab:first-child {
    border-radius: 9px 0 0 9px;
}

.kumquat-tab:last-child {
    border-radius: 0 9px 9px 0;
}

.kumquat-tab:hover {
    background: alpha(@tng_accent, 0.14);
}

.kumquat-tab:checked,
.kumquat-tab:checked:hover {
    background: @tng_accent;
    color: @tng_on_accent;
}

/* ---- embedded file picker ---------------------------------------------- */

.kumquat-picker {
    /* No background here: the page is framed by .kumquat-panel, and an
       equal-specificity rule declared later would override its fill. */
    color: @tng_fg;
}

.kumquat-picker-header {
    padding-bottom: 8px;
    margin-bottom: 6px;
    border-bottom: 1px solid alpha(@tng_muted, 0.55);
}

.kumquat-picker-path {
    font-family: monospace;
    font-size: 12px;
    color: @tng_fg;
    min-width: 0;
    padding: 0 6px;
}

.kumquat-picker-list {
    padding: 2px;
}

.kumquat-picker-list row {
    border-radius: 8px;
    padding: 3px 8px;
    min-height: 0;
    color: @tng_fg;
    background: transparent;
}

.kumquat-picker-list row:hover {
    background: alpha(@tng_accent, 0.14);
}

.kumquat-picker-list row:selected,
.kumquat-picker-list row:selected:hover {
    background: @tng_accent;
    color: @tng_on_accent;
}

.kumquat-picker-list row:focus-visible {
    outline: 1px solid alpha(@tng_fg, 0.35);
    outline-offset: -2px;
}

.kumquat-picker-row.is-dir {
    font-weight: 600;
}

.kumquat-picker-icon {
    min-width: 20px;
    margin-right: 8px;
}

.kumquat-picker-name {
    min-width: 0;
}

/* ---- tool choices: same panel frame, opaque input surfaces --------------- */

.kumquat-tool-options {
    color: @tng_fg;
}

.kumquat-option-row {
    color: @tng_fg;
    margin-top: 4px;
    margin-bottom: 4px;
}

.kumquat-option-row entry,
.kumquat-option-row spinbutton,
.kumquat-option-row dropdown > button,
.kumquat-option-row textview,
.kumquat-option-row textview text {
    background: @tng_surface;
    background-image: none;
    color: @tng_fg;
    border-radius: 6px;
    border: 1px solid alpha(@tng_fg, 0.30);
    box-shadow: none;
}

.kumquat-option-row entry:focus-within,
.kumquat-option-row spinbutton:focus-within,
.kumquat-option-row dropdown > button:focus-visible {
    outline: 2px solid @tng_fg;
    outline-offset: 1px;
}

.kumquat-option-error {
    color: @tng_fg;
    font-weight: 700;
    margin-top: 6px;
    border-left: 3px solid @tng_fg;
    padding-left: 8px;
}
""")


def build_css(palette: Palette, *, appearance: str = "opaque",
              opacity: float = 0.90) -> str:
    """Return the GTK stylesheet for ``palette``.

    Opaque is the compatible default. Glass applies alpha to the shared panel
    background only; compositor blur is deliberately not configured here.
    Bad programmatic arguments raise ValueError; config loading supplies the
    safe fallback. Theme alpha is discarded so it cannot dim text or bypass
    the opaque preference.

    Every placeholder is substituted (``Template.substitute`` raises on a
    missing one), so the result contains no ``$``; the sheet is verified to
    parse cleanly in real GTK 4 by ``tests/test_css_gtk.py``.
    """
    preferences = Appearance(style=appearance, opacity=opacity)
    colours = {field.name: getattr(palette, field.name) for field in fields(Palette)}
    if not all(is_colour(value) for value in colours.values()):
        raise ValueError("palette values must be strict hex colours")
    colours = {name: value[:7] if len(value) == 9 else value
               for name, value in colours.items()}
    glass = preferences.style == "glass"
    return _TEMPLATE.substitute(
        **colours,
        panel_background=(f"alpha(@tng_surface, {preferences.opacity:.3f})"
                          if glass else "@tng_surface"),
        panel_highlight="inset 0 1px alpha(@tng_fg, 0.12)" if glass else "none",
    )

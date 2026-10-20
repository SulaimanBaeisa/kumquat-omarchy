"""Omarchy theme palette: read the active theme's colors.toml.

Omarchy publishes the live palette at
`~/.local/state/omarchy/current/theme/colors.toml`. We read it on every launch
and derive the six colours the UI needs. Themes differ in which keys they
ship (``lighter_bg`` vs ``lighter_background``, only ANSI ``color0``-``color15``,
no ``selection_foreground`` ...), so every role tries a list of keys, then a
value derived from the colours that *are* present, and only then the neutral
built-in palette for the theme's mode. A missing or malformed file never
blocks startup.

Pure standard library: this module never imports GTK, so it can be unit-tested
inside a virtualenv that has no `gi` bindings.
"""
from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

THEME_DIR = Path.home() / ".local/state/omarchy/current/theme"
COLORS_FILE = THEME_DIR / "colors.toml"

FALLBACK: dict[str, str] = {
    "background": "#101014",
    "foreground": "#e4e4e7",
    "accent": "#f31895",
    "muted": "#3f3f46",
    "lighter_bg": "#18181f",
    "selection_foreground": "#101014",
}
"""Built-in dark palette, used per role when a theme gives no usable value."""

FALLBACK_LIGHT: dict[str, str] = {
    "background": "#fafafa",
    "foreground": "#1f1f23",
    "accent": "#c4106f",
    "muted": "#c8c8cf",
    "lighter_bg": "#f0f0f3",
    "selection_foreground": "#ffffff",
}
"""Built-in light palette, used instead of FALLBACK when ``mode = "light"``."""

BLACK = "#000000"
WHITE = "#ffffff"

MIN_SELECTION_CONTRAST = 4.5
"""Normal-sized selected-row text needs 4.5:1, even when bold."""

MIN_BODY_CONTRAST = 4.5
"""Minimum foreground contrast against the opaque panel surface."""

SURFACE_MIX = 0.06
"""Share of foreground blended into background for a derived panel surface."""

MUTED_MIX = 0.25
"""Share of foreground blended into background for a derived muted colour."""

_HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")

# Candidate keys per role, most specific first. The aliases cover naming
# variants seen across real Omarchy themes.
_BACKGROUND_KEYS = ("background", "bg")
_FOREGROUND_KEYS = ("foreground", "fg")
_ACCENT_KEYS = ("accent", "selection_background")
_SURFACE_KEYS = ("lighter_bg", "lighter_background", "color0")
_MUTED_KEYS = ("muted", "color8", "dark_fg", "dark_foreground")
_SELECTION_FG_KEYS = ("selection_foreground",)

# WCAG 2.x sRGB linearisation and contrast constants.
_SRGB_THRESHOLD = 0.04045
_SRGB_LINEAR_SCALE = 12.92
_SRGB_OFFSET = 0.055
_SRGB_GAMMA = 2.4
_LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)
_CONTRAST_FLARE = 0.05
_CHANNEL_MAX = 255


@dataclass(frozen=True)
class Palette:
    """Colours the wheel draws with, each validated as a ``#hex`` string."""

    background: str
    foreground: str
    accent: str
    muted: str
    surface: str
    selection_fg: str


def is_colour(value: object) -> TypeGuard[str]:
    """Return True only for ``#rgb``, ``#rrggbb`` or ``#rrggbbaa`` strings.

    Anything else (names, ``rgb()``, whitespace, trailing CSS) is rejected, so
    theme values can be pasted into the stylesheet without escaping.
    """
    return isinstance(value, str) and _HEX_COLOUR.fullmatch(value) is not None


def _rgb(colour: str) -> tuple[int, int, int]:
    """Split a validated hex colour into 0-255 channels, ignoring alpha."""
    digits = colour[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _linear(channel: int) -> float:
    """Convert one 0-255 sRGB channel to linear light."""
    scaled = channel / _CHANNEL_MAX
    if scaled <= _SRGB_THRESHOLD:
        return scaled / _SRGB_LINEAR_SCALE
    return ((scaled + _SRGB_OFFSET) / (1 + _SRGB_OFFSET)) ** _SRGB_GAMMA


def relative_luminance(colour: str) -> float:
    """WCAG relative luminance of a hex colour: 0.0 (black) to 1.0 (white)."""
    channels = zip(_LUMA_WEIGHTS, _rgb(colour), strict=True)
    return sum(weight * _linear(channel) for weight, channel in channels)


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two hex colours, from 1.0 to 21.0."""
    darker, lighter = sorted((relative_luminance(first), relative_luminance(second)))
    return (lighter + _CONTRAST_FLARE) / (darker + _CONTRAST_FLARE)


def readable_on(colour: str) -> str:
    """Return BLACK or WHITE, whichever contrasts more with ``colour``."""
    if contrast_ratio(BLACK, colour) >= contrast_ratio(WHITE, colour):
        return BLACK
    return WHITE


def mix(base: str, other: str, amount: float) -> str:
    """Blend ``amount`` (0.0-1.0) of ``other`` into ``base``; returns ``#rrggbb``."""
    pairs = zip(_rgb(base), _rgb(other), strict=True)
    return "#" + "".join(f"{round(b + (o - b) * amount):02x}" for b, o in pairs)


def _pick(data: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    """Return the first valid colour among ``keys`` in ``data``, if any."""
    for key in keys:
        value = data.get(key)
        if is_colour(value):
            return value
    return None


def _read(path: Path) -> dict[str, object]:
    """Parse ``path`` as TOML, returning ``{}`` on any read or parse problem."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def _is_light(data: Mapping[str, object]) -> bool:
    """True when the theme declares ``mode = "light"`` (case-insensitive)."""
    mode = data.get("mode")
    return isinstance(mode, str) and mode.strip().lower() == "light"


def _selection_fg(data: Mapping[str, object], accent: str) -> str:
    """Theme's selection text colour if legible on ``accent``, else black/white."""
    chosen = _pick(data, _SELECTION_FG_KEYS)
    if chosen and contrast_ratio(chosen, accent) >= MIN_SELECTION_CONTRAST:
        return chosen
    return readable_on(accent)


def load_palette(path: Path = COLORS_FILE) -> Palette:
    """Load an Omarchy palette, deriving or falling back per colour role.

    The theme file is treated as untrusted input: a missing or unreadable
    file, invalid TOML or UTF-8, and any value that is not a strict ``#hex``
    colour are ignored rather than raised. Resolution order per role: the
    theme's key, its alias keys, a value derived from the theme's own
    background/foreground, then the built-in palette for the theme's mode.
    Selected-row text always reaches ``MIN_SELECTION_CONTRAST`` on the accent.
    An unreadable body foreground is replaced with black/white on the surface;
    translucent panels cannot guarantee that ratio over arbitrary backdrops.
    """
    data = _read(path)
    defaults = FALLBACK_LIGHT if _is_light(data) else FALLBACK
    background = _pick(data, _BACKGROUND_KEYS) or defaults["background"]
    foreground = _pick(data, _FOREGROUND_KEYS) or defaults["foreground"]
    accent = _pick(data, _ACCENT_KEYS) or defaults["accent"]
    surface = _pick(data, _SURFACE_KEYS) or mix(background, foreground, SURFACE_MIX)
    muted = _pick(data, _MUTED_KEYS) or mix(background, foreground, MUTED_MIX)
    if contrast_ratio(foreground, surface) < MIN_BODY_CONTRAST:
        foreground = readable_on(surface)
    return Palette(
        background=background,
        foreground=foreground,
        accent=accent,
        muted=muted,
        surface=surface,
        selection_fg=_selection_fg(data, accent),
    )

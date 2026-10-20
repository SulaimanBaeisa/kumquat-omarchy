"""App-local appearance preferences; importing this module never imports GTK."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Appearance:
    """Opaque by default; opacity affects only the glass panel's background."""

    style: str = "opaque"
    opacity: float = 0.90

    def __post_init__(self) -> None:
        if self.style not in ("opaque", "glass"):
            raise ValueError("appearance style must be 'opaque' or 'glass'")
        if (isinstance(self.opacity, bool)
                or not isinstance(self.opacity, (int, float))
                or not 0.75 <= self.opacity <= 1.0):
            raise ValueError("appearance opacity must be a number from 0.75 to 1.0")


def load_appearance(path: str | Path | None = None) -> Appearance:
    """Read the app's appearance.toml; unreadable/broken files stay opaque."""
    if path is None:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        path = config_home / "kumquat/appearance.toml"
        former = config_home / "tangerine-wheel/appearance.toml"  # before the rename
        if not path.exists() and former.exists():
            path = former
    try:
        with Path(path).open("rb") as handle:
            data = tomllib.load(handle)
        preferences = data.get("appearance", {})
        if not isinstance(preferences, dict):
            return Appearance()
        return Appearance(
            style=preferences.get("style", "opaque"),
            opacity=preferences.get("opacity", 0.90),
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return Appearance()

"""Render Kumquat under several stock Omarchy themes and stitch one gallery PNG.

Each theme is drawn by a separate `make_screenshots.py --theme NAME` process
(the stylesheet is installed once per process). Only themes that ship with
Omarchy (/usr/share/omarchy/themes) are used, never a personal theme.

Usage (needs a Wayland session):
    PYTHONPATH=src /usr/bin/python3 tests/make_theme_gallery.py [OUT.png]
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GTK_PYTHON = "/usr/bin/python3"  # the interpreter that has PyGObject/GTK 4
THEMES = (
    "tokyo-night", "catppuccin", "gruvbox", "nord",
    "rose-pine", "everforest", "kanagawa", "catppuccin-latte",
)
COLUMNS = 4
TILE_W, TILE_H = 520, 640
GAP, LABEL_H = 24, 44
BACKDROP = (24, 24, 27)
LABEL = (228, 228, 231)


def render(theme: str, work: Path) -> Path:
    out = work / theme
    result = subprocess.run(
        [GTK_PYTHON, str(HERE / "make_screenshots.py"),
         str(out), "--theme", theme, "--scenes", "convert"],
        capture_output=True, text=True, timeout=240,
        env={**os.environ, "PYTHONPATH": str(HERE.parent / "src")},
    )
    image = out / "wheel-convert.png"
    if result.returncode != 0 or not image.is_file():
        tail = (result.stdout + result.stderr)[-800:]
        raise RuntimeError(f"{theme}: rendering failed\n{tail}")
    return image


def stitch(images: list[tuple[str, Path]], target: Path) -> None:
    rows = -(-len(images) // COLUMNS)
    width = COLUMNS * TILE_W + (COLUMNS + 1) * GAP
    height = rows * (TILE_H + LABEL_H) + (rows + 1) * GAP
    sheet = Image.new("RGB", (width, height), BACKDROP)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=26)
    for index, (name, path) in enumerate(images):
        x = GAP + (index % COLUMNS) * (TILE_W + GAP)
        y = GAP + (index // COLUMNS) * (TILE_H + LABEL_H + GAP)
        with Image.open(path) as shot:
            tile = shot.convert("RGBA")
            sheet.paste(tile, (x, y + LABEL_H), tile)
        draw.text((x + 4, y + 4), name, fill=LABEL, font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, optimize=True)
    print(f"wrote {target} ({sheet.width}x{sheet.height}, {len(images)} themes)")


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else Path("docs/images/themes.png")
    with tempfile.TemporaryDirectory(prefix="kumquat-themes-") as scratch:
        work = Path(scratch)
        shots = [(theme, render(theme, work)) for theme in THEMES]
        stitch(shots, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

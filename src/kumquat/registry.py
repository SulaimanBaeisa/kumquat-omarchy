"""Declarative registry: every option the wheel shows. No I/O here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Conversion:
    id: str            # e.g. "image-jpg-to-png"
    label: str         # wheel label
    inputs: tuple      # mime prefixes or extensions, e.g. ("image/", ".svg")
    output_ext: str    # ".png"
    # category: images|video|audio|pdf|documents|slides|spreadsheets|subtitles|archives
    category: str


REGISTRY: list[Conversion] = []
TOOLS: list[str] = []
ACTIONS: list[str] = ["share", "float", "copy", "move", "copy-path", "open-terminal"]


def register(c: Conversion):
    REGISTRY.append(c)
    return c


def options_for(filename: str, mime: str) -> list[Conversion]:
    fn = filename.lower()
    out = []
    for c in REGISTRY:
        for i in c.inputs:
            if i.endswith("/") and mime.startswith(i):
                out.append(c)
                break
            if i.startswith(".") and fn.endswith(i):
                out.append(c)
                break
    return out

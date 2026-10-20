"""Slides conversion rows — data only, no logic.

Conversion matrix:
  ppt/pptx->[pdf,jpg,png] (ppt is input-only, so it never appears
  as an output; self filtered).
  ppt: 3 rows; pptx: 2 rows. Total: 6 rows.
Label rule: gz->"GZIP" else UPPER (no gz here; kept for consistency).
"""
from .registry import Conversion, register

_SLIDE_INPUTS = ("ppt", "pptx")
_SLIDE_OUTPUTS = ("pdf", "jpg", "png")

_SLIDE_EXTS = {
    "ppt": (".ppt",),
    "pptx": (".pptx",),
}


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _src in _SLIDE_INPUTS:
    for _dst in _SLIDE_OUTPUTS:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"slide-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_SLIDE_EXTS[_src],
            output_ext="." + _dst,
            category="slides",
        ))

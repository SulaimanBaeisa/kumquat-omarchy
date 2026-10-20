"""PDF conversion rows — data only, no logic.

Conversion matrix:
  pdf->[docx,pages,pptx,xlsx,jpg,png,epub,txt,md] (9 outputs).
Label rule: gz->"GZIP" else UPPER (no gz here; kept for consistency).
"""
from .registry import Conversion, register

_PDF_OUTS = ["docx", "pages", "pptx", "xlsx", "jpg", "png", "epub", "txt", "md"]


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _dst in _PDF_OUTS:
    register(Conversion(
        id=f"pdf-to-{_dst}",
        label=_label(_dst),
        inputs=(".pdf",),
        output_ext="." + _dst,
        category="pdf",
    ))

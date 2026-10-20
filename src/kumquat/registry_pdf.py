"""PDF conversion rows — data only, no logic.

Encodes the observed conversion matrix:
  pdf->[docx,pages,pptx,xlsx,jpg,png,epub,txt,md] (9 outputs).
Label rule E: gz->"GZIP" else UPPER (no gz here, kept for fidelity).
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

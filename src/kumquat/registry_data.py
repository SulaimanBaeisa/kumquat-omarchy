"""Image conversion rows — data only, no logic.

Encodes the observed conversion matrix: se→qe with self filtered.
  se (inputs)  = ["jpg","png","webp","heic","tiff","svg","avif","bmp"]
  qe (outputs) = ["jpg","png","webp","heic","tiff","avif","bmp","pdf"]
svg is input-only (never an output), so it yields 8 rows; the other
7 inputs yield 7 rows each (qe minus self). Total: 57 rows.
Label rule E: gz→"GZIP" else UPPER (no gz here, kept for fidelity).
"""
# Import order IS registration order (REGISTRY is an append-only list) and
# fixes the order options appear in the wheel -- do not let isort sort it.
# isort: off
from .registry import Conversion, register
from . import registry_av as _registry_av  # noqa: F401 -- AV rows join the registry too
from . import registry_pdf as _registry_pdf  # noqa: F401 -- PDF rows join the registry too
from . import registry_docs as _registry_docs  # noqa: F401 -- docs/sheets/subs rows too
from . import registry_archives as _registry_archives  # noqa: F401 -- archive rows too
from . import registry_slides as _registry_slides  # noqa: F401 -- slides rows too
# isort: on

_QE = ["jpg", "png", "webp", "heic", "tiff", "avif", "bmp", "pdf"]
_SE = ["jpg", "png", "webp", "heic", "tiff", "svg", "avif", "bmp"]

_EXTS = {
    "jpg": (".jpg", ".jpeg"),
    "png": (".png",),
    "webp": (".webp",),
    "heic": (".heic", ".heif"),
    "tiff": (".tiff", ".tif"),
    "svg": (".svg",),
    "avif": (".avif",),
    "bmp": (".bmp",),
}


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _src in _SE:
    for _dst in _QE:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"image-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_EXTS[_src],
            output_ext="." + _dst,
            category="images",
        ))

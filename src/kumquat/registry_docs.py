"""Docs/sheets/subs conversion rows — data only, no logic.

Encodes the observed conversion matrix:
  re (doc inputs) = ["docx","pages","md","rtf","rtfd","textClipping"]
  Xe (doc outputs) = ["docx","pages","pdf","txt","md","html","epub","png","jpg"]
  He (input-only formats filtered from outputs): rtf/rtfd/textClipping
  (xls too, on the sheets side). Self filtered.
  -> docx/pages/md: 8 rows each; rtf/rtfd/textClipping: 9 rows each.
  Total re rows: 51. Category "documents".
  epub->[pdf,docx,pages,txt,md,html]: 6 rows. Category "documents".
  txt->[docx,pages,pdf,md,html,epub,jpg,png]: 8 rows. Category "documents".
  H (sheet inputs) = ["xlsx","xls","ods","csv","tsv"]
  H outputs = [...H,"pdf"] (xls input-only per He, never an output; self filtered)
  -> xlsx/ods/csv/tsv: 4 rows each; xls: 5 rows. Total: 21. Category "spreadsheets".
  X (subs inputs) = ["srt","vtt"], X outputs = [other,"txt"]: 2 rows each.
  Total: 4. Category "subtitles".
New rows: 65 + 21 + 4 = 90. Registry total: 170 -> 260.
Label rule E: gz->"GZIP" else UPPER (no gz here, kept for fidelity).
"""
from .registry import Conversion, register

_RE = ["docx", "pages", "md", "rtf", "rtfd", "textclipping"]
_XE = ["docx", "pages", "pdf", "txt", "md", "html", "epub", "png", "jpg"]
_EPUB_OUTS = ["pdf", "docx", "pages", "txt", "md", "html"]
_TXT_OUTS = ["docx", "pages", "pdf", "md", "html", "epub", "jpg", "png"]
_H = ["xlsx", "xls", "ods", "csv", "tsv"]
_X = ["srt", "vtt"]

_DOC_EXTS = {
    "docx": (".docx",),
    "pages": (".pages",),
    "md": (".md", ".markdown"),
    "rtf": (".rtf",),
    "rtfd": (".rtfd",),
    "textclipping": (".textclipping",),
    "epub": (".epub",),
    "txt": (".txt",),
}

_SHEET_EXTS = {
    "xlsx": (".xlsx",),
    "xls": (".xls",),
    "ods": (".ods",),
    "csv": (".csv",),
    "tsv": (".tsv",),
}

_SUB_EXTS = {
    "srt": (".srt",),
    "vtt": (".vtt",),
}


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _src in _RE:
    for _dst in _XE:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"doc-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_DOC_EXTS[_src],
            output_ext="." + _dst,
            category="documents",
        ))

for _dst in _EPUB_OUTS:
    register(Conversion(
        id=f"doc-epub-to-{_dst}",
        label=_label(_dst),
        inputs=_DOC_EXTS["epub"],
        output_ext="." + _dst,
        category="documents",
    ))

for _dst in _TXT_OUTS:
    register(Conversion(
        id=f"doc-txt-to-{_dst}",
        label=_label(_dst),
        inputs=_DOC_EXTS["txt"],
        output_ext="." + _dst,
        category="documents",
    ))

for _src in _H:
    for _dst in _H + ["pdf"]:
        if _dst in ("xls", _src):
            continue
        register(Conversion(
            id=f"sheet-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_SHEET_EXTS[_src],
            output_ext="." + _dst,
            category="spreadsheets",
        ))

for _src in _X:
    _other = _X[1] if _src == _X[0] else _X[0]
    for _dst in (_other, "txt"):
        register(Conversion(
            id=f"sub-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_SUB_EXTS[_src],
            output_ext="." + _dst,
            category="subtitles",
        ))

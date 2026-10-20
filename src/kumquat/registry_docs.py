"""Docs/sheets/subs conversion rows — data only, no logic.

Conversion matrix:
  doc inputs = ["docx","pages","md","rtf","rtfd","textClipping"]
  doc outputs = ["docx","pages","pdf","txt","md","html","epub","png","jpg"]
  input-only formats (filtered from outputs): rtf/rtfd/textClipping
  (xls too, on the sheets side). Self filtered.
  -> docx/pages/md: 8 rows each; rtf/rtfd/textClipping: 9 rows each.
  Total doc-input rows: 51. Category "documents".
  epub->[pdf,docx,pages,txt,md,html]: 6 rows. Category "documents".
  txt->[docx,pages,pdf,md,html,epub,jpg,png]: 8 rows. Category "documents".
  sheet inputs = ["xlsx","xls","ods","csv","tsv"]
  sheet outputs = [...sheet inputs,"pdf"] (xls input-only, never an output; self filtered)
  -> xlsx/ods/csv/tsv: 4 rows each; xls: 5 rows. Total: 21. Category "spreadsheets".
  subtitle inputs = ["srt","vtt"], subtitle outputs = [other,"txt"]: 2 rows each.
  Total: 4. Category "subtitles".
New rows: 65 + 21 + 4 = 90. Registry total: 170 -> 260.
Label rule: gz->"GZIP" else UPPER (no gz here; kept for consistency).
"""
from .registry import Conversion, register

_DOC_INPUTS = ["docx", "pages", "md", "rtf", "rtfd", "textclipping"]
_DOC_OUTPUTS = ["docx", "pages", "pdf", "txt", "md", "html", "epub", "png", "jpg"]
_EPUB_OUTS = ["pdf", "docx", "pages", "txt", "md", "html"]
_TXT_OUTS = ["docx", "pages", "pdf", "md", "html", "epub", "jpg", "png"]
_SHEETS = ["xlsx", "xls", "ods", "csv", "tsv"]
_SUBTITLES = ["srt", "vtt"]

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


for _src in _DOC_INPUTS:
    for _dst in _DOC_OUTPUTS:
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

for _src in _SHEETS:
    for _dst in _SHEETS + ["pdf"]:
        if _dst in ("xls", _src):
            continue
        register(Conversion(
            id=f"sheet-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_SHEET_EXTS[_src],
            output_ext="." + _dst,
            category="spreadsheets",
        ))

for _src in _SUBTITLES:
    _other = _SUBTITLES[1] if _src == _SUBTITLES[0] else _SUBTITLES[0]
    for _dst in (_other, "txt"):
        register(Conversion(
            id=f"sub-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_SUB_EXTS[_src],
            output_ext="." + _dst,
            category="subtitles",
        ))

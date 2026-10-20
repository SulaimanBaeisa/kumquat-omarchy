"""Docs/sheets/subs converters (LibreOffice + openpyxl + pure-python backends).

Originals are never modified.

Backend policy (mirrors converters_pdf):
- docx/md/rtf/txt inputs: LibreOffice headless (soffice); else BackendMissing.
  Writer filters probed on LO 26.8: docx/pdf/txt/html/png/jpg direct export
  works (txt filter is "txt:Text (encoded):UTF8" — no space before UTF8).
  md has NO export filter -> md output goes through the txt bridge
  (txt->md is a pure copy; other inputs convert to txt first, then rename).
- csv/tsv<->xlsx and csv<->tsv: openpyxl/csv stdlib, native, no backend.
- xls/ods inputs and xls/ods/pdf sheet outputs: LO Calc filters
  (xlsx/csv/pdf/html/ods/xls all probed working); else BackendMissing.
- srt<->vtt, srt/vtt->txt: pure python (timestamp comma<->dot + cue text).
- png/jpg doc outputs: direct Writer export (writer_png_Export /
  writer_jpg_Export, probed working) — no pdf bridge needed.
- pages in/out: impossible headless -> BackendMissing ALWAYS (needs macOS).
- epub in/out: this LO build has NO epub filter (0xc10 write error, probed)
  and pandoc is absent -> BackendMissing('epub export needs pandoc/macOS').
- rtfd/textClipping in: no headless Linux reader -> BackendMissing ALWAYS.
"""
import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ._loshell import profile_args
from .converters_pdf import BackendMissing, output_path

_WRITER_FILTERS = {
    "docx": "docx:MS Word 2007 XML",
    "pdf": "pdf:writer_pdf_Export",
    "txt": "txt:Text (encoded):UTF8",
    "html": "html:XHTML Writer File:UTF8",
    "png": "png:writer_png_Export",
    "jpg": "jpg:writer_jpg_Export",
}

_CALC_FILTERS = {
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "xls": "xls:MS Excel 97",
    "ods": "ods",
    "csv": "csv:Text - txt - csv (StarCalc)",
    "tsv": "csv:Text - txt - csv (StarCalc)",
    "pdf": "pdf:calc_pdf_Export",
    "html": "html:XHTML Calc File:UTF8",
}

_DOC_INPUTS = ("docx", "md", "rtf", "txt")
_SHEET_INPUTS = ("xlsx", "xls", "ods", "csv", "tsv")
_SHEET_OUTPUTS = ("xlsx", "xls", "ods", "csv", "tsv", "pdf")

_TS = re.compile(r"(\d{2}:\d{2}(?::\d{2})?)[,.](\d{3})")


def _need_soffice() -> str:
    for binary in ("soffice", "libreoffice"):
        if shutil.which(binary) is not None:
            return binary
    raise BackendMissing(
        "backend missing: LibreOffice (soffice) not installed (docs/sheets support)"
    )


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def _soffice_convert(src: Path, dst_ext: str, filter_spec: str, dest_dir: Path) -> Path:
    soffice = _need_soffice()
    with tempfile.TemporaryDirectory(prefix="kumquat-docs-") as tmp:
        _run([soffice, *profile_args(tmp), "--headless", "--convert-to", filter_spec,
              "--outdir", tmp, str(src)])
        built = Path(tmp) / (src.stem + "." + dst_ext)
        if not built.exists():
            raise RuntimeError(f"soffice produced no {dst_ext} for {src}")
        dest = output_path(dest_dir / (src.stem + "." + dst_ext))
        shutil.move(str(built), dest)
    return dest


def _need_pandoc() -> str:
    """Pandoc binary, or BackendMissing (epub in/out has no other backend)."""
    exe = shutil.which("pandoc")
    if not exe:
        raise BackendMissing(
            "backend missing: pandoc is required for epub in/out")
    return exe


_PANDOC_INPUTS = ("docx", "md", "txt", "rtf", "html", "epub")


def convert_doc(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    """Convert a doc (docx/md/rtf/txt/epub) to dest_ext; returns output path."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = src.suffix.lstrip(".").lower()
    key = {"markdown": "md"}.get(key, key)
    dst = dest_ext.lstrip(".").lower()
    if key in ("pages", "rtfd", "textclipping"):
        raise BackendMissing(
            f"backend missing: {key} input needs macOS "
            "(no headless Linux reader for it)"
        )
    if key not in _DOC_INPUTS + ("epub",):
        raise ValueError(f"unsupported doc input: {src.suffix!r}")
    if dst == "pages":
        raise BackendMissing(
            "backend missing: Apple Pages export needs macOS "
            "(no headless Linux exporter exists)"
        )
    if dst == "epub":
        # Pandoc reads docx/md/txt/rtf/html/epub and writes epub; LibreOffice
        # on this platform has no epub filter at all.
        pandoc = _need_pandoc()
        dest = output_path(dest_dir / (src.stem + ".epub"))
        _run([pandoc, str(src), "-o", str(dest), "--standalone"])
        if not dest.exists():
            raise RuntimeError(f"pandoc produced no epub for {src}")
        return dest
    if key == "epub":
        # epub input: pandoc to an intermediate LibreOffice-readable form,
        # then the normal writer path handles the requested output.
        pandoc = _need_pandoc()
        with tempfile.TemporaryDirectory(prefix="kumquat-epub-") as tmp:
            bridge = Path(tmp) / (src.stem + ".docx")
            _run([pandoc, str(src), "-o", str(bridge)])
            if not bridge.exists():
                raise RuntimeError(f"pandoc produced no docx for {src}")
            return convert_doc(bridge, dst, dest_dir)
    if dst == "md":
        # No LO md export filter (probed): go through the txt bridge.
        if key == "txt":
            dest = output_path(dest_dir / (src.stem + ".md"))
            dest.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")
            return dest
        with tempfile.TemporaryDirectory(prefix="kumquat-docs-") as tmp:
            bridge = _soffice_convert(src, "txt", _WRITER_FILTERS["txt"], Path(tmp))
            dest = output_path(dest_dir / (src.stem + ".md"))
            dest.write_text(bridge.read_text(encoding="utf-8-sig"), encoding="utf-8")
        return dest
    if dst in _WRITER_FILTERS:
        return _soffice_convert(src, dst, _WRITER_FILTERS[dst], dest_dir)
    raise ValueError(f"unsupported doc output: {dest_ext!r}")


def _delim_of(key: str) -> str:
    return "\t" if key == "tsv" else ","


def _delim_to_xlsx(src: Path, key: str, dest_dir: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    with open(src, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f, delimiter=_delim_of(key)):
            ws.append(row)
    dest = output_path(dest_dir / (src.stem + ".xlsx"))
    wb.save(dest)
    return dest


def _xlsx_to_delim(src: Path, dst: str, dest_dir: Path) -> Path:
    from openpyxl import load_workbook

    dest = output_path(dest_dir / (src.stem + "." + dst))
    ws = load_workbook(src, read_only=True, data_only=True).active
    with open(dest, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=_delim_of(dst))
        for row in ws.iter_rows(values_only=True):
            writer.writerow(["" if v is None else v for v in row])
    return dest


def _delim_to_delim(src: Path, key: str, dst: str, dest_dir: Path) -> Path:
    dest = output_path(dest_dir / (src.stem + "." + dst))
    with open(src, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=_delim_of(key)))
    with open(dest, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=_delim_of(dst)).writerows(rows)
    return dest


def convert_sheet(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    """Convert a sheet (xlsx/xls/ods/csv/tsv) to dest_ext; returns output path."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = src.suffix.lstrip(".").lower()
    dst = dest_ext.lstrip(".").lower()
    if key not in _SHEET_INPUTS:
        raise ValueError(f"unsupported sheet input: {src.suffix!r}")
    if dst not in _SHEET_OUTPUTS:
        raise ValueError(f"unsupported sheet output: {dest_ext!r}")
    if key in ("csv", "tsv") and dst == "xlsx":
        return _delim_to_xlsx(src, key, dest_dir)  # native, no backend
    if key == "xlsx" and dst in ("csv", "tsv"):
        return _xlsx_to_delim(src, dst, dest_dir)  # native, no backend
    if key in ("csv", "tsv") and dst in ("csv", "tsv"):
        return _delim_to_delim(src, key, dst, dest_dir)  # native, no backend
    if dst in ("csv", "tsv") and key in ("ods", "xls"):
        # LibreOffice's CSV filter always writes "<stem>.csv" (its filter
        # list has no TSV output), so re-delimit a private CSV bridge
        # natively. Do not leave/overwrite an unrelated CSV beside a TSV.
        if dst == "csv":
            return _soffice_convert(src, "csv", _CALC_FILTERS["csv"], dest_dir)
        with tempfile.TemporaryDirectory(prefix="kumquat-tsv-") as tmp:
            built = _soffice_convert(src, "csv", _CALC_FILTERS["csv"], Path(tmp))
            return _delim_to_delim(built, "csv", "tsv", dest_dir)
    return _soffice_convert(src, dst, _CALC_FILTERS[dst], dest_dir)


def _retime(line: str, to_vtt: bool) -> str:
    sep = "." if to_vtt else ","
    return _TS.sub(lambda m: m.group(1) + sep + m.group(2), line)


def _read_cues(text: str, is_vtt: bool) -> list[tuple[str, list[str]]]:
    """Parse subtitle text into (timestamp-line, text-lines) cues."""
    lines = [ln.strip() for ln in text.splitlines()]
    if is_vtt and lines and lines[0].upper() == "WEBVTT":
        lines = lines[1:]
    cues: list[tuple[str, list[str]]] = []
    stamp: str | None = None
    body: list[str] = []
    for ln in lines + [""]:
        if "-->" in ln:
            if stamp is not None and body:
                cues.append((stamp, body))
            stamp, body = ln, []
        elif not ln:
            if stamp is not None and body:
                cues.append((stamp, body))
            stamp, body = None, []
        elif stamp is not None:
            # NOTE: digit-lines are only cue indices *before* a timestamp
            # (stamp is None there, so they fall through and are skipped).
            # Once a timestamp was seen every line is body — numeric-only
            # bodies like "42"/"911" must be preserved, not dropped.
            body.append(ln)
    return cues


def convert_sub(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    """Convert subtitles (srt/vtt) to the other format or txt; pure python."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = src.suffix.lstrip(".").lower()
    dst = dest_ext.lstrip(".").lower()
    if key not in ("srt", "vtt"):
        raise ValueError(f"unsupported subtitle input: {src.suffix!r}")
    if dst not in ("srt", "vtt", "txt"):
        raise ValueError(f"unsupported subtitle output: {dest_ext!r}")
    cues = _read_cues(src.read_text(encoding="utf-8-sig"), is_vtt=(key == "vtt"))
    if not cues:
        raise ValueError(f"no subtitle cues found in {src.name}")
    dest = output_path(dest_dir / (src.stem + "." + dst))
    if dst == "txt":
        dest.write_text("\n".join(ln for _, b in cues for ln in b) + "\n",
                        encoding="utf-8")
        return dest
    to_vtt = dst == "vtt"
    parts = ["WEBVTT", ""] if to_vtt else []
    for i, (stamp, body) in enumerate(cues, 1):
        if not to_vtt:
            parts.append(str(i))
        parts.append(_retime(stamp, to_vtt=to_vtt))
        parts.extend(body)
        parts.append("")
    dest.write_text("\n".join(parts), encoding="utf-8")
    return dest

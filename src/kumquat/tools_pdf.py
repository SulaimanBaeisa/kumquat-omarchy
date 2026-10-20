"""PDF file tools.

Originals are never modified — every function writes into ``dest_dir``
and leaves ``src`` bytes untouched.

- ``merge_pdfs`` is re-exported from
  :mod:`kumquat.converters_pdf` — mergePDF has no fixed
  suffix, so the ``<first-stem>-merged.pdf`` name stays.
- ``split_pdf`` reuses the converter's page extraction
  but places parts in a ``<stem>-Pages/`` folder
  (``Pages->folder``), named ``<stem>-<n>.pdf``.
- ``organize_pdf`` takes a JSON spec (dict, JSON
  string, or ``.json`` path) with ``reorder`` / ``drop`` / ``dup`` /
  ``rotate`` keys and writes ``<stem>-Organized.pdf``
  (``Organized``).

PyMuPDF is a pinned dependency (always present) — no ``BackendMissing``
path applies here.
"""
import json
from pathlib import Path

import fitz

from .converters_pdf import split_pdf as _converter_split
from .tools_images import unique_path

__all__ = ["merge_pdfs", "organize_pdf", "split_pdf"]

_SPEC_KEYS = {"reorder", "drop", "dup", "rotate"}


def split_pdf(src: Path, dest_dir: Path) -> list[Path]:
    """Split into one single-page pdf per page inside ``<stem>-Pages/``."""
    src = Path(src)
    folder = unique_path(Path(dest_dir) / f"{src.stem}-Pages")
    folder.mkdir(parents=True, exist_ok=False)
    return _converter_split(src, folder)


def merge_pdfs(srcs: list[Path], dest_dir: Path) -> Path:
    """Merge pages in input order without overwriting earlier output."""
    if not srcs:
        raise ValueError("merge_pdfs needs at least one input")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir / f"{Path(srcs[0]).stem}-merged.pdf")
    with fitz.open() as out:
        for src in srcs:
            with fitz.open(src) as doc:
                out.insert_pdf(doc)
        out.save(dest)
    return dest


def compress_pdf(src: Path, dest_dir: Path) -> Path:
    """Losslessly compact PDF objects and deflate content streams."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir / f"{src.stem}-Compressed.pdf")
    with fitz.open(src) as doc:
        doc.save(dest, garbage=4, deflate=True)
    return dest


def strip_metadata(src: Path, dest_dir: Path) -> Path:
    """Remove document Info and XMP in a full rewrite, not a reversible edit."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir / f"{src.stem}-No Metadata.pdf")
    with fitz.open(src) as doc:
        doc.set_metadata({})
        doc.del_xml_metadata()
        doc.save(dest, garbage=4, deflate=True)
    return dest


def _load_spec(spec) -> dict:
    """Accept a dict, a JSON string, or a path to a JSON file."""
    if spec is None:
        return {}
    if isinstance(spec, dict):
        return dict(spec)
    text = Path(spec).read_text(encoding="utf-8") if _is_file(spec) else spec
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError) as err:
        raise ValueError(f"organize spec is not valid JSON: {spec!r}") from err
    if not isinstance(parsed, dict):
        raise ValueError(f"organize spec must be a JSON object: {spec!r}")
    return parsed


def _is_file(spec) -> bool:
    return isinstance(spec, (str, Path)) and Path(spec).is_file()


def _idx_list(spec: dict, key: str, count: int) -> list[int]:
    vals = spec.get(key, [])
    if not isinstance(vals, list) or any(
            not isinstance(v, int) or isinstance(v, bool) for v in vals):
        raise ValueError(f"spec[{key!r}] must be a list of page indices")
    for v in vals:
        if not 0 <= v < count:
            raise ValueError(f"spec[{key!r}] index {v} outside range({count})")
    return vals


def organize_pdf(src: Path, dest_dir: Path, spec=None, *, require_change=False) -> Path:
    """Reorder / drop / duplicate / rotate pages per a JSON spec.

    ``spec`` keys (all optional, 0-based page indices):

    - ``reorder``: full permutation of the pages (default: identity).
    - ``drop``: pages to remove.
    - ``dup``: pages to append as copies (after drop).
    - ``rotate``: ``{page: degrees}`` — degrees must be a multiple of 90
      (JSON object keys arrive as strings; both are accepted).

    Pipeline: reorder → drop → dup-append → rotate.
    ``drop`` and ``dup`` may not share a page; dropping everything is
    an error; unknown keys are an error (likely a typo).
    """
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    parsed = _load_spec(spec)
    unknown = set(parsed) - _SPEC_KEYS
    if unknown:
        raise ValueError(f"unknown organize spec keys: {sorted(unknown)}")
    with fitz.open(src) as doc:
        count = doc.page_count
        order = _idx_list(parsed, "reorder", count) or list(range(count))
        if "reorder" in parsed and sorted(order) != list(range(count)):
            raise ValueError(
                f"spec['reorder'] must permute range({count}): {order!r}")
        drop = set(_idx_list(parsed, "drop", count))
        dup = _idx_list(parsed, "dup", count)
        if clash := (drop & set(dup)):
            raise ValueError(
                f"spec pages both dropped and duplicated: {sorted(clash)}")
        kept = [i for i in order if i not in drop]
        final = kept + dup
        if not final:
            raise ValueError("organize spec drops every page")
        rotate = parsed.get("rotate", {})
        if not isinstance(rotate, dict):
            raise ValueError("spec['rotate'] must be an object {page: deg}")
        turns: dict[int, int] = {}
        for k, deg in rotate.items():
            try:
                page = int(k)
            except (TypeError, ValueError) as err:
                raise ValueError(f"spec['rotate'] bad page key: {k!r}") from err
            if not 0 <= page < count:
                raise ValueError(
                    f"spec['rotate'] page {page} outside range({count})")
            if not isinstance(deg, int) or isinstance(deg, bool) \
                    or deg % 90 != 0:
                raise ValueError(
                    f"spec['rotate'][{page}] must be a multiple of 90: "
                    f"{deg!r}")
            turns[page] = deg % 360
        if require_change and final == list(range(count)) and not any(
                turns.get(i, doc[i].rotation) != doc[i].rotation for i in final):
            raise ValueError("page order and rotations are unchanged; choose a change")
        out = fitz.open()
        try:
            for i in final:
                out.insert_pdf(doc, from_page=i, to_page=i)
            for n, i in enumerate(final):
                if turns.get(i):
                    out[n].set_rotation(turns[i])
            dest = unique_path(dest_dir / f"{src.stem}-Organized.pdf")
            out.save(dest)
        finally:
            out.close()
    return dest

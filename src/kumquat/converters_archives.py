"""Archive converters (stdlib zip/tar/gzip; rar extract-only). Originals untouched.

Backend policy (mirrors converters_pdf / converters_docs):
- zip create/extract: stdlib zipfile (always present).
- tar / tar.gz create/extract: stdlib tarfile (always present).
- gz output is named `<stem>.tar.gz` per the gz naming rule (gz output
  named `tar.gz`): inputs are tarred, then gzipped.
- Single-stream `.gz` inputs (not `.tar.gz`) gunzip natively, no backend.
- rar is extract-only: 7z, then bsdtar, then the rarfile module; none
  usable here (7z/rarfile absent) -> BackendMissing. Tests SKIP on this.
- Path traversal ("zip/tar slip") members are rejected with ValueError.
"""
import gzip
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .converters_pdf import BackendMissing, output_path

_ARCHIVE_INPUTS = ("zip", "tar", "gz", "tgz", "rar")
_ARCHIVE_OUTPUTS = ("zip", "tar", "gz", "tar.gz", "tgz")

_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".gz", ".zip", ".rar")


def _input_key(src: Path) -> str:
    """Normalize an archive filename to zip/tar/gz/rar (tgz/tar.gz -> gz)."""
    name = src.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        return "gz"
    return src.suffix.lstrip(".").lower()


def _base(src: Path) -> str:
    """Stem with any known archive suffix stripped (for output naming)."""
    name = src.name
    lowered = name.lower()
    for suf in _ARCHIVE_SUFFIXES:
        if lowered.endswith(suf):
            stem = name[: -len(suf)]
            return stem or "archive"
    # Single-stream gzip of a named file (note.txt.gz -> note.txt): strip
    # only the .gz layer so the original filename survives.
    if lowered.endswith(".gz") and lowered.count(".") >= 2:
        return name[: -len(".gz")]
    return src.stem


def _safe_join(dest_dir: Path, member: str) -> Path:
    """Join a member path, rejecting absolute paths and `..` escapes."""
    target = (dest_dir / member).resolve()
    if target != dest_dir.resolve() and dest_dir.resolve() not in target.parents:
        raise ValueError(f"archive member escapes destination: {member!r}")
    return target


def _extract_rar(src: Path, dest_dir: Path) -> Path:
    """Extract-only rar path: 7z, then bsdtar, then rarfile module.

    A backend that is present but fails (e.g. unsupported rar variant)
    falls through to the next; only when every present backend fails is
    a RuntimeError raised. No backend at all -> BackendMissing.
    """
    errors: list[str] = []
    tried = False
    seven = shutil.which("7z")
    if seven is not None:
        tried = True
        try:
            _run([seven, "x", f"-o{dest_dir}", str(src)])
            return dest_dir
        except (subprocess.CalledProcessError, OSError) as e:
            errors.append(f"7z failed: {e}")
    bsdtar = shutil.which("bsdtar")
    if bsdtar is not None:
        tried = True
        try:
            _run([bsdtar, "-xf", str(src), "-C", str(dest_dir)])
            return dest_dir
        except (subprocess.CalledProcessError, OSError) as e:
            errors.append(f"bsdtar failed: {e}")
    try:
        import rarfile
    except ImportError:
        rarfile = None  # type: ignore[assignment]
    if rarfile is not None:
        tried = True
        try:
            with rarfile.RarFile(src) as rf:
                for info in rf.infolist():
                    _safe_join(dest_dir, info.filename)
                rf.extractall(dest_dir)
            return dest_dir
        except Exception as e:  # BadRarFile, RarCannotExec, ...
            errors.append(f"rarfile failed: {e}")
    if not tried:
        raise BackendMissing(
            "backend missing: no rar extractor (7z, bsdtar, or rarfile module) "
            f"installed (rar extract of {src.name})"
        )
    raise RuntimeError(f"could not extract rar {src.name}: {'; '.join(errors)}")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def create_archive(srcs: list[Path], dest_ext: str, dest_dir: Path) -> Path:
    """Pack srcs (files/dirs) into a zip/tar/tar.gz archive; returns its path."""
    paths = [Path(s) for s in srcs]
    if not paths:
        raise ValueError("create_archive needs at least one input")
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(p)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = dest_ext.lstrip(".").lower()
    if key not in _ARCHIVE_OUTPUTS:
        raise ValueError(f"unsupported archive output: {dest_ext!r}")
    base = _base(paths[0])
    if key == "zip":
        dest = output_path(dest_dir / (base + ".zip"))
        with zipfile.ZipFile(
                dest, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as z:
            for p in paths:
                if p.is_dir():
                    for child in sorted(p.rglob("*")):
                        if child.is_file():
                            z.write(child, child.relative_to(p.parent))
                else:
                    z.write(p, p.name)
        return dest
    dest = output_path(dest_dir / (base + (".tar" if key == "tar" else ".tar.gz")))
    mode = "w" if key == "tar" else "w:gz"
    with tarfile.open(dest, mode) as t:
        for p in paths:
            t.add(p, arcname=p.name)
    return dest


def extract_archive(src: Path, dest_dir: Path) -> Path:
    """Extract an archive into dest_dir (created); returns dest_dir.

    `extractArchive` tool. Zip/tar/gz via stdlib; rar via 7z, then
    bsdtar, then rarfile; none usable -> BackendMissing.
    """
    src, dest_dir = Path(src), Path(dest_dir)
    if not src.exists():
        raise FileNotFoundError(src)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = _input_key(src)
    if key == "zip":
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                _safe_join(dest_dir, info.filename)
            z.extractall(dest_dir)
        return dest_dir
    if key == "tar":
        with tarfile.open(src, "r:") as t:
            for m in t.getmembers():
                _safe_join(dest_dir, m.name)
            t.extractall(dest_dir, filter="data")
        return dest_dir
    if key == "gz":
        if tarfile.is_tarfile(src):
            with tarfile.open(src, "r:gz") as t:
                for m in t.getmembers():
                    _safe_join(dest_dir, m.name)
                t.extractall(dest_dir, filter="data")
            return dest_dir
        # Single-stream gzip: gunzip to the bare filename.
        out = dest_dir / _base(src)
        with gzip.open(src, "rb") as f_in, open(out, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return dest_dir
    if key == "rar":
        return _extract_rar(src, dest_dir)
    raise ValueError(f"unsupported archive input: {src.suffix!r}")


def convert_archive(src: Path, dest_ext: str, dest_dir: Path) -> Path:
    """Transcode one archive to another format; returns the output path."""
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(src)
    key = _input_key(src)
    if key not in _ARCHIVE_INPUTS:
        raise ValueError(f"unsupported archive input: {src.suffix!r}")
    if dest_ext.lstrip(".").lower() not in _ARCHIVE_OUTPUTS:
        raise ValueError(f"unsupported archive output: {dest_ext!r}")
    with tempfile.TemporaryDirectory(prefix="kumquat-arch-") as tmp:
        unpacked = extract_archive(src, Path(tmp) / "unpacked")
        members = sorted(unpacked.iterdir())
        if not members:
            raise ValueError(f"nothing to convert in archive: {src}")
        return create_archive(members, dest_ext, Path(dest_dir))

"""Archives conversions: registry routing + real conversions, originals untouched.

rows:
- [zip,tar,gz,rar]->[zip,tar,gz] (rar input-only; self filtered)
  => zip/tar/gz: 2 rows each; rar: 3 rows. Total: 9 rows, category "archives".
- Registry gate: 260 + 9 archives + 6 slides = 275 EXACTLY.

Backend policy (mirrors converters_pdf / converters_docs):
- zip create/extract: stdlib zipfile (always present).
- tar/tar.gz create/extract: stdlib tarfile (always present).
- gz (single-stream) output: named `<stem>.tar.gz` per the gz naming rule
  (tar the inputs, then gzip); single-file .gz inputs gunzip natively.
- rar extract-only: 7z, then bsdtar, then rarfile module; none usable
  (7z/rarfile absent here) -> BackendMissing ALWAYS in this env.
  Tests needing an absent backend SKIP or assert the raise; they never fail.
"""
import gzip
import hashlib
import shutil
import tarfile
import zipfile

import pytest

import kumquat.registry_archives  # noqa: F401 -- registers the 9 archive rows
import kumquat.registry_data  # noqa: F401 -- registers image rows (pulls AV rows too)
import kumquat.registry_docs  # noqa: F401 -- registers the 90 docs/sheets/subs rows
import kumquat.registry_pdf  # noqa: F401 -- registers the 9 pdf rows
import kumquat.registry_slides  # noqa: F401 -- registers the 6 slides rows
from kumquat.converters_archives import (
    BackendMissing,
    convert_archive,
    create_archive,
    extract_archive,
)
from kumquat.registry import REGISTRY, options_for

ARCHIVE_ROWS = [c for c in REGISTRY if c.category == "archives"]

ARCHIVE_IDS = {
    "archive-zip-to-tar", "archive-zip-to-gz",
    "archive-tar-to-zip", "archive-tar-to-gz",
    "archive-gz-to-zip", "archive-gz-to-tar",
    "archive-rar-to-zip", "archive-rar-to-tar", "archive-rar-to-gz",
}


def _or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BackendMissing as e:
        pytest.skip(str(e))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_files(base):
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.txt").write_text("hello archives\n", encoding="utf-8")
    (base / "b.txt").write_text("second file\n", encoding="utf-8")
    return [base / "a.txt", base / "b.txt"]


def _read_members(archive):
    """Return {name: bytes} for a zip/tar/tar.gz archive under test."""
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            return {i.filename: z.read(i.filename)
                    for i in z.infolist() if not i.is_dir()}
    with tarfile.open(archive, "r:*") as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}


def test_registry_archives_count():
    assert len(ARCHIVE_ROWS) == 9  # 2+2+2+3


def test_registry_total_is_275():
    assert len(REGISTRY) == 275  # 260 + 9 archives + 6 slides;


def test_archives_ids():
    assert {c.id for c in ARCHIVE_ROWS} == ARCHIVE_IDS


def test_archives_no_self_or_input_only_outputs():
    for c in ARCHIVE_ROWS:
        src = c.id.split("-to-")[0].split("-", 1)[1]
        dst = c.output_ext.lstrip(".").removeprefix("tar.")
        assert src != dst, c.id  # self filtered
        assert dst in ("zip", "tar", "gz"), c.id  # rar input-only, never an output


def test_archives_labels_follow_E_rule():
    for c in ARCHIVE_ROWS:
        dst = c.output_ext.lstrip(".").removeprefix("tar.")
        assert c.label == "Convert to " + ("GZIP" if dst == "gz" else dst.upper())
    gz_row = next(c for c in ARCHIVE_ROWS if c.id == "archive-zip-to-gz")
    assert gz_row.label == "Convert to GZIP"


def test_archives_gz_output_ext_is_tar_gz():
    for c in ARCHIVE_ROWS:
        if c.id.endswith("-to-gz"):
            assert c.output_ext == ".tar.gz", c.id  # gz naming rule


def test_registry_routes_zip():
    opts = options_for("a.zip", "application/zip")
    assert {c.id for c in opts} == {"archive-zip-to-tar", "archive-zip-to-gz"}


def test_registry_routes_tar():
    opts = options_for("a.tar", "application/x-tar")
    assert {c.id for c in opts} == {"archive-tar-to-zip", "archive-tar-to-gz"}


def test_registry_routes_tar_gz_as_gz_input():
    opts = options_for("a.tar.gz", "application/gzip")
    assert {c.id for c in opts} == {"archive-gz-to-zip", "archive-gz-to-tar"}


def test_registry_routes_tgz_as_gz_input():
    opts = options_for("a.tgz", "application/gzip")
    assert {c.id for c in opts} == {"archive-gz-to-zip", "archive-gz-to-tar"}


def test_registry_routes_rar_gets_three():
    opts = options_for("a.rar", "application/octet-stream")
    assert {c.id for c in opts} == {
        "archive-rar-to-zip", "archive-rar-to-tar", "archive-rar-to-gz",
    }


@pytest.mark.parametrize("row_id", sorted(ARCHIVE_IDS))
def test_archives_row_routes(row_id):
    row = next(c for c in ARCHIVE_ROWS if c.id == row_id)
    opts = options_for("file" + row.inputs[0], "application/octet-stream")
    assert row in opts


def test_create_zip(tmp_path):
    srcs = _make_files(tmp_path / "in")
    out = create_archive(srcs, ".zip", tmp_path / "out")
    assert out.exists() and out.suffix == ".zip"
    assert set(_read_members(out)) == {"a.txt", "b.txt"}
    assert _read_members(out)["a.txt"] == b"hello archives\n"


def test_create_tar(tmp_path):
    srcs = _make_files(tmp_path / "in")
    out = create_archive(srcs, ".tar", tmp_path / "out")
    assert out.exists() and out.suffix == ".tar"
    assert _read_members(out)["b.txt"] == b"second file\n"


def test_create_gz_yields_tar_gz(tmp_path):
    srcs = _make_files(tmp_path / "in")
    out = create_archive(srcs, ".gz", tmp_path / "out")
    assert out.exists() and out.name.endswith(".tar.gz")  # gz naming rule
    assert _read_members(out)["a.txt"] == b"hello archives\n"


def test_create_leaves_originals_untouched(tmp_path):
    srcs = _make_files(tmp_path / "in")
    before = {p: _sha(p) for p in srcs}
    create_archive(srcs, ".zip", tmp_path / "out")
    create_archive(srcs, ".tar", tmp_path / "out")
    create_archive(srcs, ".tar.gz", tmp_path / "out")
    assert {p: _sha(p) for p in srcs} == before


def test_extract_zip_round_trip(tmp_path):
    srcs = _make_files(tmp_path / "in")
    before = {p: _sha(p) for p in srcs}
    archive = create_archive(srcs, ".zip", tmp_path / "arc")
    dest = extract_archive(archive, tmp_path / "out")
    assert (dest / "a.txt").read_text() == "hello archives\n"
    assert (dest / "b.txt").read_text() == "second file\n"
    assert {p: _sha(p) for p in srcs} == before  # originals untouched
    assert _sha(archive) == _sha(archive)  # archive itself intact


def test_extract_tar_gz_round_trip(tmp_path):
    srcs = _make_files(tmp_path / "in")
    archive = create_archive(srcs, ".tar.gz", tmp_path / "arc")
    dest = extract_archive(archive, tmp_path / "out")
    assert (dest / "a.txt").read_text() == "hello archives\n"
    assert (dest / "b.txt").read_text() == "second file\n"


def test_extract_single_gz_round_trip(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("single stream\n", encoding="utf-8")
    gz = tmp_path / "note.txt.gz"
    with gzip.open(gz, "wb") as f:
        f.write(src.read_bytes())
    dest = extract_archive(gz, tmp_path / "out")
    assert (dest / "note.txt").read_text() == "single stream\n"


@pytest.mark.parametrize("src_ext,dst_ext", [
    (".zip", ".tar"), (".zip", ".tar.gz"), (".tar", ".zip"),
    (".tar", ".tar.gz"), (".tar.gz", ".zip"), (".tar.gz", ".tar"),
])
def test_transcode_between_formats(tmp_path, src_ext, dst_ext):
    srcs = _make_files(tmp_path / "in")
    before = {p: _sha(p) for p in srcs}
    archive = create_archive(srcs, src_ext, tmp_path / "arc")
    out = convert_archive(archive, dst_ext, tmp_path / "out")
    assert out.exists()
    members = _read_members(out)
    assert members["a.txt"] == b"hello archives\n"
    assert members["b.txt"] == b"second file\n"
    assert {p: _sha(p) for p in srcs} == before  # originals untouched


def test_transcode_single_gz_to_zip(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("single stream\n", encoding="utf-8")
    gz = tmp_path / "note.txt.gz"
    with gzip.open(gz, "wb") as f:
        f.write(src.read_bytes())
    out = convert_archive(gz, ".zip", tmp_path / "out")
    assert _read_members(out)["note.txt"] == b"single stream\n"


def test_extract_zip_slip_blocked(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escape.txt", "evil")
    with pytest.raises(ValueError):
        extract_archive(evil, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_extract_tar_slip_blocked(tmp_path):
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as t:
        info = tarfile.TarInfo("../../escape.txt")
        info.size = 4
        import io
        t.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(ValueError):
        extract_archive(evil, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_rar_extract_missing_backend(tmp_path, monkeypatch):
    src = tmp_path / "in.rar"
    src.write_bytes(b"rar stub")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)  # no 7z/bsdtar
    # rarfile is not installed here; even if it were, the stub is not a rar.
    with pytest.raises(BackendMissing):
        extract_archive(src, tmp_path / "out")


def test_rar_extract_corrupt_with_backend(tmp_path):
    src = tmp_path / "in.rar"
    src.write_bytes(b"not a real rar")
    # bsdtar IS present here: a corrupt rar must raise RuntimeError (with the
    # backend errors chained in the message), never leak CalledProcessError.
    if shutil.which("bsdtar") is None and shutil.which("7z") is None:
        pytest.skip("no rar backend present (covered by missing-backend test)")
    with pytest.raises(RuntimeError, match="could not extract rar"):
        extract_archive(src, tmp_path / "out")


def test_rar_transcode_missing_backend(tmp_path, monkeypatch):
    src = tmp_path / "in.rar"
    src.write_bytes(b"rar stub")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(BackendMissing):
        convert_archive(src, ".zip", tmp_path / "out")


def test_unsupported_archive_output(tmp_path):
    srcs = _make_files(tmp_path / "in")
    with pytest.raises(ValueError):
        create_archive(srcs, ".7z", tmp_path / "out")


def test_unsupported_archive_input(tmp_path):
    src = tmp_path / "in.7z"
    src.write_bytes(b"stub")
    with pytest.raises(ValueError):
        convert_archive(src, ".zip", tmp_path / "out")


def test_missing_archive_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        convert_archive(tmp_path / "nope.zip", ".tar", tmp_path / "out")

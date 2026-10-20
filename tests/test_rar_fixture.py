"""A hand-written RAR5 archive must be a REAL one: the official extractor reads it."""

import shutil
import subprocess

import pytest
from rar_fixture import write_rar5_stored

pytestmark = pytest.mark.skipif(shutil.which("7z") is None, reason="7z not installed")

FILES = {
    "hello.txt": b"Kumquat archive payload 42\n",
    "dir/inner.bin": bytes(range(256)) * 3,
}


def test_7z_lists_and_tests_the_archive(tmp_path):
    archive = write_rar5_stored(tmp_path / "fixture.rar", FILES)
    listing = subprocess.run(
        ["7z", "l", "-slt", str(archive)], capture_output=True, text=True, check=True
    ).stdout
    assert "Type = Rar5" in listing
    assert "Path = hello.txt" in listing and "Path = dir/inner.bin" in listing
    subprocess.run(["7z", "t", str(archive)], capture_output=True, check=True)


def test_7z_extracts_byte_identical_contents(tmp_path):
    archive = write_rar5_stored(tmp_path / "fixture.rar", FILES)
    out = tmp_path / "out"
    subprocess.run(
        ["7z", "x", f"-o{out}", "-y", str(archive)], capture_output=True, check=True
    )
    for name, data in FILES.items():
        assert (out / name).read_bytes() == data


def test_a_corrupted_archive_is_rejected_by_7z(tmp_path):
    archive = write_rar5_stored(tmp_path / "fixture.rar", FILES)
    raw = bytearray(archive.read_bytes())
    raw[len(raw) // 2] ^= 0xFF  # flip a byte inside the stored data
    archive.write_bytes(bytes(raw))
    result = subprocess.run(["7z", "t", str(archive)], capture_output=True)
    assert result.returncode != 0, "a flipped byte must fail the CRC check"


def test_rejects_unsafe_member_names(tmp_path):
    with pytest.raises(ValueError):
        write_rar5_stored(tmp_path / "bad.rar", {"../escape.txt": b"x"})
    with pytest.raises(ValueError):
        write_rar5_stored(tmp_path / "bad.rar", {"/abs.txt": b"x"})

"""Write a genuine RAR5 archive (stored, uncompressed) without the proprietary tool.

There is no RAR *encoder* on this machine (7-Zip reads RAR but cannot write it),
and the QA sweep must not fabricate a fixture it cannot validate. The RAR 5.0
block layout is public and small, so this writes one by hand. It is genuine
because the official-format readers accept it: ``tests/test_rar_fixture.py``
has 7-Zip list, test and extract it byte-for-byte, and reject a flipped byte.

Layout (all integers little-endian; ``vint`` = 7 bits per byte, high bit means
"more bytes follow"):  signature, main-archive header, one file header + data
per member, end-of-archive header. Each header is
``CRC32 | size vint | type | flags | ...`` where the CRC covers everything
after itself up to the end of the header (the data area is not included).
"""

from __future__ import annotations

import zlib
from pathlib import PurePosixPath

SIGNATURE = b"Rar!\x1a\x07\x01\x00"
TYPE_MAIN, TYPE_FILE, TYPE_END = 1, 2, 5
HEADER_HAS_DATA = 0x0002
FILE_HAS_MTIME, FILE_HAS_CRC = 0x0002, 0x0004
METHOD_STORE = 0  # compression info 0: version 0, not solid, method "store"
HOST_OS_UNIX = 1
FIXED_MTIME = 1_700_000_000  # keeps the fixture byte-for-byte reproducible
UNIX_FILE_MODE = 0o100644


def _vint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _u32(value: int) -> bytes:
    return value.to_bytes(4, "little")


def _block(body: bytes, data: bytes = b"") -> bytes:
    """Frame ``body`` as a header (size + CRC) followed by its data area."""
    sized = _vint(len(body)) + body
    return _u32(zlib.crc32(sized)) + sized + data


def _check_name(name: str) -> bytes:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe or empty archive member name: {name!r}")
    return name.encode("utf-8")


def _file_block(name: str, data: bytes) -> bytes:
    encoded = _check_name(name)
    body = (
        _vint(TYPE_FILE)
        + _vint(HEADER_HAS_DATA)
        + _vint(len(data))  # packed size (== unpacked: stored)
        + _vint(FILE_HAS_MTIME | FILE_HAS_CRC)
        + _vint(len(data))  # unpacked size
        + _vint(UNIX_FILE_MODE)
        + _u32(FIXED_MTIME)
        + _u32(zlib.crc32(data))
        + _vint(METHOD_STORE)
        + _vint(HOST_OS_UNIX)
        + _vint(len(encoded))
        + encoded
    )
    return _block(body, data)


def write_rar5_stored(path, files: dict[str, bytes]):
    """Write ``files`` (member name -> bytes) as a stored RAR5 archive at ``path``."""
    if not files:
        raise ValueError("a RAR archive needs at least one member")
    main = _block(_vint(TYPE_MAIN) + _vint(0) + _vint(0))  # no flags, archive flags 0
    members = b"".join(_file_block(name, data) for name, data in files.items())
    end = _block(_vint(TYPE_END) + _vint(0) + _vint(0))
    path.write_bytes(SIGNATURE + main + members + end)
    return path

"""Archive conversion rows — data only, no logic.

Conversion matrix:
  zip/tar/gz/rar->[zip,tar,gz] with self filtered; rar is input-only, so it
  never appears as an output.
  zip/tar/gz: 2 rows each; rar: 3 rows. Total: 9 rows.
Label rule: gz->"GZIP" else UPPER. gz naming rule: gz output is
named `tar.gz` (output_ext ".tar.gz"); see converters_archives.
"""
from .registry import Conversion, register

_ARCHIVE_INPUTS = ("zip", "tar", "gz", "rar")
_ARCHIVE_OUTPUTS = ("zip", "tar", "gz")

_ARCHIVE_EXTS = {
    "zip": (".zip",),
    "tar": (".tar",),
    "gz": (".gz", ".tgz", ".tar.gz"),
    "rar": (".rar",),
}


def _label(ext: str) -> str:
    return "Convert to " + ("GZIP" if ext == "gz" else ext.upper())


for _src in _ARCHIVE_INPUTS:
    for _dst in _ARCHIVE_OUTPUTS:
        if _dst == _src:
            continue
        register(Conversion(
            id=f"archive-{_src}-to-{_dst}",
            label=_label(_dst),
            inputs=_ARCHIVE_EXTS[_src],
            output_ext=".tar.gz" if _dst == "gz" else "." + _dst,
            category="archives",
        ))

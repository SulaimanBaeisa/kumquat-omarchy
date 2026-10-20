"""Read Nautilus script selections without GTK, subprocesses or a clipboard."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit


def nautilus_files(environ: Mapping[str, str]) -> list[str]:
    """Return local paths in selection order, or reject the whole selection.

    URI paths are percent-decoded exactly once. Files and directories are both
    accepted; neither clipboard state nor a shell participates in this lookup.
    """
    uri_selection = "NAUTILUS_SCRIPT_SELECTED_URIS" in environ
    value = (
        environ["NAUTILUS_SCRIPT_SELECTED_URIS"]
        if uri_selection
        else environ.get("NAUTILUS_SCRIPT_SELECTED_FILE_PATHS", "")
    )
    paths: list[str] = []
    for entry in value.splitlines():
        try:
            path = entry
            if uri_selection:
                parsed = urlsplit(entry)
                if (
                    not entry.startswith("file://")
                    or any(ord(char) <= 32 or ord(char) == 127 for char in entry)
                    or parsed.netloc not in ("", "localhost")
                    or parsed.query
                    or parsed.fragment
                    or re.search(r"%(?![0-9a-fA-F]{2})", entry)
                ):
                    raise ValueError("expected a local file:// URI")
                path = unquote(parsed.path, errors="strict")
            if "\x00" in path or not Path(path).is_absolute() or not Path(path).exists():
                raise ValueError("path must be absolute and exist")
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid Nautilus selection {entry!r}: {exc}") from exc
        if path not in paths:
            paths.append(path)
    if not paths:
        raise ValueError("No Nautilus selection; select files or directories first.")
    return paths

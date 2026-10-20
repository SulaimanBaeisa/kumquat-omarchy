#!/usr/bin/env python3
"""Check that a folder is a valid, publishable Omarchy plugin.

    python3 scripts/validate-plugin.py [PLUGIN_DIR]

This script encodes the rules Omarchy documents for third-party plugins
(https://plugins.omarchy.org/develop.html and /publish.html) and the limits of
the marketplace's automated scan, so CI can catch a regression before a
maintainer does. It does not replace Omarchy's own check; on an Omarchy machine
also run:

    omarchy plugin validate .

Exit status is 0 when the plugin passes and 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

# kind -> the entryPoints key that must exist for it
ENTRY_KEY = {
    "bar-widget": "barWidget",
    "panel": "panel",
    "overlay": "overlay",
    "menu": "menu",
    "service": "service",
    "bar": "bar",
}
BAR_SECTIONS = {"left", "centerBegin", "center", "centerEnd", "tray", "right"}
REQUIRED = ("id", "name", "version", "author", "description", "kinds", "entryPoints")

# Recommended by the marketplace: a lowercase, namespaced id such as
# io.github.yourname.plugin-name. "omarchy." is reserved for built-in plugins.
ID_PATTERN = re.compile(r"^[a-z0-9]+(\.[a-z0-9][a-z0-9-]*)+$")
MAX_VERSION = 64  # the marketplace shows at most 64 characters
MAX_DESCRIPTION = 200  # keeps the listing card readable (our rule, not Omarchy's)

# Limits of the marketplace's automated scan; going over them fails closed.
MAX_FILES = 1000
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
}

# The deterministic patterns the marketplace's security baseline reports. They are
# assembled from fragments so this file never contains the risky text itself and
# therefore cannot trip the same scan it emulates.
_SH = r"(?:ba|z|da|k)?" + "sh"
_FETCH = r"\b(?:c" + r"url|w" + r"get)\b"
_SUDO = r"(?:s" + r"udo|pk" + r"exec)"
SECURITY_PATTERNS = (
    (
        "downloaded text piped into a shell",
        re.compile(_FETCH + r"[^\n|]*\|\s*" + _SUDO + r"?\s*" + _SH + r"\b"),
    ),
    (
        "shell fed from a download by process substitution",
        re.compile(_SH + r"\s+<\(\s*" + _FETCH),
    ),
    (
        "git-hosted crate install without a full commit pin",
        re.compile(r"cargo\s+install\b(?![^\n]*--rev\s+[0-9a-f]{40}\b)[^\n]*--git\b"),
    ),
    ("passwordless sudoers rule", re.compile(r"\bNO" + r"PASSWD\b")),
    (
        "privileged command driven by a pid file in /tmp",
        re.compile(_SUDO + r"\b[^\n]*(?:/tmp/[\w./-]*\.pid|\$\(\s*cat\s+/tmp/)"),
    ),
)

LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")


def _is_safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and not pure.is_absolute()
        and ".." not in pure.parts
        and "\\" not in path
    )


def _walk(root: Path):
    """Every file and symlink under root, skipping tool and VCS folders."""
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_symlink() or path.is_file():
            yield path, rel


def _check_manifest(root: Path, errors: list[str]) -> dict | None:
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        errors.append("manifest.json must be a regular file in the repository root")
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"manifest.json is not valid JSON: {exc}")
        return None
    if not isinstance(manifest, dict):
        errors.append("manifest.json must contain a JSON object")
        return None

    if manifest.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    for key in REQUIRED:
        if key not in manifest:
            errors.append(f"missing required field: {key}")
    for key in ("name", "author", "description", "version", "id"):
        if key in manifest and not (
            isinstance(manifest[key], str) and manifest[key].strip()
        ):
            errors.append(f"{key} must be a non-empty string")

    plugin_id = manifest.get("id")
    if isinstance(plugin_id, str) and plugin_id:
        if plugin_id.startswith("omarchy."):
            errors.append(
                "id must not start with omarchy. (reserved for built-in plugins)"
            )
        elif not ID_PATTERN.match(plugin_id):
            errors.append(
                "id should be lowercase and namespaced, "
                "like io.github.yourname.plugin-name"
            )
    version = manifest.get("version")
    if isinstance(version, str) and len(version) > MAX_VERSION:
        errors.append(f"version is longer than {MAX_VERSION} characters")
    description = manifest.get("description")
    if isinstance(description, str) and len(description) > MAX_DESCRIPTION:
        errors.append(f"description is longer than {MAX_DESCRIPTION} characters")

    kinds = manifest.get("kinds")
    entries = manifest.get("entryPoints")
    if not (isinstance(kinds, list) and kinds and all(isinstance(k, str) for k in kinds)):
        errors.append("kinds must be a non-empty list of strings")
        kinds = []
    if not isinstance(entries, dict):
        errors.append("entryPoints must be an object")
        entries = {}
    if len(set(kinds)) != len(kinds):
        errors.append("kinds lists the same kind twice")

    wanted_keys = set()
    for kind in kinds:
        key = ENTRY_KEY.get(kind)
        if key is None:
            errors.append(f"unknown kind {kind!r}; expected one of {sorted(ENTRY_KEY)}")
            continue
        wanted_keys.add(key)
        if key not in entries:
            errors.append(f"kind {kind!r} needs entryPoints.{key}")
    for key in entries:
        if key not in wanted_keys:
            errors.append(f"entryPoints.{key} has no matching entry in kinds")
    for key, value in entries.items():
        if not isinstance(value, str) or not _is_safe_relative(value):
            errors.append(f"entryPoints.{key} must be a safe relative path")
            continue
        target = root / value
        if target.is_symlink() or not target.is_file():
            errors.append(
                f"entryPoints.{key} points at {value}, which is not a regular file"
            )

    if "bar-widget" in kinds:
        widget = manifest.get("barWidget")
        if not isinstance(widget, dict):
            errors.append("a bar-widget plugin needs a barWidget object")
        else:
            for key in ("displayName", "category"):
                if not (isinstance(widget.get(key), str) and widget[key].strip()):
                    errors.append(f"barWidget.{key} must be a non-empty string")
            if not isinstance(widget.get("allowMultiple"), bool):
                errors.append("barWidget.allowMultiple must be true or false")
            section = widget.get("defaultSection")
            if section is not None and section not in BAR_SECTIONS:
                errors.append(
                    f"barWidget.defaultSection must be one of {sorted(BAR_SECTIONS)}"
                )
    return manifest


def _check_tree(root: Path, errors: list[str]) -> list[Path]:
    files: list[Path] = []
    total = 0
    for path, rel in _walk(root):
        if path.is_symlink():
            errors.append(f"{rel}: symlinks are not allowed")
            continue
        size = path.stat().st_size
        total += size
        files.append(path)
        if size > MAX_FILE_BYTES:
            errors.append(
                f"{rel}: {size} bytes exceeds the {MAX_FILE_BYTES}-byte "
                "per-file scan limit"
            )
    if len(files) > MAX_FILES:
        errors.append(f"{len(files)} files exceeds the {MAX_FILES}-file scan limit")
    if total > MAX_TOTAL_BYTES:
        errors.append(f"{total} bytes exceeds the {MAX_TOTAL_BYTES}-byte scan limit")
    return files


def _check_docs(root: Path, errors: list[str]) -> None:
    if not any((root / name).is_file() for name in LICENSE_NAMES):
        errors.append("a license file (LICENSE) is required")
    readme = root / "README.md"
    if not readme.is_file():
        errors.append("README.md is required")
        return
    headings = [
        line.lstrip("#").strip().lower()
        for line in readme.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    ]
    for label, words in (
        ("install steps", ("install",)),
        ("removal steps", ("uninstall", "remov")),
        ("external dependencies", ("dependenc", "requirement")),
    ):
        if not any(word in heading for heading in headings for word in words):
            errors.append(f"README.md needs a heading for {label}")


def _check_security(root: Path, files: list[Path], errors: list[str]) -> None:
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable; size limits were checked above
        if "\x00" in text:
            continue
        for label, pattern in SECURITY_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{path.relative_to(root)}:{line}: {label}")


def validate(root: Path) -> list[str]:
    """Return a list of problems; an empty list means the plugin passes."""
    root = Path(root)
    errors: list[str] = []
    if not root.is_dir():
        return [f"{root} is not a directory"]
    _check_manifest(root, errors)
    files = _check_tree(root, errors)
    _check_docs(root, errors)
    _check_security(root, files, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "plugin_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1]),
        help="folder containing manifest.json (default: this repository)",
    )
    args = parser.parse_args(argv)
    errors = validate(Path(args.plugin_dir))
    if errors:
        for problem in errors:
            print(f"FAIL: {problem}", file=sys.stderr)
        print(f"{len(errors)} problem(s) found", file=sys.stderr)
        return 1
    print(
        "OK: manifest, entry points, documentation, scan limits and baseline checks pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

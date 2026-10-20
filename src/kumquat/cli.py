"""Wheel CLI: `kumquat --files ... --list | --gui | --convert ID`.

This module only parses arguments and dispatches:

- ``--list`` prints the headless text wheel (`selection.format_listing`); it
  needs no display.
- ``--convert ID`` applies one conversion to every file.
- ``--gui`` opens the GTK wheel (`gui.app.run_gui`). Bare ``--gui`` always
  opens the embedded file browser, without consulting the clipboard.
- ``--from-clipboard`` takes the files from the clipboard instead of
  ``--files``.
- ``--from-nautilus`` takes the current Nautilus script selection; ``--tab``
  chooses the initial wheel tab without applying an option.

The wheel tables, prompts and the notes behind them live in
`selection`; they are re-exported here for older callers. No GTK is imported
at module scope.
"""
from __future__ import annotations

import argparse
import os
import shutil  # noqa: F401 -- tests patch cli.shutil.which (one shared module)
import subprocess  # noqa: F401 -- tests patch cli.subprocess.run
import sys
from pathlib import Path

from . import registry_data as _registry_data  # noqa: F401 -- populates REGISTRY
from .gui.app import run_gui
from .nautilus_selection import nautilus_files
from .selection import (
    ACTION_TITLES,
    ACTIONS,
    EMPTY_STATE,
    KEY_HINT,
    PROMPTS,
    TOOL_TITLES,
    TOOLS,
    clipboard_files,
    detect_mime,
    files_listing,
    format_listing,
    tools_for,
)

# Re-exported for backwards compatibility: tests and `make_screenshots.py`
# import the wheel tables and text helpers from `kumquat.cli`.
__all__ = [
    "ACTIONS",
    "ACTION_TITLES",
    "EMPTY_STATE",
    "KEY_HINT",
    "MODIFIER_MAP",
    "PROMPTS",
    "TOOLS",
    "TOOL_TITLES",
    "clipboard_files",
    "detect_mime",
    "files_listing",
    "format_listing",
    "main",
    "run_gui",
    "tools_for",
]

# Modifier -> wheel mode (the GTK key names are in gui.wheel).
MODIFIER_MAP = {
    "Shift": "conversions",
    "Meta": "tools",      # Super/Cmd key
    "Control": "actions",
}

# `tests/make_screenshots.py` still imports the pre-refactor private name.
_detect_mime = detect_mime

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def _parser() -> argparse.ArgumentParser:
    """Build the `kumquat` argument parser."""
    parser = argparse.ArgumentParser(prog="kumquat",
                                     description="Kumquat")
    parser.add_argument("--files", nargs="+", default=[],
                        help="input files to list/show the wheel for")
    parser.add_argument("--list", action="store_true",
                        help="print the headless text wheel (no display needed)")
    parser.add_argument("--gui", action="store_true",
                        help="open the GTK4 wheel window")
    parser.add_argument("--tab", choices=("conversions", "tools", "actions"),
                        default="conversions", help="initial wheel tab")
    parser.add_argument("--convert", metavar="ID",
                        help="apply one conversion id (see --list) to --files")
    parser.add_argument("--out", metavar="DIR", default=None,
                        help="output directory for --convert "
                             "(default: next to each source file)")
    parser.add_argument("--from-clipboard", action="store_true",
                        help="use the files copied in your file manager "
                             "(Ctrl+C) instead of --files")
    parser.add_argument("--from-nautilus", action="store_true",
                        help="use the current Nautilus script selection")
    return parser


def _take_clipboard(args: argparse.Namespace) -> bool:
    """Replace ``args.files`` only for explicit ``--from-clipboard``."""
    if not args.from_clipboard:
        return False
    picked = clipboard_files()
    if picked:
        args.files = picked
    return bool(picked)


def _convert(conv_id: str, files: list[str], out_dir: str | None) -> int:
    """Apply ``conv_id`` to each file, printing outputs; nonzero if any failed."""
    from .apply import apply_conversion

    rc = EXIT_OK
    for f in files:
        src = Path(f)
        dest = Path(out_dir) if out_dir else src.parent
        try:
            print(apply_conversion(conv_id, src, dest))
        except Exception as exc:  # report every file, keep going
            print(f"{f}: {type(exc).__name__}: {exc}", file=sys.stderr)
            rc = EXIT_FAILED
    return rc


def main(argv: list[str] | None = None) -> int:
    """Entry point for `kumquat`; returns the process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.from_nautilus:
        if args.files or args.from_clipboard:
            parser.error("--from-nautilus cannot be combined with --files "
                         "or --from-clipboard")
        try:
            args.files = nautilus_files(os.environ)
        except ValueError as exc:
            print(f"kumquat: {exc}", file=sys.stderr)
            return EXIT_FAILED
    clipboard_used = _take_clipboard(args)

    if args.convert:
        if not args.files:
            parser.error("--convert needs --files")
        return _convert(args.convert, args.files, args.out)
    if args.gui:
        if args.tab == "conversions":
            run_gui(args.files, from_clipboard=clipboard_used)
        else:
            run_gui(args.files, from_clipboard=clipboard_used, initial_mode=args.tab)
        return EXIT_OK
    if not args.files:
        parser.print_help()
        return EXIT_USAGE
    sys.stdout.write(format_listing(
        files_listing(args.files, [detect_mime(f) for f in args.files])))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

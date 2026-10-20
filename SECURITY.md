# Security policy

Kumquat runs locally and opens files you choose, often with powerful external tools
(FFmpeg, ImageMagick, LibreOffice, 7-Zip…). Treat untrusted files accordingly.

## What we already guard against

- **Archive traversal:** extraction rejects members that would escape the output folder
  (`../`, absolute paths); this is covered by tests.
- **Overwrite protection:** outputs never replace an existing file or the source.
- **Theme input:** values read from an Omarchy theme file are validated as strict `#hex`
  colours before they reach the stylesheet.
- **No shell interpolation of file names** when invoking backends.

## About this being a shell plugin

Omarchy shell plugins run **unsandboxed inside the shell process** with your user's permissions,
and the plugin marketplace lists plugins without a security audit. Read what you install.

What this plugin's shell-side code can do is intentionally narrow: `Overlay.qml` and
`BarWidget.qml` build an argument list (`Launch.js`) and start `bin/kumquat` through `/bin/sh` with
`Quickshell.execDetached`. They read no files, make no network requests, and put nothing into a
shell string; the `summon` payload is parsed as JSON and only absolute file paths and one of three
tab names are accepted. Installing the plugin runs no code, and nothing needs `sudo`. The optional
`scripts/install-shortcuts.py` edits your Hyprland and Files configuration only when you run it,
backs up each file first, and `--uninstall` reverses it.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private
vulnerability reporting for this repository (*Security → Report a vulnerability*). Include the
affected version or commit, steps to reproduce, and the impact you expect. Do not include real
private documents; a minimal synthetic file is better.

This is a spare-time project, so there is no guaranteed response time, but reports are read.

## Scope notes

Vulnerabilities inside the third-party tools Kumquat calls belong upstream. Kumquat is not a
sandbox: do not use it to open files you would not open with those tools directly.

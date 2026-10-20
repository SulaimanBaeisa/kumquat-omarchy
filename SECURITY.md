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

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private
vulnerability reporting for this repository (*Security → Report a vulnerability*). Include the
affected version or commit, steps to reproduce, and the impact you expect. Do not include real
private documents; a minimal synthetic file is better.

This is a spare-time project, so there is no guaranteed response time, but reports are read.

## Scope notes

Vulnerabilities inside the third-party tools Kumquat calls belong upstream. Kumquat is not a
sandbox: do not use it to open files you would not open with those tools directly.
